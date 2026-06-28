"""答案净化器：把 Excel 原始答案在喂给 Judge 前按规则预处理。

背景：日志「答案」列常是整坨 JSON（含相似问/关联问/模板结构），原封不动喂给
模型会让模型误判「已解决」。需按 BU / 答案特征做净化，只保留真正回答客户的正文。

抽象成「规则链」：每条规则 = (适用判断 match, 转换 transform)。按序匹配，命中第一条
即用其 transform，都不命中则原样返回。新增净化场景 = 往 _RULES 加一条，不改主流程。

接入点：pipeline.build_sample 构造 answer_text 时调 sanitize_answer。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SanitizeRule:
    name: str                              # 规则名（日志/排查用）
    match: Callable[[str, str], bool]      # (raw_answer, bu_code) -> 是否适用本规则
    transform: Callable[[str], str]        # raw_answer -> 净化后文本


# ── 通用 JSON 工具：嵌套结构里递归找字段，不写死路径，抗层级变动 ──────────────

def _parse(raw: str):
    """把答案解析成 JSON 对象；失败返回 None。兼容顶层 list/dict。"""
    try:
        return json.loads(raw)
    except Exception:
        return None


def _walk(obj):
    """深度遍历 JSON 树，yield 每个 (key, value)（dict 项）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)


def _find_first(raw_obj, target_key: str):
    """递归找第一个 key==target_key 的值；msgContext 这类「JSON 字符串」会自动下钻。"""
    stack = [raw_obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            inner = _parse(cur)        # 值本身是 JSON 字符串（如 msgContext）→ 下钻
            if inner is not None:
                stack.append(inner)
            continue
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == target_key and isinstance(v, str) and v.strip():
                    return v
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def _has_field_value(raw_obj, key: str, value: str) -> bool:
    """递归判断树里是否存在 key==value（含 JSON 字符串下钻）。"""
    stack = [raw_obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            inner = _parse(cur)
            if inner is not None:
                stack.append(inner)
            continue
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == key and v == value:
                    return True
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


# ── 规则 1：证券 · 小安机器人答案，只取 msgContent ────────────────────────────

def _match_securities_xiaoan(raw: str, bu_code: str) -> bool:
    if bu_code != "securities":
        return False
    obj = _parse(raw)
    return obj is not None and _has_field_value(obj, "sema_bot", "小安")


def _transform_take_msg_content(raw: str) -> str:
    """只保留 msgContent 正文，丢弃 relatedQuestions/template 等结构。

    取不到 msgContent 则原样返回（不丢数据）。
    """
    obj = _parse(raw)
    content = _find_first(obj, "msgContent") if obj is not None else None
    return content if content else raw


# ── 规则链：按序匹配，命中第一条即用其 transform；都不命中原样返回 ────────────

_RULES: list[SanitizeRule] = [
    SanitizeRule(
        name="securities_xiaoan_msg_content",
        match=_match_securities_xiaoan,
        transform=_transform_take_msg_content,
    ),
]


def sanitize_answer(raw: str, bu_code: str) -> str:
    """按规则链净化答案，返回喂给 Judge 的答案文本。空/非字符串原样返回。"""
    if not raw or not isinstance(raw, str):
        return raw
    for rule in _RULES:
        try:
            if rule.match(raw, bu_code):
                return rule.transform(raw)
        except Exception:
            continue   # 单条规则异常不应影响评测，跳过该规则
    return raw
