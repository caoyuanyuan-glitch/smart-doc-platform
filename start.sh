#!/bin/bash
# 智能技术文档平台 - 一键启动脚本
# 适用于 Linux/Mac 系统

echo "======================================"
echo "  智能技术文档平台 v1.1.9"
echo "======================================"

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 Python3，请先安装 Python"
    exit 1
fi

# 检查 Node.js 是否安装
if ! command -v node &> /dev/null; then
    echo "❌ 错误：未找到 Node.js，请先安装 Node.js"
    exit 1
fi

echo ""
echo "📦 检查并安装后端依赖..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q

echo "✅ 后端依赖安装完成"
echo ""

echo "🔄 初始化数据库..."
python init_data.py

echo "✅ 数据库初始化完成"
echo ""

echo "🚀 启动后端服务 (端口 8000)..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "后端服务 PID: $BACKEND_PID"

# 等待后端启动
sleep 3

echo ""
echo "📦 检查前端依赖..."
cd ../frontend
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm install -q
    echo "✅ 前端依赖安装完成"
fi

echo ""
echo "🚀 启动前端服务 (端口 5173)..."
nohup npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "前端服务 PID: $FRONTEND_PID"

# 等待前端启动
sleep 3

echo ""
echo "======================================"
echo "🎉 服务启动完成！"
echo "======================================"
echo ""
echo "📱 前端访问地址: http://localhost:5173"
echo "🔧 后端API地址: http://localhost:8000"
echo ""
echo "📋 停止服务命令:"
echo "  kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "日志文件:"
echo "  - 后端日志: backend/backend.log"
echo "  - 前端日志: frontend/frontend.log"
echo "======================================"

# 保存 PID 到文件
echo "$BACKEND_PID" > backend.pid
echo "$FRONTEND_PID" > frontend.pid