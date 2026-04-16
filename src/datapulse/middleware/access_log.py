"""Access logging middleware for FastAPI.

日志格式：
  2024-01-15 14:30:25 [ACCESS] [trace_id] username | METHOD /path | params=... | body=... | status | Nms

说明：
  - 时间：本地时间，精确到秒
  - trace_id：由 TraceMiddleware 写入 ContextVar，此处读取（TraceMiddleware 先于本中间件执行）
  - username：从 Authorization Bearer JWT 的 payload.sub 字段解析，不重新验证签名；
              无 token 或解析失败时显示 "-"
"""

from __future__ import annotations

import json
import logging
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

# 需要在日志中脱敏的字段名（大小写不敏感）
_SENSITIVE_KEYS = {"password", "password_hash", "old_password", "new_password", "token", "secret"}


def _now_str() -> str:
    return datetime.now(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _extract_username(request: Request) -> str:
    """从 Authorization Bearer token 中提取用户名，不验证签名。
    解析失败或无 token 时返回 "-"。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "-"
    token = auth_header[len("Bearer "):]
    try:
        # get_unverified_claims 仅解码 payload，不验证签名/过期
        claims = _jose_jwt.get_unverified_claims(token)
        return claims.get("sub") or "-"
    except Exception:
        return "-"


def _mask_dict(d: dict) -> dict:
    """递归脱敏字典中的敏感字段。"""
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
    """脱敏 application/x-www-form-urlencoded 格式的 body（如 login 表单）。"""
    parts = []
    for pair in raw.split("&"):
        if "=" in pair:
            key, _, val = pair.partition("=")
            key_decoded = urllib.parse.unquote_plus(key)
            if key_decoded.lower() in _SENSITIVE_KEYS:
                parts.append(f"{key}=***")
            else:
                parts.append(pair)
        else:
            parts.append(pair)
    return "&".join(parts)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """每个请求打印一行结构化日志，包含时间、trace_id、用户名、耗时等信息。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        excluded_paths = {"/api/health", "/assets", "/"}
        if request.url.path in excluded_paths or request.url.path.startswith("/assets"):
            return await call_next(request)

        start_time   = time.time()
        method       = request.method
        path         = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}
        username     = _extract_username(request)
        # trace_id 由 TraceMiddleware 在本中间件执行之前已写入 ContextVar
        trace_id     = get_trace_id() or "-"

        # 读取并缓存 body（BaseHTTPMiddleware 会自动处理，下游仍可正常读取）
        body = b""
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()

        # 格式化 body 并脱敏（截断至 500 字符）
        body_str = "null"
        if body:
            content_type = request.headers.get("content-type", "")
            try:
                if "application/x-www-form-urlencoded" in content_type:
                    body_str = _mask_form(body.decode("utf-8", errors="ignore"))[:500]
                else:
                    body_dict = json.loads(body.decode("utf-8"))
                    body_str = json.dumps(_mask_dict(body_dict), ensure_ascii=False)[:500]
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_str = body.decode("utf-8", errors="ignore")[:500]

        response    = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000)
        query_str   = json.dumps(query_params, ensure_ascii=False) if query_params else "null"
        status_code = response.status_code

        log_message = (
            f"{_now_str()} [ACCESS] [{trace_id}] {username}"
            f" | {method} {path}"
            f" | params={query_str}"
            f" | body={body_str}"
            f" | {status_code}"
            f" | {duration_ms}ms"
        )

        if status_code >= 500:
            logger.error(log_message)
        elif status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        return response
