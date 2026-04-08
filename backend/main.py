"""
Datapulse Web 服务入口

FastAPI 同时托管 API 和前端静态文件。
存储层：PostgreSQL（主数据） + 本地文件（Embedding 向量）
"""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import annotation, auth, config, data, datasets, export, pipeline, templates, users
from config.settings import get_settings
from storage.db import init_db

app = FastAPI(
    title="Datapulse API",
    description="AI 数据飞轮 - 数据生产平台",
    version="0.5.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    settings = get_settings()
    init_db(settings.db_url)

    from storage.db import get_db
    db = get_db()
    db.seed_defaults()   # 幂等写入预置角色和默认数据集


# ── API 路由 ───────────────────────────────────────────────────────────────────

app.include_router(auth.router,       prefix="/api/auth",       tags=["认证"])
app.include_router(users.router,      prefix="/api/users",      tags=["用户管理"])
app.include_router(datasets.router,   prefix="/api/datasets",   tags=["数据集"])
app.include_router(data.router,       prefix="/api/data",       tags=["数据管理"])
app.include_router(pipeline.router,   prefix="/api/pipeline",   tags=["Pipeline"])
app.include_router(annotation.router, prefix="/api/annotation", tags=["标注"])
app.include_router(config.router,     prefix="/api/config",     tags=["配置中心"])
app.include_router(export.router,     prefix="/api/export",     tags=["导出"])
app.include_router(templates.router,  prefix="/api/templates",  tags=["导出模板"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "datapulse", "version": "0.5.0"}


# ── 前端静态文件托管 ────────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    _assets = _FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return {"message": "前端尚未构建，请先运行 build.sh", "api_docs": "/api/docs"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["./"])
