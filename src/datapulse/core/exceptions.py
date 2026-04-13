"""业务异常定义 + 全局异常处理器"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from datapulse.core.response import Code, error


class AppException(Exception):
    """业务异常基类"""

    def __init__(self, code: int = Code.INTERNAL_ERROR, message: str | None = None):
        self.code    = code
        self.message = message
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(Code.NOT_FOUND, message)


class ForbiddenError(AppException):
    def __init__(self, message: str = "无权限"):
        super().__init__(Code.FORBIDDEN, message)


class ParamError(AppException):
    def __init__(self, message: str = "参数错误"):
        super().__init__(Code.PARAM_ERROR, message)


class PipelineRunningError(AppException):
    def __init__(self, message: str = "Pipeline 正在运行中，请勿重复触发"):
        super().__init__(Code.PIPELINE_RUNNING, message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（在 main.py 中调用）"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return error(code=exc.code, message=exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        detail = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        return error(code=Code.PARAM_ERROR, message=f"参数校验失败: {detail}", http_status=400)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return error(code=Code.INTERNAL_ERROR, message=f"系统内部错误: {exc}", http_status=500)
