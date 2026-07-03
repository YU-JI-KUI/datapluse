"""证券专属答案解析器（bu_codes=("securities",)）。

证券日志特有的渲染卡结构。专属解析器优先于通用解析器。
"""
from __future__ import annotations

from datapulse.modules.eval.answer_sanitizer.base import (
    AnswerParser,
    dig,
    first_dict,
    loads_maybe,
    register,
    strip_html,
)


def _msg_context(parsed):
    """证券卡片统一入口：first.msgContext(可能是 JSON 字符串)解析成 dict。取不到返回 None。"""
    first = first_dict(parsed)
    if first is None:
        return None
    inner = loads_maybe(first.get("msgContext"))
    return inner if isinstance(inner, dict) else None


def _msg_info(parsed):
    """证券卡片 msgContext.msgInfo。取不到返回 None。"""
    ctx = _msg_context(parsed)
    mi = ctx.get("msgInfo") if isinstance(ctx, dict) else None
    return mi if isinstance(mi, dict) else None


def _header_questions(header, questions) -> str | None:
    """把「header + 候选问题列表」格式化为：header 一行 + 每个问题一行。空则 None。"""
    lines = []
    h = strip_html(header or "")
    if h:
        lines.append(h)
    lines += [strip_html(q) for q in (questions or []) if q]
    return "\n".join(lines) or None


@register
class RobotMenuItemsParser(AnswerParser):
    """证券·菜单卡（msgContext.template=robotMenuItems）：机器人反问，列出候选问题让用户选。

    结构：msgContext.template=="robotMenuItems"，header 与 questions 都在
    msgInfo.menuItems 内（msgContent 常是空串）。提取 = header + 各候选问题逐行。
    priority 小于小安卡，先匹配。
    """
    name = "securities.robot_menu"
    bu_codes = ("securities",)
    priority = 5

    def _menu(self, parsed):
        ctx = _msg_context(parsed)
        if not (isinstance(ctx, dict) and ctx.get("template") == "robotMenuItems"):
            return None
        mi = loads_maybe(dig(ctx, "msgInfo", "menuItems"))
        return mi if isinstance(mi, dict) else None

    def match(self, raw, parsed) -> bool:
        return self._menu(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        mi = self._menu(parsed)
        if mi is None:
            return None
        return _header_questions(mi.get("header"), mi.get("questions"))


@register
class RobotTextAnswerParser(AnswerParser):
    """证券·关联问卡（msgContext.template=robotTextAnswer）：列出关联问题让用户确认。

    结构：msgContext.template=="robotTextAnswer"，问题在 msgInfo.relatedQuestions
    ={header:"...", questions:[...]}（注意 relatedQuestions 直接挂 msgInfo 下，无 msgContent 层）。
    提取 = header + 各相关问题逐行。priority 小于小安卡，先匹配。
    """
    name = "securities.robot_text_answer"
    bu_codes = ("securities",)
    priority = 6

    def _related(self, parsed):
        ctx = _msg_context(parsed)
        if not (isinstance(ctx, dict) and ctx.get("template") == "robotTextAnswer"):
            return None
        rq = loads_maybe(dig(ctx, "msgInfo", "relatedQuestions"))
        return rq if isinstance(rq, dict) else None

    def match(self, raw, parsed) -> bool:
        return self._related(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        rq = self._related(parsed)
        if rq is None:
            return None
        return _header_questions(rq.get("header"), rq.get("questions"))


@register
class XiaoAnCardParser(AnswerParser):
    """证券·小安机器人特有渲染卡：同花顺智能选股 thsData、列表卡片 list。

    统一入口 first.msgContext.msgInfo.data。基础的 msgContent/data.content 由通用
    MsgContextCardParser 处理，这里只认证券日志特有的两种结构。
    """
    name = "securities.xiaoan_card"
    bu_codes = ("securities",)
    priority = 10

    def _data(self, parsed):
        mi = _msg_info(parsed)
        return (mi.get("data") or {}) if isinstance(mi, dict) else {}

    def match(self, raw, parsed) -> bool:
        return self.parse(raw, parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._data(parsed)

        # 同花顺智能选股 thsData：answer[0].txt[0].content(又是 JSON 串)→ components[0].data.content
        ths = data.get("thsData") or {}
        if ths:
            content_json = dig(ths, "answer", 0, "txt", 0, "content")
            comp_content = dig(loads_maybe(content_json), "components", 0, "data", "content")
            if comp_content:
                return strip_html(comp_content)
            reply = ths.get("reply")   # thsData.reply 兜底
            if reply:
                return strip_html(reply)

        # 列表卡片 data.list[].data.content（取含 <p> 的项）
        for item in (data.get("list") or []):
            c = dig(item, "data", "content")
            if c and "<p>" in str(c):
                return strip_html(c)

        return None
