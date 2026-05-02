#!/bin/bash
# 构建前端静态文件 + 文档站（生产部署前执行一次）

set -e
cd "$(dirname "$0")"

echo "======================================"
echo "  Datapulse - 构建"
echo "======================================"

cd frontend

# ── 1. 安装依赖（含 VitePress）─────────────────────────────────────────────
echo ""
echo "[1/3] 安装依赖..."
npm install

# ── 2. 构建文档站（输出到 public/docs/，Vite build 时会自动复制）──────────
echo ""
echo "[2/3] 构建文档站..."
npm run docs:build
echo "      ✓ frontend/public/docs/ 已生成"

# ── 3. 构建 React 应用（同时打包 public/docs/ 进 dist/）──────────────────
echo ""
echo "[3/3] 构建 React 应用..."
npm run build
echo "      ✓ frontend/dist/ 已生成（含 dist/docs/）"

cd ..

# ── 完成 ────────────────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  构建完成！"
echo "======================================"
echo "  前端：frontend/dist/"
echo "  文档：frontend/dist/docs/  → 访问路径 /docs"
echo ""
echo "  现在运行 ./start.sh 启动服务"
