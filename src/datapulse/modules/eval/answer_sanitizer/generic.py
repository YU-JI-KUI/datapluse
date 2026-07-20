"""通用答案解析器（所有 BU 通用，bu_codes=("*",)）。

跨 BU 都可能出现的答案结构。寿险等 BU 的 JSON 答案也可命中这里。
每个类 = 一种答案结构。
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


def _first(parsed):
    """取顶层 JSON 的首元素（list 取 [0]，否则原对象）。content_data 需要它返回内层 list。"""
    if isinstance(parsed, list):
        return parsed[0] if parsed else None
    return parsed


def _msg_info(parsed):
    """渲染卡统一入口：first.msgContext(可能是 JSON 字符串).msgInfo。取不到返回 None。"""
    first = first_dict(parsed)
    ctx = loads_maybe(first.get("msgContext")) if isinstance(first, dict) else None
    mi = ctx.get("msgInfo") if isinstance(ctx, dict) else None
    return mi if isinstance(mi, dict) else None


@register
class JumpPlatformParser(AnswerParser):
    """跳端卡（crossCardType=JUMPPLATFORM）：本 BU 拒识后给出的跨 App 跳转卡。

    结构：{crossCardType:"JUMPPLATFORM", title, desc}，真实日志外层多套一层数组。
    如寿险金管家里问题被拒识，返回跳转平安乐健康的卡片。
    输出固定话术，标明本 BU 不承接、引导用户改用目标 App。
    priority 小于 LlmApiResp（跳端卡也带 appType，须先于它匹配，否则被当 LLM 响应取空 msg）。
    """
    name = "generic.jump_platform"
    bu_codes = ("*",)
    priority = 5

    def match(self, raw, parsed) -> bool:
        first = first_dict(parsed)
        return isinstance(first, dict) and first.get("crossCardType") == "JUMPPLATFORM"

    def parse(self, raw, parsed) -> str | None:
        first = first_dict(parsed)
        if not isinstance(first, dict):
            return None
        title = strip_html(first.get("title") or "").strip()
        desc = strip_html(first.get("desc") or "").strip()
        if not title:
            return None
        tail = f"，{desc}" if desc else ""
        return f"本 BU 不承接，请使用【{title}】{tail}"


@register
class MsgContextCardParser(AnswerParser):
    """渲染卡通用提取（msgContext.msgInfo）：寿险/证券日志的主体结构。

    统一入口 first.msgContext.msgInfo，按已知路径逐个兜底取正文：
    msgContent（纯文本）/ data.content（最常见）/ data.context.data.content（多一层）。
    证券特有的 thsData 同花顺、list 列表卡片由证券专属解析器处理（专属先于通用）。
    """
    name = "generic.msgcontext_card"
    bu_codes = ("*",)
    priority = 30

    def match(self, raw, parsed) -> bool:
        return _msg_info(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        mi = _msg_info(parsed)
        if mi is None:
            return None
        data = mi.get("data") or {}

        # 路径1：msgContent 纯文本（对象结构如菜单卡由专属解析器处理，这里只取字符串）
        content = mi.get("msgContent")
        if content and isinstance(content, str):
            return strip_html(content)

        # 路径2a：data.content（最常见，content 直接挂 data 下）
        content = dig(data, "content")
        if content:
            return strip_html(content)

        # 路径2b：data.context.data.content（多一层 context 的变体）
        content = dig(data, "context", "data", "content")
        if content:
            return strip_html(content)

        return None


@register
class BenefitCardParser(AnswerParser):
    """权益领取结果卡（catalogId + data.benefits）：领权益后返回的结果卡。

    结构：first.catalogId 存在，data.benefits=[{benefitName:"..."}]，
    data.cardHead.mainTitle 为标题。提取 = 标题 + 各权益名，以空格拼接为一行。
    """
    name = "generic.benefit_card"
    bu_codes = ("*",)
    priority = 8

    def _card(self, parsed):
        first = first_dict(parsed)
        if not (isinstance(first, dict) and first.get("catalogId")):
            return None
        data = first.get("data")
        benefits = data.get("benefits") if isinstance(data, dict) else None
        return data if isinstance(benefits, list) and benefits else None

    def match(self, raw, parsed) -> bool:
        return self._card(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._card(parsed)
        if data is None:
            return None
        lines = []
        title = strip_html(dig(data, "cardHead", "mainTitle") or "")
        if title:
            lines.append(title)
        for b in data.get("benefits", []):
            name = strip_html(b.get("benefitName") or "") if isinstance(b, dict) else ""
            if name:
                lines.append(name)
        return " ".join(lines) or None


@register
class AgreementCardParser(AnswerParser):
    """协议同意卡（agreements 数组）：首次使用/协议更新时弹出的协议列表。

    结构：{agreements:[{title:"...", version:"..."}], isUpdate:0}，真实日志外层
    常多套一层数组 [[{...}]]。非对用户问题的回答，而是让用户勾选同意的协议弹窗。
    输出协议标题，标明需用户同意（供 Judge 判未承接）。
    """
    name = "generic.agreement_card"
    bu_codes = ("*",)
    priority = 9

    def _agreements(self, parsed):
        first = first_dict(parsed)
        ags = first.get("agreements") if isinstance(first, dict) else None
        return ags if isinstance(ags, list) and ags else None

    def match(self, raw, parsed) -> bool:
        return self._agreements(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        ags = self._agreements(parsed)
        if ags is None:
            return None
        titles = [strip_html(a.get("title") or "") for a in ags if isinstance(a, dict) and a.get("title")]
        if not titles:
            return None
        return "请阅读并同意以下协议：" + "、".join(titles)


@register
class ContentDataParser(AnswerParser):
    """文本回复：顶层 list → first[0].content_data。

    content_data 为 jgj_ 前缀的转人工标识串（金管家转人工工单号）时，正文对模型无意义，
    统一归一为「金管家转人工」，让 Judge 识别为转人工而非正常文本回复。
    """
    name = "generic.content_data"
    bu_codes = ("*",)
    priority = 10

    def _inner(self, parsed):
        first = _first(parsed)
        inner = dig(first, 0) if isinstance(first, list) else None
        return inner if isinstance(inner, dict) and "content_data" in inner else None

    def match(self, raw, parsed) -> bool:
        return self._inner(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        inner = self._inner(parsed)
        if not inner:
            return None
        content = strip_html(inner.get("content_data") or "")
        if content.startswith("jgj_"):
            return "金管家转人工"
        return content


@register
class ServiceNavCardParser(AnswerParser):
    """服务导航卡（title + subTitle + tabs.funcList 功能菜单）：如「平安救急服务」导航页。

    结构：first 含非空 tabs 数组、每个 tab 有 funcList（功能菜单）。跨 BU 通用。
    只取 title + subTitle 概括，功能菜单跨 tab 大量重复、对判定无益，不进正文。
    """
    name = "generic.service_nav"
    bu_codes = ("*",)
    priority = 12

    def _card(self, parsed):
        first = first_dict(parsed)
        if not isinstance(first, dict):
            return None
        tabs = first.get("tabs")
        has_func = isinstance(tabs, list) and any(
            isinstance(t, dict) and t.get("funcList") for t in tabs
        )
        return first if has_func else None

    def match(self, raw, parsed) -> bool:
        return self._card(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        first = self._card(parsed)
        if first is None:
            return None
        lines = []
        for key in ("title", "subTitle"):
            v = strip_html(first.get(key) or "")
            if v:
                lines.append(v)
        return " ".join(lines) or None


@register
class LlmApiRespParser(AnswerParser):
    """LLM API 响应：first.appType 存在 → 取 msg / standardQuestion。"""
    name = "generic.llm_api"
    bu_codes = ("*",)
    priority = 20

    def match(self, raw, parsed) -> bool:
        first = first_dict(parsed)
        return isinstance(first, dict) and "appType" in first

    def parse(self, raw, parsed) -> str | None:
        first = first_dict(parsed)
        if not isinstance(first, dict):
            return None
        v = first.get("msg") or first.get("standardQuestion") or ""
        return strip_html(v) if v else None
