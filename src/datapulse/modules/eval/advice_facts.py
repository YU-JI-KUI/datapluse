"""优化建议的原始料聚合层。

多专项建议要「错误归因」，靠的是评测模型逐条算好的归因字段（unresolved_cause、
dispatch_reason、business_type）。这些字段完整落在 t_eval_task_row 的 row_json 里，
但流式聚合器 _StreamAggregator 为控内存只留了数字 + 少量问题文本，归因全丢了。

本模块在建议生成阶段，用 store.iter_rows 把已落盘的 rows 逐批读回、内存里重聚合，
产出五类卡片各自需要的料。逐批即弃、只存必要字段（问题/答案/归因），不全量驻留、
零 N+1（复用续跑同款 keyset 分页）。截断不在这里做——尽量全收，交给编排层按每卡
token 预算裁，好把上下文窗口喂满。
"""
from __future__ import annotations

from collections import Counter, defaultdict

from datapulse.modules.eval import _store
from datapulse.modules.eval.bu.base import BUConfig

# AI 答案单条硬顶：防个别超长答案挤爆 token 预算；正常答案远短于此。
_MAX_ANSWER_CHARS = 800
# 各料池收集上限：设得足够大，让小/中数据集全量进来；真截断在编排层按预算做。
# 上限只为超大数据集兜底，避免建议阶段驻留过多样例。
_CAP = 5000

# 未解决四归因（与 task_resolved.md 的枚举一致）
_UNRESOLVED_CAUSES = ("答非所问", "信息不全", "事实存疑", "分发错误")
# 非本 BU 的原始占位值（judge.business_type 在闭集折叠前的取值）
_NON_BU = "非本BU"


def _clip(s: str, n: int = _MAX_ANSWER_CHARS) -> str:
    """超长答案在句子边界截断，避免把喂给模型的样例切成半句话。

    先硬切到 n，再在末尾一段窗口内回退到最近的句末标点（。！？!?换行），
    找不到就退化为硬切。让样例保持自洽，模型归因不被半句话误导。
    """
    s = (s or "").strip()
    if len(s) <= n:
        return s
    head = s[:n]
    cut = max(head.rfind(c) for c in "。！？!?\n")
    if cut >= n - 120:            # 边界离末尾不太远才用，避免砍掉太多
        head = head[: cut + 1]
    return head.rstrip() + "…"


def _example(r: dict) -> dict:
    """从一行提取失败样例的必要字段（不含整 row，控内存）。"""
    judge = r.get("judge") if isinstance(r.get("judge"), dict) else {}
    return {
        "question": r.get("question", ""),
        "answer_text": _clip(r.get("answer_text", "")),
        "unresolved_cause": judge.get("unresolved_cause", ""),
        "dispatch_reason": judge.get("dispatch_reason", ""),
    }


class _IntentFacts:
    """单个业务分类的建议料。"""
    __slots__ = ("dispatch_examples", "unresolved_dist", "unresolved_examples",
                 "in_bu", "resolved_yes")

    def __init__(self) -> None:
        self.dispatch_examples: list[dict] = []   # 漏收/误收样例（带 dispatch_reason）
        self.unresolved_dist: Counter = Counter()  # 四归因计数
        self.unresolved_examples: list[dict] = []  # 未解决样例（问题+答案+归因）
        self.in_bu = 0
        self.resolved_yes = 0


def build_facts(task_id: str | None, bu: BUConfig, bu_dispatch: dict | None = None) -> dict:
    """从已落盘 rows 重聚合五类建议料。

    task_id 为空（测试/小数据路径未落盘）→ 返回空 facts，编排层走规则兜底。
    """
    empty = {"dispatch_global": None, "resolved_global": None,
             "new_business": None, "by_intent": {}}
    if not task_id:
        return empty

    # ── 全局分发（①）──
    miss_examples: list[dict] = []   # 漏收：该分未分
    over_examples: list[dict] = []   # 误收：该拒未拒
    miss_q: Counter = Counter()      # 高频被漏收问题
    over_q: Counter = Counter()      # 高频被误收问题

    # ── 全局解决率（②）──
    resolved_dist: Counter = Counter()
    resolved_examples: list[dict] = []

    # ── 新业务分类（③）──
    non_bu_q: Counter = Counter()    # 非本BU 问题去重计数

    # ── 逐分类（④⑤）──
    by_intent: dict[str, _IntentFacts] = defaultdict(_IntentFacts)

    for batch in _store.iter_rows(task_id, batch_size=1000):
        for r in batch:
            judge = r.get("judge") if isinstance(r.get("judge"), dict) else {}
            question = r.get("question", "")
            intent = r.get("j_intent") or "(未分类)"
            in_bu = bool(r.get("dispatched_to_bu"))
            scene = r.get("dispatch_scene", "")
            raw = r.get("j_resolved_raw", "")
            cause = judge.get("unresolved_cause", "")

            # ① 全局分发：按场景归入漏收/误收
            if scene == "该分未分":  # 漏收
                if len(miss_examples) < _CAP:
                    miss_examples.append(_example(r))
                miss_q[question] += 1
            elif scene == "该拒未拒":  # 误收
                if len(over_examples) < _CAP:
                    over_examples.append(_example(r))
                over_q[question] += 1

            # ③ 新业务分类：原始 business_type == 非本BU
            if judge.get("business_type") == _NON_BU and question:
                non_bu_q[question] += 1

            # 分类切片
            sl = by_intent[intent]
            # ④ 逐分类分发样例
            if scene in ("该分未分", "该拒未拒") and len(sl.dispatch_examples) < _CAP:
                ex = _example(r)
                ex["scene"] = scene
                sl.dispatch_examples.append(ex)

            # ⑤ 逐分类解决率（分母=分发到本BU）
            if in_bu:
                sl.in_bu += 1
                if raw == "yes":
                    sl.resolved_yes += 1
                elif raw in ("no", "partial"):
                    c = cause if cause in _UNRESOLVED_CAUSES else "其他"
                    sl.unresolved_dist[c] += 1
                    if len(sl.unresolved_examples) < _CAP:
                        sl.unresolved_examples.append(_example(r))
                    # ② 全局解决率同步累计
                    resolved_dist[c] += 1
                    if len(resolved_examples) < _CAP:
                        ex = _example(r)
                        ex["intent"] = intent
                        resolved_examples.append(ex)

    dispatch_global = {
        "accuracy": (bu_dispatch or {}).get("accuracy"),
        "miss_count": (bu_dispatch or {}).get("miss_should_accept_but_rejected", len(miss_examples)),
        "over_count": (bu_dispatch or {}).get("over_should_reject_but_accepted", len(over_examples)),
        "top_missed": miss_q.most_common(50),   # [(问题, 次数)]
        "top_over": over_q.most_common(50),
        "miss_examples": miss_examples,
        "over_examples": over_examples,
    }
    resolved_global = {
        "unresolved_dist": dict(resolved_dist),
        "examples": resolved_examples,
    }
    new_business = {
        "count": sum(non_bu_q.values()),
        "distinct": len(non_bu_q),
        "questions": non_bu_q.most_common(),   # 全量去重 [(问题, 次数)]，编排层按预算裁
    }
    # 只吐现有闭集分类（bu.intents）+ 实际出现过的，(未分类) 不给建议
    intents = {}
    for name, f in by_intent.items():
        if name == "(未分类)":
            continue
        intents[name] = {
            "in_bu": f.in_bu,
            "resolved_yes": f.resolved_yes,
            "resolved_rate": (f.resolved_yes / f.in_bu) if f.in_bu else None,
            "dispatch_examples": f.dispatch_examples,
            "unresolved_dist": dict(f.unresolved_dist),
            "unresolved_examples": f.unresolved_examples,
        }

    return {
        "dispatch_global": dispatch_global,
        "resolved_global": resolved_global,
        "new_business": new_business,
        "by_intent": intents,
    }
