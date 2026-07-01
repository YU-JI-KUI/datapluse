"""会话轮次分布测试：按会话总轮次动态分桶（1/2/3 单独 + 高轮次分位数归桶），不写死区间。"""
from datapulse.modules.eval.evaluator import turn_distribution


def _samples(session_turns):
    """session_turns: {会话id: 该会话的样本轮次列表} → 展开成 samples。"""
    out = []
    for sid, turns in session_turns.items():
        for t in turns:
            out.append({"session": sid, "turn": t})
    return out


def _as_dict(dist):
    return {d["name"]: d["count"] for d in dist}


def test_empty():
    assert turn_distribution([]) == []


def test_low_turns_separate():
    """1/2/3 轮各单独档，按会话总轮次。"""
    # S1 总2轮, S2 总1轮, S3 总3轮, S4 总1轮
    s = _samples({"S1": [1, 2], "S2": [1], "S3": [1, 2, 3], "S4": [1]})
    d = _as_dict(turn_distribution(s))
    assert d == {"1轮": 2, "2轮": 1, "3轮": 1}   # 无高轮次,不硬凑 5 档


def test_high_turns_bucketed():
    """>3 轮的用分位数动态切两档 + 封顶档，区间由数据定。"""
    # 造:各档都有量 + 一批 4~10 轮的高轮次会话
    st = {f"a{i}": list(range(1, 2)) for i in range(3)}    # 3 个 1轮会话
    st.update({f"b{i}": list(range(1, 3)) for i in range(2)})   # 2 个 2轮
    # 高轮次会话:4,5,6,8,10 轮各一个
    for i, mx in enumerate([4, 5, 6, 8, 10]):
        st[f"h{i}"] = list(range(1, mx + 1))
    d = turn_distribution(_samples(st))
    names = [x["name"] for x in d]
    total = sum(x["count"] for x in d)
    assert total == len(st)                        # 每通会话恰好归一档
    assert "1轮" in names and "2轮" in names
    # 高轮次被切成两档（形如 4-N轮 / N+1轮及以上），且不写死具体数字
    high_buckets = [n for n in names if "及以上" in n or "-" in n]
    assert len(high_buckets) >= 1


def test_by_session_not_by_sample():
    """口径是「按会话总轮次」，不是「按样本处于第几轮」。"""
    # 一通 5 轮会话 → 应算 1 个「高轮次会话」，而不是 5 条分散到各档
    d = turn_distribution(_samples({"S": [1, 2, 3, 4, 5]}))
    assert sum(x["count"] for x in d) == 1         # 只有 1 通会话
