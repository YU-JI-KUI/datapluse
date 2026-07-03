"""寿险专属答案解析器（bu_codes=("life",)）—— 模板/占位。

内网拿到寿险真实答案结构后，照下面模板填 match / parse 即可（一种答案结构一个类），
不用改入口和主流程。当前未注册任何真实解析器，寿险答案暂走通用层 + 原文兜底。

新增示例（复制改造）：
    @register
    class LifePolicyCardParser(AnswerParser):
        name = "life.policy_card"
        bu_codes = ("life",)
        priority = 10

        def match(self, raw, parsed) -> bool:
            first = parsed[0] if isinstance(parsed, list) and parsed else parsed
            return isinstance(first, dict) and "你的判据字段" in first

        def parse(self, raw, parsed) -> str | None:
            first = parsed[0] if isinstance(parsed, list) and parsed else parsed
            return strip_html(dig(first, "路径", "到", "正文"))   # 提取纯文本，取不到返回 None
"""
from __future__ import annotations

# 供内网新增解析器时直接使用（示例已在 docstring）：
from datapulse.modules.eval.answer_sanitizer.base import (  # noqa: F401
    AnswerParser,
    dig,
    loads_maybe,
    register,
    strip_html,
)

# ── 在此下方按模板新增寿险专属解析器 ──────────────────────────────────────────
