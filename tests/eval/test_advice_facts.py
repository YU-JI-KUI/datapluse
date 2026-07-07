"""build_facts 聚合口径测试。

保证：从 rows 重聚合出的五类建议料（漏收/误收、四归因分布、非本BU、逐分类）
口径正确——这是多专项建议能做「错误归因」的数据地基。
"""
from datapulse.modules.eval import advice_facts
from datapulse.modules.eval.evaluator import assemble_row


def _sample(idx, **kw):
    base = {
        "row_index": idx, "session": f"s{idx}", "turn": 1, "question": f"q{idx}",
        "context": [], "next_user_turn": "", "dispatched_intent": "",
        "dispatched_to_bu": True, "answer_text": f"ans{idx}",
        "gold": {"dispatch": "", "resolved": ""},
    }
    base.update(kw)
    return base


def _rows():
    """闭集分类 = {交易, 开户}。造覆盖各场景的 rows。"""
    allowed = {"交易", "开户"}
    other = "非证券业务"
    out = []
    idx = 0

    def add(judge, **kw):
        nonlocal idx
        out.append(assemble_row(_sample(idx, **kw), judge, allowed_intents=allowed, other=other))
        idx += 1

    # 交易：进漏斗、已解决
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "yes"})
    # 交易：进漏斗、未解决(信息不全)
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "no",
         "unresolved_cause": "信息不全"})
    # 开户：进漏斗、未解决(答非所问)
    add({"should_dispatch_to_bu": True, "business_type": "开户", "answer_resolved": "no",
         "unresolved_cause": "答非所问"})
    # 漏收：该分未分(should=T 但 actual=F)
    add({"should_dispatch_to_bu": True, "business_type": "交易", "answer_resolved": "unknown",
         "dispatch_reason": "应由本BU承接"}, dispatched_to_bu=False)
    # 误收：该拒未拒(should=F 但 actual=T)
    add({"should_dispatch_to_bu": False, "business_type": "非本BU", "answer_resolved": "no",
         "unresolved_cause": "分发错误", "dispatch_reason": "不该本BU承接"})
    # 非本BU：judge.business_type 原始值 == 非本BU（未进漏斗）
    add({"should_dispatch_to_bu": False, "business_type": "非本BU", "answer_resolved": "unknown"},
        dispatched_to_bu=False)
    return out


class _FakeBU:
    name = "证券"
    code = "securities"
    intents = {"交易": "", "开户": ""}


def test_build_facts_none_task():
    """无 task_id → 空 facts（走规则兜底）。"""
    facts = advice_facts.build_facts(None, _FakeBU())
    assert facts["dispatch_global"] is None
    assert facts["by_intent"] == {}


def test_build_facts_aggregation(monkeypatch):
    rows = _rows()
    # mock 逐批读回：一批返回全部
    monkeypatch.setattr(advice_facts._store, "iter_rows", lambda tid, batch_size=1000: iter([rows]))

    bu_dispatch = {"accuracy": 0.5, "miss_should_accept_but_rejected": 1,
                   "over_should_reject_but_accepted": 1}
    facts = advice_facts.build_facts("t1", _FakeBU(), bu_dispatch)

    # ① 分发：1 漏收 + 1 误收
    dg = facts["dispatch_global"]
    assert dg["miss_count"] == 1 and dg["over_count"] == 1
    assert len(dg["miss_examples"]) == 1 and len(dg["over_examples"]) == 1
    assert dg["miss_examples"][0]["dispatch_reason"] == "应由本BU承接"

    # ② 全局解决率：信息不全1 + 答非所问1 + 分发错误1
    dist = facts["resolved_global"]["unresolved_dist"]
    assert dist.get("信息不全") == 1
    assert dist.get("答非所问") == 1
    assert dist.get("分发错误") == 1

    # ③ 非本BU：judge.business_type=='非本BU' 有 2 条（误收那条 + 纯非本BU那条）
    assert facts["new_business"]["count"] == 2

    # ④⑤ 逐分类：交易 in_bu=2(1解决1未解决)、开户 in_bu=1
    交易 = facts["by_intent"]["交易"]
    assert 交易["in_bu"] == 2 and 交易["resolved_yes"] == 1
    assert 交易["unresolved_dist"].get("信息不全") == 1
    开户 = facts["by_intent"]["开户"]
    assert 开户["in_bu"] == 1 and 开户["unresolved_dist"].get("答非所问") == 1

    # 未分类不出现在建议料里
    assert "(未分类)" not in facts["by_intent"]
