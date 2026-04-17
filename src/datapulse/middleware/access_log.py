"""Access logging middleware for FastAPI.

日志格式（带 ANSI 颜色）：
  2024-01-15 14:30:25 ACCESS [a3f9c2b1] admin | GET /api/path | params=... | body=... | 200 | 3ms

颜色方案：
  时间        → 暗灰
  ACCESS      → 白色粗体
  trace_id    → 青色（取前 8 位）
  用户名      → 黄色粗体
  HTTP 方法   → 按类型着色（GET 蓝 / POST 绿 / PUT 黄 / DELETE 红 / PATCH 品红）
  路径        → 白色
  params/body → 暗灰
  状态码      → 2xx 绿 / 3xx 青 / 4xx 黄 / 5xx 红粗体
  耗时        → <100ms 绿 / <500ms 黄 / ≥500ms 红

设置 NO_COLOR=1 或 TERM=dumb 可禁用颜色（如写入文件时）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from jose import jwt as _jose_jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from datapulse.core.context import get_trace_id

logger = logging.getLogger(__name__)

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SENSITIVE_KEYS = {"password", "password_hash", "old_password", "new_password", "token", "secret"}

# ── ANSI 颜色 ──────────────────────────────────────────────────────────────────

def _supports_color() -> bool:
    """检测当前 stderr 是否支持 ANSI 颜色输出。"""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    # Windows 10 1511+ 原生支持 ANSI；旧版本通过 colorama 支持
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32          # type: ignore[attr-defined]
            # 启用 VIRTUAL_TERMINAL_PROCESSING (0x0004)
            kernel.SetConsoleMode(kernel.GetStdHandle(-12), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


_COLOR = _supports_color()


class _C:
    """ANSI 颜色常量。"""
    RST  = "\033[0m"
    BOLD = "\033[1m"
    DIM  = "\033[2m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BRIGHT_RED     = "\033[91m"
    BRIGHT_GREEN   = "\033[92m"
    BRIGHT_YELLOW  = "\033[93m"
    BRIGHT_BLUE    = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN    = "\033[96m"
    BRIGHT_WHITE   = "\033[97m"


def _c(code: str, text: str) -> str:
    """包裹 ANSI 颜色，不支持颜色时直接返回原文本。"""
    return f"{code}{text}{_C.RST}" if _COLOR else text


# ── 各段颜色规则 ──────────────────────────────────────────────────────────────

_METHOD_COLOR = {
    "GET":     _C.BRIGHT_BLUE,
    "POST":    _C.BRIGHT_GREEN,
    "PUT":     _C.BRIGHT_YELLOW,
    "DELETE":  _C.BRIGHT_RED,
    "PATCH":   _C.BRIGHT_MAGENTA,
    "HEAD":    _C.CYAN,
    "OPTIONS": _C.DIM,
}


def _color_method(method: str) -> str:
    color = _METHOD_COLOR.get(method, _C.WHITE)
    return _c(f"{_C.BOLD}{color}", f"{method:<7}")


def _color_status(code: int) -> str:
    if code < 300:
        return _c(f"{_C.BOLD}{_C.BRIGHT_GREEN}", str(code))
    if code < 400:
        return _c(_C.BRIGHT_CYAN, str(code))
    if code < 500:
        return _c(f"{_C.BOLD}{_C.BRIGHT_YELLOW}", str(code))
    return _c(f"{_C.BOLD}{_C.BRIGHT_RED}", str(code))


def _color_duration(ms: int) -> str:
    text = f"{ms}ms"
    if ms < 100:
        return _c(_C.GREEN, text)
    if ms < 500:
        return _c(_C.YELLOW, text)
    return _c(_C.BRIGHT_RED, text)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _extract_username(request: Request) -> str:
    """从 Authorization Bearer token 中提取用户名，不验证签名。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "-"
    try:
        claims = _jose_jwt.get_unverified_claims(auth[7:])
        return claims.get("sub") or "-"
    except Exception:
        return "-"


def _mask_dict(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _mask_dict(v)
        else:
            out[k] = v
    return out


def _mask_form(raw: str) -> str:
    parts = []
    for pair in raw.split("&"):
        if "=" in pair:
            key, _, _ = pair.partition("=")
            if urllib.parse.unquote_plus(key).lower() in _SENSITIVE_KEYS:
                parts.append(f"{key}=***")
                continue
        parts.append(pair)
    return "&".join(parts)


# ── Middleware ────────────────────────────────────────────────────────────────

class AccessLogMiddleware(BaseHTTPMiddleware):
    """每个请求打印一行彩色结构化日志：时间 / trace_id / 用户名 / 方法 / 路径 / 状态 / 耗时。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in {"/api/health", "/"} or request.url.path.startswith("/assets"):
            return await call_next(request)

        start_time   = time.time()
        method       = request.method
        path         = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}
        username     = _extract_username(request)
        trace_id     = (get_trace_id() or "--------")[:8]   # 取前 8 位，够标识一次请求

        body = b""
        if method in {"POST", "PUT", "PATCH"}:
            body = await request.body()

        body_str = "null"
        if body:
            ct = request.headers.get("content-type", "")
            try:
                if "application/x-www-form-urlencoded" in ct:
                    body_str = _mask_form(body.decode("utf-8", errors="ignore"))[:500]
                else:
                    body_str = json.dumps(
                        _mask_dict(json.loads(body.decode("utf-8"))),
                        ensure_ascii=False,
                    )[:500]
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_str = body.decode("utf-8", errors="ignore")[:500]

        response    = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000)
        query_str   = json.dumps(query_params, ensure_ascii=False) if query_params else "null"
        status_code = response.status_code

        # ── 拼装日志行 ──────────────────────────────────────────────────────────
        time_part    = _c(_C.DIM, _now_str())
        label_part   = _c(f"{_C.BOLD}{_C.WHITE}", "ACCESS")
        trace_part   = _c(_C.CYAN, f"[{trace_id}]")
        user_part    = _c(f"{_C.BOLD}{_C.YELLOW}", username)
        method_part  = _color_method(method)
        path_part    = _c(_C.BRIGHT_WHITE, path)
        params_part  = _c(_C.DIM, f"params={query_str}")
        body_part    = _c(_C.DIM, f"body={body_str}")
        status_part  = _color_status(status_code)
        dur_part     = _color_duration(duration_ms)

        sep = _c(_C.DIM, "|")
        msg = (
            f"{time_part} {label_part} {trace_part} {user_part} "
            f"{sep} {method_part} {path_part} "
            f"{sep} {params_part} "
            f"{sep} {body_part} "
            f"{sep} {status_part} "
            f"{sep} {dur_part}"
        )

        if status_code >= 500:
            logger.error(msg)
        elif status_code >= 400:
            logger.warning(msg)
        else:
            logger.info(msg)

        return response
