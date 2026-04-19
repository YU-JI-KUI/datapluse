"""
Datapulse Web 服务入口 v2.0

FastAPI 同时托管 API 和前端静态文件。
存储层：PostgreSQL（主数据）+ 本地文件（Embedding 向量）

API 规范：统一响应结构 {code, message, data, trace_id, timestamp}
"""

from __future__ import annotations

# ── 必须在所有第三方库 import 之前设置（跨平台：macOS / Windows / Linux 均适用）──
# 背景：faiss 和 torch 各自捆绑一份 OpenMP 运行时；两者同时加载时，第二个初始化
#       会触发 "OMP Error #15: already initialized" 并 Abort。
#
# KMP_DUPLICATE_LIB_OK=TRUE  — 允许多份 OpenMP 共存（Intel/LLVM 官方 workaround）
# TOKENIZERS_PARALLELISM=false — 禁止 HuggingFace tokenizers 启动 Rust 并行线程
# OMP_NUM_THREADS=1           — 限制 OpenMP 线程数（意图分类规模下单线程足够）
import os as _os
_os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
_os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_os.environ.setdefault("OMP_NUM_THREADS", "1")

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from datapulse.api import auth, config, datasets, export, pipeline, templates, users
from datapulse.config.settings import get_settings
from datapulse.core.exceptions import register_exception_handlers
from datapulse.middleware.access_log import AccessLogMiddleware
from datapulse.middleware.trace import TraceMiddleware
from datapulse.repository import get_db, init_db

# 新版 router（遵循统一响应规范）
from datapulse.router import annotation, comment, conflict, data_item, data_state, pre_annotation


def _configure_logging() -> None:
    """配置应用层日志。

    必须在 lifespan 中调用（即 uvicorn 完成自身 logging 初始化之后），原因：
      1. uvicorn 启动时会调用 logging.config.dictConfig() 配置自己的 logger 层级
         （uvicorn / uvicorn.error / uvicorn.access），这会覆盖模块加载时的任何设置。
      2. lifespan 在 uvicorn 的 dictConfig 执行完毕之后才运行，此时修改才能生效。

    做两件事：
      A. 关闭 uvicorn 内置 access log（格式固定且信息少），由 AccessLogMiddleware 替代。
      B. 为 datapulse.* logger 添加 StreamHandler，否则 uvicorn 不会为应用层 logger
         配置任何 handler，导致 INFO 日志被 Python logging 默认静默丢弃。
    """
    # ── A. 关闭 uvicorn 内置 access log ──────────────────────────────────────
    uv_access = logging.getLogger("uvicorn.access")
    uv_access.handlers.clear()
    uv_access.propagate = False

    # ── B. 为 datapulse.* 配置 handler ───────────────────────────────────────
    app_logger = logging.getLogger("datapulse")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        # 仅输出消息本身，时间/级别已在 AccessLogMiddleware 的 log_message 里拼好
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False   # 防止日志冒泡到 root logger 造成重复输出


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()           # ← 必须在 uvicorn logging 初始化之后执行
    settings = get_settings()
    init_db(settings.db_url)
    get_db().seed_defaults()
    yield


app = FastAPI(
    title="Datapulse API",
    description="AI 数据飞轮 — 数据生产平台 v2.0",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── 中间件（注册顺序：后添加的先执行）──────────────────────────────────────────
app.add_middleware(AccessLogMiddleware)
app.add_middleware(TraceMiddleware)          # trace_id 注入
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局异常处理 ───────────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── API 路由（新版，统一响应规范）─────────────────────────────────────────────
app.include_router(data_item.router,      prefix="/api/data-items",       tags=["数据管理"])
app.include_router(annotation.router,     prefix="/api/annotations",      tags=["标注系统"])
app.include_router(comment.router,        prefix="/api/comments",         tags=["评论系统"])
app.include_router(conflict.router,       prefix="/api/conflicts",        tags=["冲突检测"])
app.include_router(pre_annotation.router, prefix="/api/pre-annotations",  tags=["LLM预标注"])
app.include_router(data_state.router,     prefix="/api/data-state",       tags=["状态流转"])

# ── API 路由（旧版，保持兼容）────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api/auth",      tags=["认证"])
app.include_router(users.router,      prefix="/api/users",     tags=["用户管理"])
app.include_router(datasets.router,   prefix="/api/datasets",  tags=["数据集"])
app.include_router(pipeline.router,   prefix="/api/pipeline",  tags=["Pipeline"])
app.include_router(config.router,     prefix="/api/config",    tags=["配置中心"])
app.include_router(export.router,     prefix="/api/export",    tags=["导出"])
app.include_router(templates.router,  prefix="/api/templates", tags=["导出模板"])


@app.get("/api/health")
async def health():
    from datapulse.core.response import success
    return success({"service": "datapulse", "version": "2.0.0"})


# ── 前端静态文件托管 ────────────────────────────────────────────────────────────
_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    _assets = _FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # 先尝试直接返回 dist/ 下的静态文件（logo.ico、logo.svg 等根目录资源）
        static_file = _FRONTEND_DIST / full_path
        if full_path and static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        # 其余路径交给 React SPA 处理
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        from datapulse.core.response import success
        return success({"message": "前端尚未构建，请先运行 build.sh", "api_docs": "/api/docs"})


if __name__ == "__main__":
    uvicorn.run("datapulse.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["./"])
