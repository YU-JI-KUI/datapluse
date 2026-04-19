"""
日志系统核心：structlog + dictConfig + QueueListener 异步写入

架构
────
                          ┌─ console_handler (同步，彩色/JSON 取决于 env)
datapulse.*        ───────┤
                          └─ app_queue_handler ──→ QueueListener ──→ app-{inst}.log   (INFO+, 仅 datapulse.*)
                                                                  └──→ error-{inst}.log (WARNING+, 全局)

datapulse.access   ───── [dev: console_handler] + access_queue_handler
  (propagate=False)                                  └──→ QueueListener ──→ access-{inst}.log

uvicorn.*          ───── console_handler (WARNING+) + app_queue_handler (error.log WARNING+)
sqlalchemy.engine  ───── app_queue_handler (WARNING+)
root               ───── app_queue_handler (WARNING+)

所有 JSON 文件均包含字段：timestamp / level / logger / service / env / instance / trace_id / message
trace_id 由 structlog.contextvars 注入（TraceMiddleware 在每次请求开头 bind）。

环境策略
────────
  dev  — console 彩色（ConsoleRenderer），文件 JSON
  test — console JSON，文件 JSON
  prod — 无 console（或 WARNING+ console），文件 JSON

日志轮转
────────
  rotation=time （默认）— 每天午夜轮转，保留 backup_count 天
  rotation=size          — 单文件超过 max_bytes 轮转，保留 backup_count 份

多实例部署
──────────
  日志文件名含 instance_id（默认 hostname），各实例写各自的文件，避免 RotatingFileHandler 并发冲突。
"""

from __future__ import annotations

import copy
import logging
import logging.config
import logging.handlers
import queue
import socket
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from ._masking import masking_processor

__all__ = ["setup_logging", "shutdown_logging"]


# ── 自定义 QueueHandler：不预序列化 record ────────────────────────────────────────
#
# 问题根因（Python 3.12）：
#   logging.handlers.QueueHandler.prepare() 默认先调用 self.format(record)，
#   这会把 record.msg（structlog 存入的 dict）序列化成字符串，再 copy.copy(record)
#   入队。下游 QueueListener 里的 ProcessorFormatter 检测到 structlog 标记属性，
#   却发现 msg 已变成字符串，调用 dict.copy() 时抛出 AttributeError。
#
# 修复：重写 prepare()，只做浅拷贝，不调用 self.format()，保留原始 record.msg（dict）。
# 同时把该 handler 排在 console_handler 之前注册，确保队列先 copy 到原始状态，
# 再由 console_handler 完成渲染（console_handler 不会影响已入队的副本）。

class _PassthroughQueueHandler(logging.handlers.QueueHandler):
    """不预格式化的 QueueHandler，保留 structlog 原始 event_dict 直接入队。"""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # 只做浅拷贝，清除不可 pickle 的异常信息，其余保持原样。
        rv = copy.copy(record)
        rv.exc_info  = None
        rv.exc_text  = None
        return rv


# ── 全局 QueueListener 持有（进程退出或 lifespan 结束时 shutdown）─────────────────
_app_listener:    logging.handlers.QueueListener | None = None
_access_listener: logging.handlers.QueueListener | None = None
_initialized:     bool = False


# ── 自定义处理器（service / env / instance 注入）──────────────────────────────

def _make_add_service(
    service: str, env: str, instance: str
):
    """工厂：返回给 structlog 注入服务元信息的处理器闭包。"""
    def _processor(
        _logger: WrappedLogger, _method: str, event_dict: EventDict
    ) -> EventDict:
        event_dict.setdefault("service", service)
        event_dict.setdefault("env",     env)
        event_dict.setdefault("instance", instance)
        return event_dict
    return _processor


def _rename_event_to_message(
    _logger: WrappedLogger, _method: str, event_dict: EventDict
) -> EventDict:
    """将 structlog 的 'event' 字段重命名为 'message'，兼容 ELK / Loki 字段规范。"""
    event_dict["message"] = event_dict.pop("event", "")
    return event_dict


# ── 文件 handler 过滤器 ───────────────────────────────────────────────────────

class _AppFileFilter(logging.Filter):
    """app.log 只接受 datapulse.* 业务日志，排除 datapulse.access。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return (
            record.name == "datapulse"
            or (
                record.name.startswith("datapulse.")
                and not record.name.startswith("datapulse.access")
            )
        )


class _ErrorFileFilter(logging.Filter):
    """error.log 接受所有 WARNING+ 日志，但排除 uvicorn.access（高频且无用）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        return (
            record.levelno >= logging.WARNING
            and record.name != "uvicorn.access"
        )


# ── 核心配置函数 ──────────────────────────────────────────────────────────────

def setup_logging(settings: Any) -> None:
    """
    初始化日志系统。

    在 FastAPI lifespan 内调用（uvicorn 完成自身 logging.config.dictConfig 后），
    保证我们的配置不被 uvicorn 覆盖。

    幂等：重复调用无副作用。
    """
    global _app_listener, _access_listener, _initialized
    if _initialized:
        return
    _initialized = True

    env          = getattr(settings, "app_env",          "dev")
    level_str    = getattr(settings, "log_level",        "INFO").upper()
    level        = getattr(logging, level_str, logging.INFO)
    service      = getattr(settings, "service_name",     "datapulse")
    instance     = getattr(settings, "instance_id",      "") or socket.gethostname()
    log_dir      = Path(getattr(settings, "log_dir",     "./logs"))
    rotation     = getattr(settings, "log_rotation",     "time")
    max_bytes    = getattr(settings, "log_max_bytes",    100 * 1024 * 1024)
    backup_count = getattr(settings, "log_backup_count", 30)

    log_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. 共享 structlog 处理器链 ────────────────────────────────────────────
    #    同时用于 structlog.configure 和 ProcessorFormatter.foreign_pre_chain
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,           # 注入 trace_id 等 contextvar
        structlog.stdlib.add_log_level,                    # level 字段
        structlog.stdlib.add_logger_name,                  # logger 字段
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),  # timestamp 本地时间
        structlog.stdlib.PositionalArgumentsFormatter(),   # %s 位置参数插值
        structlog.processors.StackInfoRenderer(),          # stack_info 渲染
        _make_add_service(service, env, instance),         # service / env / instance
        masking_processor,                                 # 敏感信息脱敏
    ]

    # ── 2. 配置 structlog ─────────────────────────────────────────────────────
    structlog.configure(
        processors=shared_processors + [
            # 最后包装成 stdlib LogRecord 可识别的格式，由 ProcessorFormatter 接管渲染
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── 3. 两种 Formatter ──────────────────────────────────────────────────────
    # JSON：用于文件，始终输出结构化 JSON
    _json_post: list[Any] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.ExceptionRenderer(),
        _rename_event_to_message,
        structlog.processors.JSONRenderer(sort_keys=False),
    ]
    json_fmt = structlog.stdlib.ProcessorFormatter(
        processors=_json_post,
        foreign_pre_chain=shared_processors,
    )

    # Console：dev 彩色，其他环境同 JSON
    if env == "dev":
        _console_post: list[Any] = [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        console_fmt = structlog.stdlib.ProcessorFormatter(
            processors=_console_post,
            foreign_pre_chain=shared_processors,
        )
    else:
        console_fmt = json_fmt

    # ── 4. 文件 Handler 工厂 ──────────────────────────────────────────────────
    def _make_file_handler(template: str) -> logging.Handler:
        path = log_dir / template.format(instance=instance)
        if rotation == "size":
            h: logging.Handler = logging.handlers.RotatingFileHandler(
                path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:  # time（默认：每天午夜轮转）
            h = logging.handlers.TimedRotatingFileHandler(
                path,
                when="midnight",
                interval=1,
                backupCount=backup_count,
                encoding="utf-8",
                utc=False,
            )
        h.setFormatter(json_fmt)
        return h

    # ── 5. 具体文件 Handler ───────────────────────────────────────────────────
    app_handler = _make_file_handler("app-{instance}.log")
    app_handler.setLevel(level)
    app_handler.addFilter(_AppFileFilter())

    error_handler = _make_file_handler("error-{instance}.log")
    error_handler.setLevel(logging.WARNING)
    error_handler.addFilter(_ErrorFileFilter())

    access_handler = _make_file_handler("access-{instance}.log")
    access_handler.setLevel(logging.INFO)

    # ── 6. Console Handler（同步，无需 Queue）────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_fmt)
    console_handler.setLevel(level if env != "prod" else logging.WARNING)

    # ── 7. QueueListener + QueueHandler（异步写文件）────────────────────────
    _app_q    = queue.Queue(maxsize=-1)   # -1 = 无界队列
    _access_q = queue.Queue(maxsize=-1)

    _app_listener = logging.handlers.QueueListener(
        _app_q,
        app_handler,
        error_handler,
        respect_handler_level=True,   # 让各 handler 自己决定接不接受
    )
    _access_listener = logging.handlers.QueueListener(
        _access_q,
        access_handler,
        respect_handler_level=True,
    )
    _app_listener.start()
    _access_listener.start()

    app_q_h    = _PassthroughQueueHandler(_app_q)
    app_q_h.setLevel(logging.DEBUG)    # 不过滤，交给下游 handler
    access_q_h = _PassthroughQueueHandler(_access_q)
    access_q_h.setLevel(logging.DEBUG)

    # ── 8. dictConfig：配置 logger 层级（level / propagate）──────────────────
    #    Handler 通过 dictConfig 设置为空，之后手动 attach（支持自定义对象）
    logging.config.dictConfig({
        "version":                1,
        "disable_existing_loggers": False,
        "loggers": {
            # 业务日志
            "datapulse": {
                "handlers": [], "level": level_str, "propagate": False,
            },
            # HTTP 访问日志（独立路由，不冒泡到 datapulse）
            "datapulse.access": {
                "handlers": [], "level": "INFO", "propagate": False,
            },
            # uvicorn 框架日志
            "uvicorn": {
                "handlers": [], "level": "WARNING", "propagate": False,
            },
            # uvicorn 自带 access log 静默（由我们自己的 AccessLogMiddleware 替代）
            "uvicorn.access": {
                "handlers": [], "level": "CRITICAL", "propagate": False,
            },
            # SQLAlchemy（默认只要 WARNING+）
            "sqlalchemy.engine": {
                "handlers": [], "level": "WARNING", "propagate": False,
            },
        },
        "root": {"handlers": [], "level": "WARNING"},
    })

    # ── 9. 手动挂载 Handler ───────────────────────────────────────────────────
    def _set_handlers(name: str, *handlers: logging.Handler) -> None:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        for h in handlers:
            lg.addHandler(h)

    # 注意：队列 handler 必须排在 console_handler 之前。
    # 原因：Python 3.12 的 QueueHandler.prepare() 默认会调用 self.format() 把
    # record.msg（structlog dict）序列化成字符串，我们用 _PassthroughQueueHandler
    # 跳过了这一步，改为直接浅拷贝入队。但若 console_handler 先运行，它的
    # ProcessorFormatter 会修改原始 record 的 msg，导致入队的副本是字符串而非 dict。
    # 先让队列 handler 拷贝原始 record，再让 console_handler 渲染原始 record，两者互不干扰。

    # datapulse 业务日志 → async → app.log + error.log；同时 console（dev 彩色）
    _set_handlers("datapulse", app_q_h, console_handler)

    # access 日志 → dev 下也输出到 console，始终写 access.log
    if env == "dev":
        _set_handlers("datapulse.access", access_q_h, console_handler)
    else:
        _set_handlers("datapulse.access", access_q_h)

    # uvicorn 错误 → async → error.log；同时 console（WARNING+）
    _set_handlers("uvicorn", app_q_h, console_handler)
    _set_handlers("uvicorn.access")                    # 完全静默
    _set_handlers("sqlalchemy.engine", app_q_h)        # 只入文件

    # root：兜底，只入 error.log
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(app_q_h)


def shutdown_logging() -> None:
    """
    优雅关闭：停止 QueueListener，确保队列内所有日志写入磁盘后再退出。
    在 FastAPI lifespan 的 finally 块中调用。
    """
    global _app_listener, _access_listener, _initialized
    if _app_listener:
        _app_listener.stop()
        _app_listener = None
    if _access_listener:
        _access_listener.stop()
        _access_listener = None
    _initialized = False
