# =============================================================================
# Datapulse — 内网生产镜像
#
# 构建前提：
#   1. 先在本机完成前端构建（需要能访问 npm）：
#      cd frontend && npm install && npm run build
#   2. 确保 frontend/dist/ 目录存在（已从 .gitignore 临时包含或本地已 build）
#   3. 在项目根目录执行构建：
#      docker build -t datapulse:latest .
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
#   - 基础镜像若无法 pull，请提前在有网机器上 pull 后 docker save/load 到内网
#   - 内网 Harbor 镜像仓库地址请替换 FROM 行中的镜像源
# =============================================================================

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

# ── 复制前端构建产物 ──────────────────────────────────────────────────────────
# frontend/dist/ 须在 docker build 前已在本机生成：
#   cd frontend && npm install && npm run build
# 若目录不存在，构建会报错，这是有意为之（强制先 build 前端）
COPY frontend/dist/ ./frontend/dist/

# ── 运行时配置 ────────────────────────────────────────────────────────────────
# .env 文件通过 docker run --env-file 注入，不打入镜像
EXPOSE 8000

# 非 root 用户运行（安全最佳实践）
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# 向量文件 / 日志目录（挂载到宿主机持久化）
VOLUME ["/app/nas"]

CMD ["python", "-m", "uvicorn", "datapulse.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
