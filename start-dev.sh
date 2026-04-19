#!/bin/bash

# ReflexionOS 备用 Web 开发启动脚本 (Git Bash / WSL)

echo "========================================"
echo " ReflexionOS 备用 Web 开发启动脚本"
echo "========================================"
echo ""

PYTHON_BIN="${REFLEXION_PYTHON_PATH:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

# 启动后端（依赖来源: backend/requirements.txt）
echo "[1/2] 启动后端服务..."
cd backend
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true
"$PYTHON_BIN" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 启动前端 Web 调试界面
echo "[2/2] 启动前端 Web 调试界面..."
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
echo "推荐桌面开发: cd frontend && pnpm dev"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo "========================================"
echo ""

# 等待子进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
