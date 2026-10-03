# ReflexionOS 执行层事件地图（Event Map）

> 创建：2026-10-02 ｜ 对应 Spec：[2026-10-02-session-replay-testing-design.md](superpowers/specs/2026-10-02-session-replay-testing-design.md)
> 覆盖范围：`backend/app/execution/`、`backend/app/agents/`（服务层 / WebSocket 层事件不在本图，见文末说明）
> 活性保障：`backend/tests/test_execution/test_event_map.py` 双向比对本表与代码——**新增/删除事件必须同步更新本表，否则测试失败**。

## 事件流总览

```
RapidExecutionLoop / ToolCallExecutor
        │  await self._emit(event_type, payload)
        ▼
event_callback（注入，agent_service 装配）
        ├──► ConversationRuntimeAdapter.handle_event  ──► ConversationEvent 落库（事件溯源）
        └──► WebSocket 广播 ──► 前端实时渲染
```

只有 `rapid_loop.py` 与 `tool_call_executor.py` 两个文件直接发射事件；`sub_agent_runner.py` 不发射新事件类型，它创建嵌套 `RapidExecutionLoop` 并透传 `event_callback`，子 agent 复用同一套事件。

**持久 / 瞬态的判定**：经 `ConversationRuntimeAdapter` 翻译为 `ConversationEvent` 落库的为**持久**（负载契约不可破坏，影响历史回放）；仅用于实时推送的为**瞬态**。特殊：`llm:content` / `llm:reasoning` / `summary:token` 是瞬态增量事件，但其内容会被适配器缓冲、在消息边界批量落库为消息段落。

## 事件清单

### Run 生命周期（6 种，全部持久）

| 事件类型 | 生产者 | 消费者 | 负载字段 | 持久/瞬态 |
|---|---|---|---|---|
| `run:start` | rapid_loop.py `run()` | 适配器→落库；前端 | `run_id`, `task` | 持久 |
| `run:complete` | rapid_loop.py `run()` | 适配器→落库；前端 | `status`, `result`, `total_steps`, `duration` | 持久 |
| `run:error` | rapid_loop.py `run()` 异常收尾 | 适配器→落库；前端 | `error` | 持久 |
| `run:cancelled` | rapid_loop.py `run()` 取消收尾（两处发射点） | 适配器→落库；前端 | `status`, `result`, `total_steps` | 持久 |
| `run:waiting_for_approval` | rapid_loop.py `_handle_approval` | 适配器→落库；前端审批 UI | `run_id`, `approval_id`, `step_number`, `tool_name`, `tool_call_id` | 持久 |
| `run:resuming` | rapid_loop.py `_handle_approval`（批准/拒绝两处） | 适配器→落库；前端 | `run_id`, `approval_id`, `execution_success`；拒绝时附加 `approval_rejected: true` | 持久 |

### 工具调用（4 种，全部持久）

| 事件类型 | 生产者 | 消费者 | 负载字段 | 持久/瞬态 |
|---|---|---|---|---|
| `tool:start` | tool_call_executor.py `execute()` | 适配器→落库（创建工具消息）；前端 | `tool_name`, `arguments`, `tool_call_id`, `step_number` | 持久 |
| `tool:result` | tool_call_executor.py `execute()` 正常返回路径；rapid_loop.py 审批批准重放路径 | 适配器→落库（工具消息终态）；前端 | `tool_name`, `tool_call_id`, `success`, `output`, `error`, `duration`，外加 `result.data` 的扩展字段（如有） | 持久 |
| `tool:error` | rapid_loop.py（只读批次收尾、写操作收尾、审批拒绝三处） | 适配器→落库（等价失败的 tool:result）；前端 | `tool_name`, `tool_call_id`, `step_number`, `error`, `duration`；多数发射点带 `success: false`, `output`；审批拒绝变体带 `arguments`、无 `output` | 持久 |
| `approval:required` | tool_call_executor.py `execute()` 审批分支 | 适配器→落库；前端审批 UI | `tool_name`, `arguments`, `tool_call_id`, `approval_id`, `step_number`, `approval`（ToolApprovalRequest 序列化）, `run_id`（子 agent 场景前端关联用） | 持久 |

> 注意 `tool:result` 与 `tool:error` 的分工：**工具正常返回但失败**（`success=False`）走 `tool:result`；**工具抛异常**由 executor 捕获转为 FAILED 步骤、交回主循环发 `tool:error`。适配器对两者都做终态处理且幂等（已终态的消息跳过）。

### LLM 流式（3 种，全部瞬态）

| 事件类型 | 生产者 | 消费者 | 负载字段 | 持久/瞬态 |
|---|---|---|---|---|
| `llm:content` | rapid_loop.py `_call_llm` / 重压重跑路径（on_content 回调，协程内 fire-and-forget） | 前端打字机渲染；适配器仅缓冲不落库 | `content`（增量文本片段） | 瞬态（内容随消息段落批量落库） |
| `llm:reasoning` | rapid_loop.py 同上（on_reasoning 回调） | 前端推理过程展示；适配器仅缓冲 | `reasoning_content`（增量片段） | 瞬态（同上） |
| `summary:token` | rapid_loop.py `_get_final_summary` 流式循环 | 前端最终总结渲染；适配器缓冲 | `token`（增量片段） | 瞬态（同上） |

### 计划与指标（2 种，全部瞬态）

| 事件类型 | 生产者 | 消费者 | 负载字段 | 持久/瞬态 |
|---|---|---|---|---|
| `plan:updated` | rapid_loop.py `run()` 收尾；tool_call_executor.py PlanTool 调用后 | 前端计划面板 | `Plan.to_dict()` 全部字段 | 瞬态（计划本体由 PlanFileSync 落盘，不经事件日志） |
| `metrics:llm_call` | rapid_loop.py `_emit_llm_metrics`（每次 LLM 调用后） | 前端监控展示 | `run_id`, `model`, `attempt`, `duration`, `first_chunk_latency`, `prompt_tokens`, `message_count`, `tool_count`, `finish_reason`, `content_chars`, `reasoning_chars`, `tool_call_count`；出错时附加 `error` | 瞬态（适配器不处理） |

**合计 15 种事件**（早先粗扫的 16 种中，`goal:` 为 prompt 文本非事件，`tool:error` 文档字符串提及非发射点，已剔除）。

## 维护规则

1. **新增事件**：先在代码中实现 → 在本表登记（含全部列）→ 活性测试通过。
2. **修改持久事件的负载**：只允许**新增**字段，不得改名/删除/改语义——历史会话回放依赖旧负载。
3. **修改瞬态事件负载**：可改，但需同步检查前端消费点与适配器缓冲逻辑。
4. **删除事件**：代码移除后同步删除本表条目（活性测试双向比对，漏删会失败）。

## 范围说明

本图只覆盖执行层。以下层级的"事件"不在此列：`services/conversation_runtime_adapter.py` 产出的 `ConversationEvent`（`EventType.*`，事件溯源持久层，契约由 `conversation_projection.py` 与存储模型约束）、`websocket_manager.py` 的传输层消息。这两层若需要同等待遇，另立文档。
