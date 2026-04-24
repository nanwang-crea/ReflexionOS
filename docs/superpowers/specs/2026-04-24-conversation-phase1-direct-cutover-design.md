# ReflexionOS Conversation Phase 1 直接切换设计

> 日期：2026-04-24  
> 状态：已在对话中确认，可作为下一步实施计划的唯一设计依据  
> 适用范围：ReflexionOS 会话底座 Phase 1  
> 来源：在 [conversation重构.md](/Users/munan/Documents/munan/my_project/ai/ReflexionOS/docs/superpowers/plans/conversation重构.md) 的架构方向上，进一步收敛出的可施工设计  
> 切换方式：一次性切换后端 API / WebSocket / 前端 store，不保留旧 `conversations + rounds + execution websocket` 兼容层

## 1. 背景与结论

当前 ReflexionOS 的会话链路仍然建立在以下旧模型上：

- 后端持久化使用 `sessions + executions + conversations`
- 前端历史读取使用 `GET /api/sessions/{session_id}/history`
- 前端状态主体是 `rounds -> items`
- 运行中的中间过程依赖 WebSocket overlay 和执行期临时状态

这套模型能支撑“能跑”，但不能作为通用 Agent 的稳定会话底座，主要问题有：

- `Execution`、`conversation item`、前端 `rounds` 混在一起，边界不清
- 中间过程不是稳定消息对象，断线、重开、回看都要靠补丁逻辑兜底
- WebSocket 协议围绕 `execution_id`，不适合作为长期会话同步协议
- 前端展示模型和后端存储模型耦合，`messageViewModel` 缺少稳定事实层

这轮设计的结论是：

- 直接切到 `Session + Turn + Run + Event + Projection + Message`
- `Event` 是运行期唯一写入真相
- `Message` 是长期会话真相和前端稳定主键
- `Turn` 管轮次边界，`Run` 管执行尝试
- 前端改为 `snapshot + afterSeq event sync`
- 工具过程和系统通知进入正式 `Message` 层
- 旧接口、旧表、旧前端 `rounds` 结构直接删除

这不是渐进兼容方案，而是一次性切换方案。

## 2. 设计目标

这一轮只解决 Phase 1 最小闭环，目标如下：

1. 让会话拥有稳定的事实层，而不是依赖执行期 overlay。
2. 让用户消息、assistant 输出、工具过程、系统通知都成为稳定 `Message`。
3. 让流式输出、取消、失败、断线补齐都通过统一 `ConversationEvent` 协议驱动。
4. 让前端在重开页面、重新连接后可以通过 `snapshot + afterSeq` 恢复状态。
5. 为未来 `memory`、`search`、`summary` 留下干净锚点，但本轮不实现这些能力。

## 3. 非目标

本轮明确不做以下内容：

- 不做历史数据迁移
- 不保留旧 API、旧 WebSocket、旧前端 adapter
- 不实现多 `Run` per `Turn` 的 regenerate / retry 能力
- 不实现事件清理策略、归档策略、分层冷热存储
- 不实现 `memory`、`branch`、`summary`、`embedding`
- 不实现跨设备同步和复杂离线缓存

因为当前数据库内容基本都是测试数据，本轮允许直接重建本地开发数据库或直接 drop 旧会话相关表，不承担向后兼容成本。

## 4. 总体架构

Phase 1 统一采用如下主链路：

```text
前端输入
-> Session Conversation WebSocket
-> 后端生成 ConversationEvent
-> 事务内 append Event
-> Projection 更新 Session / Turn / Run / Message
-> commit
-> 广播 ConversationEvent
```

前端统一采用如下读路径：

```text
GET conversation snapshot
-> 打开 session websocket
-> 发送 afterSeq 同步请求
-> 接收 ConversationEvent
-> ConversationStore
-> messageViewModel
-> Chat UI
```

这里有三个强约束：

1. 后端只保留一套标准化 `ConversationEvent`，不再区分 domain event / session event。
2. 前端不再把 `rounds` 当业务真相，`messageViewModel` 只是展示派生。
3. 广播必须发生在数据库提交之后，保证前端看到的事件一定能被 snapshot 复现。

## 5. 核心领域模型

### 5.1 Session

`Session` 仍然表示一个会话线程，职责是承载会话级配置和同步游标。

Phase 1 中，`Session` 至少包含以下字段：

- `id`
- `project_id`
- `title`
- `preferred_provider_id`
- `preferred_model_id`
- `last_event_seq`
- `active_turn_id`
- `created_at`
- `updated_at`

约束：

- `last_event_seq` 在一个 session 内单调递增。
- `active_turn_id` 为空表示当前没有活跃轮次。

### 5.2 Turn

`Turn` 是一次用户发送及其后续响应的容器，是系统内部的一轮对话边界。

字段：

- `id`
- `session_id`
- `turn_index`
- `root_message_id`
- `status`
- `active_run_id`
- `created_at`
- `updated_at`
- `completed_at`

`status` 枚举：

- `created`
- `running`
- `completed`
- `failed`
- `cancelled`

Phase 1 约束：

- 新一次用户发送必然创建一个新 `Turn`
- 一个 `Turn` 只包含一条根 `user_message`
- 一个 `Turn` 最多只包含一个 `Run`

### 5.3 Run

`Run` 是系统对某个 `Turn` 的一次执行尝试，也是对当前持久化 `Execution` 概念的替代。

字段：

- `id`
- `session_id`
- `turn_id`
- `attempt_index`
- `status`
- `provider_id`
- `model_id`
- `workspace_ref`
- `started_at`
- `finished_at`
- `error_code`
- `error_message`

`status` 枚举：

- `created`
- `running`
- `completed`
- `failed`
- `cancelled`

约束：

- `Run.id` 直接作为运行期关联 ID，外部协议不再暴露独立 `execution_id`
- Phase 1 中 `attempt_index` 固定为 `1`

### 5.4 Message

`Message` 是用户长期可感知的稳定实体，也是前端同步主键和未来 memory 锚点。

字段：

- `id`
- `session_id`
- `turn_id`
- `run_id`
- `message_index`
- `role`
- `message_type`
- `stream_state`
- `display_mode`
- `content_text`
- `payload_json`
- `created_at`
- `updated_at`
- `completed_at`

`role` 枚举：

- `user`
- `assistant`
- `tool`
- `system`

`message_type` 枚举：

- `user_message`
- `assistant_message`
- `tool_trace`
- `system_notice`

`stream_state` 枚举：

- `idle`
- `streaming`
- `completed`
- `failed`
- `cancelled`

`display_mode` 枚举：

- `default`
- `collapsed`

约束：

- 消息顺序由 `(turn_index, message_index)` 决定，不依赖时间戳排序
- `user_message` 的 `run_id` 为空
- `tool_trace` 默认 `display_mode=collapsed`
- `assistant_message` 默认 `display_mode=default`

### 5.5 ConversationEvent

`ConversationEvent` 是运行期唯一 append-only 写入真相。

字段：

- `id`
- `session_id`
- `seq`
- `turn_id`
- `run_id`
- `message_id`
- `event_type`
- `payload_json`
- `created_at`

约束：

- `seq` 在同一个 `session` 内严格单调递增
- 所有运行期状态变化都必须先写 `ConversationEvent`
- `Projection` 必须从 `ConversationEvent` 推导 `Turn / Run / Message`

## 6. Message 数据约束

为了避免再次退化成“结构全塞进 metadata_json”，Phase 1 必须固定消息内容规则。

### 6.1 user_message

- `content_text`：用户原始输入
- `payload_json`：固定为空对象

### 6.2 assistant_message

- `content_text`：assistant 正文
- `payload_json`：仅允许少量展示相关字段，例如 `finish_reason`

本轮不允许把工具执行细节塞进 `assistant_message.payload_json`。

### 6.3 tool_trace

- `content_text`：折叠态展示用的一行短摘要
- `payload_json`：固定使用以下 schema

```json
{
  "trace_kind": "thought|tool_call|tool_result|progress",
  "summary": "string",
  "tool_name": "string|null",
  "tool_status": "pending|running|success|failed|cancelled|null",
  "input_preview": "string|null",
  "output_preview": "string|null",
  "error_preview": "string|null",
  "started_at": "datetime|null",
  "finished_at": "datetime|null"
}
```

约束：

- 本轮只允许使用这组字段
- 工具输入输出只保留 preview，不把完整原始载荷直接塞给 UI

### 6.4 system_notice

- `content_text`：用户可读通知，例如“本次执行已取消”
- `payload_json`：仅允许 `notice_code`、`related_run_id`、`retryable` 这类有限字段

## 7. 标准事件协议

Phase 1 只保留以下事件类型：

- `turn.created`
- `run.created`
- `run.started`
- `run.completed`
- `run.failed`
- `run.cancelled`
- `message.created`
- `message.delta_appended`
- `message.payload_updated`
- `message.completed`
- `message.failed`
- `system.notice_emitted`

### 7.1 事件 payload 约束

#### `turn.created`

```json
{
  "turn_id": "turn_x",
  "turn_index": 3,
  "root_message_id": "msg_user_x"
}
```

#### `run.created`

```json
{
  "run_id": "run_x",
  "turn_id": "turn_x",
  "attempt_index": 1,
  "provider_id": "openai",
  "model_id": "gpt-5.4",
  "workspace_ref": "/workspace/path"
}
```

#### `run.started`

```json
{
  "run_id": "run_x",
  "started_at": "2026-04-24T10:00:00Z"
}
```

#### `message.created`

```json
{
  "message_id": "msg_x",
  "turn_id": "turn_x",
  "run_id": "run_x",
  "role": "assistant",
  "message_type": "assistant_message",
  "message_index": 2,
  "display_mode": "default",
  "content_text": "",
  "payload_json": {}
}
```

#### `message.delta_appended`

```json
{
  "message_id": "msg_x",
  "delta": "增量文本"
}
```

#### `message.payload_updated`

```json
{
  "message_id": "msg_x",
  "payload_json": {
    "tool_status": "running"
  }
}
```

#### `message.completed`

```json
{
  "message_id": "msg_x",
  "completed_at": "2026-04-24T10:00:05Z"
}
```

#### `message.failed`

```json
{
  "message_id": "msg_x",
  "error_code": "tool_failed",
  "error_message": "命令执行失败"
}
```

#### `run.completed`

```json
{
  "run_id": "run_x",
  "finished_at": "2026-04-24T10:00:10Z"
}
```

#### `run.failed`

```json
{
  "run_id": "run_x",
  "error_code": "runtime_error",
  "error_message": "工具执行异常",
  "finished_at": "2026-04-24T10:00:10Z"
}
```

#### `run.cancelled`

```json
{
  "run_id": "run_x",
  "finished_at": "2026-04-24T10:00:10Z"
}
```

#### `system.notice_emitted`

```json
{
  "message_id": "msg_notice_x",
  "notice_code": "run_cancelled",
  "content_text": "本次执行已取消",
  "related_run_id": "run_x"
}
```

### 7.2 协议约束

- 前端永远只接收标准化 `ConversationEvent`
- Provider、LLM、Tool 的底层原始事件不直接透传给前端
- `message.delta_appended` 只允许用于文本增量，不允许夹带结构更新
- 结构更新统一走 `message.payload_updated`

## 8. Projection 规则

`Projection` 是 `Event -> Session / Turn / Run / Message` 的唯一收敛器，必须保证确定性和幂等性。

### 8.1 事务顺序

后端每次写事件都遵守同一个事务顺序：

```text
append event
-> apply projection
-> update session.last_event_seq
-> commit
-> broadcast
```

不允许：

- 先广播再提交
- 只写 Event 不投影
- 直接改 `Message` 而不产生日志事件

### 8.2 核心投影规则

#### 用户发送消息

后端先生成本轮固定 ID 集合：`turn_id`、`root_message_id`、`run_id`，再开始 append 事件。

1. 生成 `turn.created`
2. 生成根 `user_message` 的 `message.created`
3. 生成 `run.created`

投影结果：

- 新建 `Turn`
- 新建根 `user_message`
- 新建 `Run`
- 更新 `Session.active_turn_id`

#### assistant 开始回答

1. 生成空白 `assistant_message` 的 `message.created`
2. 每个流式 token 生成 `message.delta_appended`
3. 完成时生成 `message.completed`
4. 结束时生成 `run.completed`

投影结果：

- 创建一条稳定 `assistant_message`
- 流式阶段只追加正文，不新增额外临时消息
- 将 `Run.status` 标记为 `completed`
- 将 `Turn.status` 标记为 `completed`
- 清空 `Session.active_turn_id`

#### 工具过程

每个工具步骤对应一条独立 `tool_trace` 消息：

1. 工具开始时 `message.created`
2. 进度和结构变化时 `message.payload_updated`
3. 完成或失败时 `message.completed` / `message.failed`

投影结果：

- 工具过程可回看
- 前端默认折叠显示
- 工具状态由 `payload_json.tool_status` 体现

#### 取消或失败

1. 生成 `run.cancelled` 或 `run.failed`
2. 同步生成 `system.notice_emitted`

投影结果：

- 关闭 `Run`
- 关闭 `Turn`
- 追加一条 `system_notice`
- 清空 `Session.active_turn_id`

### 8.3 幂等要求

`Projection` 必须支持“同一个 event 因重复消费再次进入 apply”但不产生重复状态。

最低要求：

- `ConversationEvent.id` 唯一
- `Projection` 更新按 `message_id` / `run_id` / `turn_id` 精确定位
- `message.completed`、`run.completed` 这类终态事件重复应用时结果一致

## 9. 持久化模型设计

### 9.1 保留和新增表

保留：

- `projects`
- `sessions`

新增或替换：

- `turns`
- `runs`
- `messages`
- `conversation_events`

删除：

- `conversations`
- `executions`

### 9.2 表结构建议

#### `sessions`

在现有字段上补充：

- `last_event_seq INTEGER NOT NULL DEFAULT 0`
- `active_turn_id TEXT NULL`

#### `turns`

- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `turn_index INTEGER NOT NULL`
- `root_message_id TEXT NOT NULL`
- `status TEXT NOT NULL`
- `active_run_id TEXT NULL`
- `created_at DATETIME NOT NULL`
- `updated_at DATETIME NOT NULL`
- `completed_at DATETIME NULL`

索引：

- `(session_id, turn_index)` 唯一
- `(session_id, status)`

#### `runs`

- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `turn_id TEXT NOT NULL`
- `attempt_index INTEGER NOT NULL`
- `status TEXT NOT NULL`
- `provider_id TEXT NULL`
- `model_id TEXT NULL`
- `workspace_ref TEXT NULL`
- `started_at DATETIME NULL`
- `finished_at DATETIME NULL`
- `error_code TEXT NULL`
- `error_message TEXT NULL`

索引：

- `(turn_id, attempt_index)` 唯一
- `(session_id, status)`

#### `messages`

- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `turn_id TEXT NOT NULL`
- `run_id TEXT NULL`
- `message_index INTEGER NOT NULL`
- `role TEXT NOT NULL`
- `message_type TEXT NOT NULL`
- `stream_state TEXT NOT NULL`
- `display_mode TEXT NOT NULL`
- `content_text TEXT NOT NULL DEFAULT ''`
- `payload_json JSON NOT NULL DEFAULT '{}'`
- `created_at DATETIME NOT NULL`
- `updated_at DATETIME NOT NULL`
- `completed_at DATETIME NULL`

索引：

- `(turn_id, message_index)` 唯一
- `(session_id, created_at)`
- `(session_id, message_type)`

#### `conversation_events`

- `id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `seq INTEGER NOT NULL`
- `turn_id TEXT NULL`
- `run_id TEXT NULL`
- `message_id TEXT NULL`
- `event_type TEXT NOT NULL`
- `payload_json JSON NOT NULL`
- `created_at DATETIME NOT NULL`

索引：

- `(session_id, seq)` 唯一
- `(session_id, created_at)`

### 9.3 数据库切换策略

因为旧数据不需要保留，本轮采用直接切换：

1. 删除旧 `conversations` 与 `executions` 表
2. 创建 `turns`、`runs`、`messages`、`conversation_events`
3. 更新 `sessions` 表字段

如果当前开发库迁移成本高于重建成本，允许直接删除本地 SQLite 数据文件并重建整个 schema。

## 10. 后端模块重构

### 10.1 新的职责边界

建议形成如下模块边界：

- `backend/app/models/conversation.py`
  - 领域模型：`Turn`、`Run`、`Message`、`ConversationEvent`
- `backend/app/models/conversation_snapshot.py`
  - snapshot DTO
- `backend/app/storage/repositories/turn_repo.py`
- `backend/app/storage/repositories/run_repo.py`
- `backend/app/storage/repositories/message_repo.py`
- `backend/app/storage/repositories/conversation_event_repo.py`
- `backend/app/services/conversation_projection.py`
  - 只负责投影，不负责协议
- `backend/app/services/conversation_service.py`
  - 统一写入、读取、同步入口
- `backend/app/services/conversation_runtime_adapter.py`
  - 把 rapid loop / tool / LLM 流转成标准事件

### 10.2 现有模块的退场清单

以下模块在本轮结束后应直接删除或退场：

- `backend/app/models/transcript.py`
- `backend/app/models/session_history.py`
- `backend/app/storage/repositories/conversation_repo.py`
- `backend/app/storage/repositories/execution_repo.py`
- `backend/app/services/transcript_service.py`
- 当前围绕 `execution` 查询、持久化、历史聚合的 DTO 和 repository

### 10.3 对现有 Agent 运行链路的要求

当前 `rapid_loop` 或 `agent_service` 如果仍以 `execution_id` 作为内部变量，可以在过渡代码中保留局部变量名，但外部持久化和协议语义必须统一映射到 `run_id`。

原则是：

- 对外不再出现新的 `execution_id` 协议
- 运行时关联 ID 统一以 `run_id` 表达

## 11. HTTP API 设计

### 11.1 保留接口

- `POST /api/projects/{project_id}/sessions`
- `GET /api/projects/{project_id}/sessions`
- `GET /api/sessions/{session_id}`
- `PATCH /api/sessions/{session_id}`

### 11.2 删除接口

- `GET /api/sessions/{session_id}/history`
- `GET /api/agent/status/{execution_id}`
- `GET /api/agent/history`
- `POST /api/agent/cancel/{execution_id}`

### 11.3 新增接口

`GET /api/sessions/{session_id}/conversation`

返回标准 snapshot：

```json
{
  "session": {
    "id": "sess_1",
    "project_id": "proj_1",
    "title": "会话标题",
    "preferred_provider_id": "openai",
    "preferred_model_id": "gpt-5.4",
    "last_event_seq": 42,
    "active_turn_id": "turn_3",
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:10Z"
  },
  "turns": [],
  "runs": [],
  "messages": []
}
```

约束：

- 不再返回 `rounds`
- snapshot 是当前会话事实的完整读取结果
- 前端自己做 normalized store，不要求后端返回 map 结构

## 12. WebSocket 协议设计

### 12.1 连接地址

```text
WS /api/ws/sessions/{session_id}/conversation
```

WebSocket 归属 `session`，而不是 `execution`。

### 12.2 客户端消息

#### `conversation.sync`

```json
{
  "type": "conversation.sync",
  "data": {
    "after_seq": 42
  }
}
```

含义：

- 客户端已通过 snapshot 拿到 `last_event_seq=42`
- 请求服务端补发 `seq > 42` 的事件并进入 live 模式

#### `conversation.start_turn`

```json
{
  "type": "conversation.start_turn",
  "data": {
    "content": "请检查当前项目结构",
    "provider_id": "openai",
    "model_id": "gpt-5.4"
  }
}
```

含义：

- 在当前 `session` 下开启一个新 `Turn`
- 后端在同一个写链路中创建 `Turn + user_message + Run`

#### `conversation.cancel_run`

```json
{
  "type": "conversation.cancel_run",
  "data": {
    "run_id": "run_x"
  }
}
```

### 12.3 服务端消息

#### `conversation.synced`

```json
{
  "type": "conversation.synced",
  "data": {
    "session_id": "sess_1",
    "last_event_seq": 42
  }
}
```

#### `conversation.event`

```json
{
  "type": "conversation.event",
  "data": {
    "id": "evt_x",
    "session_id": "sess_1",
    "seq": 43,
    "turn_id": "turn_3",
    "run_id": "run_3",
    "message_id": "msg_9",
    "event_type": "message.delta_appended",
    "payload_json": {
      "delta": "正在分析项目结构"
    },
    "created_at": "2026-04-24T10:00:11Z"
  }
}
```

#### `conversation.resync_required`

```json
{
  "type": "conversation.resync_required",
  "data": {
    "reason": "after_seq_too_old",
    "expected_after_seq": 42
  }
}
```

#### `conversation.error`

```json
{
  "type": "conversation.error",
  "data": {
    "code": "invalid_request",
    "message": "当前会话已有运行中的 turn"
  }
}
```

### 12.4 同步策略

前端连接流程固定为：

1. `GET /conversation` 获取 snapshot
2. 打开 session websocket
3. 发送 `conversation.sync { after_seq: snapshot.session.last_event_seq }`
4. 接收补发事件
5. 收到 `conversation.synced` 后进入 live

如果服务端无法用 `after_seq` 补齐，则发送 `conversation.resync_required`，前端重新拉 snapshot。

## 13. 前端状态模型

### 13.1 新的 store 形态

当前前端 `historyBySessionId -> rounds -> items` 结构应整体删除，替换为标准化 conversation store。

建议结构：

```ts
type ConversationState = {
  sessionId: string
  lastEventSeq: number
  turnOrder: string[]
  turnsById: Record<string, TurnEntity>
  runsById: Record<string, RunEntity>
  messageOrder: string[]
  messagesById: Record<string, MessageEntity>
}
```

要求：

- `turnOrder` 按 `turn_index`
- `messageOrder` 按 `(turn_index, message_index)` 展平
- `messageViewModel` 只从实体状态派生 UI 展示字段

### 13.2 前端模块建议

建议新增：

- `frontend/src/types/conversation.ts`
- `frontend/src/features/conversation/conversationApi.ts`
- `frontend/src/features/conversation/conversationStore.ts`
- `frontend/src/features/conversation/conversationReducer.ts`
- `frontend/src/features/conversation/messageViewModel.ts`
- `frontend/src/services/sessionConversationWebSocket.ts`

建议删除或退场：

- `frontend/src/features/sessions/sessionHistoryRound.ts`
- `frontend/src/features/sessions/sessionLoader.ts` 中历史拉取相关逻辑
- `frontend/src/types/workspace.ts` 里的 `WorkspaceSessionRound` 与 `SessionHistory`
- `historyBySessionId`
- 承载事实状态的 execution overlay 拼接逻辑
- 当前 `ExecutionWebSocket` 及其围绕 `execution:*` 的事件处理

### 13.3 UI 派生原则

- `user_message` 直接渲染
- `assistant_message` 直接渲染并支持 streaming 态
- `tool_trace` 默认折叠，但来自正式消息列表
- `system_notice` 以 notice 样式展示，但仍占据正式消息位置

前端不再自己拼“活动轮次历史补丁”，也不再在执行结束后依赖整段 `refreshSessionHistory` 回填。

## 14. 关键交互流程

### 14.1 发起一轮对话

```text
用户发送消息
-> 前端发 conversation.start_turn
-> 后端依次写 turn.created / message.created(user) / run.created
-> 投影出 Turn、user_message、Run
-> 运行开始时写 run.started
-> LLM 输出 assistant_message
```

### 14.2 assistant 流式输出

```text
message.created(assistant)
-> 多次 message.delta_appended
-> message.completed
-> run.completed
-> turn.completed
```

`turn.completed` 不需要额外独立事件，本轮由 `run.completed` 投影出 `Turn.status=completed` 即可。

### 14.3 工具执行

```text
message.created(tool_trace)
-> 多次 message.payload_updated
-> message.completed 或 message.failed
```

### 14.4 取消

```text
conversation.cancel_run
-> run.cancelled
-> system.notice_emitted
-> 投影关闭 Run / Turn
```

### 14.5 断线恢复

```text
页面重开
-> 拉 snapshot(last_event_seq=120)
-> websocket sync(after_seq=120)
-> 服务端补 121..n
-> 前端继续 live
```

## 15. 旧接口淘汰与直接清理策略

本轮不采用“deprecated 一段时间再删”的策略，而是直接清理。

### 15.1 后端直接删除清单

- `conversations` 表
- `executions` 表
- `TranscriptRecord`
- `SessionHistoryItemDto`
- `SessionHistoryRoundDto`
- `SessionHistoryResponse`
- `ConversationRepository`
- `ExecutionRepository`
- `TranscriptService`
- `/api/sessions/{session_id}/history`
- `/api/agent/status/{execution_id}`
- `/api/agent/history`
- `/api/agent/cancel/{execution_id}`
- `WS /ws/execution/{execution_id}`

### 15.2 前端直接删除清单

- `rounds` 历史读取模型
- `WorkspaceSessionRound`
- `SessionHistory`
- `sessionHistoryRound` 正规化逻辑
- `refreshSessionHistory` / `ensureSessionHistoryLoaded`
- 以 `execution_id` 为中心的 websocket 连接模型
- 以“执行完成后重新拉 history 修正 UI”为目的的补丁逻辑

### 15.3 数据处理原则

- 不迁移旧 `conversations`
- 不迁移旧 `executions`
- 不为测试数据编写兼容脚本
- 允许开发环境重建数据库

## 16. 测试要求

这一轮设计至少需要覆盖以下测试层次：

### 16.1 后端单元测试

- `conversation_projection` 对每类事件的投影结果
- 重复事件应用时的幂等行为
- `message.delta_appended` 与 `message.payload_updated` 的边界

### 16.2 后端 API / WebSocket 测试

- `GET /api/sessions/{session_id}/conversation` snapshot 正确性
- `conversation.sync` 的 afterSeq 补发逻辑
- `conversation.resync_required` 触发条件
- `conversation.start_turn` 到 `run.completed` 的完整链路
- `conversation.cancel_run` 的终态行为

### 16.3 前端 reducer / store 测试

- snapshot 导入后的 normalized 状态
- event 追加后的 store 变化
- `messageViewModel` 对 `tool_trace` 的折叠派生
- reconnect 后的 afterSeq 同步

### 16.4 集成测试

- 发消息 -> 流式回答 -> 完成
- 发消息 -> 工具执行 -> 工具结果可回看
- 发消息 -> 中途取消 -> UI 和后端状态一致
- 页面刷新 -> snapshot + event sync 后恢复一致

## 17. 验收标准

完成本设计后，系统应满足以下结果：

1. 会话历史不再依赖 `rounds`。
2. 中间过程能够以正式 `Message` 形式回看。
3. 前端连接恢复通过 `afterSeq` 完成，而不是靠重新拉整段旧 history 修补。
4. 后端对外只暴露 `Session / Turn / Run / Message / ConversationEvent` 语义。
5. 旧 `conversations / executions / history` 整套模型不再出现在运行代码中。

## 18. 下一步

这份设计确认后，下一步只做一件事：

- 基于本 spec 编写实施计划，拆出数据库重构、后端协议切换、前端 store 切换、旧接口删除、测试收口五个施工面。

在进入实施计划之前，不再新增新的领域对象或兼容层。
