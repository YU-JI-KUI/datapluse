"""回归：模型布尔字段归一化。

修复 bug：LLM 常把 should_dispatch_to_bu 等返回成字符串 "true"/"false"，
而 Python bool("false")==True，导致分发/复核判定全反。parse_judge_output 须把
布尔字段统一归一成真 bool。
"""
import json

import pytest

from datapulse.modules.eval.judge import parse_judge_output


# 覆盖所有可能写法：true/false、True/False、T/F、Y/N、yes/no、1/0、是/否、对/错
@pytest.mark.parametrize("raw_true", [
    "true", "True", "TRUE", "T", "t", "yes", "Yes", "YES", "y", "Y",
    "是", "对", "1", 1, True, "√",
])
def test_all_truthy_forms(raw_true):
    out = parse_judge_output(json.dumps({"should_dispatch_to_bu": raw_true}))
    assert out["should_dispatch_to_bu"] is True


@pytest.mark.parametrize("raw_false", [
    "false", "False", "FALSE", "F", "f", "no", "No", "NO", "n", "N",
    "否", "错", "0", 0, False, "", "×",
])
def test_all_falsy_forms(raw_false):
    out = parse_judge_output(json.dumps({"should_dispatch_to_bu": raw_false}))
    assert out["should_dispatch_to_bu"] is False


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


# ── 回归：模型返回值净化（修 3 个过夜 eval 任务失败）────────────────────────────
# 根因：模型偶尔把 business_type 返回成数字/bool → 下游 (x or "").strip() 崩；
# 返回含 NaN/Infinity → judge dict 写 judge_json(JSONB) 崩。均属"每次不同"的
# 模型输出问题，重跑就好，正是过夜任务时好时坏的原因。

def test_business_type_int_coerced_to_str():
    """模型把 business_type 返回成数字 → 强转字符串（修 'int' has no strip）。"""
    out = parse_judge_output(json.dumps({"business_type": 3}))
    assert out["business_type"] == "3"
    out["business_type"].strip()   # 下游会 strip，不崩即通过


def test_business_type_bool_coerced_to_str():
    """模型把 business_type 返回成 bool → 强转字符串（修 'bool' has no strip）。"""
    out = parse_judge_output(json.dumps({"business_type": True}))
    assert out["business_type"] == "True"
    out["business_type"].strip()


def test_nan_infinity_sanitized_to_none():
    """模型返回 NaN/Infinity → 清洗成 None，保证写 JSONB 不崩。"""
    out = parse_judge_output('{"business_type": "证券", "confidence": NaN, "score": Infinity}')
    assert out["confidence"] is None
    assert out["score"] is None
    # 关键：整个 dict 能序列化成合法 JSON（allow_nan=False 模拟 PG JSONB 严格性）
    json.dumps(out, allow_nan=False)


def test_nested_nan_sanitized():
    """嵌套结构里的 NaN 也要递归清洗。"""
    out = parse_judge_output('{"detail": {"x": NaN, "y": [1, Infinity, 3]}}')
    assert out["detail"]["x"] is None
    assert out["detail"]["y"] == [1, None, 3]
    json.dumps(out, allow_nan=False)


def test_normal_string_business_type_unchanged():
    """正常字符串 business_type 不受影响。"""
    out = parse_judge_output(json.dumps({"business_type": "证券融资"}))
    assert out["business_type"] == "证券融资"
