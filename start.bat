@echo off
chcp 65001 >nul
echo ======================================
echo   智能技术文档平台 v1.1.9
echo ======================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查 Node.js 是否安装
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误：未找到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

echo.
echo 📦 检查并安装后端依赖...
cd backend
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q

echo ✅ 后端依赖安装完成
echo.

echo 🔄 初始化数据库...
python init_data.py

echo ✅ 数据库初始化完成
echo.

echo 🚀 启动后端服务 (端口 8000)...
start "后端服务" uvicorn app.main:app --host 0.0.0.0 --port 8000

REM 等待后端启动
timeout /t 3 /nobreak >nul

echo.
echo 📦 检查前端依赖...
cd ..\frontend
if not exist node_modules (
    echo 安装前端依赖...
    npm install -q
    echo ✅ 前端依赖安装完成
)

echo.
echo 🚀 启动前端服务 (端口 5173)...
start "前端服务" npm run dev

REM 等待前端启动
timeout /t 3 /nobreak >nul

echo.
echo ======================================
echo 🎉 服务启动完成！
echo ======================================
echo.
echo 📱 前端访问地址: http://localhost:5173
echo 🔧 后端API地址: http://localhost:8000
echo.
echo 📋 停止服务: 关闭弹出的命令窗口即可
echo ======================================

pause