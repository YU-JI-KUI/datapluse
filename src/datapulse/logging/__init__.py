"""
datapulse 日志系统

使用方式
────────
  from datapulse.logging import get_logger

  logger = get_logger(__name__)
  logger.info("数据处理完成", dataset_id=1, count=200)
  logger.error("发生错误", exc_info=True)

  # access 日志（由 AccessLogMiddleware 使用，通常不需要直接调用）
  access_log = get_logger("datapulse.access")
"""

from __future__ import annotations

import structlog

from ._core import setup_logging, shutdown_logging
from ._masking import mask_dict, mask_string, masking_processor

__all__ = [
    "setup_logging",
    "shutdown_logging",
    "get_logger",
    "mask_dict",
    "mask_string",
    "masking_processor",
]


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    获取 structlog logger。

    推荐用法：
      logger = get_logger(__name__)

    返回的 logger 支持 .info() / .warning() / .error() / .debug() / .critical()，
    可通过关键字参数附加结构化字段：
      logger.info("用户登录", username="alice", ip="1.2.3.4")
    """
    return structlog.get_logger(name)
