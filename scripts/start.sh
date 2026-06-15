#!/bin/bash

echo "Starting Smart Doc Platform..."

# Start backend
cd backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
echo "Backend started on http://localhost:8000"

# Start frontend
cd ../frontend
npm run dev -- --host 0.0.0.0 &
echo "Frontend started on http://localhost:5173"

echo ""
echo "=========================================="
echo "Services are starting..."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "=========================================="