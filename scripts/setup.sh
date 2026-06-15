#!/bin/bash
echo "Setting up development environment..."

# Backend setup
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q
python init_data.py

# Frontend setup
cd ../frontend
if [ ! -d "node_modules" ]; then
    npm install
fi

echo "Setup complete!"
echo "To start the project, run:"
echo "  1. Backend: cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "  2. Frontend: cd frontend && npm run dev"