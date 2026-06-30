"""人工复核指标重算测试：复核覆盖 AI 判定后，分发准确率/解决率/需复核数按最终值重算。"""
from datapulse.modules.eval.evaluator import apply_reviews_to_result


def _result(*, scored, correct, in_bu, resolved_yes, needs_review, miss=0, over=0):
    rate = round(resolved_yes / in_bu, 4) if in_bu else 0.0
    acc = round(correct / scored, 4) if scored else 0.0
    return {
        "summary": {
            "bu_dispatch": {"scored": scored, "correct": correct, "wrong": scored - correct,
                            "accuracy": acc, "miss_should_accept_but_rejected": miss,
                            "over_should_reject_but_accepted": over},
            "dispatch_accuracy": acc, "resolved_rate": rate, "end_to_end_resolved_rate": rate,
            "needs_review": needs_review,
        },
        "insights": {"overall": {"in_bu_count": in_bu, "resolved_rate": rate, "dispatch_accuracy": acc}},
    }


def _ai_row(idx, *, j_dispatch="", j_resolved="", dispatched_to_bu=False, needs_review=False):
    return {idx: {
        "row_index": idx, "j_dispatch": j_dispatch, "j_resolved": j_resolved,
        "dispatched_to_bu": dispatched_to_bu, "judge": {"needs_human_review": needs_review},
    }}


def test_no_reviews_unchanged():
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    out = apply_reviews_to_result(r, [], {})
    assert out["summary"]["dispatch_accuracy"] == 0.8
    assert out["summary"]["reviewed_count"] == 0


def test_dispatch_wrong_to_right_bumps_accuracy():
    """复核把分发从「错」改「对」：correct +1，准确率上升。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    ai = _ai_row(5, j_dispatch="否")          # AI 判分发错
    reviews = [{"row_index": 5, "reviewed_dispatch": "是", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["bu_dispatch"]["correct"] == 81
    assert out["summary"]["dispatch_accuracy"] == round(81 / 100, 4)
    assert out["summary"]["reviewed_count"] == 1


def test_dispatch_right_to_wrong_drops_accuracy():
    """复核把分发从「对」改「错」：correct -1。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    ai = _ai_row(5, j_dispatch="是")
    reviews = [{"row_index": 5, "reviewed_dispatch": "否", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["bu_dispatch"]["correct"] == 79


def test_resolved_only_for_in_bu():
    """复核「是否解决」仅对进漏斗（dispatched_to_bu=True）的行生效。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    # 行5 未进漏斗：复核解决不应改 resolved_yes
    ai = _ai_row(5, j_resolved="否", dispatched_to_bu=False)
    reviews = [{"row_index": 5, "reviewed_dispatch": "", "reviewed_resolved": "是", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["resolved_rate"] == round(30 / 60, 4)   # 不变


def test_resolved_in_bu_bumps_rate():
    """进漏斗的行，复核未解决→已解决：resolved_yes +1。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    ai = _ai_row(5, j_resolved="否", dispatched_to_bu=True)
    reviews = [{"row_index": 5, "reviewed_dispatch": "", "reviewed_resolved": "是", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["resolved_rate"] == round(31 / 60, 4)


def test_reviewed_row_decrements_needs_review():
    """被复核的行若原本 needs_review，则需复核数 -1（视为已人工确认）。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    ai = _ai_row(5, j_dispatch="是", needs_review=True)
    reviews = [{"row_index": 5, "reviewed_dispatch": "是", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["needs_review"] == 9


def test_same_value_no_change():
    """复核值与 AI 一致（确认无误）：correct 不变，但仍算已复核、扣需复核。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    ai = _ai_row(5, j_dispatch="是", needs_review=True)
    reviews = [{"row_index": 5, "reviewed_dispatch": "是", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["bu_dispatch"]["correct"] == 80   # 一致，不变
    assert out["summary"]["needs_review"] == 9
    assert out["summary"]["reviewed_count"] == 1


def test_miss_over_unchanged():
    """复核不细分两类错误：漏收/误收数保持 AI 原值。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10, miss=7, over=13)
    ai = _ai_row(5, j_dispatch="否")
    reviews = [{"row_index": 5, "reviewed_dispatch": "是", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, ai)
    assert out["summary"]["bu_dispatch"]["miss_should_accept_but_rejected"] == 7
    assert out["summary"]["bu_dispatch"]["over_should_reject_but_accepted"] == 13


def test_stale_review_ignored():
    """复核指向的行已不存在（重测过）：跳过，不计入 reviewed_count。"""
    r = _result(scored=100, correct=80, in_bu=60, resolved_yes=30, needs_review=10)
    reviews = [{"row_index": 999, "reviewed_dispatch": "是", "reviewed_resolved": "", "reviewed_intent": ""}]
    out = apply_reviews_to_result(r, reviews, {})   # ai_rows 空
    assert out["summary"]["reviewed_count"] == 0
    assert out["summary"]["bu_dispatch"]["correct"] == 80
