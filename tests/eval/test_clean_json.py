"""回归：落盘前清洗 inf/nan。PostgreSQL JSONB 不接受 Infinity/NaN，
否则整条 insert 报 invalid input syntax for type json (Token "Infinity" is invalid)。"""
import json

from datapulse.modules.eval.repository import _clean_json


def test_inf_nan_become_none():
    row = {"a": float("inf"), "b": float("-inf"), "c": float("nan"), "d": 0.95, "e": 0}
    out = _clean_json(row)
    assert out["a"] is None and out["b"] is None and out["c"] is None
    assert out["d"] == 0.95 and out["e"] == 0   # 正常值不动


def test_nested_cleaned():
    row = {"j": {"score": float("inf")}, "lst": [1.0, float("nan"), {"x": float("-inf")}]}
    out = _clean_json(row)
    assert out["j"]["score"] is None
    assert out["lst"][1] is None and out["lst"][2]["x"] is None


def test_output_pg_safe():
    # 清洗后必须能被 allow_nan=False 序列化（等价于 PG 能接受）
    row = {"a": [float("inf"), {"b": float("nan")}], "ok": "文本"}
    json.dumps(_clean_json(row), allow_nan=False)   # 不抛错即通过
