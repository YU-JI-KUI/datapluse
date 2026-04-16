"""Access logging middleware for FastAPI."""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# 需要在日志中脱敏的字段名（大小写不敏感）
_SENSITIVE_KEYS = {"password", "password_hash", "old_password", "new_password", "token", "secret"}


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
    """Middleware to log all API requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details."""
        excluded_paths = {"/api/health", "/assets", "/"}
        if request.url.path in excluded_paths or request.url.path.startswith("/assets"):
            return await call_next(request)

        start_time = time.time()
        method      = request.method
        path        = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}

        # 读取并缓存 body（FastAPI 会自动 cache，下游仍可正常读取）
        body = b""
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()

        # 格式化 body 并脱敏（截断至 500 字符）
        body_str = ""
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

        response     = await call_next(request)
        duration_ms  = round((time.time() - start_time) * 1000)
        query_str    = json.dumps(query_params, ensure_ascii=False) if query_params else "null"
        status_code  = response.status_code

        log_message = (
            f"[ACCESS] {method} {path} | params={query_str} | body={body_str} | {status_code} | {duration_ms}ms"
        )

        if status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        return response
