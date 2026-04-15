# ReflexionOS Backend

FastAPI 后端服务,提供 Agent 执行引擎和 API 接口。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并填写配置项。

## 运行

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 测试

```bash
pytest
```
