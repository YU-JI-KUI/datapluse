"""Access logging middleware for FastAPI."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details."""
        # Paths to exclude from logging
        excluded_paths = {"/api/health", "/assets", "/"}

        # Check if path should be excluded
        if request.url.path in excluded_paths or request.url.path.startswith("/assets"):
            response = await call_next(request)
            return response

        # Record start time
        start_time = time.time()

        # Capture request details
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}

        # Capture request body if present
        body = b""
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()

            # Re-assign body for downstream processing
            async def receive():
                return {"type": "http.request", "body": body}

            request._receive = receive

        # Format body for logging (truncate to 500 chars)
        body_str = ""
        if body:
            try:
                body_dict = json.loads(body.decode("utf-8"))
                body_str = json.dumps(body_dict, ensure_ascii=False)[:500]
            except (json.JSONDecodeError, UnicodeDecodeError):
                body_str = body.decode("utf-8", errors="ignore")[:500]

        # Get response
        response = await call_next(request)

        # Calculate duration
        duration_ms = round((time.time() - start_time) * 1000)

        # Format query params
        query_str = json.dumps(query_params, ensure_ascii=False) if query_params else "null"

        # Log the access
        status_code = response.status_code
        log_message = (
            f"[ACCESS] {method} {path} | params={query_str} | body={body_str} | {status_code} | {duration_ms}ms"
        )

        if status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)

        return response
