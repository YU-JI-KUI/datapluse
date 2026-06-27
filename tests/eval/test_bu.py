"""BU 领域知识层测试:注册表、意图体系、Judge 按 BU 注入。"""

from datapulse.modules.eval.bu.registry import DEFAULT_BU, get_bu, list_bus
from datapulse.modules.eval.judge import build_messages
from datapulse.modules.eval.llm.mock_judge import mock_judge


def test_registry_has_securities_and_life():
    codes = {b["code"] for b in list_bus()}
    assert "securities" in codes
    assert "life" in codes


def test_get_bu_fallback_to_default():
    """未知 code 回默认 BU(证券),不报错。"""
    assert get_bu("不存在的BU").code == DEFAULT_BU
    assert get_bu(None).code == DEFAULT_BU


def test_securities_and_life_have_different_intents():
    sec = get_bu("securities")
    life = get_bu("life")
    assert "查持仓" in sec.intents          # 证券独有
    assert "理赔咨询" in life.intents        # 寿险独有
    assert "查持仓" not in life.intents
    assert "理赔咨询" not in sec.intents


def test_build_messages_uses_bu_intents():
    """Judge prompt 里的意图清单 + 专家身份随 BU 变化。"""
    sample = {"question": "住院了怎么理赔", "context": [], "dispatched_intent": "理赔助手"}
    life_msgs = build_messages(sample, get_bu("life"))
    life_prompt = life_msgs[1]["content"]
    assert "理赔咨询" in life_prompt          # 寿险意图在 prompt 里
    assert "查持仓" not in life_prompt        # 证券意图不在
    assert "寿险" in life_msgs[0]["content"]  # 专家身份是寿险


def test_mock_judge_respects_bu_rules():
    """寿险 mock 用寿险规则:住院→理赔咨询。"""
    life = get_bu("life")
    j = mock_judge({"question": "住院了怎么理赔", "dispatched_intent": "理赔助手",
                    "answer_text": "理赔流程如下", "next_user_turn": None}, life)
    assert j["intent_pred"] == "理赔咨询"
    assert j["business_type"] == "理赔咨询"


def test_sample_filenames_configured():
    """每个 BU 都配了样例文件名,供 /eval/sample 使用。"""
    for code in ("securities", "life"):
        bu = get_bu(code)
        assert bu.sample_calib and bu.sample_prod


def test_matches_dispatch_uses_aliases():
    """分发BU值匹配:用 dispatch_aliases 精确相等,与展示名解耦。"""
    sec = get_bu("securities")
    assert sec.matches_dispatch("证券") is True
    assert sec.matches_dispatch("证券业务") is True      # 别名也认
    assert sec.matches_dispatch("寿险") is False         # 别的BU不认
    assert sec.matches_dispatch("") is False             # 空=拒识
    assert sec.matches_dispatch(None) is False
    # 寿险不会把"证券"误判成自己
    assert get_bu("life").matches_dispatch("证券") is False


def test_matches_dispatch_fallback_to_name():
    """未配 aliases 时回退到 name 子串匹配(兼容旧数据)。"""
    from datapulse.modules.eval.bu.base import BUConfig
    bu = BUConfig(code="x", name="产险", description="")  # 无 aliases
    assert bu.matches_dispatch("产险业务线") is True       # 子串
    assert bu.matches_dispatch("证券") is False
