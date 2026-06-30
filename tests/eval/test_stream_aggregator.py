"""流式累加器等价性测试。

核心保证(P0-② A 案):_StreamAggregator 分批喂入的结果，必须与原纯函数
(compute_insights / _bu_dispatch_stats / _intent_distribution / _compute_metrics)
全量计算完全一致。否则百万级流式聚合会给出错误指标。
"""
from datapulse.modules.eval.evaluator import (
    _StreamAggregator,
    _bu_dispatch_stats,
    _compute_metrics,
    _intent_distribution,
    assemble_row,
    compute_insights,
)


def _sample(row_index, **kw):
    base = {
        "row_index": row_index, "session": f"s{row_index}", "turn": 1, "question": f"q{row_index}",
        "context": [], "next_user_turn": "", "dispatched_intent": "",
        "dispatched_to_bu": True, "answer_text": "a",
        "gold": {"dispatch": "", "resolved": ""},
    }
    base.update(kw)
    return base


def _make_rows():
    """造一批多样化 rows，覆盖：in_bu/非in_bu、resolved yes/no/partial、需复核、
    error、金标配对(是/否四象限)、多 intent、未分类。"""
    rows = []
    idx = 0

    def add(judge, **sample_kw):
        nonlocal idx
        rows.append(assemble_row(_sample(idx, **sample_kw), judge))
        idx += 1

    # 业务分类 A：进漏斗、已解决
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "yes"},
        dispatched_to_bu=True, gold={"dispatch": "是", "resolved": "是"})
    # 业务分类 A：进漏斗、未解决(no) + 需复核
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "no",
         "needs_human_review": True},
        dispatched_to_bu=True, gold={"dispatch": "是", "resolved": "否"})
    # 业务分类 A：进漏斗、partial
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "partial"},
        dispatched_to_bu=True, gold={"dispatch": "是", "resolved": "否"})
    # 业务分类 B：未进漏斗(actual=False)，但 AI 认为该接 → 漏收(miss)
    add({"should_dispatch_to_bu": True, "business_type": "查询", "answer_resolved": "yes"},
        dispatched_to_bu=False, gold={"dispatch": "否", "resolved": "是"})
    # 误收：AI 认为不该接，实际分进来 → over
    add({"should_dispatch_to_bu": False, "business_type": "非本BU", "answer_resolved": "no"},
        dispatched_to_bu=True, gold={"dispatch": "否", "resolved": "否"})
    # 未分类(business_type 空) + 进漏斗已解决
    add({"should_dispatch_to_bu": True, "business_type": "", "answer_resolved": "yes"},
        dispatched_to_bu=True, gold={"dispatch": "是", "resolved": "是"})
    # judge 出错：计入 errors，dispatch_correct=None 不进分发统计
    add({"_error": "boom", "needs_human_review": True}, dispatched_to_bu=True)
    # 业务分类 B：进漏斗未解决，金标分发=否预测=是(配对覆盖更全)
    add({"should_dispatch_to_bu": False, "business_type": "查询", "answer_resolved": "no"},
        dispatched_to_bu=True, gold={"dispatch": "否", "resolved": "否"})
    return rows


def _feed_in_batches(rows, batch_size):
    agg = _StreamAggregator()
    for start in range(0, len(rows), batch_size):
        agg.update(rows[start:start + batch_size])
    return agg


def test_aggregator_matches_pure_functions():
    rows = _make_rows()
    # 分多种批大小喂，验证与批边界无关
    for bs in (1, 2, 3, len(rows)):
        agg = _feed_in_batches(rows, bs)
        assert agg.insights() == compute_insights(rows), f"insights 不一致 (batch={bs})"
        assert agg.bu_dispatch() == _bu_dispatch_stats(rows), f"bu_dispatch 不一致 (batch={bs})"
        assert agg.intent_distribution() == _intent_distribution(rows), f"intent_dist 不一致 (batch={bs})"
        assert agg.metrics() == _compute_metrics(rows), f"metrics 不一致 (batch={bs})"


def test_aggregator_summary_counts():
    rows = _make_rows()
    agg = _feed_in_batches(rows, 3)
    assert agg.total == len(rows)
    assert agg.errors == sum(1 for r in rows if isinstance(r["judge"], dict) and "_error" in r["judge"])
    assert agg.needs_review == sum(
        1 for r in rows if isinstance(r["judge"], dict) and r["judge"].get("needs_human_review")
    )
    assert agg.disagreement_count == sum(1 for r in rows if r["is_disagreement"])
