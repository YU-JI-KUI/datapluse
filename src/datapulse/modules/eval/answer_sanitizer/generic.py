"""通用答案解析器（所有 BU 通用，bu_codes=("*",)）。

跨 BU 都可能出现的答案结构。寿险等 BU 的 JSON 答案也可命中这里。
每个类 = 一种答案结构。
"""
from __future__ import annotations

from datapulse.modules.eval.answer_sanitizer.base import (
    AnswerParser,
    dig,
    register,
    strip_html,
)


def _first(parsed):
    """取顶层 JSON 的首元素（list 取 [0]，否则原对象）。"""
    if isinstance(parsed, list):
        return parsed[0] if parsed else None
    return parsed


@register
class JumpPlatformParser(AnswerParser):
    """跳端卡（crossCardType=JUMPPLATFORM）：本 BU 拒识后给出的跨 App 跳转卡。

    结构：顶层 list，first.crossCardType=="JUMPPLATFORM"，含 title/desc。
    如寿险金管家里问题被拒识，返回跳转平安乐健康的卡片。
    输出固定话术，标明本 BU 不承接、引导用户改用目标 App。
    priority 小于 LlmApiResp（跳端卡也带 appType，须先于它匹配，否则被当 LLM 响应取空 msg）。
    """
    name = "generic.jump_platform"
    bu_codes = ("*",)
    priority = 5

    def match(self, raw, parsed) -> bool:
        first = _first(parsed)
        return isinstance(first, dict) and first.get("crossCardType") == "JUMPPLATFORM"

    def parse(self, raw, parsed) -> str | None:
        first = _first(parsed)
        title = strip_html(first.get("title") or "").strip()
        desc = strip_html(first.get("desc") or "").strip()
        if not title:
            return None
        tail = f"，{desc}" if desc else ""
        return f"本 BU 不承接，请使用【{title}】{tail}"


@register
class ContentDataParser(AnswerParser):
    """文本回复：顶层 list → first[0].content_data。"""
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
        return strip_html(inner.get("content_data") or "") if inner else None


@register
class LlmApiRespParser(AnswerParser):
    """LLM API 响应：first.appType 存在 → 取 msg / standardQuestion。"""
    name = "generic.llm_api"
    bu_codes = ("*",)
    priority = 20

    def match(self, raw, parsed) -> bool:
        first = _first(parsed)
        return isinstance(first, dict) and "appType" in first

    def parse(self, raw, parsed) -> str | None:
        first = _first(parsed)
        v = first.get("msg") or first.get("standardQuestion") or ""
        return strip_html(v) if v else None
