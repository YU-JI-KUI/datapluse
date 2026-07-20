"""评测流水线:列解析 → 会话重组 → 样本构造。

把日志原始 Excel 变成一批可喂给 Judge 的样本(sample dict)。上传什么评什么,
不做样本过滤(避免按行删破坏多轮上下文)。
列名用「包含匹配」做鲁棒解析,兼容不同导出的细微差异。
"""
from __future__ import annotations

import pandas as pd

from datapulse.modules.eval.answer_sanitizer import sanitize_answer
from datapulse.modules.eval.text_sanitize import sanitize_jsonb_text

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


# row_index 分段宽度：单文件按 file_index 占一段，段内是文件内 0-based 行号。
# 运营平台单文件上限 5 万行，1000 万段宽绰绰有余、永不溢出；分段让 row_index 天然
# 稳定——续跑/重跑/复核/导出全靠 (task_id, row_index) 对齐，分段后新增/重传某文件
# 不影响其他文件已落盘行的 row_index，无需依赖"全局排序完全可复现"这个脆弱前提。
_ROW_SEGMENT = 10_000_000


def load_and_prep(path: str) -> tuple[pd.DataFrame, dict[str, str], dict]:
    """读单个 Excel → 解析列 → 排序 → 打 row_index。多文件走 load_and_merge。"""
    return load_and_merge([path])


def load_and_merge(paths: list[str]) -> tuple[pd.DataFrame, dict[str, str], dict]:
    """读 1..N 个 Excel，逐文件解析+排序打段内 row_index，再合并成一个 DataFrame。

    - 每个文件独立 resolve_columns 校验表头（不同导出批次表头微差各自报错，定位清晰）。
    - row_index = file_index * _ROW_SEGMENT + 文件内按(会话,轮次)排序后的 0-based 行号。
    - 会话重组（多轮上下文）在 build_all_samples 里按全局 session 分组，跨文件自然拼接
      （同一「应用会话ID」= 同一通对话，被运营平台按 5 万行拆到多个文件时接回来）。

    不做样本过滤：上传什么评什么（按行删会破坏多轮上下文）。
    """
    if not paths:
        raise ValueError("至少需要一个文件")
    parts: list[pd.DataFrame] = []
    m: dict[str, str] = {}
    per_file_rows: list[int] = []
    for fi, path in enumerate(paths):
        df = pd.read_excel(path, dtype=str).fillna("")
        fm = resolve_columns(df)
        if fi == 0:
            m = fm
        df = df.copy()
        df["_turn_n"] = pd.to_numeric(df[fm["turn"]], errors="coerce").fillna(0).astype(int)
        # 文件内按会话+轮次排序（决定段内行号，须稳定），列名统一到首文件的映射键
        df = df.rename(columns={fm[k]: m[k] for k in fm if k in m and fm[k] != m[k]})
        df = df.sort_values([m["session"], "_turn_n"]).reset_index(drop=True)
        df["_row_index"] = fi * _ROW_SEGMENT + df.index.to_numpy()
        per_file_rows.append(len(df))
        parts.append(df)
    merged = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    stats = {"total": len(merged), "files": len(paths), "per_file_rows": per_file_rows}
    return merged, m, stats


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


def _cell(v) -> str:
    """把 Excel 单元格原始值统一成字符串，并净化掉写 JSONB 会崩的非法字符。

    pd.read_excel(dtype=str) 对布尔列/合并单元格/特定格式并非 100% 生效，
    仍可能漏进 bool / int / float('nan')；原始文本还可能带孤立代理项 / NUL /
    C0 控制字符（客户输入截断的半个 emoji 等）。这些下游一旦 .strip() 或写入
    JSONB 就会崩（'bool' object has no attribute 'strip'、invalid input
    syntax for type json）。此处是所有样本的唯一取数入口，统一净化：
    NaN/None → ""，其余强转字符串后剥掉孤立代理/NUL/C0 控制符（保留 \t\n\r）。
    """
    if v is None:
        return ""
    # float('nan') != 自身，pandas 空单元格在部分路径会以 nan 漏出
    if isinstance(v, float) and v != v:
        return ""
    return sanitize_jsonb_text(str(v)).strip()


def _extract_row(df: pd.DataFrame, i: int, m: dict[str, str]) -> dict:
    """把第 i 行抽成轻量 dict(只取评测用到的列),供组内切片复用,避免重复 df.iloc。

    所有字段经 _cell() 强制转字符串，杜绝非字符串单元格污染下游 strip / JSONB。
    """
    row = df.iloc[i]

    def col(key: str) -> str:
        return _cell(row.get(m[key], "")) if key in m else ""

    # row_index 优先取 load_and_merge 打好的分段值；未预处理（如直接喂 df 的调用/测试）
    # 回退到位置索引 i，等价旧行为。
    ri = int(row["_row_index"]) if "_row_index" in row else int(i)
    return {
        "row_index": ri,
        "session": _cell(row[m["session"]]),
        "_turn_n": int(row["_turn_n"]),
        "question": _cell(row[m["question"]]),
        "ask_time": col("question_time"),
        "answer": _cell(row[m["answer"]]),
        "sys_intent": col("sys_intent"),
        "dispatch_reason": col("dispatch_reason"),
        "dispatched_bu": col("dispatch_bu"),
        "gold": {
            "dispatch": col("gold_dispatch"),
            "resolved": col("gold_resolved"),
            "qtype": col("gold_qtype"),
            "module": col("gold_module"),
            "unresolved_reason": col("unresolved_reason"),
        },
    }


def build_all_samples(df: pd.DataFrame, m: dict[str, str], bu
                      ) -> tuple[list[dict], dict, list[dict]]:
    """构造全部评测样本。先按会话分组(一次),组内切片取前后文,整体 O(N)。

    bu(BUConfig)用于判断分发BU是否代表本BU、以及该行是否为活动标问。
    活动标问(前端写死按钮触发的写死回复)不喂模型、不计评测指标; 但其行仍留在 group 里
    作为后续轮的上下文,且单独产出 activity_samples 落库(source=activity)——供"每日频率"
    按来源分维、且"日志数=活动+规则+AI"等式成立。落库的活动标问行由聚合层显式排除,
    不污染解决率/分发准确率/高频问/分类分布。
    返回 (评测 samples 按 row_index 升序, 活动标问细分计数 {活动名: 条数}, activity_samples)。
    续跑依赖 row_index 对齐。细分计数供来源分布柱状图,总数 = 各值之和。
    """
    from collections import Counter
    groups: dict[str, list[dict]] = {}
    for i in range(len(df)):
        r = _extract_row(df, i, m)
        groups.setdefault(r["session"], []).append(r)

    samples = []
    activity_samples = []
    activity_breakdown: Counter = Counter()
    for group in groups.values():
        for pos in range(len(group)):
            q = group[pos]["question"]
            if bu.is_activity(q):
                # 按活动名聚合（同活动多个问题累加成一条）；活动名空时兜底用 question
                act = bu.activity_of(q) or (q or "").strip()
                activity_breakdown[act] += 1  # 不评测，但留组内当前文 + 落库计数
                s = _sample_from_group(group, pos, m, bu)
                s["is_activity"] = True
                activity_samples.append(s)
                continue
            samples.append(_sample_from_group(group, pos, m, bu))
    samples.sort(key=lambda s: s["row_index"])
    activity_samples.sort(key=lambda s: s["row_index"])
    return samples, dict(activity_breakdown), activity_samples
