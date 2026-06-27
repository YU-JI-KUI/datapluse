"""评测流水线:列解析 → 会话重组 → 样本构造。

把日志原始 Excel 变成一批可喂给 Judge 的样本(sample dict)。上传什么评什么,
不做样本过滤(避免按行删破坏多轮上下文)。
列名用「包含匹配」做鲁棒解析,兼容不同导出的细微差异。
"""
from __future__ import annotations

import pandas as pd

# 逻辑键 -> 候选列名(按包含匹配,命中第一个)
COLS: dict[str, list[str]] = {
    "question": ["客户问题"],
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
    "gold_oneclick": ["一键场景分发是否正确"],
    "gold_resolved": ["答案是否解决客户问题"],
    "gold_qtype": ["问题类型"],
    "gold_module": ["常规意图识别模块"],
    "unresolved_reason": ["未解决原因"],
}


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """把逻辑键映射到 DataFrame 实际列名。缺关键列直接报错。

    匹配策略:先精确匹配(避免「答案」误命中「答案一级围栏标签」「标准问答案」
    这类含子串的列),精确命中不到再退化到包含匹配。
    """
    cols = [str(c) for c in df.columns]
    m: dict[str, str] = {}
    for key, cands in COLS.items():
        hit = None
        for cand in cands:  # 第一优先级:精确相等
            if cand in cols:
                hit = cand
                break
        if hit is None:  # 第二优先级:包含匹配
            for c in cols:
                if any(cand in c for cand in cands):
                    hit = c
                    break
        if hit is not None:
            m[key] = hit
    miss = [k for k in ("question", "session", "turn", "answer") if k not in m]
    if miss:
        raise KeyError(f"缺少关键列: {miss}(请确认上传的是日志导出+人工标注的标准表)")
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
_GOLD_BINARY_KEYS = ("gold_dispatch", "gold_oneclick", "gold_resolved")


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


def build_sample(df: pd.DataFrame, i: int, m: dict[str, str], bu) -> dict:
    """把第 i 行还原成一条评测样本:拼接同会话前文上下文 + 记录下一轮。

    bu:BUConfig,用 bu.matches_dispatch() 判断该行「分发BU」是否代表本 BU。
    """
    row = df.iloc[i]
    sess = row[m["session"]]
    prior = df[(df[m["session"]] == sess) & (df["_turn_n"] < row["_turn_n"])]
    nxt = df[(df[m["session"]] == sess) & (df["_turn_n"] > row["_turn_n"])]

    # 答案不做代码解析:格式无法穷举,硬解会崩(如 list/dict 结构不定)。
    # 直接把答案列原文(JSON+标签+一切)丢给 LLM,由模型自己读懂。
    dispatched = (row.get(m["sys_intent"], "") if "sys_intent" in m else "") or "(未知)"
    reason = row.get(m["dispatch_reason"], "") if "dispatch_reason" in m else ""

    # 上下文 = 前文每一轮的「用户问 + AI 答原文」(答案原文,不解析)。
    context = [
        {
            "turn": int(r["_turn_n"]),
            "user": r[m["question"]],
            "ai": r[m["answer"]],
        }
        for _, r in prior.iterrows()
    ]

    _dbu = (row.get(m["dispatch_bu"], "") if "dispatch_bu" in m else "").strip()

    return {
        "row_index": int(i),
        "question": row[m["question"]],
        "session": sess,
        "turn": int(row["_turn_n"]),
        "context": context,
        "dispatched_intent": dispatched,
        "dispatch_reason": reason,
        # 日志「分发BU」是否代表本BU;是→系统承接了,否则→对本BU视为拒识
        "dispatched_bu": _dbu,
        "dispatched_to_bu": bu.matches_dispatch(_dbu),
        "target_bu": bu.name,
        "answer_text": row[m["answer"]],   # 答案原文,交给 LLM 读
        "next_user_turn": (nxt.iloc[0][m["question"]] if len(nxt) else None),
        # 透传金标供校准
        "gold": {
            "dispatch": row.get(m.get("gold_dispatch", ""), "") if "gold_dispatch" in m else "",
            "oneclick": row.get(m.get("gold_oneclick", ""), "") if "gold_oneclick" in m else "",
            "resolved": row.get(m.get("gold_resolved", ""), "") if "gold_resolved" in m else "",
            "qtype": row.get(m.get("gold_qtype", ""), "") if "gold_qtype" in m else "",
            "module": row.get(m.get("gold_module", ""), "") if "gold_module" in m else "",
            "unresolved_reason": (
                row.get(m.get("unresolved_reason", ""), "") if "unresolved_reason" in m else ""
            ),
        },
    }


def build_all_samples(df: pd.DataFrame, m: dict[str, str], bu) -> list[dict]:
    """构造全部样本。bu(BUConfig)用于判断每行分发BU是否代表本BU。"""
    return [build_sample(df, i, m, bu) for i in range(len(df))]
