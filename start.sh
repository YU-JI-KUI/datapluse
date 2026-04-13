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

# 清除可能存在的旧 venv 环境变量（防止与其他项目的 venv 冲突）
unset VIRTUAL_ENV
unset VIRTUAL_ENV_PROMPT

# 安装/同步依赖（uv sync 是幂等的，依赖未变时极快）
if [ ! -d ".venv" ]; then
    echo "[1/2] 首次运行，安装 Python 依赖..."
else
    echo "[1/2] 同步依赖..."
fi
uv sync

# 启动服务（直接调用 .venv 中的 Python，避免 uv run 的 venv 检测歧义）
echo "[2/2] 启动 Web 服务 → http://localhost:8000"
echo ""
.venv/bin/python -m uvicorn datapulse.main:app --host 0.0.0.0 --port 8000
