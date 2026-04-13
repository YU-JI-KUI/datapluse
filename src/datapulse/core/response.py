"""统一 Response 封装 + 业务状态码

所有接口必须通过 success() / error() 返回，禁止裸 JSON。

返回结构：
{
    "code":      0,               # 0=成功，非零=业务错误
    "message":   "success",
    "data":      {...} | null,
    "trace_id":  "xxx",           # 由 TraceMiddleware 写入
    "timestamp": 1710000000000    # 毫秒时间戳
}
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.responses import JSONResponse

from datapulse.core.context import get_trace_id


# ── 业务状态码 ────────────────────────────────────────────────────────────────

class Code:
    OK               = 0
    # 通用错误 1xxx
    PARAM_ERROR      = 1001
    NOT_FOUND        = 1002
    ALREADY_EXISTS   = 1003
    FORBIDDEN        = 1004
    UNAUTHORIZED     = 1005
    # 数据相关 2xxx
    DATA_DUPLICATE   = 2001
    DATA_INVALID     = 2002
    # 标注相关 3xxx
    ANNOTATION_CONFLICT = 3001
    ANNOTATION_EMPTY    = 3002
    # Pipeline 相关 4xxx
    PIPELINE_RUNNING = 4001
    PIPELINE_FAILED  = 4002
    # 系统错误 5xxx
    INTERNAL_ERROR   = 5000


_CODE_MSG: dict[int, str] = {
    Code.OK:                 "success",
    Code.PARAM_ERROR:        "参数错误",
    Code.NOT_FOUND:          "资源不存在",
    Code.ALREADY_EXISTS:     "资源已存在",
    Code.FORBIDDEN:          "无权限",
    Code.UNAUTHORIZED:       "未登录或 token 已过期",
    Code.DATA_DUPLICATE:     "数据重复",
    Code.DATA_INVALID:       "数据无效",
    Code.ANNOTATION_CONFLICT:"标注冲突",
    Code.ANNOTATION_EMPTY:   "标注内容为空",
    Code.PIPELINE_RUNNING:   "Pipeline 正在运行中",
    Code.PIPELINE_FAILED:    "Pipeline 执行失败",
    Code.INTERNAL_ERROR:     "系统内部错误",
}


# ── 响应构建 ──────────────────────────────────────────────────────────────────

def _build(code: int, message: str | None, data: Any) -> dict:
    return {
        "code":      code,
        "message":   message or _CODE_MSG.get(code, "unknown"),
        "data":      data,
        "trace_id":  get_trace_id(),
        "timestamp": int(time.time() * 1000),
    }


def success(data: Any = None, message: str = "success") -> JSONResponse:
    """成功响应，HTTP 200"""
    return JSONResponse(status_code=200, content=_build(Code.OK, message, data))


def error(
    code: int = Code.INTERNAL_ERROR,
    message: str | None = None,
    data: Any = None,
    http_status: int = 200,
) -> JSONResponse:
    """业务错误响应（默认 HTTP 200，业务码非零）"""
    return JSONResponse(status_code=http_status, content=_build(code, message, data))


def page_data(lst: list, page: int, page_size: int, total: int) -> dict:
    """构建分页数据结构"""
    return {
        "list": lst,
        "pagination": {
            "page":      page,
            "page_size": page_size,
            "total":     total,
        },
    }
