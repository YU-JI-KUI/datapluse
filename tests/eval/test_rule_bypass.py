"""规则短路测试：问题精确+答案一致才命中，命中用写死 judge 免 LLM，未命中走 LLM。"""
import asyncio
from dataclasses import replace

from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval import evaluator
from datapulse.modules.eval.evaluator import _StreamAggregator, _judge_streaming


# 一条转人工规则：问题「转人工」+ 答案「正在为您转接」→ 判非本BU、业务分类咨询客服
_RULE_JUDGE = {
    "should_dispatch_to_bu": False, "business_type": "非本BU",
    "answer_resolved": "unknown", "needs_human_review": False,
}
RULES = {"转人工": {"expected_answer": "正在为您转接", "judge": _RULE_JUDGE}}


def _bu(**kw):
    return replace(SEC, intents={"咨询客服": "x", "开户": "y"}, rules=RULES, **kw)


def test_match_rule_question_and_answer():
    bu = _bu()
    # 问题+答案都对 → 命中，返回写死 judge
    assert bu.match_rule("转人工", "正在为您转接") == _RULE_JUDGE
    assert bu.match_rule(" 转人工 ", "正在为您转接") == _RULE_JUDGE   # 去空格
    # 问题对但答案不对 → 不命中（走 LLM）
    assert bu.match_rule("转人工", "别的答案") is None
    # 问题不在规则里 → 不命中
    assert bu.match_rule("我要开户", "正在为您转接") is None


def test_no_rules_never_matches():
    bu = replace(SEC, rules={})
    assert bu.match_rule("转人工", "正在为您转接") is None


def _sample(idx, q, ans):
    return {
        "row_index": idx, "session": f"s{idx}", "turn": 1, "question": q,
        "context": [], "next_user_turn": "", "dispatched_intent": "",
        "dispatched_bu": "", "dispatched_to_bu": False, "answer_text": ans,
        "gold": {"dispatch": "", "resolved": ""},
    }


def test_streaming_rule_hit_skips_llm(monkeypatch):
    """命中规则的样本不进 judge_batch；未命中的才调 LLM。"""
    called = {"batch": 0}

    async def fake_judge_batch(batch, bu):
        called["batch"] += len(batch)
        return [{"should_dispatch_to_bu": True, "business_type": "开户",
                 "answer_resolved": "yes", "needs_human_review": False} for _ in batch]

    monkeypatch.setattr(evaluator, "judge_batch", fake_judge_batch)

    bu = _bu()
    samples = [
        _sample(0, "转人工", "正在为您转接"),   # 命中规则 → 免 LLM
        _sample(1, "转人工", "答案变了"),        # 问题命中但答案不符 → 走 LLM
        _sample(2, "我要开户", "开户流程如下"),   # 不在规则 → 走 LLM
    ]
    agg = _StreamAggregator()
    rule_breakdown = asyncio.run(_judge_streaming(samples, bu, None, None, False, agg))

    assert sum(rule_breakdown.values()) == 1   # 只有 row0 命中规则
    assert rule_breakdown == {"转人工": 1}      # 按规则问题细分
    assert called["batch"] == 2          # 只有 row1、row2 进了 LLM
    assert agg.total == 3                # 3 条都进了统计（命中的也计入指标）


def test_rule_hit_counts_into_metrics():
    """规则命中的结果计入业务分类分布（说明它像 AI 一样被统计）。"""
    bu = _bu()
    samples = [_sample(0, "转人工", "正在为您转接")]
    agg = _StreamAggregator()
    # 规则判 business_type=非本BU（占位）→ 归兜底桶「非证券业务」
    asyncio.run(_judge_streaming(samples, bu, None, None, False, agg))
    dist = {x["name"] for x in agg.intent_distribution()["by_intent"]}
    assert dist == {"非证券业务"}        # 命中样本计入了分类分布
