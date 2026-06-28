"""LLM-as-a-Judge:意图分发正确性 + 答案解决度 + 业务分类。

只负责「构造给模型的消息」和「解析模型输出」,不绑定具体模型后端。
真正调谁(平安大模型 / Mock 桩)由 app.core.llm 决定,judge 通过传入的
judge_fn 解耦。

核心约束(交接文档第 10 节):
  - 无知识库 → 不判业务事实正确性,只判相关/完整/是否解决这些不依赖业务事实的维度。
  - 是否解决用下游轨迹补强:用户下一轮重问/不满 → 倾向 no/partial。
  - 意图判别优于生成:让模型判「该问题属于哪个意图」比从零预测稳。
"""
from __future__ import annotations

import json

from datapulse.modules.eval.bu.base import BUConfig
from datapulse.modules.eval.prompt_loader import load_bu_prompt, load_prompt

# 各评测维度的判定规则文件,按此顺序拼进【任务】块。调某维度只改对应文件。
_TASK_PROMPTS = (
    "task_dispatch.md",        # 1. 该不该本BU承接(should_dispatch_to_bu)
    "task_business_type.md",   # 2. 业务分类打标(business_type)
    "task_resolved.md",        # 3. 是否解决(answer_resolved)
    "task_review.md",          # 4. 需人工复核(needs_human_review)
)

# Judge 必须输出的字段及其含义(也作为 prompt 里给模型的输出契约)。
# 新口径:BU 分发漏斗。分发对错由代码算(should_dispatch_to_bu vs 日志分发BU),
# 不要模型直接给 dispatch_correct。
OUTPUT_SCHEMA = {
    "should_dispatch_to_bu": "true/false:该问题该不该由本BU承接(该承接true,该拒识false);只看当前问题+上下文,不看下一轮",
    "dispatch_reason": "一句话依据:为什么该/不该本BU承接",
    "business_type": "业务类型标签(从意图清单选一个;不该本BU承接的填'非本BU')",
    "business_type_reason": "为什么打这个业务类型标签",
    "answer_relevant": "true/false",
    "answer_complete": "true/false",
    "answer_resolved": "yes/partial/no/unknown:仅当该问题被分到本BU时判,否则填unknown",
    "resolved_reason": "依据:基于相关性/完整性/下游轨迹(用户下一轮),不靠业务对错",
    "unresolved_cause": "没解决时的原因归类(答非所问/信息不全/事实存疑/分发错误),解决了填空串",
    "needs_human_review": "true/false",
    "review_reason": "原因或空串",
}


def build_messages(sample: dict, bu: BUConfig) -> list[dict]:
    """根据一条样本 + BU 领域知识构造 chat messages。

    sample 期望字段:question / context / answer_text(原文) / next_user_turn。
    bu 提供意图清单与评测专家身份(证券/寿险不同)。
    """
    intents = bu.intents_block()
    # 上下文按轮次展开;context 是 [{turn, user, ai}, ...],含 AI 上一轮回答,
    # 以便判断「第二个的走势」这类指代上一轮答案的多轮问题。
    ctx_lines = []
    for c in sample.get("context", []):
        ctx_lines.append(f"    第{c['turn']}轮 用户:{c['user']}")
        ai = (c.get("ai") or "").strip()
        if ai:
            ctx_lines.append(f"         AI答:{ai}")
    ctx = "\n".join(ctx_lines) or "    (无前文,这是首轮)"
    # 各评测维度的判定规则按 BU 拆分(<bu_code>/ 优先,_default/ 回退),
    # 按 _TASK_PROMPTS 顺序拼进【任务】块。改某 BU 某维度只动对应文件。
    tasks = "\n\n".join(load_bu_prompt(bu.code, f).strip() for f in _TASK_PROMPTS)
    # 从外置模板填空(用 replace 而非 format,避免与模板内 JSON 的花括号冲突)
    fields = {
        "{intents}": intents,
        "{question}": str(sample["question"]),
        "{ctx}": ctx,
        "{answer_text}": str(sample.get("answer_text", "(空)")),
        "{next_user_turn}": str(sample.get("next_user_turn") or "(无/会话结束)"),
        "{dispatched_flag}": (
            "是(进入解决度评测)" if sample.get("dispatched_to_bu")
            else "否(拒识/分给他BU,不评解决度)"
        ),
        "{tasks}": tasks,
        "{output_schema}": json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2),
    }
    user = load_prompt("judge_user.md")
    for k, v in fields.items():
        user = user.replace(k, v)
    # system 人设走 prompts/<bu>/judge_system.md,缺则回退 prompts/_default/judge_system.md
    system = load_bu_prompt(bu.code, "judge_system.md")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# 模型输出里语义为布尔的字段。LLM 常把它们返回成字符串 "true"/"false"，
# 而 Python bool("false") == True，会让分发/复核判定全反——必须统一归一成真 bool。
_BOOL_FIELDS = ("should_dispatch_to_bu", "answer_relevant", "answer_complete", "needs_human_review")

_TRUE_TOKENS = {"true", "1", "yes", "y", "是", "对"}
_FALSE_TOKENS = {"false", "0", "no", "n", "否", "错", ""}


def _to_bool(v) -> bool:
    """把模型返回的布尔字段（可能是 bool / "true" / "false" / "是"…）归一成 bool。

    无法识别的值默认 False（保守：不轻易判「该承接 / 需复核」）。
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_TOKENS
    return False


def parse_judge_output(text: str) -> dict:
    """解析模型返回的文本为 dict。模型有时用 Markdown 围栏包裹 JSON,先剥掉。

    解析后把布尔字段统一归一成真 bool，避免下游 bool("false")==True 的判定错误。
    """
    fence = chr(96) * 3  # 三个反引号
    t = text.strip().replace(fence + "json", "").replace(fence, "")
    try:
        out = json.loads(t.strip())
    except json.JSONDecodeError as e:
        # 给出可定位的错误,而非裸 JSONDecodeError;上层据此判断是「模型输出
        # 不符格式」而非「评测逻辑出错」,对应内网验收第 ④ 步。
        raise ValueError(f"模型输出不是有效 JSON(前120字): {t[:120]!r}") from e
    if isinstance(out, dict):
        for f in _BOOL_FIELDS:
            if f in out:
                out[f] = _to_bool(out[f])
    return out
