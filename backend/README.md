# ReflexionOS Backend

FastAPI 后端服务,提供 Agent 执行引擎和 API 接口。

## 依赖来源

Python 依赖统一以 `requirements.txt` 为准。`pyproject.toml` 不再声明依赖。

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并填写配置项。

## 桌面开发

推荐从仓库根目录执行 `cd frontend && pnpm dev`。

Electron 会在启动时探测一个满足 `backend/requirements.txt` 的 Python 环境并自动拉起后端。

如果自动探测失败,可以显式设置:

```bash
export REFLEXION_PYTHON_PATH=/path/to/python
```

## 备用 Web / 后端单独调试

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 测试

```bash
PYTHONPATH=. pytest
```
