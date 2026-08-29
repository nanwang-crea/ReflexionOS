# 子 Agent 事件处理修复总结

## 修复后的状态

子 agent 事件现在走实时事件专线：

1. 后端把子 agent 事件广播为 `sub_agent:*`
2. 前端 WebSocket 层转换为 `sub_agent:event`
3. `useConversationRuntime` 用当前连接的 `sessionId` 写入 `useSubAgentEventsStore`
4. store 按 `sessionId + delegate_call_id` 分组
5. `DelegateToolCall` 和 `SubAgentDetailPanel` 读取对应子任务步骤并展示工具状态、输出和审批卡片

普通 conversation reducer 仍保留 `sub_agent:` 前缀兼容处理，但它不再是子 agent 实时步骤展示的主路径。

## 已修复的问题

- 子 agent 事件不会再被普通消息流吞掉或错误平铺到父会话里
- 多会话并行时，相同 `delegate_call_id` 不会串台
- 会话重置会清理对应 session 的子 agent 步骤
- 子 agent 的审批 payload 统一用 `buildApprovalDetailFromPayload` 解析
- 子 agent 详情面板能正确配对并发工具调用的 `tool:start` / `tool:result`
- 子 agent 的 `trust_and_allow` 会写入父 session trust rules
- 父 run 取消时，会过期同 session 中尚未处理的子 agent pending approvals
- 后端 run 结束后会清理 session approval flow 引用，避免残留旧对象

## 关键文件

- `backend/app/tools/delegate_tool.py`
- `backend/app/agents/sub_agent_runner.py`
- `backend/app/services/agent_service.py`
- `backend/app/execution/approval_store.py`
- `frontend/src/services/sessionConversationWebSocket.ts`
- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/hooks/useSubAgentEvents.ts`
- `frontend/src/components/workspace/DelegateToolCall.tsx`
- `frontend/src/components/workspace/SubAgentDetailPanel.tsx`
- `frontend/src/components/execution/receiptUtils.ts`

## 主要测试

- `backend/tests/test_execution/test_sub_agent_runner.py`
- `backend/tests/test_execution/test_approval_store.py`
- `backend/tests/test_services/test_agent_service.py`
- `frontend/src/hooks/__tests__/useSubAgentEvents.test.ts`
- `frontend/src/hooks/__tests__/useConversationRuntime.multi-session.test.ts`
- `frontend/src/hooks/__tests__/useConversationRuntime.test.ts`
- `frontend/src/components/workspace/__tests__/SubAgentDetailPanel.test.ts`
- `frontend/src/components/execution/__tests__/receiptUtils.test.ts`

## 后续注意

新增子 agent 事件时，优先接入 WebSocket `sub_agent:event` 和 `useSubAgentEventsStore`。只有需要持久化到父会话历史的事件，才应进入普通 conversation event / reducer 路径。
