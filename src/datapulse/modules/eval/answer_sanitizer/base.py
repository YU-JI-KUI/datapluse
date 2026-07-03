"""答案净化框架：抽象基类 + 注册机制 + 公用工具。

设计目标：一种答案结构 = 一个 AnswerParser 子类 = 一个小文件。内网新增一种答案类型时，
只需新写一个子类（实现 match / parse）并 @register 注册，不动入口与主流程。

匹配策略（入口 sanitize_answer 实现）：
  当前 BU 的专属 parser 优先 → 未命中回退通用 parser（bu_codes 含 "*"）→ 都不命中保留原文截断。
"""
from __future__ import annotations

import json
import re
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")

# 提取不出正文时保留原文的长度上限：超大 JSON 原样落盘会撑大 row_json、拖慢导出，
# 且对模型判定无益（净化本就是为了去掉整坨结构）。统一截断防爆。
RAW_MAX_LEN = 2000


def strip_html(s: Any) -> str:
    """去掉 HTML 标签并 strip。所有提取路径的最后一步，得到纯文本。"""
    return _TAG_RE.sub("", str(s)).strip()


def parse_json(raw: str):
    """把答案解析成 JSON 对象；失败返回 None。容忍换行/多余空格。"""
    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(str(raw).replace("\n", "").strip())
        except Exception:
            return None


def loads_maybe(v):
    """值可能是 JSON 字符串（如 msgContext），尝试解析；不是就原样返回。"""
    if isinstance(v, str):
        inner = parse_json(v)
        if inner is not None:
            return inner
    return v


def first_dict(parsed, max_depth=3):
    """逐层剥开嵌套数组，取到第一个 dict。真实日志的卡片外层常多套一层数组
    （如 [[{...}]]），只剥单层会拿到内层 list、匹配失败。取不到返回 None。"""
    cur = parsed
    for _ in range(max_depth):
        if isinstance(cur, dict):
            return cur
        if isinstance(cur, list) and cur:
            cur = cur[0]
        else:
            return None
    return cur if isinstance(cur, dict) else None


def dig(obj, *keys):
    """安全多级取值：dig(d, 'a', 'b') ≈ d['a']['b']，任一层缺失/类型不符返回 None。
    遇到 JSON 字符串值自动下钻一层（用于 msgContext 这类嵌套 JSON 字符串）。"""
    cur = obj
    for k in keys:
        cur = loads_maybe(cur)
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


def truncate(s: str) -> str:
    return s[:RAW_MAX_LEN] + "…(原文超长已截断)" if len(s) > RAW_MAX_LEN else s


class AnswerParser:
    """一种答案结构的解析器。子类实现 match / parse。

    约定：
      - bu_codes：该解析器适用的 BU code 元组；含 "*" 表示通用（所有 BU）。
      - priority：同一 BU 内多个解析器的尝试顺序，小的先试（默认 100）。
      - match(raw, parsed)：这条答案是不是本解析器能处理的结构。parsed 是顶层 JSON
        解析结果（parse_json(raw)，可能为 None）；子类通常判 parsed 的结构特征。
      - parse(raw, parsed)：提取出纯文本正文；无法提取返回 None（交给下一个解析器）。
    """
    name: str = "base"
    bu_codes: tuple = ("*",)
    priority: int = 100

    def applies_to(self, bu_code: str) -> bool:
        return "*" in self.bu_codes or bu_code in self.bu_codes

    def match(self, raw: str, parsed) -> bool:      # noqa: ARG002
        raise NotImplementedError

    def parse(self, raw: str, parsed) -> str | None:  # noqa: ARG002
        raise NotImplementedError


# ── 注册表 ────────────────────────────────────────────────────────────────────
_REGISTRY: list[AnswerParser] = []


def register(cls):
    """类装饰器：把解析器实例登记进全局注册表。用法：@register  class XxxParser(AnswerParser): ..."""
    _REGISTRY.append(cls())
    return cls


def parsers_for(bu_code: str) -> list[AnswerParser]:
    """取适用于某 BU 的解析器，专属优先于通用、同组按 priority 升序。"""
    applicable = [p for p in _REGISTRY if p.applies_to(bu_code)]
    # 专属（不含 "*"）排在通用（含 "*"）前面；组内按 priority
    applicable.sort(key=lambda p: (("*" in p.bu_codes), p.priority))
    return applicable
