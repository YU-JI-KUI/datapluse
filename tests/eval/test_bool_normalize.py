"""回归：模型布尔字段归一化。

修复 bug：LLM 常把 should_dispatch_to_bu 等返回成字符串 "true"/"false"，
而 Python bool("false")==True，导致分发/复核判定全反。parse_judge_output 须把
布尔字段统一归一成真 bool。
"""
from datapulse.modules.eval.judge import parse_judge_output


def test_string_false_becomes_bool_false():
    out = parse_judge_output('{"should_dispatch_to_bu": "false", "needs_human_review": "false"}')
    assert out["should_dispatch_to_bu"] is False
    assert out["needs_human_review"] is False


def test_string_true_becomes_bool_true():
    out = parse_judge_output('{"should_dispatch_to_bu": "true", "answer_relevant": "True"}')
    assert out["should_dispatch_to_bu"] is True
    assert out["answer_relevant"] is True


def test_real_bool_unchanged():
    out = parse_judge_output('{"should_dispatch_to_bu": false, "answer_complete": true}')
    assert out["should_dispatch_to_bu"] is False
    assert out["answer_complete"] is True


def test_chinese_tokens():
    out = parse_judge_output('{"should_dispatch_to_bu": "是", "needs_human_review": "否"}')
    assert out["should_dispatch_to_bu"] is True
    assert out["needs_human_review"] is False


def test_unknown_value_defaults_false():
    # 无法识别 → 保守判 False（不轻易判「该承接/需复核」）
    out = parse_judge_output('{"should_dispatch_to_bu": "maybe"}')
    assert out["should_dispatch_to_bu"] is False


def test_answer_resolved_not_touched():
    # answer_resolved 是 yes/partial/no 枚举，不是 bool，不应被归一
    out = parse_judge_output('{"answer_resolved": "no"}')
    assert out["answer_resolved"] == "no"
