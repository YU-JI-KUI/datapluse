"""短路规则测试（规则集）：客户问题 ∈ 触发问题集 且 答案 ∈ 期望答案集（独立组合）才命中，
命中用写死 judge 免 LLM、报告按规则名聚合，未命中走 LLM。"""
import asyncio
from dataclasses import replace

from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval import evaluator
from datapulse.modules.eval.evaluator import _StreamAggregator, _judge_streaming


# 一条「转人工」规则集：3 个触发问题 × 2 个期望答案。规则命中行不计入业务分类维度，
# 故 judge 无需配 business_type（配了也会因 source=rule 被排除出分类统计）。
# load_rules 扁平化后的结构：每个触发问题 → {rule_name, answers(set), judge}。
_RULE_JUDGE = {
    "should_dispatch_to_bu": False,
    "answer_resolved": "unknown", "needs_human_review": False,
}
_ANSWERS = {"你好", "你好呀"}
RULES = {
    q: {"rule_name": "转人工", "answers": _ANSWERS, "judge": _RULE_JUDGE}
    for q in ("转人工", "转人工。", "我要转人工")
}


def _bu(**kw):
    return replace(SEC, intents={"咨询客服": "x", "开户": "y"}, rules=RULES, **kw)


def test_match_rule_set_independent_combination():
    """问题 ∈ 触发集 且 答案 ∈ 答案集（任意问 × 任意答）→ 命中，返回 (judge, 规则名)。"""
    bu = _bu()
    # 独立组合：任一问 × 任一答都命中
    for q in ("转人工", "转人工。", "我要转人工"):
        for a in ("你好", "你好呀"):
            assert bu.match_rule(q, a) == (_RULE_JUDGE, "转人工")
    assert bu.match_rule(" 转人工 ", " 你好 ") == (_RULE_JUDGE, "转人工")   # 去空格
    # 答案不在答案集 → 不命中（走 LLM）
    assert bu.match_rule("转人工", "别的答案") is None
    # 问题不在触发集 → 不命中
    assert bu.match_rule("我要开户", "你好") is None


def test_no_rules_never_matches():
    bu = replace(SEC, rules={})
    assert bu.match_rule("转人工", "你好") is None


def _sample(idx, q, ans):
    return {
        "row_index": idx, "session": f"s{idx}", "turn": 1, "question": q,
        "context": [], "next_user_turn": "", "dispatched_intent": "",
        "dispatched_bu": "", "dispatched_to_bu": False, "answer_text": ans,
        "gold": {"dispatch": "", "resolved": ""},
    }


def test_streaming_rule_hit_skips_llm(monkeypatch):
    """命中规则的样本不进 judge_batch；未命中的才调 LLM；报告按规则名聚合。"""
    called = {"batch": 0}

    async def fake_judge_batch(batch, bu):
        called["batch"] += len(batch)
        return [{"should_dispatch_to_bu": True, "business_type": "开户",
                 "answer_resolved": "yes", "needs_human_review": False} for _ in batch]

    monkeypatch.setattr(evaluator, "judge_batch", fake_judge_batch)

    bu = _bu()
    samples = [
        _sample(0, "转人工", "你好"),          # 命中（问∈集 且 答∈集）→ 免 LLM
        _sample(1, "我要转人工", "你好呀"),     # 命中（另一组合）→ 免 LLM
        _sample(2, "转人工", "答案变了"),        # 问命中但答不在集 → 走 LLM
        _sample(3, "我要开户", "开户流程如下"),   # 不在触发集 → 走 LLM
    ]
    agg = _StreamAggregator()
    rule_breakdown = asyncio.run(_judge_streaming(samples, bu, None, None, False, agg))

    assert sum(rule_breakdown.values()) == 2   # row0、row1 命中
    assert rule_breakdown == {"转人工": 2}       # 按规则名聚合（不再按单个问题散开）
    assert called["batch"] == 2          # 只有 row2、row3 进了 LLM
    assert agg.total == 4                # 4 条都进了统计（命中的也计入指标）


def test_rule_hit_excluded_from_intent_but_counted_overall():
    """规则命中行不进业务分类维度（无从归类），但仍计入整体指标（total）。

    这是「短路规则不该有业务分类」的核心口径：命中行不出现在分类分布/分类切片/
    按分类的优化建议里，避免「通用分类」这类占位分类污染报告；但它是真实已处理的
    问答，total、解决率、分发等整体指标照常计入。
    """
    bu = _bu()
    samples = [_sample(0, "转人工", "你好")]
    agg = _StreamAggregator()
    asyncio.run(_judge_streaming(samples, bu, None, None, False, agg))

    # 不进分类分布，也不产生「(未分类)」切片
    dist = {x["name"] for x in agg.intent_distribution()["by_intent"]}
    assert dist == set()
    assert "(未分类)" not in agg.slices
    # 但整体仍计入
    assert agg.total == 1
