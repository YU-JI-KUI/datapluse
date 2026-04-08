#!/bin/bash
# 构建前端并复制到 backend/static

set -e
cd "$(dirname "$0")"

echo "======================================"
echo "  Datapulse - 构建前端"
echo "======================================"

cd frontend

echo "[1/3] 安装 npm 依赖..."
npm install

echo "[2/3] 构建 React 应用..."
npm run build

echo "[3/3] 完成! dist/ 已生成"
echo "现在运行 ./start.sh 启动服务"
