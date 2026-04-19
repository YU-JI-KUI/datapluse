"""
Trace ID 中间件

职责：
  1. 从入站请求头 X-Trace-Id 读取已有 trace_id，否则生成新 UUID
  2. 写入 asyncio contextvar（供 core.context.get_trace_id 读取）
  3. 通过 structlog.contextvars 绑定 trace_id，后续所有 structlog/stdlib 日志自动携带
  4. 把 trace_id 写入响应头 X-Trace-Id，方便调用方透传
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from datapulse.core.context import set_trace_id


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4()).replace("-", "")

        # 写入 asyncio contextvar（供旧代码 get_trace_id() 读取）
        set_trace_id(trace_id)

        # 绑定到 structlog contextvars，所有后续日志自动带上 trace_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
