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

**Agent 层 `agent_service.reset_session(session_id)`（参照已有 `edit_and_rerun` 的范式）：**

1. 校验 session 存在，否则抛 `NotFoundValueError`。
2. **写锁外**先停 run：解析当前 active run（`resolve_active_run_id_from_conversation`），若有则 `await self.cancel_run(run_id)`。
   - `cancel_run` 已实现完整的"先停"：发送取消事件、`task.cancel()`、轮询等待任务真正结束、再落库取消状态。
   - 为什么放写锁外：`cancel_run` 内部会自行短暂获取写锁并 `await` 任务结束，若整段持锁会与之冲突死锁。这与 `edit_and_rerun` 的做法一致。
3. 调用 `conversation_service.reset_session(session_id)` 清库（清库段在写锁内重新校验，见下）。

> **关于原子性（修订）**：第 2 步的 `cancel_run` 是异步取消，本身不持有贯穿到清库的写锁，因此「取消完成」到「进入清库段」之间存在并发窗口（理论上极小，但不为零）。本方案不声称端到端原子，而是把约束收紧为：清库段进入写锁后**重新校验**该 session 已无 active run（`active_turn_id` 对应的 run 不处于运行/等待审批态）。若校验发现仍有活跃 run（极端竞态：取消后又被拉起），则放弃删除并返回冲突错误，由前端重试，绝不在有活跃 run 时删库。

**Service 层 `ConversationService.reset_session(session_id)`：**

在该 session 的写锁（`acquire_session_write_lock`）+ 一个 DB 事务内：

1. 重读 session，校验无活跃 run（见上「关于原子性」）；有则抛冲突错误，不删。
2. 取该 session 全部 turn（`turn_repo.list_by_session`）的 id 列表。
3. 级联删除（复用已有删除原语，与 `truncate_after_message` 同源）：
   - `message_search_repo.delete_by_turn_ids`
   - `message_repo.delete_by_turn_ids`
   - `run_repo.delete_by_turn_ids`
   - `event_repo.delete_by_turn_ids`
   - `turn_repo.delete_by_session_after_index(session_id, 0)`（从 turn_index 0 起，等价于全删）
4. 重置 `SessionModel`：`active_turn_id = None`、`last_event_seq = 0`。

> 语义等价于"把会话截断到第 0 个 turn 之前"，即清空所有 turn，但保留 session 行本身。

### 5.3 前端：成功后才清显示（并同步两类真值）

清空聊天区只是其中一步。后端 reset 会改变两类前端依赖的"真值"，必须一并同步，否则侧边栏会显示陈旧状态：

- **会话列表真值（`session.store` 的 `SessionSummary`）**：侧边栏的标题、忙碌态、未读判断读的是 `session.store`，而非 `conversation.store`。现有 `updateSession` / `deleteSession` 都会 `upsertSession` + `ensureProjectSessionsLoaded` 来回写；reset 也必须照做，否则列表里这条会话的 `lastEventSeq` / `activeTurnId` 还停在旧值。
- **未读已读基线（`workspace.store` 的 `lastSeenEventSeqBySessionId`）**：`markSessionSeen` 是**单调递增**的（`lastEventSeq <= current` 直接 return）。后端 `last_event_seq` 清零后从 1 重新计数，但前端 seen 仍停在旧高位（如 120），会导致重置后新消息在 1..120 区间**永远判不出未读**。必须把该会话的 seen 基线强制回退到 0。

**API client：** 新增 `resetSession(sessionId)`，对应 `POST /api/sessions/{id}/reset`，返回重置后的 `Session`。

**新增 store 动作 `workspace.store.resetSessionSeen(sessionId)`：** 把 `lastSeenEventSeqBySessionId[sessionId]` 删除/置 0。这是 `markSessionSeen` 之外唯一允许让 seen **回退**的入口，专供 reset 使用，不破坏正常路径的单调性。

**改造 `resetConversationRuntime`（`useConversationRuntime.ts`）：**

1. `await resetSession(currentSessionId)`，拿到返回的 Session。
2. 成功后同步真值与显示（顺序无强依赖，但都在成功分支内）：
   - `clearConversation(currentSessionId)` — 清 conversation 内存快照。
   - `upsertSession(projectId, session)` — 用返回的 Session 回写列表真值（计数已清零）。
   - `resetSessionSeen(currentSessionId)` — 回退未读基线，避免"永不未读"。
   - 关 WS、清取消标志（保持原有行为）。
3. 失败则**不**清前端任何状态，弹出错误提示（避免前端清空、后端没清导致的不一致）。

> 备选：第 2 步也可只调 `ensureProjectSessionsLoaded(projectId)` 全量补拉列表，与 `updateSession`/`deleteSession` 完全对齐；但 reset 接口已返回单个 Session，`upsertSession` 更省一次往返。实现时二选一，plan 里定。

**二次确认：** 重置是破坏性操作，按钮点击后弹出确认对话框（"确定要清空当前会话的全部对话记录吗？此操作不可恢复。"），确认后才真正调用。

### 5.4 数据流

```
用户点"重置对话"
  → 前端二次确认
  → POST /api/sessions/{id}/reset
      → agent_service.reset_session
          → (写锁外, 若有 active run) cancel_run  [先停，等任务真正结束]
          → conversation_service.reset_session  [写锁内: 重校验无活跃run → 级联删库 → 重置 session 计数]
      → 返回 Session
  → 前端(成功分支):
        clearConversation        [清聊天区快照]
        upsertSession(Session)    [同步会话列表真值]
        resetSessionSeen(id)      [回退未读基线]
        关 WS + 清取消标志
  → 用户看到空白对话, 侧边栏状态同步清零
```

## 6. 边界与降级

- **空会话重置**：没有任何 turn 时，重置应是幂等无害的（删除 0 行，session 计数已是 0），返回成功。
- **会话不存在**：返回 NotFound 错误（复用 `value_error_to_app_error`）。
- **运行中重置**：先 `cancel_run`（写锁外）等待真正停止，再进清库段；清库段在写锁内**重新校验**已无活跃 run，校验失败返回冲突错误由前端重试，绝不在有活跃 run 时删库。写锁保证清库段本身不会有新事件并发插入。
- **取消与清库之间的竞态**：`cancel_run` 完成到进入写锁之间存在极小窗口（见 5.2「关于原子性」）。靠写锁内重校验兜底，而非声称端到端原子。
- **后端失败 / 返回冲突**：前端不清空任何显示与列表/未读状态，提示用户重试，保持前后端一致。
- **未读基线回退**：reset 成功后必须 `resetSessionSeen`，否则后端计数清零、前端 seen 仍在旧高位，会"永不未读"（见 5.3）。
- **会话列表真值同步**：reset 成功后必须用返回的 Session `upsertSession`（或全量补拉），否则侧边栏标题/忙碌/未读读到的仍是旧 `SessionSummary`（见 5.3）。
- **重置当前正在查看的会话 vs 后台会话**：HTTP 入口对两者一视同仁；后台会话重置后，下次切回拉快照得到空白。

## 7. 测试策略

**后端：**

- `ConversationService.reset_session`：建若干 turn/run/message/event/search 后重置，断言全部清空、`active_turn_id=None`、`last_event_seq=0`；空会话重置幂等。
- `ConversationService.reset_session` 冲突路径：写锁内重校验发现仍有活跃 run 时，抛冲突错误且**不删任何数据**。
- `agent_service.reset_session`：有 active run 时先调用 `cancel_run` 再清库（mock 校验调用顺序）；无 active run 时直接清库。
- API：`POST /sessions/{id}/reset` 返回 200 + 重置后的 session；会话不存在返回错误；冲突返回相应错误码。

**前端：**

- `resetConversationRuntime` 成功路径：调用 `resetSession` 后才 `clearConversation` + `upsertSession`（同步列表真值）+ `resetSessionSeen`（回退未读基线）+ 关 WS。
- `resetConversationRuntime` 失败路径：不 `clearConversation`、不 `upsertSession`、不动未读基线，保持原状并提示。
- `workspace.store.resetSessionSeen`：把指定会话的 seen 置 0，且不影响其他会话；验证它是 `markSessionSeen` 单调性之外唯一的回退入口。
- 未读派生回归：reset 后 seen=0，后端从 1 重新计数时新事件能正确判为未读（覆盖 1..旧高位 区间）。
- `WorkspaceHeader` / `AgentWorkspace`：点击按钮触发二次确认，确认后才调用。
