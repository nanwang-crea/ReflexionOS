# Plan 全量替换改造设计

## 背景

当前 Plan 系统采用增量操作模式（create → step_done / block / adjust），导致 LLM 容易"忘记"调用 plan tool 更新状态。为弥补此缺陷，系统通过多层消息注入（SYSTEM render + USER Focus + USER Audit + tool result anchor）持续提醒 LLM，造成大量 token 浪费（每次 LLM 调用 plan 相关信息被重复注入 2-3 条消息）。

参考 Crush（原 OpenCode）的 `todos` 工具设计：LLM 每次调用传入完整步骤列表，tool 全量替换存储。这使得 plan 状态天然存在于 tool result 历史中，无需任何额外消息注入。

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Tool 调用模式 | 单一 action，全量替换 | 与 Crush 对齐，消除"忘记更新"问题 |
| 消息注入 | 全部删除 | plan 状态通过 tool result 传递，不需要额外注入 |
| Plan 数据模型 | 简化：删除 id、current_step_index | 由 in_progress 状态隐式确定当前步骤 |
| 文件持久化 | 保留，改为 session 级路径 | 用于恢复和查看 |
| runtime_tool_definitions | 统一为单一 schema | 不再区分 create / progress schema |

## 改造详情

### 1. PlanTool：统一为单一全量替换

**删除**：`get_create_schema()`、`get_progress_schema()`、`_create()`、`_step_done()`、`_block()`、`_adjust()`

**新 schema**：

```json
{
  "name": "plan",
  "description": "Manage execution plans for multi-step tasks. Send the full step list each call. Keep exactly one step in_progress at a time. Skip for simple tasks that need fewer than 3 steps.",
  "parameters": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "goal": {
        "type": "string",
        "description": "Overall goal (required on first call, optional after)"
      },
      "steps": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "content": {
              "type": "string",
              "description": "What needs to be done (imperative form)"
            },
            "status": {
              "type": "string",
              "enum": ["pending", "in_progress", "completed", "blocked"],
              "description": "Step status"
            },
            "findings": {
              "type": "string",
              "description": "Key results when completed (required when status=completed)"
            }
          },
          "required": ["content", "status"]
        },
        "minItems": 1,
        "maxItems": 12,
        "description": "The complete step list. Send ALL steps every time, including already completed ones."
      }
    },
    "required": ["steps"]
  }
}
```

**Tool result 格式**：

```
Plan updated. 2 pending, 1 in_progress, 3 completed.
[Current] Fix the authentication module
Ensure you use the plan to track your progress. Proceed with the current step.
```

**返回 metadata**（供前端渲染）：

```json
{
  "is_new": true,
  "just_completed": ["Analyze the codebase"],
  "just_started": "Fix the authentication module",
  "completed": 3,
  "total": 6
}
```

**执行逻辑**：

1. 解析传入的 steps 列表
2. 验证：恰好一个 in_progress 或 0 个（全部完成/全部待定）
3. 如果 goal 为空且尚未有 plan → 返回错误
4. 如果 goal 非空且尚无 plan → 创建新 plan
5. 全量替换 plan.steps，更新 plan.goal（如果提供）
6. 对比旧 steps 识别状态变更（just_completed / just_started）
7. 触发 plan_file_sync 持久化
8. 返回 tool result

### 2. PlanEngine：简化数据模型

**PlanStep**：

```python
@dataclass
class PlanStep:
    content: str
    status: Literal["pending", "in_progress", "completed", "blocked"] = "pending"
    findings: str = ""
```

**删除字段**：`id`（LLM 通过内容识别步骤）、`cancelled`/`failed` 状态

**Plan**：

```python
@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
```

**删除字段**：`current_step_index`

**删除方法**：`advance()`、`block()`、`adjust_remaining()`、`finalize_for_completion()`、`finalize_for_failure()`、`finalize_for_cancellation()`

**保留方法**：
- `current_step`（property）：返回唯一的 in_progress 步骤
- `is_complete`（property）：所有步骤 completed
- `completed_findings()`：返回已完成步骤的 findings（用于 compaction 摘要参考）
- `render_for_context()`：保留但简化，仅用于文件持久化和前端展示
- `render_to_markdown()` / `parse_from_markdown()`：适配新格式

**新增方法**：
- `replace_from(steps, goal=None)`：全量替换，对比旧 steps 计算状态变更

### 3. 消息注入：全部删除

**loop_message_builder.py**：

- `build()` 中删除整个 `if context.plan:` 块（render_for_context + Focus + Audit 的 SYSTEM 注入）
- `build_final_summary()` 中删除 plan 相关注入

**tool_call_executor.py**：

- 删除 `plan_update_required` / `steps_since_last_plan_update` 计数逻辑（line 191-202）
- 删除 plan_file_sync 调用（line 196-198，改由 tool 内部处理）

**rapid_loop.py**：

- 删除 `steps_since_last_plan_update` 追踪
- 删除 `_confirm_plan_exit` 中的 plan_file_sync 调用
- finally 块中 plan 相关逻辑简化（删除 finalize 调用，保留 plan_file_sync 用于 session 结束时最终持久化）

### 4. RuntimeToolDefinitions：统一 schema

- 删除 `get_create_schema()` 和 `get_progress_schema()` 的区分
- `for_initial_plan()`：暴露统一的 plan schema
- `for_context()`：无论 plan 是否存在，始终暴露同一个 schema
- PlanTool 只保留一个 `get_schema()` 方法

### 5. 文件持久化：session 级路径

**plan_file_sync.py**：

- 路径模板：`.reflexion/plans/{session_id}.md`
- `sync()` 方法签名改为 `sync(plan, session_id, project_path)`
- `write()` / `read()` 适配新 markdown 格式

**Markdown 格式**：

```markdown
# Execution Plan
goal: Fix the authentication module

## Steps
- [pending] Write unit tests
- [in_progress] Fix the authentication module
- [completed] Analyze the codebase
  findings: Found bug in auth.py line 42
```

**InitialPlanBootstrapper**：

- 仍负责首轮 LLM 调用生成 plan
- LLM 返回的不再是 `action: "create"`，而是直接的 `steps` + `goal` 参数
- 删除 `if tool_call.arguments.get("action") != "create": continue` 检查
- 删除 `context.metadata["plan_update_required"]` / `steps_since_last_plan_update` 设置
- 恢复逻辑适配：`_check_plan_relevance()` 中 `plan.current_step.description` 改为 `plan.current_step.content`
- plan 文件路径改为 session 级：`plan_file_sync.write(context.plan, session_id=context.session_id, ...)`

### 6. context_manager.py

- `context.plan_file_path` 改为基于 session_id 的路径
- 删除 `context.metadata` 中的 plan 相关键值追踪（`plan_update_required`、`steps_since_last_plan_update`、`_injected_focus_step_id`）

## 涉及文件清单

| 文件 | 改动类型 |
|------|----------|
| `app/tools/plan_tool.py` | 重写 |
| `app/execution/plan_engine.py` | 重写 |
| `app/execution/loop_message_builder.py` | 大幅删除 |
| `app/execution/tool_call_executor.py` | 删除 plan 计数逻辑 |
| `app/execution/rapid_loop.py` | 删除 plan finalize 和计数追踪 |
| `app/execution/runtime_tool_definitions.py` | 简化 schema 选择 |
| `app/execution/plan_file_sync.py` | 改为 session 级路径 |
| `app/execution/initial_plan_bootstrapper.py` | 适配新 schema |
| `app/execution/context_manager.py` | 清理 plan 相关 metadata |
| `tests/test_tools/test_plan_tool.py` | 重写 |
| `tests/test_execution/test_plan_engine.py` | 重写 |
| `tests/test_execution/test_loop_message_builder.py` | 大幅删除 |
| `tests/test_execution/test_rapid_loop.py` | 适配 |
| `tests/test_execution/test_runtime_tool_definitions.py` | 适配 |
| `tests/test_execution/test_plan_file_sync.py` | 适配 |

## 预期效果

| 指标 | 改造前 | 改造后 |
|------|--------|--------|
| Plan 相关 SYSTEM/USER 消息 | 每轮 1-3 条 | 0 条 |
| Tool result anchor | 每轮 N 次（每次工具调用） | 0 次 |
| plan_update_required 追踪 | 每轮更新 metadata | 不存在 |
| Plan schema 数量 | 3 个（create/progress/create-only） | 1 个 |
| "call step_done" 指令出现次数 | 6 处 | 0 处（tool description 自包含） |
| Token 估算节省 | — | plan 相关 token 减少 70-80% |
