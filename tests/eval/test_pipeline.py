"""流水线测试:列解析(精确优先)、会话重组、不做样本过滤。"""
import json

import pandas as pd

from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval.pipeline import (
    _extract_row, build_all_samples, load_and_prep, resolve_columns,
)


def _df():
    return pd.DataFrame([
        {
            "客户问题": "手机充值", "客户咨询轮次": "1", "应用会话ID": "A1",
            "答案一级围栏标签": "x", "标准问答案": "y", "答案": "真答案", "分发BU": "证券",
            "分发是否正确": "否", "答案是否解决客户问题": "否",
        },
    ])


def test_exact_match_beats_substring():
    """关键回归:『答案』必须精确命中『答案』列,而非『答案一级围栏标签』。"""
    m = resolve_columns(_df())
    assert m["answer"] == "答案"  # 不能是『答案一级围栏标签』或『标准问答案』
    assert m["gold_resolved"] == "答案是否解决客户问题"


def test_no_filter_keeps_all_rows(tmp_path):
    """不做样本过滤:上传几行就评几行,一行不删(保上下文完整)。"""
    df = pd.DataFrame([
        {"客户问题": "。。。", "客户咨询轮次": "1", "应用会话ID": "S", "答案": "", "分发BU": "证券"},
        {"客户问题": "我的总资产", "客户咨询轮次": "2", "应用会话ID": "S", "答案": "52万", "分发BU": "证券"},
    ])
    p = tmp_path / "log.xlsx"
    df.to_excel(p, index=False)
    out, m, stats = load_and_prep(str(p))
    assert stats["total"] == 2
    assert len(out) == 2  # 无效的"。。。"那行也保留,不删


def test_session_context_reconstruction():
    """同会话多轮:第2轮应能拿到第1轮作为上下文,第1轮记录下一轮。"""
    df = pd.DataFrame([
        {"客户问题": "融资利率", "客户咨询轮次": "1", "应用会话ID": "S", "答案": "6.5%", "分发BU": "证券"},
        {"客户问题": "融资成本", "客户咨询轮次": "2", "应用会话ID": "S", "答案": "中等", "分发BU": "证券"},
    ])
    m = resolve_columns(df)
    df["_turn_n"] = pd.to_numeric(df[m["turn"]]).astype(int)
    df = df.sort_values(["应用会话ID", "_turn_n"]).reset_index(drop=True)
    samples, _excluded = build_all_samples(df, m, SEC)
    assert samples[0]["next_user_turn"] == "融资成本"
    # 第2轮的上下文应含第1轮的「用户问 + AI 答原文」
    ctx = samples[1]["context"]
    assert len(ctx) == 1
    assert ctx[0]["user"] == "融资利率"
    assert ctx[0]["ai"] == "6.5%"


def test_dirty_cells_coerced_to_str():
    """回归:Excel 非字符串单元格(bool/int/nan)必须被强制转字符串。

    根因:pd.read_excel(dtype=str) 对布尔列/数字列并非 100% 生效,漏进的
    bool/int/nan 会让下游 .strip() 崩(''bool'/'int' object has no attribute
    'strip'')、写 JSONB 崩(invalid input syntax for type json)。
    此前 3 个过夜 eval 任务即因此失败。
    """
    df = pd.DataFrame([{
        "应用会话ID": 12345,          # 数字会话ID → int
        "客户咨询轮次": "1",
        "客户问题": "怎么开户",
        "答案": True,                  # 布尔答案 → bool
        "模型意图": float("nan"),      # 空单元格 → nan
        "分发BU": 0,                   # 数字分发BU → int
        "分发理由": "规则命中",
    }])
    df["_turn_n"] = 1
    m = resolve_columns(df)
    row = _extract_row(df, 0, m)

    # 所有字段都是 str,NaN → "",bool/int → str
    assert row["session"] == "12345"
    assert row["answer"] == "True"
    assert row["dispatched_bu"] == "0"
    assert row["sys_intent"] == ""     # nan → ""

    # 关键:能安全 strip(修复前 bool/int 直接 AttributeError)
    for k in ("session", "question", "answer", "sys_intent",
              "dispatch_reason", "dispatched_bu", "ask_time"):
        assert isinstance(row[k], str)
        row[k].strip()

    # 关键:能安全写 JSONB(修复前 nan → 非法 JSON token)
    json.dumps(row, ensure_ascii=False)
