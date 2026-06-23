# ReflexionOS 重置对话功能设计

## 1. 背景

工作区头部已经有一个"重置对话"按钮（`WorkspaceHeader.tsx`），但它目前**没有实际效果**。

当前点击按钮触发 `useConversationRuntime.ts` 的 `resetConversationRuntime`，它只做三件**纯前端**的事：

1. `closeSessionConnection(currentSessionId)` — 关掉当前会话的 WebSocket 连接
2. `setSessionCancelling(currentSessionId, false)` — 清掉前端取消标志
3. `clearConversation(currentSessionId)` — 清掉前端内存里缓存的会话快照

后端的对话数据（DB 中的 turns / runs / messages / conversation_events / message_search_documents，均按 `session_id` 级联）完全没有改动。Agent 每次执行都从 DB 重建上下文，没有独立的内存历史。

因此，用户一旦切走再切回该会话，或前端重新拉取快照（`GET /api/sessions/{id}/conversation`），旧对话会原样恢复。按钮看起来"没有意义"。

## 2. 目标

让"重置对话"按钮真正生效，语义为**清空历史、保留会话**：

- 同一个会话 ID、标题、在列表/标签中的位置都不变。
- 该会话的对话记录被清空，变回一个空白对话。
- **重新进入该会话也不会恢复旧对话**（因为 DB 中的数据被真实删除）。
- 若点击重置时该会话正有 run 在执行，**先停止该 run，再清空历史**（先停后清）。
- Agent 后续在该会话执行时，从空的 DB 重建上下文，不再携带旧历史。

## 3. 非目标

- 不删除会话本身（会话 ID / 标题 / 配置保留）。
- 不提供"撤销重置 / 回收站"能力，重置即真实删除，不可恢复。
- 不重置会话的 LLM provider / model 偏好、agent_mode 等配置项（这些不属于"对话历史"）。
- 不影响其他会话。
- 不清理与对话无关的资源（如已上传附件文件、浏览器实例）——除非后续明确需要。

## 4. 用户故事

### 4.1 在当前会话重新开始

作为用户，我在一个会话里聊了很久、上下文已经发散，我希望点"重置对话"把这个会话清空，从头开始，而不必新建一个会话、丢掉当前标签位置。

### 4.2 重进不恢复

作为用户，我重置后切到别的会话再切回来，期望看到的仍是空白对话，而不是旧记录又冒出来。

### 4.3 运行中也能重置

作为用户，如果当前会话正在执行任务，我点重置时，期望系统先把正在跑的任务安全停掉，再清空，而不是留下半截脏数据或报错。

## 5. 方案

### 5.1 入口：HTTP `POST /api/sessions/{session_id}/reset`

选择 HTTP 而非 WebSocket 消息的原因：

- 多会话并行模型下，WS 连接按优先级**动态连接 / 回收**（见 `useConversationRuntime` 调度逻辑），后台会话可能当前未连 WS。重置必须"任何会话、任何时刻都能干净执行"，HTTP 不依赖连接状态。
- 重置是破坏性、一次性操作，请求-响应模型语义清晰、易测试、易处理失败。
- 与现有 `DELETE /api/sessions/{id}`、`PATCH /api/sessions/{id}` 风格一致。

接口返回重置后的会话对象（`Session`），或在会话不存在时走现有错误处理（`value_error_to_app_error`）。

### 5.2 后端：先停后清

**Agent 层 `agent_service.reset_session(session_id)`：**

1. 查询 session，取 `active_turn_id`；若有对应的 active run，`await self.cancel_run(run_id)`。
   - `cancel_run` 已实现完整的"先停"：发送取消事件、`task.cancel()`、轮询等待任务真正结束、再落库取消状态。
2. 调用 `conversation_service.reset_session(session_id)` 清库。

**Service 层 `ConversationService.reset_session(session_id)`：**

在该 session 的写锁（`acquire_session_write_lock`）+ 一个 DB 事务内：

1. 取该 session 全部 turn（`turn_repo.list_by_session`）的 id 列表。
2. 级联删除（复用已有删除原语，与 `truncate_after_message` 同源）：
   - `message_search_repo.delete_by_turn_ids`
   - `message_repo.delete_by_turn_ids`
   - `run_repo.delete_by_turn_ids`
   - `event_repo.delete_by_turn_ids`
   - `turn_repo.delete_by_session_after_index(session_id, 0)`（从 turn_index 0 起，等价于全删）
3. 重置 `SessionModel`：`active_turn_id = None`、`last_event_seq = 0`。

> 语义等价于"把会话截断到第 0 个 turn 之前"，即清空所有 turn，但保留 session 行本身。

### 5.3 前端：成功后才清显示

**API client：** 新增 `resetSession(sessionId)`，对应 `POST /api/sessions/{id}/reset`。

**改造 `resetConversationRuntime`（`useConversationRuntime.ts`）：**

1. `await resetSession(currentSessionId)`。
2. 成功后再执行原有三步：关 WS、清取消标志、`clearConversation`。
3. 失败则不清前端显示，弹出错误提示（避免前端清空、后端没清导致的不一致）。

**二次确认：** 重置是破坏性操作，按钮点击后弹出确认对话框（"确定要清空当前会话的全部对话记录吗？此操作不可恢复。"），确认后才真正调用。

### 5.4 数据流

```
用户点"重置对话"
  → 前端二次确认
  → POST /api/sessions/{id}/reset
      → agent_service.reset_session
          → (若有 active run) cancel_run  [先停，等任务真正结束]
          → conversation_service.reset_session  [写锁+事务内级联删库 + 重置 session 计数]
      → 返回 Session
  → 前端：关 WS + 清取消标志 + clearConversation  [清显示]
  → 用户看到空白对话
```

## 6. 边界与降级

- **空会话重置**：没有任何 turn 时，重置应是幂等无害的（删除 0 行，session 计数已是 0），返回成功。
- **会话不存在**：返回 NotFound 错误（复用 `value_error_to_app_error`）。
- **运行中重置**：先 `cancel_run` 等待真正停止，再删库，避免孤儿 run 或正在写入的并发冲突；写锁保证清库期间不会有新事件插入。
- **后端失败**：前端不清空显示，提示用户重试，保持前后端一致。
- **重置当前正在查看的会话 vs 后台会话**：HTTP 入口对两者一视同仁；后台会话重置后，下次切回拉快照得到空白。

## 7. 测试策略

**后端：**

- `ConversationService.reset_session`：建若干 turn/run/message/event/search 后重置，断言全部清空、`active_turn_id=None`、`last_event_seq=0`；空会话重置幂等。
- `agent_service.reset_session`：有 active run 时先调用 `cancel_run` 再清库（可用 mock 校验调用顺序）。
- API：`POST /sessions/{id}/reset` 返回 200 + 重置后的 session；会话不存在返回错误。

**前端：**

- `resetConversationRuntime`：成功路径调用 `resetSession` 后才 `clearConversation` + 关 WS；失败路径不清显示。
- `WorkspaceHeader` / `AgentWorkspace`：点击按钮触发二次确认，确认后才调用。
