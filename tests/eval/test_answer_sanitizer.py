"""答案净化器测试：多路径提取（证券小安/同花顺/列表卡片 + 通用文本回复/LLM-API）、
去 HTML、容错回退、幂等。"""
import json

from datapulse.modules.eval.answer_sanitizer import sanitize_answer


def _wrap_msgcontext(msg_context: dict) -> str:
    """模拟真实日志：顶层 list，msgContext 是嵌套 JSON 字符串。"""
    return json.dumps([{"msgContext": json.dumps(msg_context, ensure_ascii=False)}],
                      ensure_ascii=False)


# ── 证券专属路径 ──────────────────────────────────────────────────────────────

def test_securities_msg_content():
    raw = _wrap_msgcontext({
        "msgInfo": {"msgContent": "尊敬的客户，您的总资产为 <b>52万</b>。"},
        "relatedQuestions": {"questions": ["撤单方式"]},
    })
    out = sanitize_answer(raw, "securities")
    assert out == "尊敬的客户，您的总资产为 52万。"   # 取 msgContent 且去 HTML 标签
    assert "relatedQuestions" not in out


def test_securities_data_context_content():
    raw = _wrap_msgcontext({
        "msgInfo": {"data": {"context": {"data": {"content": "<p>持仓查询结果</p>"}}}},
    })
    assert sanitize_answer(raw, "securities") == "持仓查询结果"


def test_securities_ths_select_stock():
    inner_txt = json.dumps({"components": [{"data": {"content": "<p>主力净流入前三：A/B/C</p>"}}]},
                           ensure_ascii=False)
    raw = _wrap_msgcontext({
        "msgInfo": {"data": {"thsData": {"answer": [{"txt": [{"content": inner_txt}]}]}}},
    })
    assert sanitize_answer(raw, "securities") == "主力净流入前三：A/B/C"


def test_securities_list_card():
    raw = _wrap_msgcontext({
        "msgInfo": {"data": {"list": [{"data": {"content": "<p>开户营业部：深圳分公司</p>"}}]}},
    })
    assert sanitize_answer(raw, "securities") == "开户营业部：深圳分公司"


def test_securities_robot_menu_items():
    """菜单卡 template=robotMenuItems：header + 各候选问题逐行。"""
    raw = _wrap_msgcontext({
        "msgInfo": {"msgContent": {
            "template": "robotMenuItems",
            "header": "请问您是想咨询以下哪个问题：",
            "menuItems": {"questions": ["交易股票有什么费用", "交易基金有什么费用", "交易债券有什么费用"]},
        }},
    })
    assert sanitize_answer(raw, "securities") == (
        "请问您是想咨询以下哪个问题：\n交易股票有什么费用\n交易基金有什么费用\n交易债券有什么费用"
    )


def test_securities_robot_text_answer():
    """关联问卡 msgContext.template=robotTextAnswer：header + relatedQuestions.questions 逐行。"""
    ctx = {
        "template": "robotTextAnswer",
        "msgInfo": {"relatedQuestions": {
            "footer": "",
            "questions": ["什么是当日委托", "撤单的介绍", "受理成功的订单介绍"],
            "header": "您咨询的是否为以下问题：",
        }},
    }
    raw = json.dumps([{"msgContext": json.dumps(ctx, ensure_ascii=False)}], ensure_ascii=False)
    assert sanitize_answer(raw, "securities") == (
        "您咨询的是否为以下问题：\n什么是当日委托\n撤单的介绍\n受理成功的订单介绍"
    )


# ── 通用路径（所有 BU，寿险也能走）────────────────────────────────────────────

def test_generic_jump_platform():
    """跳端卡 crossCardType=JUMPPLATFORM：本 BU 拒识 → 固定话术引导跳转目标 App。"""
    raw = json.dumps([{
        "crossCardType": "JUMPPLATFORM",
        "appType": "jkbx",          # 也带 appType，须先于 LlmApiResp 命中
        "title": "平安乐健康",
        "desc": "平安乐健康为您提供更完整的服务",
    }], ensure_ascii=False)
    assert sanitize_answer(raw, "life") == (
        "本 BU 不承接，请使用【平安乐健康】，平安乐健康为您提供更完整的服务"
    )


def test_generic_text_reply():
    # A1：嵌套 list → content_data
    raw = json.dumps([[{"content_data": "您的保单已生效。"}]], ensure_ascii=False)
    assert sanitize_answer(raw, "life") == "您的保单已生效。"


def test_generic_llm_api():
    # B1：appType + msg
    raw = json.dumps([{"appType": "qa", "msg": "缴费成功，<span>感谢</span>。"}], ensure_ascii=False)
    assert sanitize_answer(raw, "life") == "缴费成功，感谢。"


# ── 容错 / 幂等 ───────────────────────────────────────────────────────────────

def test_non_json_kept():
    assert sanitize_answer("一段普通纯文本答案", "securities") == "一段普通纯文本答案"


def test_unextractable_json_kept():
    # 是 JSON 但不匹配任何路径 → 保留原文，不丢数据
    raw = json.dumps([{"unknown": "结构"}], ensure_ascii=False)
    assert sanitize_answer(raw, "securities") == raw


def test_idempotent():
    # 净化后的纯文本再跑一次不变（展示净化会重复调用）
    raw = _wrap_msgcontext({"msgInfo": {"msgContent": "结果文本"}})
    once = sanitize_answer(raw, "securities")
    assert sanitize_answer(once, "securities") == once == "结果文本"


def test_empty_and_nonstr():
    assert sanitize_answer("", "securities") == ""
    assert sanitize_answer(None, "securities") is None
