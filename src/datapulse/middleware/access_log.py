"""
HTTP 访问日志中间件

输出到 datapulse.access logger，由日志系统路由到：
  - dev 环境：同时输出 console（structlog ConsoleRenderer）和 access-{inst}.log（JSON）
  - 其他环境：仅写 access-{inst}.log（JSON）

每条 access 日志包含字段：
  trace_id, username, method, path, params, body, status_code, latency_ms
  以及通用字段：timestamp, level, service, env, instance（由日志处理器链注入）

body 脱敏：密码 / token 等敏感 key 自动替换为 ***；
params 脱敏同上；手机号 / 邮箱等正则脱敏由 masking_processor 在处理器链中统一处理。

跳过路径：/api/health、静态资源（/assets/）
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable

import structlog
from fastapi import Request
from jose import jwt as _jose_jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from datapulse.logging._masking import SENSITIVE_KEYS

_log = structlog.get_logger("datapulse.access")

# 跳过不记录的路径前缀 / 精确路径
_SKIP_PATHS = {"/api/health", "/"}
_SKIP_PREFIXES = ("/assets/",)

# 请求体最大截取长度（超长截断，防止日志过大）
_BODY_MAX_LEN = 2000


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _extract_username(request: Request) -> str:
    """从 Authorization Bearer JWT 中提取 sub（用户名），不验证签名。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "-"
    try:
        claims = _jose_jwt.get_unverified_claims(auth[7:])
        return claims.get("sub") or "-"
    except Exception:
        return "-"


def _mask_sensitive_dict(d: dict) -> dict:
    """对 dict 做 key 级别脱敏（value 中的正则脱敏由处理器链统一处理）。"""
    out = {}
    for k, v in d.items():
        if k.lower() in SENSITIVE_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _mask_sensitive_dict(v)
        else:
            out[k] = v
    return out


def _mask_form(raw: str) -> dict[str, str]:
    """将 URL-encoded form 解析并脱敏，返回 dict（方便 JSON 序列化）。"""
    out: dict[str, str] = {}
    for pair in raw.split("&"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            key = urllib.parse.unquote_plus(k)
            out[key] = "***" if key.lower() in SENSITIVE_KEYS else urllib.parse.unquote_plus(v)
        else:
            out[pair] = ""
    return out


async def _parse_body(request: Request) -> dict | str | None:
    """
    读取并解析请求体，返回：
      - dict   — JSON body（已 key 级别脱敏）
      - dict   — form-encoded body（已 key 级别脱敏）
      - str    — 其他格式（截断为 _BODY_MAX_LEN 字符）
      - None   — 无 body
    注：request.body() 在 Starlette 中会缓存，重复读取安全。
    """
    body = await request.body()
    if not body:
        return None

    ct = request.headers.get("content-type", "")
    raw = body.decode("utf-8", errors="replace")

    if "application/x-www-form-urlencoded" in ct:
        return _mask_form(raw)

    if "application/json" in ct or "text/json" in ct:
        try:
            return _mask_sensitive_dict(json.loads(raw))
        except json.JSONDecodeError:
            pass

    return raw[:_BODY_MAX_LEN]


# ── Middleware ────────────────────────────────────────────────────────────────

class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    记录每次 HTTP 请求的访问日志。

    输出字段（JSON 文件）：
      timestamp, level, service, env, instance, trace_id,
      message="access",
      method, path, username, params, body, status_code, latency_ms
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # 跳过不需要记录的路径
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        start     = time.perf_counter()
        method    = request.method
        username  = _extract_username(request)
        params    = dict(request.query_params) if request.query_params else None

        # 只在写操作时读取 body（GET / DELETE / HEAD 无 body）
        body = None
        if method in {"POST", "PUT", "PATCH"}:
            body = await _parse_body(request)

        response    = await call_next(request)
        latency_ms  = round((time.perf_counter() - start) * 1000)
        status_code = response.status_code

        # 选择合适的日志级别
        if status_code >= 500:
            log_fn = _log.error
        elif status_code >= 400:
            log_fn = _log.warning
        else:
            log_fn = _log.info

        log_fn(
            "access",               # event / message
            method=method,
            path=path,
            username=username,
            params=params,
            body=body,
            status_code=status_code,
            latency_ms=latency_ms,
        )

        return response
