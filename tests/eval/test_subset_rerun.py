"""子集重跑：全量重算 summary（recompute_result_from_rows）保留数据固有字段、只重算指标。"""
from datapulse.modules.eval.evaluator import assemble_row, recompute_result_from_rows


def _sample(idx, **kw):
    base = {
        "row_index": idx, "session": f"s{idx}", "turn": 1, "question": f"q{idx}",
        "context": [], "next_user_turn": "", "dispatched_intent": "",
        "dispatched_bu": "", "dispatched_to_bu": True, "answer_text": "a",
        "gold": {"dispatch": "", "resolved": ""},
    }
    base.update(kw)
    return base


def _row(idx, dispatch_ok, resolved, need_review=False, dispatched_to_bu=True):
    """造一条已 assemble 的 row（模拟落盘的 row_json）。"""
    judge = {
        "should_dispatch_to_bu": True,
        "business_type": "开户",
        "answer_resolved": resolved,
        "needs_human_review": need_review,
    }
    s = _sample(idx, dispatched_to_bu=dispatched_to_bu)
    # dispatch_ok 通过让 should=分到本BU一致/不一致来控制
    judge["should_dispatch_to_bu"] = dispatched_to_bu if dispatch_ok else (not dispatched_to_bu)
    return assemble_row(s, judge, {"开户"}, "非证券业务")


def test_recompute_preserves_fixed_fields_and_updates_metrics():
    """重算保留 mode/sessions/filter_stats/advice，重算 needs_review/解决率/分发准确率。"""
    old = {
        "summary": {"total_samples": 3, "sessions": 3, "multi_turn_sessions": 0,
                    "needs_review": 3, "dispatch_accuracy": 0.0, "resolved_rate": 0.0},
        "mode": "production",
        "filter_stats": {"total": 3, "excluded_activity": 0, "rule_hit": 0},
        "advice": {"source": "rule", "items": [{"problem": "旧建议"}]},
        "insights": {"overall": {}},
    }
    # 重跑后的新 rows：3 条都分发判对、2 条已解决、都不再需复核
    rows = [_row(0, True, "yes"), _row(1, True, "yes"), _row(2, True, "no")]
    out = recompute_result_from_rows(old, [rows], "production")

    s = out["summary"]
    assert s["needs_review"] == 0                    # 重算：都不需复核了
    assert s["dispatch_accuracy"] == 1.0             # 3 条都判对
    assert s["resolved_rate"] == round(2 / 3, 4)     # 3 条进漏斗、2 条 yes
    assert s["total_samples"] == 3
    # 数据固有字段保留
    assert out["mode"] == "production"
    assert s["sessions"] == 3
    assert out["filter_stats"]["total"] == 3
    assert out["advice"]["items"][0]["problem"] == "旧建议"   # advice 不因重算丢失


def test_recompute_needs_review_drops_after_rerun():
    """重跑把原需复核的判成不需复核 → 需复核数下降。"""
    old = {"summary": {"needs_review": 2}, "mode": "production",
           "insights": {"overall": {}}}
    rows = [_row(0, True, "yes", need_review=False), _row(1, True, "yes", need_review=True)]
    out = recompute_result_from_rows(old, [rows], "production")
    assert out["summary"]["needs_review"] == 1       # 只剩 row1 需复核
