"""
敏感信息脱敏：正则 + key 级别屏蔽

支持：
  - 手机号（中国大陆）：保留前 3 位和后 4 位，中间替换为 ****
  - 邮箱：保留前 2 位和域名，中间替换为 **
  - 身份证（18位）：保留前 6 位和后 4 位，中间替换为 ********
  - 密码 / Token / Secret / API Key 等字段：值替换为 ***
"""

from __future__ import annotations

import re
from typing import Any

# ── 正则模式 ──────────────────────────────────────────────────────────────────

_PHONE_RE   = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_EMAIL_RE   = re.compile(r"([A-Za-z0-9._%+\-]{2})[A-Za-z0-9._%+\-]*(@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_ID_CARD_RE = re.compile(r"\b(\d{6})\d{8}(\w{4})\b")   # 身份证号：保留前6后4

# key 名中包含这些词时，整个 value 替换为 ***
SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "password_hash", "old_password", "new_password",
    "token", "access_token", "refresh_token",
    "secret", "secret_key", "api_key",
    "authorization",
    "cookie",
})


# ── 字符串脱敏 ────────────────────────────────────────────────────────────────

def mask_string(s: str) -> str:
    """对单个字符串做正则脱敏（不处理 key 级别）。"""
    s = _PHONE_RE.sub(lambda m: m.group(1)[:3] + "****" + m.group(1)[7:], s)
    s = _EMAIL_RE.sub(r"\1**\2", s)
    s = _ID_CARD_RE.sub(r"\1********\2", s)
    return s


# ── Dict 脱敏 ─────────────────────────────────────────────────────────────────

def mask_dict(d: dict[str, Any]) -> dict[str, Any]:
    """递归对 dict 做 key 级别 + 字符串正则脱敏。"""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if k.lower() in SENSITIVE_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = mask_dict(v)
        elif isinstance(v, str):
            out[k] = mask_string(v)
        else:
            out[k] = v
    return out


# ── structlog 处理器 ──────────────────────────────────────────────────────────

# 日志中不做正则脱敏的内置字段
_SKIP_KEYS = frozenset({"event", "timestamp", "level", "logger", "_record", "_from_structlog"})


def masking_processor(
    _logger: Any,
    _method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    structlog 处理器：对 event_dict 中所有字段做脱敏。

    - key 在 SENSITIVE_KEYS 中 → value 替换为 ***
    - value 为 dict → 递归 mask_dict
    - value 为 str  → regex 脱敏（电话 / 邮箱 / 身份证）
    """
    for key in list(event_dict.keys()):
        if key in _SKIP_KEYS:
            continue
        val = event_dict[key]
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***"
        elif isinstance(val, dict):
            event_dict[key] = mask_dict(val)
        elif isinstance(val, str):
            event_dict[key] = mask_string(val)
    return event_dict
