FROM pcr-sz.paic.com.cn/inference/ubuntu-py312-node24:20260413

# —— 基础环境 ——
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 设置工作目录
WORKDIR /app

RUN pip3 install uv \
    --index-url http://maven.paic.com.cn/repository/pypi/simple/ \
    --trusted-host maven.paic.com.cn --break-system-packages

# 将 uv 添加到 PATH
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH="${PYTHONPATH}:/app/src"

# —— 复制后端源码 ——
COPY src /app/src
COPY pyproject.toml .

# —— 复制前端源码 ——
COPY frontend/ /app/frontend/

RUN npm cache clean --force

RUN npm config set registry http://maven.paic.com.cn/repository/npm  && \
    npm config set fetch-retries 5 && \
    npm config set fetch-timeout 120000 && \
    npm ci --prefix /app/frontend/ && \
    npm run docs:build --prefix /app/frontend/ && \
    npm run build --prefix /app/frontend/ && \
    uv sync --all-extras --index-url http://maven.paic.com.cn/repository/pypi/simple/ --trusted-host maven.paic.com.cn && \
    rm -rf /root/.cache/uv

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "datapulse.main:app", "--host", "0.0.0.0", "--port", "8000"]
