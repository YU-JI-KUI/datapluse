"""证券专属答案解析器（bu_codes=("securities",)）。

证券日志特有的渲染卡结构。专属解析器优先于通用解析器。
"""
from __future__ import annotations

from datapulse.modules.eval.answer_sanitizer.base import (
    AnswerParser,
    dig,
    loads_maybe,
    register,
    strip_html,
)


def _first_dict(parsed):
    """取顶层首元素，且必须是 dict（证券卡片都是对象）。"""
    first = parsed[0] if isinstance(parsed, list) and parsed else parsed
    return first if isinstance(first, dict) else None


@register
class XiaoAnCardParser(AnswerParser):
    """证券·小安机器人渲染卡（含同花顺选股、列表卡片等变体）。

    统一入口是 first.msgContext.msgInfo；内部按已知字段路径逐个兜底提取正文，
    覆盖：msgContent（最常见）/ data.context / 同花顺 thsData / 列表卡片 list。
    """
    name = "securities.xiaoan_card"
    bu_codes = ("securities",)
    priority = 10

    def _msg_info(self, parsed):
        first = _first_dict(parsed)
        if first is None:
            return None
        inner = loads_maybe(first.get("msgContext"))
        if not isinstance(inner, dict):
            return None
        mi = inner.get("msgInfo")
        return mi if isinstance(mi, dict) else None

    def match(self, raw, parsed) -> bool:
        return self._msg_info(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        msg_info = self._msg_info(parsed)
        if msg_info is None:
            return None
        data = msg_info.get("data") or {}

        # 路径1：msgInfo.msgContent（小安机器人最常见）
        content = msg_info.get("msgContent")
        if content:
            return strip_html(content)

        # 路径2：msgInfo.data.context.data.content
        content = dig(data, "context", "data", "content")
        if content:
            return strip_html(content)

        # 路径3：同花顺智能选股 thsData
        ths = data.get("thsData") or {}
        if ths:
            # thsData.answer[0].txt[0].content（content 又是 JSON 字符串）→ components[0].data.content
            content_json = dig(ths, "answer", 0, "txt", 0, "content")
            comp_content = dig(loads_maybe(content_json), "components", 0, "data", "content")
            if comp_content:
                return strip_html(comp_content)
            reply = ths.get("reply")   # thsData.reply 兜底
            if reply:
                return strip_html(reply)

        # 路径4：msgInfo.data.list[].data.content（列表卡片，取含 <p> 的项）
        for item in (data.get("list") or []):
            c = dig(item, "data", "content")
            if c and "<p>" in str(c):
                return strip_html(c)

        return None
