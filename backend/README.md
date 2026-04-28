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

## 会话与记忆管线（Phase 1）

这一阶段的实现把“会话事实层”和“记忆/召回能力”拆成了几条清晰的数据面，便于 API、WebSocket、以及执行时上下文组装各自保持简单。

### 核心数据面

- `messages` 是主要的运行时阅读面。
  - HTTP `GET /api/sessions/{session_id}/conversation` 的快照会直接返回 `messages`（以及 `session/turns/runs`）。
  - UI / runtime 需要读取对话内容时，应以 `messages` 为准（包括 tool trace、system notice 等）。

- `conversation_events` 仍然是 append-only 的同步日志。
  - 主要用于 WebSocket 增量同步（`after_seq`）和回放，不建议作为“读对话内容”的主入口。

### Curated Memory（项目级）

- Curated memory 以项目为粒度落盘，目录为：
  - `{memory.base_dir}/projects/<project_id>/USER.md`
  - `{memory.base_dir}/projects/<project_id>/MEMORY.md`
  - 以及对应的 `curated_user.json` / `curated_memory.json`（条目化存储）
- `memory.base_dir` 来自 `app.config.settings.config_manager.settings.memory.base_dir`。
  - 当前默认值是 `~/.reflexion/memory`（可按团队约定改为 `~/.reflexion/memories`）。

### Recall（基于派生检索文档）

- Recall 不直接扫 `messages`，而是读取派生的规范化检索文档：`message_search_documents`。
- `message_search_documents` 会在 message 事件投影时自动维护（创建/内容提交/完成/负载更新都会触发 upsert）。
- 任意 message 只要 payload 中带 `exclude_from_recall=true`，就不会进入检索索引（用于隔离系统派生信息等）。

### Continuation Artifacts（系统派生的续航提示）

- Continuation artifact 是 compaction / post-run compression 导出的系统提示，作为“续航交接条”持久化为真实消息：
  - 表现为 `message_type=system_notice`，payload 中 `kind=continuation_artifact` 且 `derived=true`
  - 默认 `display_mode=collapsed`
  - 同时带有 `exclude_from_recall=true` / `exclude_from_memory_promotion=true`
- Context assembly（运行时三层上下文）会把“最新的一条 continuation artifact 内容”作为 supplemental block 注入执行。

## 测试

```bash
PYTHONPATH=. pytest
```
