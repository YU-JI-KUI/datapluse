#!/bin/bash
# Datapluse 启动脚本（uv 版本）

set -e

echo "======================================"
echo "  Datapluse 数据飞轮 - 启动中"
echo "======================================"

# 切换到项目根目录
cd "$(dirname "$0")"

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "[ERROR] 未找到 uv，请先安装："
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 同步依赖（自动创建 .venv）
echo "[1/3] 同步 Python 依赖..."
uv sync

# 确保向量文件目录存在（数据在 PostgreSQL，只有向量文件在本地）
echo "[2/3] 初始化本地目录..."
mkdir -p nas/embeddings nas/vector_index

# 启动服务
echo "[3/3] 启动 Web 服务 → http://localhost:8000"
echo ""
cd backend && uv run python main.py
