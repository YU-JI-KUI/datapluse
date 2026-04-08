#!/bin/bash
# Datapulse 启动脚本

set -e
cd "$(dirname "$0")"

echo "======================================"
echo "  Datapulse 数据飞轮 - 启动中"
echo "======================================"

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "[ERROR] 未找到 uv，请先安装："
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 检查 .env
if [ ! -f ".env" ]; then
    echo "[ERROR] 未找到 .env 文件，请先配置："
    echo "  cp .env.example .env  # 然后填入数据库连接信息"
    exit 1
fi

# 只在 .venv 不存在时才 sync，避免每次启动重复下载依赖
if [ ! -d ".venv" ]; then
    echo "[1/2] 首次运行，安装 Python 依赖..."
    uv sync
else
    echo "[1/2] 依赖已就绪"
fi

# 启动服务
echo "[2/2] 启动 Web 服务 → http://localhost:8000"
echo ""
uv run uvicorn datapulse.main:app --host 0.0.0.0 --port 8000
