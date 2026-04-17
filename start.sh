#!/bin/bash

# ReflexionOS 启动脚本

echo "========================================"
echo "       ReflexionOS 启动脚本"
echo "========================================"
echo ""

# 启动后端
echo "[1/2] 启动后端服务..."
cd backend
source venv/bin/activate 2>/dev/null || true
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端
echo "[2/2] 启动前端服务..."
cd frontend
pnpm dev:web &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================"
echo "服务已启动！"
echo ""
echo "后端 API: http://127.0.0.1:8000"
echo "前端 UI:  http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo "========================================"
echo ""

# 等待子进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
