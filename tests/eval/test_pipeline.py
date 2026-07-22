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
    samples, _excluded, _acts = build_all_samples(df, m, SEC)
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


# ── BU 校验：防误传日志到错误工作区 ──────────────────────────────────────────

def _write_xlsx(tmp_path, dispatch_values):
    """造含必需列的最小 Excel，分发BU 列取给定值。"""
    n = len(dispatch_values)
    df = pd.DataFrame({
        "客户问题":     [f"问{i}" for i in range(n)],
        "应用会话ID":   [f"s{i}" for i in range(n)],
        "客户咨询轮次": [1] * n,
        "答案":         [f"答{i}" for i in range(n)],
        "分发BU":       dispatch_values,
    })
    p = tmp_path / "log.xlsx"
    df.to_excel(str(p), index=False)
    return str(p)


def test_validate_bu_match_pass(tmp_path):
    """证券日志传证券工作区：前 10 行含证券取值 → 通过。"""
    from datapulse.modules.eval.pipeline import validate_bu_match
    p = _write_xlsx(tmp_path, ["证券"] * 12)
    validate_bu_match([p], SEC)   # 不抛异常即通过


def test_validate_bu_match_wrong_bu(tmp_path):
    """寿险日志误传证券工作区：前 10 行均不属于证券 → 报错。"""
    from datapulse.modules.eval.pipeline import validate_bu_match
    import pytest
    p = _write_xlsx(tmp_path, ["寿险"] * 12)
    with pytest.raises(ValueError, match="证券"):
        validate_bu_match([p], SEC)


def test_validate_bu_match_only_checks_head(tmp_path):
    """只查前 10 行：前 10 行全不匹配即报错，即使后面有匹配行。"""
    from datapulse.modules.eval.pipeline import validate_bu_match
    import pytest
    p = _write_xlsx(tmp_path, ["寿险"] * 10 + ["证券"] * 5)
    with pytest.raises(ValueError):
        validate_bu_match([p], SEC)


def test_validate_bu_match_tolerates_mixed(tmp_path):
    """前 10 行混杂但含至少一行本 BU → 通过（真实日志会有跨 BU 行）。"""
    from datapulse.modules.eval.pipeline import validate_bu_match
    p = _write_xlsx(tmp_path, ["寿险", "其他", "证券业务", "寿"] + ["证券"] * 8)
    validate_bu_match([p], SEC)


# ── 进度分子口径：活动标问行不得计入进度分子（防突破 100%）──────────────────

def test_progress_numerator_excludes_activity_rows():
    """done_count 只数 samples 内的已完成行，排除已落盘的活动标问行。

    复现多文件评测「一开始就 100% 并突破」的根因：done_idx 含活动标问行，
    total 只数评测样本，若 done_count=len(done_idx) 会 > total。
    """
    samples = [{"row_index": 0}, {"row_index": 1}, {"row_index": 2}]
    total = len(samples)
    # 已落盘：活动标问行(10~14) + 评测样本 0
    done_idx = {10, 11, 12, 13, 14, 0}

    sample_idx = {s["row_index"] for s in samples}
    done_count = len(done_idx & sample_idx)

    assert done_count == 1
    assert done_count <= total          # 不再突破 100%
    assert len(done_idx) > total        # 证明旧逻辑会爆表


def test_cross_file_session_turn_order():
    """多文件合并后同一会话跨文件、turn 物理顺序乱 → 组内按 turn 重排，上下文不错位。

    复现：运营按 5 万行硬拆，同一「应用会话ID」被拆到多个文件，merged 是各文件
    各自排序后 concat，同 session 行呈两段拼接、整体 turn 无序（如物理序 [1,2,5,3,4]）。
    修复前 next/prior 按物理顺序取，会把 turn=2 的下一轮错取成 turn=5。
    """
    df = pd.DataFrame([
        {"应用会话ID": "S", "客户咨询轮次": 1, "客户问题": "q1", "答案": "a1", "分发BU": "证券"},
        {"应用会话ID": "S", "客户咨询轮次": 2, "客户问题": "q2", "答案": "a2", "分发BU": "证券"},
        {"应用会话ID": "S", "客户咨询轮次": 5, "客户问题": "q5", "答案": "a5", "分发BU": "证券"},
        {"应用会话ID": "S", "客户咨询轮次": 3, "客户问题": "q3", "答案": "a3", "分发BU": "证券"},
        {"应用会话ID": "S", "客户咨询轮次": 4, "客户问题": "q4", "答案": "a4", "分发BU": "证券"},
    ])
    df["_turn_n"] = df["客户咨询轮次"].astype(int)
    df["_row_index"] = range(len(df))
    m = resolve_columns(df)

    samples, _, _ = build_all_samples(df, m, SEC)
    by_turn = {s["turn"]: s for s in samples}

    # 前文按 turn 有序取最近 3 轮
    assert [c["turn"] for c in by_turn[4]["context"]] == [1, 2, 3]
    # 下一轮取 turn 最小的更大轮，而非物理顺序第一个
    assert by_turn[2]["next_user_turn"] == "q3"
    assert by_turn[4]["next_user_turn"] == "q5"


def test_multifile_gold_column_union(tmp_path):
    """多文件：首文件无金标、次文件有金标 → 金标列并集纳入，模式判 calibration。

    复现 Bug：统一列映射只认首文件表头时，次文件独有的金标列被静默丢弃，
    detect_gold 拿不到金标键 → 误判 production，校准评测退化、用户无感知。
    """
    from datapulse.modules.eval.pipeline import load_and_merge, detect_gold

    base = {"客户问题": "q", "应用会话ID": "s", "客户咨询轮次": 1, "答案": "a", "分发BU": "证券"}
    f0 = tmp_path / "f0.xlsx"
    pd.DataFrame([{**base, "应用会话ID": f"a{i}"} for i in range(3)]).to_excel(str(f0), index=False)
    f1 = tmp_path / "f1.xlsx"
    pd.DataFrame(
        [{**base, "应用会话ID": f"b{i}", "分发是否正确": "是"} for i in range(3)]
    ).to_excel(str(f1), index=False)

    merged, m, _ = load_and_merge([str(f0), str(f1)])
    assert "gold_dispatch" in m                       # 次文件金标列被纳入
    assert detect_gold(merged, m)["mode"] == "calibration"   # 不再误判 production


def test_row_segment_overflow_guard(tmp_path, monkeypatch):
    """单文件行数 ≥ 段宽 → 报错，防 row_index 段溢出覆盖数据。"""
    import pytest
    from datapulse.modules.eval import pipeline

    monkeypatch.setattr(pipeline, "_ROW_SEGMENT", 5)
    base = {"客户问题": "q", "应用会话ID": "s", "客户咨询轮次": 1, "答案": "a", "分发BU": "证券"}
    p = tmp_path / "big.xlsx"
    pd.DataFrame([{**base, "应用会话ID": f"s{i}"} for i in range(6)]).to_excel(str(p), index=False)
    with pytest.raises(ValueError, match="分段上限"):
        pipeline.load_and_merge([str(p)])
