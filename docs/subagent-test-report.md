# Subagent Test Report

生成时间：2026-08-11 14:59:02 CST

## 结论

当前工作区全部验证门禁通过。

- 后端完整测试通过：`1096 passed, 38 skipped`
- 前端完整测试通过：`248 passed`
- TypeScript 类型检查通过
- ESLint 通过
- `git diff --check` 通过

前端测试期间出现的 stderr 均来自既有错误路径测试或测试环境缺少持久化 storage 的预期提示，不影响测试结果。

## 测试执行结果

| 序号 | 命令 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 | `python -m pytest backend/tests` | 通过 | `1096 passed, 38 skipped in 62.42s` |
| 2 | `pnpm test` | 通过 | `41 passed` test files, `248 passed` tests |
| 3 | `pnpm exec tsc --noEmit` | 通过 | 无类型错误输出 |
| 4 | `pnpm lint` | 通过 | ESLint `--max-warnings 0` 无失败 |
| 5 | `git diff --check` | 通过 | 无 whitespace / patch 格式问题 |

## 跳过测试说明

后端完整测试中有 `38 skipped`：

- macOS 当前环境下跳过 Windows API / sandbox 相关测试。
- 部分 shell tool Windows event loop / 平台条件测试按平台跳过。

这些跳过项是平台条件约束，不是失败。

## 本次修复问题清单

### 1. Subagent 工具集隔离不完整

问题：

- 子 agent 原先可能复用父 agent 的状态型工具实例。
- `delegate` 递归已规避，但 `plan`、`browser` 这类主会话态工具仍可能被子 agent 继承。
- shell 工具的 session id 可能沿用父 session，导致审批/trust/session 上下文混淆。

修复：

- 子 agent registry 排除 `delegate`、`plan`、`browser`。
- 对 `WorkingMemoryTool`、file/search/edit/patch/explore/skill/shell 等工具做隔离克隆。
- shell 工具重新绑定 child session id。

主要文件：

- `backend/app/agents/sub_agent_runner.py`
- `backend/tests/test_execution/test_sub_agent_runner.py`

### 2. Subagent 审批后没有使用 child loop 的真实 tool registry

问题：

- subagent pending approval 的 `run_id` 是 `sub-run-*`。
- 后端审批执行时只从父 run loop map 查 registry，查不到 child loop 时会退回临时 registry。
- 这可能导致审批后执行工具时丢失 child session、child tool state、child path/security context。

修复：

- `SubAgentRunner` 新增 child loop 生命周期回调。
- `AgentService` 维护 `sub-run-* -> child RapidExecutionLoop` 临时映射。
- `_execute_approved_tool` 优先使用父 loop 或 child loop 的真实 registry。
- child loop 结束后按对象身份安全清理映射。

主要文件：

- `backend/app/agents/sub_agent_runner.py`
- `backend/app/services/agent_service.py`
- `backend/tests/test_services/test_agent_service.py`

### 3. Subagent 审批归属校验不足

问题：

- subagent 审批分支原先缺少 pending approval 的 `session_id/run_id` 归属校验。
- 错误路由的审批请求有机会命中其他挂起审批。

修复：

- subagent 审批路径增加 `pending.session_id == session_id` 校验。
- 增加 `pending.run_id == run_id` 校验。
- 补充错误路由回归测试。

主要文件：

- `backend/app/services/agent_service.py`
- `backend/tests/test_services/test_agent_service.py`

### 4. Subagent trust_and_allow 没有写入父 session trust rule

问题：

- subagent 审批复用父 session UI，但 trust 规则需要落在父 session。
- 否则用户选择信任后，后续同类命令仍可能重复审批。

修复：

- subagent `trust_and_allow` 审批时调用统一 trust rule 写入逻辑。
- 验证 shell prefix trust 能写入父 session。

主要文件：

- `backend/app/services/agent_service.py`
- `backend/tests/test_services/test_agent_service.py`

### 5. 父 run 取消/reset/delete 时 subagent pending approval 清理不完整

问题：

- 父 run 取消后，`sub-run-*` pending approval 可能继续保留。
- reset/delete 后 session trust rules 和 pending approvals 可能残留。

修复：

- `PendingApprovalStore` 增加 `expire_for_session(session_id)`。
- cancel 父 run 时同时过期同 session pending approvals。
- reset 成功后清理 session security state；reset 失败时保持原子语义，不清理。
- delete session 时清理 browser、安全状态、附件，并为清理失败记录 warning。

主要文件：

- `backend/app/execution/approval_store.py`
- `backend/app/services/agent_service.py`
- `backend/app/api/routes/sessions.py`
- `backend/tests/test_execution/test_approval_store.py`
- `backend/tests/test_services/test_agent_service_reset.py`
- `backend/tests/test_api/test_sessions_api.py`

### 6. 前端 subagent 实时事件可能跨 session 串台

问题：

- 原先 subagent event store 只按 `delegate_call_id` 组织，多个 session 中相同 call id 可能互相污染。

修复：

- store 改为 `sessionId -> delegate_call_id -> SubAgentStep[]`。
- `useConversationRuntime` 按当前 WebSocket session 写入。
- reset conversation 时清理对应 session 的 subagent events。
- WebSocket 层对 `delegate_call_id` 做 runtime string check。

主要文件：

- `frontend/src/hooks/useSubAgentEvents.ts`
- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/services/sessionConversationWebSocket.ts`
- `frontend/src/hooks/__tests__/useSubAgentEvents.test.ts`
- `frontend/src/hooks/__tests__/useConversationRuntime.multi-session.test.ts`
- `frontend/src/services/__tests__/sessionConversationWebSocket.test.ts`

### 7. Delegate 卡片无法稳定关联子 agent 事件

问题：

- delegate UI 需要用真实 `tool_call_id` 关联子 agent event。
- transcript detail 的 `id` 是 message id，不等于 tool call id。

修复：

- transcript detail 的 `data` 中保留 `tool_call_id` 和 `session_id`。
- `DelegateToolCall` 使用 `session_id + tool_call_id` 订阅子 agent steps。
- 增加 correlation keys 回归测试。

主要文件：

- `frontend/src/components/workspace/transcriptItems.ts`
- `frontend/src/components/workspace/DelegateToolCall.tsx`
- `frontend/src/components/workspace/__tests__/transcriptItems.test.ts`

### 8. Subagent 详情面板工具批次和审批状态显示不稳定

问题：

- 并行工具调用可能被拆成多个批次，导致 UI 显示不完整。
- `approval:required` 后端随后发出的 `run:waiting_for_approval` 元事件会打断工具组，后续 `tool:result` 可能配不回原工具。

修复：

- `SubAgentDetailPanel` 保持并行工具调用在同一批次直到结果到达。
- `run:waiting_for_approval` / `run:resuming` 作为元事件处理，不打断工具组。
- 复用统一 `buildApprovalDetailFromPayload` 解析审批 payload。

主要文件：

- `frontend/src/components/workspace/SubAgentDetailPanel.tsx`
- `frontend/src/components/workspace/__tests__/SubAgentDetailPanel.test.ts`
- `frontend/src/components/execution/receiptUtils.ts`

### 9. 前端审批 payload 解析重复且不一致

问题：

- ActionReceipt、DelegateToolCall、SubAgentDetailPanel、transcriptItems 各自解析 approval payload，字段兼容性不一致。

修复：

- 新增 `buildApprovalDetailFromPayload` 统一解析入口。
- 覆盖 shell、sandbox network、sandbox path、suggested trust、parent session id。

主要文件：

- `frontend/src/components/execution/receiptUtils.ts`
- `frontend/src/components/execution/__tests__/receiptUtils.test.ts`

### 10. 完整测试套件存在 stale / 平台相关红点

问题：

- OpenAI/default headers 测试仍断言旧 `claude-cli` User-Agent。
- Prompt 测试依赖本机全局 `.reflexion` 中的私有称呼偏好。
- Windows sandbox 测试在 macOS 上尝试模拟 Windows API，导致 `msvcrt` / ACL / token 假失败。

修复：

- User-Agent 测试更新为当前 `codex-cli` 实现。
- Prompt 测试不再依赖本机私有 overlay 内容。
- Windows API 测试在非 Windows 平台跳过。

主要文件：

- `backend/tests/test_llm/test_openai_adapter.py`
- `backend/tests/test_services/test_llm_provider_service.py`
- `backend/tests/test_execution/test_prompt_manager.py`
- `backend/tests/test_security/test_sandbox_windows.py`
- `backend/tests/test_security/test_sandbox_windows_acl.py`
- `backend/tests/test_security/test_sandbox_windows_token.py`

## 剩余状态

- 当前修改尚未提交。
- 当前修改尚未推送远端。
- 当前分支仍领先远端提交，工作区包含源码、测试、文档改动。
