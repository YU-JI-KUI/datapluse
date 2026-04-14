# =============================================================================
# Datapulse — 生产镜像
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
# =============================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -e ".[faiss]"

COPY src/ ./src/

COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm install
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

EXPOSE 8000

VOLUME ["/app/nas"]

CMD ["python3", "-m", "uvicorn", "datapulse.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2"]
