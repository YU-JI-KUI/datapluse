"""流水线测试:列解析(精确优先)、会话重组、不做样本过滤。"""
import pandas as pd

from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval.pipeline import build_all_samples, load_and_prep, resolve_columns


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
