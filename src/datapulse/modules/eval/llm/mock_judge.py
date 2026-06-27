"""规则桩 Judge(Mock)。

无真实模型时也能端到端跑通:用 BU 自带的关键词规则模拟 LLM 的判断,产出与真实
Judge 完全相同结构的输出。规则来自 BUConfig(证券/寿险各一套),使得对合成数据
跑出来的指标是「有意义的」(而非随机)。

注意:这是演示/占位用途。上线时把 JUDGE_BACKEND 切到 pingan 即可换真实模型,
judge 输出契约不变。
"""
from __future__ import annotations

from datapulse.modules.eval.bu.base import BUConfig

# 负向轨迹关键词:用户下一轮出现这些,倾向未解决
_NEG_NEXT = ["不对", "没用", "听不懂", "再问", "还是", "怎么还", "不是这个", "人工"]


def _guess_intent(question: str, bu: BUConfig) -> tuple[str, float]:
    """根据问题文本 + BU 规则猜意图,返回 (意图, 置信)。"""
    for kws, intent in bu.mock_intent_rules:
        if any(k in question for k in kws):
            return intent, 0.85
    return "其他", 0.45


def _loose_match(intent: str, dispatched: str, bu: BUConfig) -> bool:
    """意图与系统分发模块的宽松映射(模块名 -> 意图),用 BU 的 module_map。"""
    for mod, intents in bu.mock_module_map.items():
        if mod in dispatched and intent in intents:
            return True
    return False


def mock_judge(sample: dict, bu: BUConfig) -> dict:
    """对一条样本产出 Judge 结果(结构与真实 Judge 一致)。"""
    q = sample.get("question", "")
    intent, conf = _guess_intent(q, bu)

    # should_dispatch_to_bu:该不该本BU承接。拒识意图→不该(False),其余→该(True)。
    should_dispatch_to_bu = intent != "拒识"

    # 解决度只对「日志分发到本BU」的样本判;拒识/未承接的填 unknown(漏斗)
    dispatched_to_bu = bool(sample.get("dispatched_to_bu"))
    answer_text = sample.get("answer_text", "") or ""
    has_answer = len(answer_text.strip()) > 0
    next_turn = sample.get("next_user_turn") or ""

    relevant = has_answer and intent != "拒识"
    complete = has_answer and len(answer_text) > 20

    if not dispatched_to_bu:
        resolved = "unknown"  # 非本BU承接,不评解决度
        unresolved_cause = ""
        resolved_reason = "非本BU承接,不评解决度"
    elif not has_answer:
        resolved = "no"
        unresolved_cause = "信息不全"
        resolved_reason = "答案为空"
    elif any(neg in next_turn for neg in _NEG_NEXT):
        resolved = "partial"
        unresolved_cause = "答非所问"
        resolved_reason = f"用户下一轮『{next_turn[:10]}』疑似不满/重问"
    else:
        resolved = "yes"
        unresolved_cause = ""
        resolved_reason = "答案相关且用户未重问"

    needs_review = conf < 0.6 or intent == "其他"

    return {
        "intent_pred": intent,
        "intent_confidence": round(conf, 2),
        "business_type": intent,  # 业务分类标签(切片用)
        "should_dispatch_to_bu": bool(should_dispatch_to_bu),
        "dispatch_reason": f"问题判为『{intent}』→ {'该' if should_dispatch_to_bu else '不该'}本BU承接",
        "answer_relevant": bool(relevant),
        "answer_complete": bool(complete),
        "answer_resolved": resolved,
        "resolved_reason": resolved_reason,
        "unresolved_cause": unresolved_cause,
        "needs_human_review": bool(needs_review),
        "review_reason": "意图置信低或分发存疑" if needs_review else "",
    }
