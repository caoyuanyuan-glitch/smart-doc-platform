#!/bin/bash

# Smart Doc Platform 一键启动脚本
# 使用方法: bash start.sh

echo "=========================================="
echo "  智能技术文档平台 - 启动脚本"
echo "=========================================="

# 创建必要的目录
mkdir -p backend/static/uploads

# 检查端口
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  端口 8000 已被占用，请先停止占用程序"
fi

if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  端口 5173 已被占用，请先停止占用程序"
fi

echo ""
echo "正在启动后端服务 (端口 8000)..."
cd backend

# 检查是否安装了依赖
if [ ! -d "venv" ]; then
    echo "  └─ 创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt -q

# 启动后端
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  └─ 后端已启动 (PID: $BACKEND_PID)"

sleep 3

# 启动前端
echo ""
echo "正在启动前端服务 (端口 5173)..."
cd ../frontend

if [ ! -d "node_modules" ]; then
    echo "  └─ 安装前端依赖..."
    npm install -q
fi

npm run dev &
FRONTEND_PID=$!
echo "  └─ 前端已启动 (PID: $FRONTEND_PID)"

echo ""
echo "=========================================="
echo "✅  服务启动完成！"
echo "   访问地址: http://localhost:5173"
echo "   后端API:  http://localhost:8000"
echo ""
echo "   停止服务: 按 Ctrl+C"
echo "=========================================="

# 等待用户终止
trap "echo '正在停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
