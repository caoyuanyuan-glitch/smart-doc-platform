@echo off
echo 智能技术文档平台启动脚本
echo =============================
echo.

cd backend
call venv\Scripts\activate.bat
pip install -r requirements.txt
python init_data.py
start "后端服务" uvicorn app.main:app --host 0.0.0.0 --port 8000

timeout /t 3

cd ..\frontend
npm install
start "前端服务" npm run dev

echo.
echo 服务正在启动...
echo 前端访问地址: http://localhost:5173
pause