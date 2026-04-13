# =============================================================================
# Datapulse — 内网生产镜像（多阶段构建）
#
# 构建：
#   docker build -t datapulse:latest .
#
# 运行：
#   docker run -d \
#     --name datapulse \
#     -p 8000:8000 \
#     --env-file .env \
#     datapulse:latest
#
# 内网说明：
#   - Python 依赖走内网私服：http://maven.paic.com.cn/repository/pypi/simple
#   - Node 镜像若无法 pull，请提前在有网机器上 docker save/load 到内网
#   - 内网 Harbor 镜像仓库地址请替换 FROM 行中的镜像源
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: 前端构建
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# 先复制依赖文件，利用层缓存（package.json 不变时跳过 npm install）
COPY frontend/package.json frontend/package-lock.json ./

RUN npm install

# 复制前端源码并构建
COPY frontend/ ./

RUN npm run build
# 构建产物在 /frontend/dist/


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Python 后端（最终镜像，不含 Node）
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ── 基础环境 ──────────────────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=http://maven.paic.com.cn/repository/pypi/simple \
    PIP_TRUSTED_HOST=maven.paic.com.cn

WORKDIR /app

# ── 安装 Python 依赖（走内网私服）────────────────────────────────────────────
# 先单独复制 pyproject.toml，利用 Docker 层缓存：
# 依赖不变时不重新安装，只有代码变了才重新走后面的 COPY
COPY pyproject.toml ./

RUN pip install --upgrade pip \
        -i http://maven.paic.com.cn/repository/pypi/simple \
        --trusted-host maven.paic.com.cn \
    && pip install -e ".[faiss]" \
        -i http://maven.paic.com.cn/repository/pypi/simple \
        --trusted-host maven.paic.com.cn

# ── 复制后端源码 ───────────────────────────────────────────────────────────────
COPY src/ ./src/

# ── 从 Stage 1 复制前端构建产物 ───────────────────────────────────────────────
COPY --from=frontend-builder /frontend/dist/ ./frontend/dist/

# ── 运行时配置 ────────────────────────────────────────────────────────────────
# .env 文件通过 docker run --env-file 注入，不打入镜像
EXPOSE 8000

# 向量文件 / 日志目录（挂载到宿主机持久化）
VOLUME ["/app/nas"]

# workers 说明：
#   每个 worker 是独立的 Python 进程，多核时可并行处理请求
#   若有进程内共享状态（全局缓存等），改为 --workers 1
CMD ["python", "-m", "uvicorn", "datapulse.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
