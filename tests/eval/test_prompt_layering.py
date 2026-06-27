"""提示词按 BU 分层:<bu_code>/ 优先,_default/ 回退。"""
from datapulse.modules.eval.bu.life_insurance import LIFE
from datapulse.modules.eval.bu.securities import SECURITIES as SEC
from datapulse.modules.eval.judge import build_messages
from datapulse.modules.eval.prompt_loader import load_bu_prompt


def _sample():
    return {
        "question": "查持仓", "context": [], "answer_text": "...",
        "next_user_turn": "", "dispatched_to_bu": True,
    }


def test_bu_specific_overrides_default():
    # 证券有专属 task_dispatch.md → 用证券版(含 SOP 字样)
    sec_dispatch = load_bu_prompt("securities", "task_dispatch.md")
    assert "证券承接 SOP" in sec_dispatch


def test_falls_back_to_default():
    # 寿险无专属 task_dispatch.md → 回退通用版(不含证券 SOP)
    life_dispatch = load_bu_prompt("life", "task_dispatch.md")
    assert "证券承接 SOP" not in life_dispatch
    assert "should_dispatch_to_bu" in life_dispatch


def test_unknown_bu_uses_default():
    # 不存在的 BU 目录也安全回退到 _default
    out = load_bu_prompt("nonexistent_bu", "task_resolved.md")
    assert "answer_resolved" in out


def test_build_messages_picks_bu_prompts():
    # 端到端:证券 prompt 含专属 SOP,寿险不含
    u_sec = build_messages(_sample(), SEC)[1]["content"]
    u_life = build_messages(_sample(), LIFE)[1]["content"]
    assert "证券承接 SOP" in u_sec
    assert "证券承接 SOP" not in u_life
    # 两者都含通用维度(回退或共用)
    for u in (u_sec, u_life):
        assert "answer_resolved" in u and "business_type" in u
