# ReflexionOS Backend

FastAPI 后端服务,提供 Agent 执行引擎和 API 接口。

## 依赖来源

Python 直接依赖统一以 `requirements.txt` 为准，`pyproject.toml` 不重复声明依赖。
运行时版本以仓库根目录的 `.python-version` 为准（当前 3.12.14），虚拟环境统一使用 `backend/.venv`。
`requirements.lock` 由 uv 生成，固定直接及间接依赖，并保留 Windows/macOS 平台条件。
安装时使用锁文件；修改依赖时同步重新生成锁，命令见[根 README](../README.md#development-baseline)。

## 安装依赖

从仓库根目录执行，先确认所用 Python 版本符合 `.python-version`。

Windows（PowerShell）：

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
```

macOS：

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
```

不要从其他机器复制 `.venv`。前端安装和 Chromium/分词缓存准备见[根 README](../README.md#recommended-desktop-development-path)。

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
# 在 backend/ 目录中激活 .venv 后执行。
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
- 有 `project_path` 时：`{project_path}/.reflexion/memory.md`
- 无 `project_path` 时：`{memory.base_dir}/projects/<project_id>/memory.md`
- 存储 format 为 Markdown（单一数据源，无 JSON），按 `## Section` 分组（Preference / Rule / Constraint / Fact），每个条目为 `- content` 列表项。
- `memory.base_dir` 来自 `app.config.settings.config_manager.settings.memory.base_dir`。
  - 当前默认值是 `~/.reflexion/memory`（可按团队约定改为 `~/.reflexion/memories`）。

### Recall（基于派生检索文档）

- Recall 不直接扫 `messages`，而是读取派生的规范化检索文档：`message_search_documents`。
- `message_search_documents` 会在 message 事件投影时自动维护（创建/内容提交/完成/负载更新都会触发 upsert）。
- 任意 message 只要 payload 中带 `exclude_from_recall=true`，就不会进入检索索引（用于隔离系统派生信息等）。

### Continuation Artifacts（系统派生的续航提示）

- Continuation artifact 是 compaction / post-run compression 导出的系统提示，作为“续航交接条”持久化为真实消息：
  - 表现为 `message_type=system_notice`，payload 中 `derived=true`
  - 默认 `display_mode=collapsed`
  - 同时带有 `exclude_from_recall=true` / `exclude_from_memory_promotion=true`
- Context assembly（运行时两层上下文：静态 system sections + recent messages）不再注入 supplemental block；LLM 通过 edit 工具直接编辑 .reflexion/memory.md，写入后由 PromptManager 在下一轮自动加载。

## 测试

从仓库根目录使用统一入口，无需激活虚拟环境：

```bash
node scripts/check-baseline.mjs --prepare
node scripts/check-baseline.mjs
```

首次运行和更新 Playwright 后需要 `--prepare`，它会下载匹配版本的 Chromium 和分词数据。
普通检查会验证 Python/Node 版本、完整锁定依赖、直接声明与锁文件的一致性及 `pip check`，隔离 HOME/USERPROFILE、工作目录和临时目录，然后执行所有后端测试、前端测试与构建。

日志、JUnit 报告、Python 包快照和整体状态写入 `.baseline/run-*/`。任一阶段失败都会返回非零退出码，缺少浏览器不会自动跳过集成测试。

后端单独调试时可以使用 `.venv` 的 Python 运行指定 pytest 文件，但直接调用 pytest 不具备上述用户数据隔离，不作为完整基线结果。
当前复核结果和未验证项见[项目状态](../docs/PROJECT_STATUS.md)。
