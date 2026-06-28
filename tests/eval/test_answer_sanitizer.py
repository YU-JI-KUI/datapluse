"""答案净化器测试：规则匹配 / msgContent 提取 / 容错回退。"""
import json

from datapulse.modules.eval.answer_sanitizer import sanitize_answer

# 模拟真实日志答案：顶层 list，msgContext 是嵌套 JSON 字符串，含 sema_bot 与 msgContent
_MSG_CONTEXT = json.dumps({
    "template": "robotTextAnswer",
    "msgInfo": {"msgContent": "尊敬的客户，您好！您可以通过以下步骤撤销策略交易订单……"},
    "relatedQuestions": {"questions": ["策略交易单数量限制", "委托撤单方式"]},
    "extraInfo": {"sema_bot": "小安", "bot_info": {"raw_text": "策略交易单修改"}},
}, ensure_ascii=False)

_SECURITIES_XIAOAN = json.dumps([{
    "roomMark": "person",
    "msgType": "aat_text",
    "msgContext": _MSG_CONTEXT,   # 注意：值是 JSON 字符串（需下钻）
    "msgId": "abc",
}], ensure_ascii=False)


def test_securities_xiaoan_keeps_only_msg_content():
    out = sanitize_answer(_SECURITIES_XIAOAN, "securities")
    assert out == "尊敬的客户，您好！您可以通过以下步骤撤销策略交易订单……"
    # 相似问/模板结构被丢弃
    assert "relatedQuestions" not in out
    assert "委托撤单方式" not in out
    assert "sema_bot" not in out


def test_other_bu_not_affected():
    # 非证券 BU：即使含小安结构也不处理（规则只对证券生效）
    assert sanitize_answer(_SECURITIES_XIAOAN, "life") == _SECURITIES_XIAOAN


def test_securities_without_xiaoan_untouched():
    # 证券但非小安机器人：不匹配规则，原样返回
    other = json.dumps([{"msgContext": json.dumps(
        {"msgInfo": {"msgContent": "x"}, "extraInfo": {"sema_bot": "其他bot"}},
        ensure_ascii=False)}], ensure_ascii=False)
    assert sanitize_answer(other, "securities") == other


def test_non_json_answer_untouched():
    # 普通文本答案：解析失败，原样返回
    assert sanitize_answer("这是一段普通的纯文本答案", "securities") == "这是一段普通的纯文本答案"


def test_empty_answer():
    assert sanitize_answer("", "securities") == ""


def test_match_but_no_msg_content_falls_back():
    # 命中小安但取不到 msgContent → 原样返回（不丢数据）
    raw = json.dumps([{"msgContext": json.dumps(
        {"extraInfo": {"sema_bot": "小安"}}, ensure_ascii=False)}], ensure_ascii=False)
    assert sanitize_answer(raw, "securities") == raw
