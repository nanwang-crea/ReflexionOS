# 子 Agent 事件处理机制

## 当前架构

子 agent 事件不进入普通 conversation reducer 的主路径。后端会把子 agent 运行时事件加上 `sub_agent:` 前缀，通过父会话的 WebSocket 直接广播；前端 WebSocket 层会把这些事件转换成 `sub_agent:event`，再写入按 `sessionId + delegate_call_id` 分组的实时 store。

这条链路避免把子 agent 的临时工具步骤持久化成父会话消息，同时仍然能在父 agent 的 `delegate` 工具卡片里实时展示子任务进度和审批卡片。

## 后端事件

`backend/app/tools/delegate_tool.py` 会包装子 agent 事件：

```python
await parent_cb(f"sub_agent:{event_type}", enriched)
```

`enriched` 至少包含：

- `delegate_call_id`：父 agent 的 delegate tool call id
- `parent_session_id`：父会话 id，用于审批响应路由
- `run_id`：子 agent 的 `sub-run-*` 运行 id
- 原始工具 / LLM / approval 事件 payload

`backend/app/services/agent_service.py` 对 `sub_agent:approval:required` 会额外注册 pending approval，使用父 session id 保存，这样用户点击审批时后端能找到对应审批记录。

## 前端事件流

`frontend/src/services/sessionConversationWebSocket.ts` 收到 `sub_agent:*` 后会映射为：

```ts
{
  event_type: 'tool:start' | 'tool:result' | 'approval:required' | string,
  delegate_call_id: string | undefined,
  payload: Record<string, unknown>
}
```

`frontend/src/hooks/useConversationRuntime.ts` 使用当前 WebSocket 连接的 `sessionId` 写入：

```ts
useSubAgentEventsStore.getState().addEvent(sessionId, data)
```

`frontend/src/hooks/useSubAgentEvents.ts` 按双键存储：

```ts
Map<sessionId, Map<delegate_call_id, SubAgentStep[]>>
```

这样多会话并行时，即便不同会话里出现相同的 `delegate_call_id`，也不会互相串台。会话重置时会调用 `clearSession(sessionId)` 清理该会话的子 agent 历史步骤。

## UI 展示

`DelegateToolCall` 从 tool trace detail 中读取：

- `data.tool_call_id`
- `data.session_id`

然后调用：

```ts
useSubAgentSteps(sessionId, callId)
```

子 agent 的实时步骤会展示在：

- delegate 卡片的运行状态与步数
- `SubAgentDetailPanel` 的全屏详情面板
- 子 agent 工具审批卡片

`SubAgentDetailPanel` 会把并发工具调用保留在同一个工具批次里，直到对应 `tool:result` / `tool:error` 到达后再显示终态。

## 审批语义

子 agent 审批沿用父会话 WebSocket：

- 前端审批 payload 带 `parentSessionId`
- WebSocket route 用 `parent_session_id` 找回父会话
- `AgentService` 通过父会话的 approval flow 恢复子 agent loop
- `trust_and_allow` 会写入父 session 的 trust rules
- 父 run 取消时，会过期同 session 下尚未处理的子 agent pending approvals

## Reducer 兼容路径

`conversation.reducer.ts` 仍保留 `sub_agent:` 前缀处理，用于兼容历史或持久化事件输入。但当前实时 UI 的主路径是 WebSocket `sub_agent:event` + `useSubAgentEventsStore`，不是把子 agent 步骤写成普通 conversation messages。

## 主要测试

- `frontend/src/hooks/__tests__/useSubAgentEvents.test.ts`
- `frontend/src/hooks/__tests__/useConversationRuntime.multi-session.test.ts`
- `frontend/src/components/workspace/__tests__/SubAgentDetailPanel.test.ts`
- `frontend/src/components/execution/__tests__/receiptUtils.test.ts`
- `backend/tests/test_services/test_agent_service.py`
- `backend/tests/test_execution/test_approval_store.py`
- `backend/tests/test_execution/test_sub_agent_runner.py`
