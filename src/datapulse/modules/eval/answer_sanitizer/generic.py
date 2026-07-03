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
