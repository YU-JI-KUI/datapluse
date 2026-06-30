"""活动标问过滤测试:命中清单的样本跳过评测、不计数到 samples、仍作后续轮上下文。"""
from dataclasses import replace

import pandas as pd

from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval.pipeline import build_all_samples, resolve_columns


def _prep(rows):
    df = pd.DataFrame(rows)
    m = resolve_columns(df)
    df["_turn_n"] = pd.to_numeric(df[m["turn"]]).astype(int)
    df = df.sort_values(["应用会话ID", "_turn_n"]).reset_index(drop=True)
    return df, m


def test_is_activity_exact_match():
    """精确相等才命中,子串不误伤。"""
    bu = replace(SEC, activity_questions=frozenset({"帮我解锁消费权益"}))
    assert bu.is_activity("帮我解锁消费权益")
    assert bu.is_activity("  帮我解锁消费权益  ")        # 去首尾空格
    assert not bu.is_activity("帮我解锁消费权益的条件")   # 子串不命中
    assert not bu.is_activity("解锁消费权益")


def test_activity_empty_set_skips_nothing():
    """空集合(未配置活动标问)不过滤任何样本。"""
    bu = replace(SEC, activity_questions=frozenset())
    df, m = _prep([
        {"客户问题": "帮我解锁消费权益", "客户咨询轮次": "1", "应用会话ID": "S", "答案": "已解锁", "分发BU": "证券"},
    ])
    samples, excluded = build_all_samples(df, m, bu)
    assert len(samples) == 1 and excluded == 0


def test_activity_skipped_and_counted():
    """命中活动标问的样本不进 samples,排除数 +1。"""
    bu = replace(SEC, activity_questions=frozenset({"帮我解锁消费权益"}))
    df, m = _prep([
        {"客户问题": "帮我解锁消费权益", "客户咨询轮次": "1", "应用会话ID": "S", "答案": "已解锁", "分发BU": "证券"},
        {"客户问题": "我的总资产", "客户咨询轮次": "2", "应用会话ID": "S", "答案": "52万", "分发BU": "证券"},
    ])
    samples, excluded = build_all_samples(df, m, bu)
    assert excluded == 1
    assert len(samples) == 1
    assert samples[0]["question"] == "我的总资产"   # 只剩非活动标问那条


def test_activity_kept_as_context():
    """活动标问自己不评,但仍作为后续轮的前文保留(它确实发生过)。"""
    bu = replace(SEC, activity_questions=frozenset({"帮我解锁消费权益"}))
    df, m = _prep([
        {"客户问题": "帮我解锁消费权益", "客户咨询轮次": "1", "应用会话ID": "S", "答案": "已为你解锁", "分发BU": "证券"},
        {"客户问题": "还有别的权益吗", "客户咨询轮次": "2", "应用会话ID": "S", "答案": "有积分", "分发BU": "证券"},
    ])
    samples, excluded = build_all_samples(df, m, bu)
    assert excluded == 1 and len(samples) == 1
    ctx = samples[0]["context"]
    # 第2轮的前文应含被跳过的活动标问那轮
    assert len(ctx) == 1
    assert ctx[0]["user"] == "帮我解锁消费权益"
