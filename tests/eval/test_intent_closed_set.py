"""业务分类闭集约束测试：模型跑飞的分类被归入「其他(清单外)」，报告不冒出几十个分类。"""
from datapulse.modules.eval.evaluator import _OTHER_BUCKET, _business_type, assemble_row


def _sample(**kw):
    base = {
        "row_index": 0, "session": "s", "turn": 1, "question": "q", "context": [],
        "next_user_turn": "", "dispatched_intent": "", "dispatched_to_bu": True,
        "answer_text": "a", "gold": {"dispatch": "", "resolved": ""},
    }
    base.update(kw)
    return base


ALLOWED = {"资产查询", "开户", "转账"}


def test_in_list_kept():
    j = {"business_type": "资产查询", "should_dispatch_to_bu": True}
    assert _business_type(j, ALLOWED) == "资产查询"


def test_out_of_list_to_other_bucket():
    """清单外的自创分类 → 归「其他(清单外)」，不原样保留。"""
    j = {"business_type": "账户资产查询", "should_dispatch_to_bu": True}   # 模型改写/细分
    assert _business_type(j, ALLOWED) == _OTHER_BUCKET


def test_placeholder_to_empty():
    """占位值(非本BU/拒识/其他/空)→ 归空，不算业务分类。"""
    for v in ("非本BU", "拒识", "其他", ""):
        assert _business_type({"business_type": v}, ALLOWED) == ""


def test_none_allowed_no_check():
    """allowed=None(测试/小数据路径)→ 不校验，保留原值。"""
    assert _business_type({"business_type": "任意自创"}, None) == "任意自创"


def test_assemble_row_applies_closed_set():
    """assemble_row 传入 allowed 后，j_intent 受闭集约束。"""
    judge = {"business_type": "我自己编的分类", "should_dispatch_to_bu": True,
             "answer_resolved": "yes"}
    row = assemble_row(_sample(), judge, ALLOWED)
    assert row["j_intent"] == _OTHER_BUCKET
    # 不传 allowed 时保留原值(兼容)
    row2 = assemble_row(_sample(), judge)
    assert row2["j_intent"] == "我自己编的分类"


def test_report_intents_are_closed():
    """端到端语义：一批含大量跑飞分类，最终 distinct 分类 ⊆ 清单 ∪ {其他桶}。"""
    flyaway = ["资产查询", "查资产", "资产查询类", "开户", "开户流程", "转账", "跨行转账", "编的X"]
    intents = set()
    for i, bt in enumerate(flyaway):
        j = {"business_type": bt, "should_dispatch_to_bu": True, "answer_resolved": "yes"}
        row = assemble_row(_sample(row_index=i), j, ALLOWED)
        if row["j_intent"]:
            intents.add(row["j_intent"])
    assert intents <= (ALLOWED | {_OTHER_BUCKET}), f"出现清单外分类: {intents - (ALLOWED | {_OTHER_BUCKET})}"
