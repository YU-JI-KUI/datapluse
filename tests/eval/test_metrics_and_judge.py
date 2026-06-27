"""指标计算与 Mock Judge 测试。"""
from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval.llm.mock_judge import mock_judge
from datapulse.modules.eval.metrics import binary_report


def test_binary_report_perfect():
    """完全一致时 κ=1、准确率=1。"""
    y = ["是", "否", "是", "否"]
    r = binary_report("t", y, y)
    assert r["accuracy"] == 1.0
    assert r["kappa"] == 1.0
    assert r["confusion_matrix"] == [[2, 0], [0, 2]]


def test_binary_report_structure():
    """返回结构含分类别 P/R/F1 与混淆矩阵。"""
    r = binary_report("t", ["是", "否"], ["是", "是"])
    assert "per_label" in r and "是" in r["per_label"]
    assert set(r["per_label"]["是"]) == {"precision", "recall", "f1"}
    assert len(r["confusion_matrix"]) == 2


def test_mock_judge_rejects_phone_recharge():
    """『手机充值』应判为拒识 → 不该证券承接(should_dispatch_to_bu=False)。"""
    s = {"question": "手机充值", "dispatched_intent": "资产查询",
         "answer_text": "无法处理", "next_user_turn": None, "dispatched_to_bu": True}
    j = mock_judge(s, SEC)
    assert j["intent_pred"] == "拒识"
    assert j["should_dispatch_to_bu"] is False  # 拒识 → 不该证券承接


def test_mock_judge_securities_business():
    """证券业务问题 → 该证券承接;分发到本BU时判解决度。"""
    s = {"question": "我的总资产多少", "dispatched_intent": "资产查询",
         "answer_text": "您的总资产为 50 万元", "next_user_turn": None, "dispatched_to_bu": True}
    j = mock_judge(s, SEC)
    assert j["intent_pred"] == "资产查询"
    assert j["should_dispatch_to_bu"] is True
    assert j["answer_resolved"] == "yes"


def test_mock_judge_not_dispatched_skips_resolution():
    """未分发到本BU(漏斗外)→ 解决度不判,填 unknown。"""
    s = {"question": "我的总资产多少", "dispatched_intent": "资产查询",
         "answer_text": "您的总资产为 50 万元", "next_user_turn": None, "dispatched_to_bu": False}
    j = mock_judge(s, SEC)
    assert j["answer_resolved"] == "unknown"


def test_mock_judge_negative_next_turn():
    """分发到本BU + 下一轮用户重问/不满 → 倾向 partial。"""
    s = {"question": "封成比怎么算", "dispatched_intent": "问诊股",
         "answer_text": "封成比=封单/成交", "next_user_turn": "还是没看懂", "dispatched_to_bu": True}
    j = mock_judge(s, SEC)
    assert j["answer_resolved"] in ("partial", "no")
