# =============================================================================
# Datapulse — 内网生产镜像
#
# 基础镜像已包含 Python 3.12 + Node 24，无需多阶段构建。
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
#   - 基础镜像来自内网 Harbor：pcr-sz.paic.com.cn
#   - Python 依赖走内网私服：http://maven.paic.com.cn/repository/pypi/simple
#   - npm 若需内网镜像源，在 npm install 后加 --registry <内网地址>
# =============================================================================

FROM pcr-sz.paic.com.cn/inference/ubuntu-py312-node24:20260413

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

RUN python3 -m pip install --upgrade pip \
        -i http://maven.paic.com.cn/repository/pypi/simple \
        --trusted-host maven.paic.com.cn \
    && python3 -m pip install -e ".[faiss]" \
        -i http://maven.paic.com.cn/repository/pypi/simple \
        --trusted-host maven.paic.com.cn

# ── 复制后端源码 ───────────────────────────────────────────────────────────────
COPY src/ ./src/

# ── 前端：安装依赖并构建 ──────────────────────────────────────────────────────
COPY frontend/package.json frontend/package-lock.json ./frontend/

RUN cd frontend && npm install

COPY frontend/ ./frontend/

RUN cd frontend && npm run build
# 构建产物在 /app/frontend/dist/，FastAPI 静态文件服务从此目录读取

# ── 运行时配置 ────────────────────────────────────────────────────────────────
# .env 文件通过 docker run --env-file 注入，不打入镜像
EXPOSE 8000

# 向量文件 / 日志目录（挂载到宿主机持久化）
VOLUME ["/app/nas"]

# workers 说明：
#   每个 worker 是独立的 Python 进程，多核时可并行处理请求
#   若有进程内共享状态（全局 FAISS 索引等），改为 --workers 1
CMD ["python3", "-m", "uvicorn", "datapulse.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
