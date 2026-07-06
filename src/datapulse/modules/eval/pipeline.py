"""评测流水线:列解析 → 会话重组 → 样本构造。

把日志原始 Excel 变成一批可喂给 Judge 的样本(sample dict)。上传什么评什么,
不做样本过滤(避免按行删破坏多轮上下文)。
列名用「包含匹配」做鲁棒解析,兼容不同导出的细微差异。
"""
from __future__ import annotations

import pandas as pd

from datapulse.modules.eval.answer_sanitizer import sanitize_answer

# 构造样本时上下文只保留最近 N 轮:judge 也只喂最近 N 轮,更早的留着纯属浪费内存。
# 长会话(几百轮)若把每轮的全部前文都塞进 context,单会话内存是 O(轮数²),5万条
# 叠加超长答案原文会 OOM。与 judge._MAX_CONTEXT_TURNS 对齐(取 judge 上限即可)。
_CONTEXT_KEEP_TURNS = 3
# 历史 AI 答只需大意,构造阶段即截断,既减小落盘 row_json 又降内存(judge 还会再截一次兜底)。
_CTX_AI_MAX_LEN = 500

# 逻辑键 -> 候选列名(按包含匹配,命中第一个)
COLS: dict[str, list[str]] = {
    "question": ["客户问题"],
    "question_time": ["时间"],   # 客户提问时间（可选）→ row_json.ask_time，供问题洞察按日聚合
    "turn": ["客户咨询轮次"],
    "session": ["应用会话ID"],
    "answer": ["答案"],
    "sys_intent": ["模型意图"],
    "agent_name": ["智能体名称"],
    "agent_class": ["智能体分类"],
    "recog_type": ["问题识别类型"],
    "dispatch_bu": ["分发BU"],
    "dispatch_reason": ["分发BU理由", "分发理由"],
    # 人工金标
    "gold_dispatch": ["分发是否正确"],
    "gold_resolved": ["答案是否解决客户问题"],
    "gold_qtype": ["问题类型"],
    "gold_module": ["常规意图识别模块"],
    "unresolved_reason": ["未解决原因"],
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """把逻辑键映射到 DataFrame 实际列名。缺关键列直接报错。

    匹配策略:先精确匹配(避免「答案」误命中「答案一级围栏标签」「标准问答案」
    这类含子串的列),精确命中不到再退化到包含匹配。question_time 候选是「时间」
    这类短词,只允许精确匹配,否则会误命中「创建时间」「响应时间」等列。
    """
    exact_only = {"question_time"}
    cols = [str(c) for c in df.columns]
    m: dict[str, str] = {}
    for key, cands in COLS.items():
        hit = None
        for cand in cands:  # 第一优先级:精确相等
            if cand in cols:
                hit = cand
                break
        if hit is None and key not in exact_only:  # 第二优先级:包含匹配
            for c in cols:
                if any(cand in c for cand in cands):
                    hit = c
                    break
        if hit is not None:
            m[key] = hit
    # dispatch_bu 也必需:分发准确率、解决率漏斗都以「实际是否分给本BU」为事实侧,
    # 缺它会让这些核心指标静默失真(全部样本被当作未分到本BU),故缺列直接报错而非放行。
    miss = [k for k in ("question", "session", "turn", "answer", "dispatch_bu") if k not in m]
    if miss:
        cn = {"question": "客户问题", "session": "应用会话ID", "turn": "客户咨询轮次",
              "answer": "答案", "dispatch_bu": "分发BU"}
        names = [cn.get(k, k) for k in miss]
        raise KeyError(f"缺少必需列: {names}(请确认上传的是日志导出+人工标注的标准表)")
    return m


def load_and_prep(path: str) -> tuple[pd.DataFrame, dict[str, str], dict]:
    """读 Excel → 解析列 → 按会话+轮次排序。

    不做样本过滤:上传什么评什么。按行删测试环境/账号/无效问题会破坏多轮上下文
    (删掉一通对话中间某轮,后续轮的前文就接不上了),且生产日志本就没有这些列。
    """
    df = pd.read_excel(path, dtype=str).fillna("")
    m = resolve_columns(df)
    df = df.copy()
    # 轮次转数字用于排序;非法值补 0
    df["_turn_n"] = pd.to_numeric(df[m["turn"]], errors="coerce").fillna(0).astype(int)
    df = df.sort_values([m["session"], "_turn_n"]).reset_index(drop=True)
    stats = {"total": len(df)}
    return df, m, stats


# 用于判定模式的二值金标列(任一列含「是/否」即算有金标)
_GOLD_BINARY_KEYS = ("gold_dispatch", "gold_resolved")


def detect_gold(df: pd.DataFrame, m: dict[str, str]) -> dict:
    """检测数据里是否真的带可用的二值金标。

    不只看列是否存在,还看列里有没有实际的「是/否」值——空标注列(运营没填)
    不算金标。据此区分:
      - calibration 模式:有金标 → 可算 κ/F1 校准
      - production  模式:无金标 → 直接出评测结论 + 业务洞察
    """
    coverage: dict[str, int] = {}
    has_any = False
    for key in _GOLD_BINARY_KEYS:
        if key not in m:
            coverage[key] = 0
            continue
        col = df[m[key]]
        n = int(col.isin(["是", "否"]).sum())
        coverage[key] = n
        if n > 0:
            has_any = True
    return {
        "mode": "calibration" if has_any else "production",
        "gold_coverage": coverage,  # 每个金标维度有多少行可用
    }


def _sample_from_group(group: list[dict], pos: int, m: dict[str, str], bu) -> dict:
    """从同会话已排序的行列表 group 中,把第 pos 条还原成一条评测样本。

    前后文不再回扫整个 df,而是在组内按 turn 比较切片(同会话规模远小于全表),
    把会话重组从 O(N²) 降到 O(N)。bu 用 matches_dispatch() 判断分发BU是否代表本BU。
    group 每个元素是预先抽好的轻量 dict(见 build_all_samples)。
    """
    row = group[pos]
    turn = row["_turn_n"]

    # 答案不做代码解析:格式无法穷举,硬解会崩(如 list/dict 结构不定)。
    # 直接把答案列原文(JSON+标签+一切)丢给 LLM,由模型自己读懂。
    dispatched = row["sys_intent"] or "(未知)"

    # 上下文 = 前文每一轮的「用户问 + AI 答原文」。用 turn 比较而非纯位置切片,
    # 保持与原实现一致:同会话相同 turn 的脏数据行互不算作对方的前/后文。
    # 只保留最近 _CONTEXT_KEEP_TURNS 轮(judge 也只喂这么多),更早的不进内存/不落盘;
    # 历史 AI 答构造阶段即净化+截断,避免长会话 context 平方膨胀导致 OOM。
    prior = [r for r in group if r["_turn_n"] < turn]
    omitted = max(0, len(prior) - _CONTEXT_KEEP_TURNS)
    context = []
    for r in prior[-_CONTEXT_KEEP_TURNS:]:
        ai = sanitize_answer((r["answer"] or "").strip(), bu.code)
        if len(ai) > _CTX_AI_MAX_LEN:
            ai = ai[:_CTX_AI_MAX_LEN] + "…(历史答案已截断)"
        context.append({"turn": r["_turn_n"], "user": r["question"], "ai": ai})
    nxt = next((r for r in group if r["_turn_n"] > turn), None)

    return {
        "row_index": row["row_index"],
        "question": row["question"],
        "ask_time": row.get("ask_time", ""),
        "session": row["session"],
        "turn": turn,
        "context": context,                  # 已裁到最近 N 轮、AI 答已净化截断
        "omitted_context_turns": omitted,    # 被省略的更早轮数(供 judge 提示)
        "dispatched_intent": dispatched,
        "dispatch_reason": row["dispatch_reason"],
        # 日志「分发BU」是否代表本BU;是→系统承接了,否则→对本BU视为拒识
        "dispatched_bu": row["dispatched_bu"],
        "dispatched_to_bu": bu.matches_dispatch(row["dispatched_bu"]),
        "target_bu": bu.name,
        # 答案先经净化器按规则预处理（如证券·小安只取 msgContent），再交给 LLM
        "answer_text": sanitize_answer(row["answer"], bu.code),
        "next_user_turn": (nxt["question"] if nxt else None),
        "gold": row["gold"],   # 透传金标供校准
    }


def _extract_row(df: pd.DataFrame, i: int, m: dict[str, str]) -> dict:
    """把第 i 行抽成轻量 dict(只取评测用到的列),供组内切片复用,避免重复 df.iloc。"""
    row = df.iloc[i]

    def col(key: str) -> str:
        return row.get(m[key], "") if key in m else ""

    return {
        "row_index": int(i),
        "session": row[m["session"]],
        "_turn_n": int(row["_turn_n"]),
        "question": row[m["question"]],
        "ask_time": str(col("question_time") or "").strip(),
        "answer": row[m["answer"]],
        "sys_intent": col("sys_intent"),
        "dispatch_reason": col("dispatch_reason"),
        "dispatched_bu": col("dispatch_bu").strip(),
        "gold": {
            "dispatch": col("gold_dispatch"),
            "resolved": col("gold_resolved"),
            "qtype": col("gold_qtype"),
            "module": col("gold_module"),
            "unresolved_reason": col("unresolved_reason"),
        },
    }


def build_all_samples(df: pd.DataFrame, m: dict[str, str], bu) -> tuple[list[dict], int]:
    """构造全部评测样本。先按会话分组(一次),组内切片取前后文,整体 O(N)。

    bu(BUConfig)用于判断分发BU是否代表本BU、以及该行是否为活动标问。
    活动标问(前端写死按钮触发的写死回复)不生成评测样本——不喂模型、不计指标;
    但其行仍留在 group 里,作为后续轮的上下文保留(它确实发生过,是对话的一部分)。
    返回 (samples 按 row_index 升序, 活动标问细分计数 {活动名: 条数})。
    续跑依赖 row_index 对齐。细分计数供来源分布柱状图,总数 = 各值之和。
    """
    from collections import Counter
    groups: dict[str, list[dict]] = {}
    for i in range(len(df)):
        r = _extract_row(df, i, m)
        groups.setdefault(r["session"], []).append(r)

    samples = []
    activity_breakdown: Counter = Counter()
    for group in groups.values():
        for pos in range(len(group)):
            q = group[pos]["question"]
            if bu.is_activity(q):
                # 按活动名聚合（同活动多个问题累加成一条）；活动名空时兜底用 question
                act = bu.activity_of(q) or (q or "").strip()
                activity_breakdown[act] += 1  # 跳过评测但留组内当前文
                continue
            samples.append(_sample_from_group(group, pos, m, bu))
    samples.sort(key=lambda s: s["row_index"])
    return samples, dict(activity_breakdown)
