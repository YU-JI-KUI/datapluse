"""答案净化器：把 Excel 原始答案（常是整坨 JSON 渲染卡）提取成人类可读正文，
再喂给 Judge / 在详情页展示。原封不动的 JSON 会让模型误判、也让人难读。

分两层规则（按序匹配，命中即用其 transform，都不命中保留原文）：
  - 通用层（所有 BU）：去 HTML 标签、文本回复(content_data)、LLM API 响应(msg)。
  - 证券专属层：小安机器人 msgContent、同花顺选股、列表卡片等证券特有结构。
寿险等其它 BU 的 JSON 答案也能走通用层。新增场景 = 加一条 SanitizeRule，不改主流程。

接入点：pipeline.build_sample（喂模型）/ judge 上下文 / eval_engine 展示净化。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SanitizeRule:
    name: str                              # 规则名（日志/排查用）
    match: Callable[[str, str], bool]      # (raw_answer, bu_code) -> 是否适用本规则
    transform: Callable[[str], str]        # raw_answer -> 净化后文本


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: Any) -> str:
    """去掉 HTML 标签并 strip。所有提取路径的最后一步，得到纯文本。"""
    return _TAG_RE.sub("", str(s)).strip()


def _parse(raw: str):
    """把答案解析成 JSON 对象；失败返回 None。容忍换行/多余空格。"""
    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(str(raw).replace("\n", "").strip())
        except Exception:
            return None


def _loads_maybe(v):
    """值可能是 JSON 字符串（如 msgContext），尝试解析；不是就原样返回。"""
    if isinstance(v, str):
        inner = _parse(v)
        if inner is not None:
            return inner
    return v


def _dig(obj, *keys):
    """安全多级取值：_dig(d, 'a', 'b') ≈ d['a']['b']，任一层缺失/类型不符返回 None。
    遇到 JSON 字符串值自动下钻一层。"""
    cur = obj
    for k in keys:
        cur = _loads_maybe(cur)
        if isinstance(k, int):
            if isinstance(cur, list) and 0 <= k < len(cur):
                cur = cur[k]
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
        if cur is None:
            return None
    return cur


# ── 证券专属提取：小安 / 同花顺 / 列表卡片，覆盖证券日志的几种渲染卡结构 ────────

def _extract_securities(first: dict, original: str) -> str | None:
    """证券答案首元素 first（dict）→ 提取正文。逐路径尝试，命中即返回纯文本。"""
    inner = _loads_maybe(first.get("msgContext"))
    if not isinstance(inner, dict):
        return None
    msg_info = inner.get("msgInfo") or {}
    data = msg_info.get("data") or {}

    # 路径1：msgInfo.msgContent（小安机器人最常见）
    content = msg_info.get("msgContent")
    if content:
        return _strip_html(content)

    # 路径2：msgInfo.data.context.data.content
    content = _dig(data, "context", "data", "content")
    if content:
        return _strip_html(content)

    # 路径3：同花顺智能选股 thsData
    ths = data.get("thsData") or {}
    if ths:
        # thsData.answer[0].txt[0].content（content 又是 JSON 字符串）→ components[0].data.content
        content_json = _dig(ths, "answer", 0, "txt", 0, "content")
        comp_content = _dig(_loads_maybe(content_json), "components", 0, "data", "content")
        if comp_content:
            return _strip_html(comp_content)
        # thsData.reply 兜底
        reply = ths.get("reply")
        if reply:
            return _strip_html(reply)

    # 路径4：msgInfo.data.list[].data.content（列表卡片，取含 <p> 的项）
    for item in (data.get("list") or []):
        c = _dig(item, "data", "content")
        if c and "<p>" in str(c):
            return _strip_html(c)

    return None


# ── 通用提取（所有 BU）：文本回复 / LLM API 响应 ──────────────────────────────

def _extract_generic(first, original: str) -> str | None:
    """跨 BU 通用结构提取。寿险等其它 BU 的 JSON 答案也可命中。"""
    # A1：文本回复，嵌套 list → first[0].content_data
    inner = _dig(first, 0) if isinstance(first, list) else None
    if isinstance(inner, dict) and "content_data" in inner:
        return _strip_html(inner.get("content_data") or "")

    # B1：LLM API 响应 → first.msg / first.standardQuestion
    if isinstance(first, dict) and "appType" in first:
        v = first.get("msg") or first.get("standardQuestion") or ""
        if v:
            return _strip_html(v)

    return None


# 提取不出正文时保留原文的长度上限：超大 JSON 原样落盘会撑大 row_json、拖慢导出，
# 且对模型判定无益（净化本就是为了去掉整坨结构）。统一截断防爆。
_RAW_MAX_LEN = 2000


def _truncate(s: str) -> str:
    return s[:_RAW_MAX_LEN] + "…(原文超长已截断)" if len(s) > _RAW_MAX_LEN else s


def _transform_extract_text(raw: str, bu_code: str) -> str:
    """统一提取入口：解析顶层 → 取首元素 → 先证券专属(仅证券BU)再通用 → 都不命中保留原文。"""
    parsed = _parse(raw)
    if parsed is None:
        return _truncate(raw)   # 非 JSON：原文（超长截断防爆）
    first = parsed[0] if isinstance(parsed, list) and parsed else parsed

    if bu_code == "securities" and isinstance(first, dict):
        got = _extract_securities(first, raw)
        if got:
            return got

    got = _extract_generic(first, raw)
    if got:
        return got

    return _truncate(raw)   # 所有路径都不命中：保留原文但截断（不丢关键信息，又防爆）


# 额外的独立净化规则（如某 BU 需要完全不同的处理）可加进这里，按序匹配命中即用。
# 当前主提取走 _transform_extract_text（内部已分证券专属 / 通用两层）。
_EXTRA_RULES: list[SanitizeRule] = []


def sanitize_answer(raw: str, bu_code: str) -> str:
    """把原始答案净化成人类/模型可读的正文。空/非字符串原样返回；任何异常保留原文。"""
    if not raw or not isinstance(raw, str):
        return raw
    try:
        for rule in _EXTRA_RULES:
            if rule.match(raw, bu_code):
                return rule.transform(raw)
        return _transform_extract_text(raw, bu_code)
    except Exception:
        return raw   # 净化绝不丢数据
