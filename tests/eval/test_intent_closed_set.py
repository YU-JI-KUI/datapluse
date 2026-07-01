"""业务分类闭集约束测试：清单内保留，占位值/清单外自创全归「非XX业务」兜底桶。
报告业务分类恒为闭集：配置的 N 个 + 一个兜底桶，别无其它（无空桶/其它/未分类）。"""
from datapulse.modules.eval.evaluator import _business_type, assemble_row, other_label


class _BU:
    def __init__(self, name):
        self.name = name


def _sample(**kw):
    base = {
        "row_index": 0, "session": "s", "turn": 1, "question": "q", "context": [],
        "next_user_turn": "", "dispatched_intent": "", "dispatched_to_bu": True,
        "answer_text": "a", "gold": {"dispatch": "", "resolved": ""},
    }
    base.update(kw)
    return base


ALLOWED = {"资产查询", "开户", "转账"}
OTHER = "非证券业务"


def test_other_label_by_bu():
    """兜底桶名按 BU 动态：证券→非证券业务，寿险→非寿险业务。"""
    assert other_label(_BU("证券")) == "非证券业务"
    assert other_label(_BU("寿险")) == "非寿险业务"


def test_in_list_kept():
    assert _business_type({"business_type": "资产查询"}, ALLOWED, OTHER) == "资产查询"


def test_out_of_list_to_other():
    """清单外的自创/改写分类 → 归兜底桶。"""
    assert _business_type({"business_type": "账户资产查询"}, ALLOWED, OTHER) == OTHER
    assert _business_type({"business_type": "查资产"}, ALLOWED, OTHER) == OTHER


def test_placeholder_to_other():
    """占位值(非本BU/拒识/其他/空)也归兜底桶——不能出现空桶/未分类。"""
    for v in ("非本BU", "拒识", "其他", ""):
        assert _business_type({"business_type": v}, ALLOWED, OTHER) == OTHER


def test_none_other_keeps_legacy():
    """other=None(测试/小数据路径)保留旧行为:占位值归空、不校验清单。"""
    assert _business_type({"business_type": "任意自创"}, None, None) == "任意自创"
    assert _business_type({"business_type": "非本BU"}, None, None) == ""


def test_assemble_row_applies_closed_set():
    judge = {"business_type": "我自己编的分类", "should_dispatch_to_bu": True, "answer_resolved": "yes"}
    row = assemble_row(_sample(), judge, ALLOWED, OTHER)
    assert row["j_intent"] == OTHER


def test_report_intents_strictly_closed():
    """端到端：一批含大量跑飞分类 + 拒识，最终 distinct 分类 ⊆ 清单 ∪ {兜底桶}，无空。"""
    cases = ["资产查询", "查资产", "资产查询类", "开户", "开户流程", "转账", "非本BU", "拒识", "编的X", ""]
    intents = set()
    for i, bt in enumerate(cases):
        j = {"business_type": bt, "should_dispatch_to_bu": True, "answer_resolved": "yes"}
        row = assemble_row(_sample(row_index=i), j, ALLOWED, OTHER)
        intents.add(row["j_intent"])
    assert "" not in intents, "闭集模式下不应有空分类"
    assert intents <= (ALLOWED | {OTHER}), f"出现清单外分类: {intents - (ALLOWED | {OTHER})}"
