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

import re

# 供内网新增解析器时直接使用（示例已在 docstring）：
from datapulse.modules.eval.answer_sanitizer.base import (  # noqa: F401
    AnswerParser,
    dig,
    first_dict,
    loads_maybe,
    register,
    strip_html,
)

# 块级标签作分段点：多段 <p>/<br>/<div> 直接拼会把句子糊在一起，按块拆开后用空格分隔
_BLOCK_RE = re.compile(r"</p>|<br\s*/?>|</div>|</li>", re.I)


def _html_to_lines(html) -> str | None:
    """把多段块级 HTML 拆成多段纯文本（</p>/<br>/</div>/</li> 作分隔）并以空格拼接，空则 None。"""
    parts = [strip_html(seg) for seg in _BLOCK_RE.split(str(html or ""))]
    lines = [p for p in parts if p]
    return " ".join(lines) or None

# ── 在此下方按模板新增寿险专属解析器 ──────────────────────────────────────────


def _card_data(parsed):
    """金管家 SuperAgent 卡片统一入口：first.card_content.data。取不到返回 None。"""
    first = first_dict(parsed)
    data = dig(first, "card_content", "data") if isinstance(first, dict) else None
    return data if isinstance(data, dict) else None


def _lead_and_options(lead, options) -> str | None:
    """把「正文 + data.options[].name 推荐问题」以空格拼接成一行（正文 + 各推荐问题）。空则 None。"""
    lines = []
    text = strip_html(lead or "")
    if text:
        lines.append(text)
    for opt in (options or []):
        name = strip_html(opt.get("name") or "") if isinstance(opt, dict) else ""
        if name:
            lines.append(name)
    return " ".join(lines) or None


@register
class LifeFaqCardParser(AnswerParser):
    """寿险·FAQ 知识库卡（金管家 askBOB）：命中知识库后返回正文 + 关联问题。

    结构：顶层 [[{...}]]，主体在 card_content.data（带 faqID/answerFrom/kbId 等
    知识库字段）。正文取 gbdData.content，兜底 card_content.data.detail[0].content；
    关联问题在 card_content.data.options[].name。提取 = 正文 + 各关联问题，以空格拼接为一行。
    """
    name = "life.faq_card"
    bu_codes = ("life",)
    priority = 10

    def _data(self, parsed):
        data = _card_data(parsed)
        # 知识库字段做判据，避免误吞其它带 card_content 的结构
        return data if isinstance(data, dict) and data.get("faqID") else None

    def match(self, raw, parsed) -> bool:
        return self._data(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._data(parsed)
        if data is None:
            return None
        first = first_dict(parsed)
        content = dig(first, "gbdData", "content") or dig(data, "detail", 0, "content")
        return _lead_and_options(content, data.get("options"))


@register
class LifePolicyListCardParser(AnswerParser):
    """寿险·保单列表卡（金管家）：查保单后返回名下保单清单。

    结构：card_content.data.policyInfos 为非空数组（区别于 FAQ 卡的 faqID）。
    抬头取 data.text（如「帮您找到6份保单」），每份保单一行 = 险种名 + 投保日。
    保单号 polNo 是长数字串对判定无益，不进正文。
    """
    name = "life.policy_list_card"
    bu_codes = ("life",)
    priority = 11

    def _policies(self, parsed):
        data = _card_data(parsed)
        pols = data.get("policyInfos") if isinstance(data, dict) else None
        return data if isinstance(pols, list) and pols else None

    def match(self, raw, parsed) -> bool:
        return self._policies(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._policies(parsed)
        if data is None:
            return None
        lines = []
        head = strip_html(data.get("text") or "")
        if head:
            lines.append(head)
        for p in data.get("policyInfos", []):
            if not isinstance(p, dict):
                continue
            plan = strip_html(p.get("planName") or "")
            date = strip_html(p.get("appDate") or "")
            row = " ".join(x for x in (plan, date) if x)
            if row:
                lines.append(row)
        return " ".join(lines) or None


@register
class LifeServiceFlowCardParser(AnswerParser):
    """寿险·服务流程卡（金管家一键办理）：把用户导向某业务办理流程，无文本正文。

    结构：gbdData.oneKeyServiceName（兜底 agentName）为服务名，card_content 无 data
    节点（区别于 FAQ 卡/保单列表卡）。输出「为您转接【服务名】服务」，让 Judge 识别为已承接。
    """
    name = "life.service_flow_card"
    bu_codes = ("life",)
    priority = 12

    def _service_name(self, parsed):
        first = first_dict(parsed)
        if not isinstance(first, dict):
            return None
        name = dig(first, "gbdData", "oneKeyServiceName") or dig(first, "gbdData", "agentName")
        return strip_html(name or "") or None

    def match(self, raw, parsed) -> bool:
        return self._service_name(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        name = self._service_name(parsed)
        return f"为您转接【{name}】服务" if name else None


@register
class LifeMultiRoundCardParser(AnswerParser):
    """寿险·多轮文本卡（金管家 COMMON_MULTIPLE）：给出正文并用胶囊引导下一轮追问。

    结构：card_content.data.answer 为正文，追问选项在 data.capsule[].label
    （区别于澄清卡的 msg + options[].name、FAQ 卡的 faqID）。
    提取 = 正文 + 各胶囊 label，以空格拼接为一行。
    """
    name = "life.multi_round_card"
    bu_codes = ("life",)
    priority = 14

    def _data(self, parsed):
        data = _card_data(parsed)
        return data if isinstance(data, dict) and data.get("answer") and data.get("capsule") else None

    def match(self, raw, parsed) -> bool:
        return self._data(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._data(parsed)
        if data is None:
            return None
        lines = []
        text = strip_html(data.get("answer") or "")
        if text:
            lines.append(text)
        for cap in data.get("capsule", []):
            label = strip_html(cap.get("label") or "") if isinstance(cap, dict) else ""
            if label:
                lines.append(label)
        return " ".join(lines) or None


@register
class LifeFaqAnswerCardParser(AnswerParser):
    """寿险·FAQ 答案卡（H5 访客 rankType=FAQ）：命中知识库后返回 HTML 正文。

    结构：card_content.data.answerList 为非空数组、data.rankType="FAQ"，正文在
    data.answer（多段 <p> HTML）。区别于 FAQ 知识库卡（keys faqID/options）、
    多轮卡（keys answer+capsule）。提取 = data.answer 按块级标签拆行的纯文本。
    """
    name = "life.faq_answer_card"
    bu_codes = ("life",)
    priority = 15

    def _data(self, parsed):
        data = _card_data(parsed)
        if not isinstance(data, dict):
            return None
        answer_list = data.get("answerList")
        ok = isinstance(answer_list, list) and answer_list and data.get("rankType") == "FAQ"
        return data if ok else None

    def match(self, raw, parsed) -> bool:
        return self._data(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._data(parsed)
        if data is None:
            return None
        answer = data.get("answer") or dig(data, "answerList", 0, "display")
        return _html_to_lines(answer)


@register
class LifeClarifyCardParser(AnswerParser):
    """寿险·意图不明澄清卡（金管家 LLM 兜底反问）：让用户从推荐问题里选。

    结构：card_content.data.msg 为澄清话术（labelId=llm_recommend），推荐问题在
    data.options[].name（无 faqID，区别于 FAQ 卡）。提取 = 澄清话术 + 各推荐问题，以空格拼接为一行。
    """
    name = "life.clarify_card"
    bu_codes = ("life",)
    priority = 13

    def _data(self, parsed):
        data = _card_data(parsed)
        return data if isinstance(data, dict) and data.get("msg") else None

    def match(self, raw, parsed) -> bool:
        return self._data(parsed) is not None

    def parse(self, raw, parsed) -> str | None:
        data = self._data(parsed)
        if data is None:
            return None
        return _lead_and_options(data.get("msg"), data.get("options"))
