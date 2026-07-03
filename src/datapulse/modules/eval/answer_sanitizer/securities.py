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


def _msg_context(parsed):
    """证券卡片统一入口：first.msgContext(可能是 JSON 字符串)解析成 dict。取不到返回 None。"""
    first = _first_dict(parsed)
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
    """证券·菜单卡（template=robotMenuItems）：机器人反问，列出候选问题让用户选。

    结构：msgInfo.msgContent = {template:"robotMenuItems", header:"...", menuItems:{questions:[...]}}。
    提取 = header + 各候选问题逐行。priority 比通用小安卡小，先于它匹配（它的 msgContent
    是对象而非纯文本，若被小安卡当文本处理会输出整坨 dict）。
    """
    name = "securities.robot_menu"
    bu_codes = ("securities",)
    priority = 5

    def _menu(self, parsed):
        mi = _msg_info(parsed)
        mc = mi.get("msgContent") if isinstance(mi, dict) else None
        mc = loads_maybe(mc)   # msgContent 可能是 JSON 字符串
        if isinstance(mc, dict) and mc.get("template") == "robotMenuItems":
            return mc
        return None

    def match(self, raw, parsed) -> bool:
        return self._menu(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        mc = self._menu(parsed)
        if mc is None:
            return None
        return _header_questions(mc.get("header"), dig(mc, "menuItems", "questions"))


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
    """证券·小安机器人渲染卡（含同花顺选股、列表卡片等变体）。

    统一入口是 first.msgContext.msgInfo；内部按已知字段路径逐个兜底提取正文，
    覆盖：msgContent（最常见）/ data.context / 同花顺 thsData / 列表卡片 list。
    """
    name = "securities.xiaoan_card"
    bu_codes = ("securities",)
    priority = 10

    def _msg_info(self, parsed):
        return _msg_info(parsed)

    def match(self, raw, parsed) -> bool:
        return self._msg_info(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        msg_info = self._msg_info(parsed)
        if msg_info is None:
            return None
        data = msg_info.get("data") or {}

        # 路径1：msgInfo.msgContent（小安机器人最常见）。仅当是纯文本时取；对象结构
        # （如 robotMenuItems 菜单卡）由更高优先级的专属解析器处理，这里跳过避免输出整坨 dict。
        content = msg_info.get("msgContent")
        if content and isinstance(content, str):
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
