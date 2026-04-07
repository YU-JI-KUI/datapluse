"""
Datapluse - 数据飞轮 Web 服务入口
FastAPI 同时托管 API 和前端静态文件
"""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import annotation, auth, config, data, export, pipeline

# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Datapluse API",
    description="AI 数据飞轮 - 数据生产平台",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS（开发时允许 Vite dev server）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API 路由 ───────────────────────────────────────────────────────────────

app.include_router(auth.router,       prefix="/api/auth",       tags=["认证"])
app.include_router(data.router,       prefix="/api/data",       tags=["数据管理"])
app.include_router(pipeline.router,   prefix="/api/pipeline",   tags=["Pipeline"])
app.include_router(annotation.router, prefix="/api/annotation", tags=["标注"])
app.include_router(config.router,     prefix="/api/config",     tags=["配置中心"])
app.include_router(export.router,     prefix="/api/export",     tags=["导出"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "datapluse"}


# ── 前端静态文件托管 ────────────────────────────────────────────────────────

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    # 挂载 assets 目录
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA fallback：所有非 API 路由返回 index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        index = FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
else:
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return {
            "message": "前端尚未构建。请先运行 build.sh，然后重启服务。",
            "api_docs": "/api/docs",
        }


# ── 启动 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["./"],
    )
