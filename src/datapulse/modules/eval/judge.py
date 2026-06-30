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
import logging

from datapulse.modules.eval.bu.base import BUConfig

logger = logging.getLogger(__name__)

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
# 字段顺序 = 模型生成顺序：每个结论字段前先写「依据」，让模型「先想后判」。
# 我们关了 thinking（省 token），靠这个 inline 依据补偿推理空间，显著降低草率误判。
# 严禁打乱顺序：reason 必须在对应结论之前。
OUTPUT_SCHEMA = {
    "dispatch_reason": "先写依据:为什么该/不该本BU承接(只看当前问题+上下文,不看下一轮)",
    "should_dispatch_to_bu": "据上面依据给结论 true/false:该承接true,该拒识false",
    "business_type_reason": "先写依据:为什么打这个业务类型标签",
    "business_type": "据上面依据给结论:从意图清单选一个;不该本BU承接的填'非本BU'",
    "answer_relevant": "true/false:答案是否答到了用户的问题",
    "answer_complete": "true/false:答案是否给全了所需信息",
    "resolved_reason": "先写依据:基于相关性/完整性/下游轨迹(用户下一轮),不靠业务对错",
    "answer_resolved": "据上面依据给结论 yes/partial/no/unknown:仅当被分到本BU时判,否则unknown",
    "unresolved_cause": "没解决时的原因归类(答非所问/信息不全/事实存疑/分发错误),解决了填空串",
    "review_reason": "先写依据:为什么需要/不需要人工复核;不需要填空串",
    "needs_human_review": "据上面依据给结论 true/false",
}


def build_messages(sample: dict, bu: BUConfig) -> list[dict]:
    """根据一条样本 + BU 领域知识构造 chat messages。

    sample 期望字段:question / context / answer_text(原文) / next_user_turn。
    bu 提供意图清单与评测专家身份(证券/寿险不同)。
    """
    intents = bu.intents_block()
    # 上下文已在 pipeline 阶段裁到最近 N 轮、AI 答已净化截断(省内存/不落盘整坨)。
    # 这里直接渲染,不再重复净化。被省略的更早轮数由 omitted_context_turns 透传。
    recent = sample.get("context", [])
    omitted = sample.get("omitted_context_turns", 0)
    ctx_lines = []
    if omitted > 0:
        ctx_lines.append(f"    (省略更早 {omitted} 轮，只保留最近 {len(recent)} 轮)")
    for c in recent:
        ctx_lines.append(f"    第{c['turn']}轮 用户:{c['user']}")
        ai = (c.get("ai") or "").strip()
        if ai:
            ctx_lines.append(f"         AI答:{ai}")
    ctx = "\n".join(ctx_lines) or "    (无前文,这是首轮)"
    # 各评测维度的判定规则按 BU 拆分(<bu_code>/ 优先,_default/ 回退),
    # 按 _TASK_PROMPTS 顺序拼进【任务】块。改某 BU 某维度只动对应文件。
    # 走 bu.prompt() 取任务快照,保证整个任务用同一份(中途改 prompt 不影响进行中的任务)。
    tasks = "\n\n".join(bu.prompt(f).strip() for f in _TASK_PROMPTS)
    # 动态数据用 XML 标签包裹再填入，把「待评数据」和「指令」清晰隔开，避免模型
    # 把答案里的标签/相似问当成指令、或在长上下文里迷失关键部分。标签名取够独特，
    # 降低与数据内容（答案常含 HTML/JSON）的冲突。占位符仍在模板里，用户不会误删标签。
    def _wrap(tag: str, val: str) -> str:
        return f"<{tag}>\n{val}\n</{tag}>"

    # 从外置模板填空(用 replace 而非 format,避免与模板内 JSON 的花括号冲突)
    fields = {
        "{intents}": _wrap("business_categories", intents),
        "{question}": _wrap("customer_question", str(sample["question"])),
        "{ctx}": _wrap("conversation_context", ctx),
        "{answer_text}": _wrap("ai_answer", str(sample.get("answer_text", "(空)"))),
        "{next_user_turn}": str(sample.get("next_user_turn") or "(无/会话结束)"),
        "{dispatched_flag}": (
            "是(进入解决度评测)" if sample.get("dispatched_to_bu")
            else "否(拒识/分给他BU,不评解决度)"
        ),
        "{tasks}": tasks,
        "{output_schema}": json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2),
    }
    user = bu.prompt("judge_user.md")
    for k, v in fields.items():
        user = user.replace(k, v)
    # system 人设走 prompts/<bu>/judge_system.md,缺则回退 prompts/_default/judge_system.md
    system = bu.prompt("judge_system.md")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# 模型输出里语义为布尔的字段。LLM 常把它们返回成字符串 "true"/"false"，
# 而 Python bool("false") == True，会让分发/复核判定全反——必须统一归一成真 bool。
_BOOL_FIELDS = ("should_dispatch_to_bu", "answer_relevant", "answer_complete", "needs_human_review")

# 模型布尔字段的各种写法 → 统一归一。覆盖：true/false、True/False、T/F、Y/N、
# yes/no、1/0、是/否、对/错（大小写不敏感）。
_TRUE_TOKENS = {"true", "t", "1", "yes", "y", "是", "对", "√", "✓"}
_FALSE_TOKENS = {"false", "f", "0", "no", "n", "否", "错", "×", "✗", ""}


def _to_bool(v) -> bool:
    """把模型返回的布尔字段（bool / "true" / "T" / "是" / 1 …）归一成真 bool。

    识别不了的值（如 typo "ture"）记一条警告并保守判 False——评测要的是确定性，
    宁可保守也不让脏值悄悄通过；警告日志便于发现模型输出异常。
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _TRUE_TOKENS:
            return True
        if s in _FALSE_TOKENS:
            return False
        logger.warning("布尔字段无法识别的取值，保守判 False: %r", v)
        return False
    logger.warning("布尔字段非预期类型，保守判 False: %r", v)
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
