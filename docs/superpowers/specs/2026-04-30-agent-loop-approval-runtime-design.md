# Agent Loop 工具审批运行时设计

## 背景

当前 runtime 默认一个工具调用只有两个有意义的结果：

- success
- failure

这个模型不足以支持需要用户审批的工具。shell 命令、破坏性文件操作、patch 删除、浏览器动作以及未来的特权工具，都需要第三种结果：

- 等待用户审批

审批状态不能只存在于某个工具内部。Agent Loop 必须理解当前 run 是暂停而不是失败，并且能在用户批准或拒绝后恢复同一个 run。

当前代码结构：

- `ToolResult` 包含 `success`、`output`、`error` 和 `data`。
- `ToolCallExecutor` 会立即执行工具，并把 success 或 failure 投射到 `LoopContext`。
- `RapidExecutionLoop` 把失败 step 当作 error recovery 输入。
- `RunStatus` 包含 `created`、`running`、`completed`、`failed` 和 `cancelled`。
- websocket 协议支持 start、sync 和 cancel，但没有 approval action。
- conversation events 持久化 tool start/result/error，但没有审批状态。

本设计在实现 shell approval 等具体工具策略前，先增加 approval-aware runtime 层。

## 决策

采用方案 C：

> 需要审批时暂停同一个 run，持久化 pending approval，用户操作后恢复同一个 run。

不要在等待用户时阻塞 Python coroutine。run task 应返回一个非终态 waiting 状态。恢复时为同一个 run 调度新的 async task，并从已持久化的 conversation state 加上已批准的工具结果重建上下文。

## 目标

- 为所有工具添加通用审批机制。
- 暂停和恢复时保持同一个 `run_id`。
- 将审批等待视为非终态 run state，而不是失败。
- 持久化足够的审批状态，支持前端刷新和 websocket 重连。
- 审批后执行存储的 tool call，而不是模型提供的替换 payload。
- 支持仅本次允许、拒绝，以及后续 trust-prefix 操作。
- 将具体工具风险逻辑留在 Agent Loop 之外。

## 非目标

- 在本设计中实现 shell 命令风险策略。
- 持久化长期项目级 trust 规则。
- 序列化运行中的 Python coroutine 状态。
- 添加分布式或多用户授权。
- 添加 sandbox。
- 在本阶段构建 post-execution loop breaker。

## 状态模型

### RunStatus

扩展 `RunStatus`：

```text
created
running
waiting_for_approval
resuming
completed
failed
cancelled
```

状态转换：

```text
created -> running
running -> waiting_for_approval
waiting_for_approval -> resuming
waiting_for_approval -> cancelled
resuming -> running
running -> completed
running -> failed
running -> cancelled
```

`waiting_for_approval` 是非终态。run 已经把控制权交还给应用，但任务语义上还没有完成。

### LoopStatus

扩展 `LoopStatus`：

```text
WAITING_FOR_APPROVAL
RESUMING
```

`RapidExecutionLoop.run()` 可以返回 `WAITING_FOR_APPROVAL`，且不发出 `run:complete` 或 `run:error`。

### StepStatus

扩展 `StepStatus`：

```text
PENDING
RUNNING
WAITING_FOR_APPROVAL
SUCCESS
FAILED
CANCELLED
```

等待中的 step 保留原始 `tool_call_id`、tool 名称、参数和 approval id。

## ToolResult 模型

保持与现有工具结果兼容，同时增加审批请求 payload。

```python
class ToolApprovalRequest(BaseModel):
    approval_id: str
    tool_name: str
    summary: str
    reasons: list[str] = []
    risks: list[str] = []
    payload: dict[str, Any] = {}
    suggested_action: str | None = None
    suggested_trust: dict[str, Any] | None = None


class ToolResult(BaseModel):
    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval: ToolApprovalRequest | None = None
```

规则：

- `approval_required=True` 表示结果既不是成功，也不是普通失败。
- `ToolCallExecutor` 必须先检查 `approval_required`，再检查 `success`。
- 审批请求不应进入普通 error recovery。

## Pending Approval 模型

创建 runtime approval store。第一版可以使用内存存储，但必须把状态投射到 conversation events 中，让前端可以从 snapshot 恢复 pending approval。

建议模型：

```python
class PendingToolApproval(BaseModel):
    id: str
    session_id: str
    turn_id: str
    run_id: str
    step_number: int
    tool_call_id: str
    tool_name: str
    tool_arguments: dict[str, Any]
    approval_payload: dict[str, Any]
    status: Literal["pending", "approved", "denied", "expired", "stale"]
    created_at: datetime
    decided_at: datetime | None = None
    decision: Literal["allow_once", "deny", "trust_and_allow"] | None = None
```

安全规则：

> 审批执行使用存储的 pending approval。用户审批永远不接受模型新提供的 command、path、patch 或 argument payload。

## Runtime 流程

### 普通工具执行

```text
LLM returns tool call
ToolCallExecutor emits tool:start
Tool executes
ToolResult success/failure
ToolCallExecutor updates LoopContext
RapidExecutionLoop continues
```

### 需要审批

```text
LLM returns tool call
ToolCallExecutor emits tool:start
Tool returns approval_required
ToolCallExecutor stores PendingToolApproval
ToolCallExecutor emits approval:required
ToolCallExecutor returns a waiting step
RapidExecutionLoop sets loop status WAITING_FOR_APPROVAL
AgentService marks run waiting_for_approval
async task exits
```

不会发出 `run:complete` 或 `run:error`。

### 仅本次允许

```text
frontend sends conversation:approve_tool
AgentService loads PendingToolApproval
AgentService marks approval approved
AgentService marks run resuming
AgentService schedules resume for same run_id
resume execution runs the stored tool call
tool result is appended to context
loop continues from the same run
```

### 拒绝

```text
frontend sends conversation:deny_tool
AgentService marks approval denied
AgentService records a denied tool result
resume execution gives the denial result to the model
model can choose an alternative path or produce final answer
```

拒绝不是 runtime failure。它是用户决策，会作为工具反馈交给模型。

## 恢复策略

不要通过保留原始 coroutine 来恢复。

改为：

1. 通过 conversation events 持久化审批状态。
2. 在 `PendingApprovalStore` 中保存 pending tool call。
3. 用户批准后执行存储的 tool call。
4. 从以下信息重建 loop context：
   - 已有 conversation history
   - 当前 task
   - 已批准的 tool result
   - 一条说明 run 因用户审批而恢复的 system note
5. 继续使用同一个 run id。

这符合当前 event-sourced conversation 方向，也让刷新和重连行为更容易处理。

### Resume Input

增加明确的 resume input 结构，而不是把恢复路径伪装成一个新的 turn：

```python
class ResumeRunInput(BaseModel):
    run_id: str
    session_id: str
    turn_id: str
    approved_approval_id: str
    approved_tool_result: ToolResult | None = None
    denied_tool_result: ToolResult | None = None
```

`RapidExecutionLoop.run()` 应接受可选 resume payload。存在 resume payload 时：

- 跳过 `InitialPlanBootstrapper.bootstrap()`
- 保留现有 `run_id`
- 从 conversation history 重建 context
- 添加一条说明 run 因用户审批而恢复的 system note
- 将已批准或已拒绝的 tool result 添加为关联原始 `tool_call_id` 的 tool message
- 从正常 planning phase 继续

恢复路径不应创建新的 user turn、新 run 或新的 initial plan。

### Tool Call 连续性

原始 assistant tool call 必须出现在恢复后的 tool result 之前。当前 `LoopMessageBuilder` 已经能在消息顺序正确时保留 assistant/tool call 分组，因此审批流程必须持久化足够的 conversation events 来重建：

```text
assistant tool_call(original)
tool result(approved execution or user denial)
```

如果应用重启后无法重建这对消息，approval 应标记为 expired，并要求用户重试该动作，而不是用孤立的 tool result 恢复。

## Conversation Events

新增事件类型：

```text
run.waiting_for_approval
run.resuming
approval.required
approval.approved
approval.denied
approval.stale
```

事件 payload 示例：

```json
{
  "approval_id": "approval-abc123",
  "tool_name": "shell",
  "step_number": 3,
  "summary": "运行 shell 命令",
  "reasons": ["使用 shell 元语法: &&"],
  "risks": ["命令会交给本地 shell 解释执行"],
  "payload": {
    "command": "pytest -q && git status --short",
    "cwd": "/project"
  },
  "actions": ["allow_once", "deny"]
}
```

`approval.required` 应出现在 conversation snapshot 中，这样 UI 刷新后可以恢复审批卡片。

## WebSocket/API 操作

新增 websocket message：

```text
conversation:approve_tool
conversation:deny_tool
conversation:trust_tool_prefix
```

请求 payload：

```json
{
  "approval_id": "approval-abc123",
  "run_id": "run-123"
}
```

trust 操作：

```json
{
  "approval_id": "approval-abc123",
  "run_id": "run-123",
  "trust": {
    "scope": "session",
    "prefix": ["pytest"]
  }
}
```

后端校验：

- approval 存在
- approval 属于当前 session
- approval 属于当前 run
- run 处于 `waiting_for_approval`
- approval 仍处于 pending

## 前端 UX

增加由 `approval.required` 渲染的审批卡片。

应展示：

- tool 名称
- summary
- 参数或安全 payload 摘要
- reasons
- risks
- 可用操作
- stale/reapproval 解释，如果适用

操作：

- 仅本次允许
- 本 session 信任，当工具策略提供该选项时展示
- 拒绝

工具 action receipt 应支持 `waiting_for_approval` 可见状态。

## 与 Shell Approval 的关系

Shell approval 是接入本 runtime 的工具级策略。

Shell policy 职责：

- 判断 `allow`、`require_approval` 或 `deny`
- 划分 shell 风险
- 建议 session trust 规则
- 附加环境快照

Approval runtime 职责：

- 持久化 pending approval
- 暂停 run
- 发出 approval events
- 接收用户决策
- 恢复同一个 run

这种分离能避免 shell 风险逻辑进入 Agent Loop。

## 错误处理

- 如果 pending approval 被拒绝，记录一个说明拒绝原因的 tool result，并继续模型 loop。
- 如果 pending approval 过期，发出 `approval.stale` 并要求新的决策。
- 如果恢复后的工具执行失败，把它当作普通工具失败处理。
- 如果 run 在等待审批时被取消，将 pending approval 标记为 expired 或 cancelled。
- 如果应用重启，v1 的内存 pending approval 会丢失；已持久化的 `approval.required` events 应渲染为 expired。

## 测试策略

后端测试：

- `approval_required=True` 的工具结果会创建 waiting step。
- waiting step 不会触发 error recovery。
- run 从 `running` 转为 `waiting_for_approval`。
- 需要审批时发出 `approval.required` 和 `run.waiting_for_approval`。
- 仅本次允许后恢复同一个 run id。
- 拒绝后记录 tool denial result，并恢复同一个 run id。
- 审批不能执行替换参数。
- 等待审批时取消 run 会让 pending approval 过期。

前端测试：

- snapshot 中存在 pending approval 时渲染审批卡片。
- 审批卡片发送 approve action。
- 审批卡片发送 deny action。
- receipt 展示 waiting-for-approval 状态。
- stale approval 解释为什么需要重新确认。

集成测试：

- run 在需要审批时暂停，且不会完成。
- 批准后同一个 run 恢复并继续到完成。
- 拒绝后同一个 run 恢复，并让模型选择其他路径。
- 需要审批后刷新页面，可以恢复 pending approval UI。

## 推进计划

Phase 1：Approval Runtime Core

- 添加 run、loop、step 的 waiting 状态。
- 添加支持 approval 的 `ToolResult`。
- 添加 `PendingApprovalStore`。
- 添加 approval required/approved/denied runtime events。
- 添加 websocket approval actions。
- 添加前端审批卡片。
- 使用一个小型测试工具或 shell mock 测试。

Phase 2：Shell Integration

- 将 shell command policy 接入 approval runtime。
- 支持仅本次允许和拒绝。
- 基础审批流程稳定后，添加 session trust。

Phase 3：Consistency Layer

- 添加 stale environment 处理。
- 高风险 approval 过期时强制 replan。
- 添加 post-execution analyzer，用于检测重复命令循环和无进展状态。

## 待定选择

pending approval 可以先使用内存存储，但 event stream 必须暴露足够状态，让前端能恢复。如果内存 approval 数据丢失，UI 应将该 approval 标记为 expired，并要求用户重试动作。

trust-prefix 持久化应保持 session-only，直到存在可见的 trust 管理 UI。
