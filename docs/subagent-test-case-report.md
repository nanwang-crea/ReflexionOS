# Subagent Test Case Report

生成时间：2026-08-11 14:59:02 CST

## 测试范围

本报告覆盖当前工作区所有未提交修改，重点包含：

- 后端 subagent runner 工具隔离、loop 生命周期、并发 delegate、审批路由。
- 后端 pending approval 过期、reset/delete/cancel 安全状态清理。
- 前端 subagent WebSocket 事件映射、session 级事件 store、delegate 卡片、详情面板、审批卡片。
- 前端 transcript 到 delegate UI 的关联键传递。
- 完整后端/前端测试门禁、TypeScript 类型检查、ESLint、diff whitespace。

## 后端测试用例

### SubAgentRunner

文件：`backend/tests/test_execution/test_sub_agent_runner.py`

| 用例 | 验证点 |
| --- | --- |
| `test_filtered_sub_agent_registry_excludes_delegate` | 子 agent 工具集排除 `delegate`，避免递归委托。 |
| `test_filtered_sub_agent_registry_excludes_plan_and_browser` | 子 agent 不复用 `plan` 和 `browser` 这类主会话态工具。 |
| `test_filtered_sub_agent_registry_isolates_stateful_tools` | `WorkingMemoryTool` 等状态型工具在子 agent 之间隔离实例。 |
| `test_filtered_sub_agent_registry_rebinds_shell_session_id` | 子 agent shell 工具绑定独立 child session id。 |
| `test_sub_agent_runner_reports_loop_lifecycle` | `sub-run-*` child loop 注册/注销生命周期回调可靠触发。 |

### AgentService / Subagent 审批

文件：`backend/tests/test_services/test_agent_service.py`

| 用例 | 验证点 |
| --- | --- |
| `test_cancel_run_expires_sub_agent_pending_approval_for_same_session` | 取消父 run 时，同 session 的 subagent pending approval 会过期。 |
| `test_run_turn_cleans_session_approval_flow_after_finish` | 父 run 完成后清理 session approval flow 映射，避免 stale flow。 |
| `test_sub_agent_trust_and_allow_adds_parent_session_trust_rule` | subagent `trust_and_allow` 写入父 session trust rule。 |
| `test_sub_agent_approved_tool_uses_child_loop_registry` | subagent 审批通过后使用 child loop 的真实 tool registry 执行工具。 |
| `test_sub_agent_approval_validates_pending_ownership` | subagent 审批校验 pending approval 的 session/run 归属。 |

### PendingApprovalStore

文件：`backend/tests/test_execution/test_approval_store.py`

| 用例 | 验证点 |
| --- | --- |
| `expire_for_session` 相关用例 | 能按 session 批量过期 pending approval，并保留其他 session 状态。 |
| 原有 approve/deny/list 用例 | 审批状态流转、深拷贝隔离、重复决策保护。 |

### Reset/Delete Session

文件：

- `backend/tests/test_services/test_agent_service_reset.py`
- `backend/tests/test_api/test_sessions_api.py`

| 用例 | 验证点 |
| --- | --- |
| reset active run 用例 | reset 前先取消活跃 run，再清理对话。 |
| reset security cleanup 用例 | reset 成功后清理 trust rules 和 pending approvals。 |
| reset failure preservation 用例 | reset 失败时不清理安全状态，保持原子语义。 |
| delete session cleanup 用例 | 删除 session 时触发 browser/security/attachment 清理路径。 |

### Rapid Loop Delegate 并发

文件：`backend/tests/test_execution/test_rapid_loop.py`

| 用例 | 验证点 |
| --- | --- |
| 连续 delegate 并发用例 | 连续 delegate 分段并发执行，总耗时接近单批延时。 |
| delegate 与普通写工具混排用例 | delegate 并发不打乱模型原始工具调用顺序。 |
| delegate 单个失败隔离用例 | 同批 delegate 一个失败不影响其他 delegate。 |
| max concurrent 用例 | delegate 并发遵守配置上限。 |

### 兼容与平台测试维护

文件：

- `backend/tests/test_execution/test_prompt_manager.py`
- `backend/tests/test_llm/test_openai_adapter.py`
- `backend/tests/test_services/test_llm_provider_service.py`
- `backend/tests/test_security/test_sandbox_windows.py`
- `backend/tests/test_security/test_sandbox_windows_acl.py`
- `backend/tests/test_security/test_sandbox_windows_token.py`

| 用例 | 验证点 |
| --- | --- |
| PromptManager 用例 | 不再依赖本机全局人格 overlay 中的私有称呼偏好。 |
| OpenAI/default headers 用例 | User-Agent 断言与当前 `codex-cli` 实现一致。 |
| Windows sandbox 用例 | Windows API 测试在非 Windows 平台跳过，避免 macOS/Linux 假失败。 |

## 前端测试用例

### WebSocket 事件映射

文件：`frontend/src/services/__tests__/sessionConversationWebSocket.test.ts`

| 用例 | 验证点 |
| --- | --- |
| subagent server message mapping | `sub_agent:*` 后端事件映射为 `sub_agent:event`。 |
| delegate_call_id runtime check | 非字符串 `delegate_call_id` 不进入关联键，避免错误污染 store。 |

### Subagent Event Store

文件：`frontend/src/hooks/__tests__/useSubAgentEvents.test.ts`

| 用例 | 验证点 |
| --- | --- |
| per session and delegate call id | 相同 `delegate_call_id` 在不同 session 下隔离存储。 |
| clearSession | 清理一个 session 不影响其他 session 的子 agent 步骤。 |

### Conversation Runtime

文件：

- `frontend/src/hooks/__tests__/useConversationRuntime.test.ts`
- `frontend/src/hooks/__tests__/useConversationRuntime.multi-session.test.ts`

| 用例 | 验证点 |
| --- | --- |
| subagent event write path | WebSocket `sub_agent:event` 写入 session-scoped store。 |
| multi-session isolation | 多会话并行时子 agent 事件不会串台。 |
| reset cleanup | reset conversation 后清理当前 session 的 subagent events。 |

### Approval Parsing

文件：`frontend/src/components/execution/__tests__/receiptUtils.test.ts`

| 用例 | 验证点 |
| --- | --- |
| shell approval payload | 从后端 `ToolApprovalRequest` 解析 shell 审批数据。 |
| sandbox path payload | 解析 sandbox path elevation 的 denied paths 和 suggested trust。 |

### Delegate / Subagent UI

文件：

- `frontend/src/components/workspace/__tests__/SubAgentDetailPanel.test.ts`
- `frontend/src/components/workspace/__tests__/transcriptItems.test.ts`

| 用例 | 验证点 |
| --- | --- |
| parallel tool calls in one batch | 并行工具调用保持在同一批次直到结果到达。 |
| approval state attached to matching tool | `approval:required` 绑定到正确工具调用。 |
| run approval meta event handling | `run:waiting_for_approval` 不打断工具批次，后续 `tool:result` 可正确配对。 |
| delegate correlation keys | transcript detail 保留 `session_id + tool_call_id`，用于关联子 agent 实时事件。 |

## 全量回归套件

| 套件 | 命令 | 覆盖 |
| --- | --- | --- |
| 后端完整测试 | `python -m pytest backend/tests` | API、执行循环、subagent、审批、安全、工具、服务、存储。 |
| 前端完整测试 | `pnpm test` | store、hooks、services、workspace UI、conversation reducer、layout、terminal。 |
| TypeScript | `pnpm exec tsc --noEmit` | 前端类型正确性。 |
| ESLint | `pnpm lint` | 前端 lint 和未使用 disable 检查。 |
| Diff whitespace | `git diff --check` | 空白、行尾和补丁格式检查。 |
