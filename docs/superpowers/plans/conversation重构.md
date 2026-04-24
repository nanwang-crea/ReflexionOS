# ReflexionOS Conversation 架构设计 V2

> 日期：2026-04-24  
> 状态：已在对话中确认，作为当前 `Conversation` 主设计文档  
> 范围：通用 Agent 的会话底座、事件同步协议、持久化模型、前端消息同步模型

## 1. 设计目标

ReflexionOS 的 `Conversation` 子系统不是单纯的聊天记录系统，而是整个通用 Agent 的会话底座。

它需要同时满足两类需求：

- 用户像普通聊天一样连续对话。
- Agent 在会话中执行工具、探索文件、生成中间过程，并且这些过程可以被回看。

这套系统的目标不是“尽量多存东西”，而是：

- 保证消息身份稳定。
- 保证流式输出稳定。
- 保证中间过程可见但默认折叠。
- 保证断线恢复和页面重开后仍可还原。
- 为以后接入 `memory` 留下干净的锚点。

一句话总结：

> `Conversation` 系统的核心职责，是为 Agent 提供稳定的会话事实层。

## 2. 核心原则

### 2.1 `Message` 是核心，`messageViewModel` 是展示派生

真正稳定的用户认知对象是 `Message`。

用户在前端看到的内容都应该是稳定的 `Message`，包括：

- 用户消息
- assistant 消息
- 工具探索过程
- 系统通知

Phase 1 中，前端的 `messageViewModel` 只是读取层，是从 `Message` 再结合少量 `Turn` / `Run` 状态派生出的展示结果，不是业务真相。

### 2.2 `Event` 是运行期写入真相，`Message` 是长期会话真相

底层系统通过 `Event` 记录状态变化，但这些 `Event` 的职责主要集中在运行期：

- 驱动当前会话同步
- 支持断线恢复和 `afterSeq` 补齐
- 保留短期排障窗口

用户可见的历史内容、前端长期展示、未来 `memory` 对接真正依赖的是 `Message`。

也就是说，`Event` 负责“变化是如何发生的”，`Message` 负责“当前会话里最终有什么”。

而 `Projection` 负责把前者稳定地收敛成后者。

Phase 1 中，不再拆成两套事件语言，而是统一只保留一套标准化 `ConversationEvent`。

所以主轴应该是：

```text
Event -> Projection -> Message
```

而不是：

```text
后端直接把 `messageViewModel` 当作独立真相层
```

### 2.3 `Turn` 和 `Run` 必须分开

- `Turn`：一次用户发送及其后续响应容器，也就是系统内部的一轮对话边界
- `Run`：系统对该 `Turn` 的一次执行尝试

当前边界先收敛为：

- 新一次用户发送 = 新一个 `Turn`
- 一个 `Turn` 当前只包含一条根 user `message`
- 一个 `Turn` 当前最多只有一个 `Run`

以后如果需要对同一轮做 regenerate / retry，再把一个 `Turn` 扩展为可承载多个 `Run`。

### 2.4 中间过程不是日志，而是消息

像下面这些内容：

- 正在思考
- 正在执行命令
- 正在探索文件
- 工具执行结果

它们不应该只存在于临时日志或 overlay 中，而应该进入 `Message` 层，只是：

- `message_type` 不同
- 默认折叠
- 展示方式不同

这样重开旧会话时才能回看全过程。

### 2.5 先做稳，再做大

第一阶段只做最小闭环：

- `Session`
- `Turn`
- `Run`
- `Event`
- `Projection`
- `Message`

不把 `memory`、`summary`、`branch`、`embedding` 一起拉进来。

## 3. 总体架构

整体架构应当明确拆成后端事实层与前端展示层。

后端主链路如下：

```text
前端输入
-> Session WebSocket
-> 后端生成 ConversationEvent
-> 事务内写 Event
-> Projection
-> 同步更新 Session / Turn / Run / Message
-> 广播 ConversationEvent
```

Phase 1 不再区分 `Domain Event` 和 `Session Event` 两套协议，而是统一只保留一套标准化 `ConversationEvent`，同时用于：

- 事件持久化
- `Projection` 输入
- live 广播
- 短期 replay

前端看到的不是 provider / tool / LLM 的原始底层事件，而是这套标准化后的 `ConversationEvent` 与后端返回的 `Message` / `Turn` / `Run` 状态。

所以前端主链应当是：

```text
snapshot / ConversationEvent
-> SessionStateStore
-> messageViewModel
-> Chat UI
```

而不是：

```text
后端单独维护 Transcript 层
```

## 4. 核心领域模型

### 4.1 `Session`

`Session` 是一个会话线程。

职责：

- 会话容器
- 持有项目归属
- 持有会话级偏好配置

它不是：

- 一次执行
- 一次提问
- 一条消息

### 4.2 `Turn`

`Turn` 是一次用户发送及其后续响应容器，也就是系统内部的一轮对话边界。

职责：

- 归拢同一轮下的消息
- 绑定这一轮的根 user `message`
- 管理这一轮是否完成、失败、取消

它不是：

- 具体的执行尝试
- 重试次数
- 原始底层事件

当前 Phase 1 约束：

- 一个 `Turn` 只包含一条根 user `message`
- 一个 `Turn` 当前最多只有一个 `Run`

### 4.3 `Run`

`Run` 是一次执行尝试。

职责：

- 绑定一个 `Turn`
- 记录这次尝试的状态
- 记录 `provider` / `model` / `workspace`
- 记录这次尝试的起止时间

它不是：

- 用户消息
- 最终 assistant 回答
- 前端消息列表主体

### 4.4 `Event`

`Event` 是写入方式 append-only、生命周期受策略控制的运行期领域事件。

职责：

- 记录 `Turn` / `Run` 执行过程中的状态变化
- 作为 `Projection` 的输入
- 作为 live / replay 的统一事件流
- 支持活跃会话的短期重放
- 支持 `afterSeq` 增量同步
- 支持短期调试和审计窗口

它不是：

- provider / tool / LLM 的原始底层事件
- 用户直接看到的对象
- 长期历史展示主数据
- `memory` 的主锚点

### 4.5 `Message`

`Message` 是最重要的稳定实体。

职责：

- 用户可感知的消息对象
- 前端同步主键
- 未来 `memory` / `search` / `summary` 的锚点

它包括：

- 用户消息
- assistant 消息
- `tool_trace`
- `system notice`

它不是：

- 原始底层事件
- 只给 UI 用的瞬时投影

对于 `tool_trace`，Phase 1 不允许把结构随意塞进 `metadata_json`。

至少固定以下结构：

```json
{
  "summary": "...",
  "tool_name": "...",
  "tool_status": "pending|running|success|failed|cancelled",
  "input": {},
  "output": {},
  "error": null
}
```

也就是说，`tool_trace` 的详情必须 schema-first，而不是任意 JSON。

### 4.6 `Projection`

`Projection` 是 `Event -> Message` 的唯一合法写入口。

它不是一张新表，而是一个受强约束的写路径模块，可以实现为类似 `MessageProjector` 的 service。

职责：

- 消费标准化后的 `ConversationEvent`
- 将运行期变化收敛为稳定的 `Message` 状态
- 保证 `Message` identity 在流式过程中保持稳定
- 保证 live 与 replay 的投影结果一致
- 在 `Message` 更新完成后，允许同一 `ConversationEvent` 被继续用于 live 广播与 replay

它不负责：

- 前端渲染
- 业务决策
- 工具执行
- LLM 调用
- 任意暴露的 `Message` CRUD

硬规则：

- 禁止业务代码直接更新 `messages` 表中的业务状态
- 所有 `Message` 的创建、追加、完成、失败，都必须通过 `Projection`
- Phase 1 不再拆 `Domain Event` / `Session Event` 两套事件语言，而是统一使用一套 `ConversationEvent`

最小投影链路应当是：

```text
Domain Intent
-> ConversationEvent
-> Event Persist
-> Projection
-> Message Upsert
-> ConversationEvent Broadcast
```

Phase 1 可以按下面这组最小规则落地：

| ConversationEvent | Projection Result |
| --- | --- |
| `turn.created` | 创建 `Turn`，并记录其根 user `message` |
| `message.created` | 创建根 user `message`，或创建普通 `message`（如 `tool_trace` / `system notice`） |
| `run.started` | 创建空的 streaming assistant `message` |
| `message.delta` | 追加目标 `message` 的正文或详情 |
| `message.updated` | 用结构化方式更新目标 `message` 的状态或详情 |
| `message.completed` | 标记目标 `message` 完成 |
| `message.failed` | 标记目标 `message` 失败 |
| `run.completed` | 收敛 `Run` 状态 |
| `run.failed` | 收敛 `Run` 状态，并保证相关消息状态收敛 |
| `run.cancelled` | 收敛 `Run` 取消状态，并保证相关消息状态收敛 |

### 4.7 前端 `messageViewModel`

`messageViewModel` 只存在于前端展示层，不是后端领域对象，也不单独持久化。

职责：

- 读取 `Message`
- 结合当前 `Turn` / `Run` 状态补充展示信息
- 生成最终可渲染的聊天列表项

它负责的事情包括：

- 按 `messages.conversation_seq` 排序
- 根据 `message_type` 决定默认折叠策略
- 合成“正在思考中”这类临时展示状态
- 输出聊天 UI 需要的最终列表项结构

它不负责：

- 持久化
- 作为同步真相
- 作为 memory / summary 的锚点
- 回写后端状态

## 5. 核心边界定义

### 5.1 `Turn` 与 `Run` 的边界

必须明确：

- `Turn` = 一次用户发送及其后续响应容器
- `Run` = 对该 `Turn` 的一次执行尝试

规则：

- 用户再次点击发送，即使内容完全一样，也必须创建新的 `Turn`
- 当前 Phase 1 中，一个 `Turn` 最多只有一个 `Run`
- 以后如果同一轮需要支持 regenerate / retry，再把一个 `Turn` 扩展为多个 `Run`

### 5.2 `Message` 与 `Turn` / `Run` 的关系

必须明确：

- 每条 `Message` 必须属于一个 `Session`
- 每条 `Message` 必须属于一个 `Turn`
- 每条 `Message` 最多属于一个 `Run`

规则：

- 根用户消息：`run_id = null`
- assistant 消息：必须绑定生成它的 `run_id`
- `tool_trace`：必须绑定生成它的 `run_id`
- 一条消息创建后，不能跨 `Turn` 或跨 `Run` 迁移

### 5.3 `Projection` 与 `Message` 的写边界

必须明确：

- `Message` 的业务状态不是任意 service 都能直接修改
- `Projection` 是 `Message` 业务写路径的唯一入口
- `message repo / DAO` 只负责持久化，不负责决定状态如何变化

规则：

- 业务代码可以产生 `ConversationEvent`，但不能绕过 `Projection` 直接改 `Message`
- 同一个 `ConversationEvent` 在 replay 和 live 下必须得到相同的 `Message` 结果
- 对前端广播的事件就是标准化后的 `ConversationEvent`，不能再额外临时拼装另一套协议
- 同一个 `event_id` 重复进入 `Projection` 时，结果必须完全一致
- `Projection` 必须保证 exactly-once effect：重复投影不能重复 append `message.delta`
- `message.delta` 只用于文本追加
- `message.updated` 用于结构化字段替换或状态更新，尤其适用于 `tool_trace`

### 5.4 `Turn` 的终态规则

当前 Phase 1 中，`Turn` 的终态是可推导状态，不单独持久化。

也就是说：

- `Turn` 不持有独立 `status`
- 不持有独立 `finished_at`
- 不产生 `turn.completed` / `turn.failed` / `turn.cancelled` 作为独立事实事件

读取层可根据以下条件推导 `Turn` 是否结束：

- 该 `Turn` 下唯一 `Run` 已进入终态
- 对应消息状态已经收敛

后续如果一个 `Turn` 需要承载多个 `Run`，再评估是否为 `Turn` 引入独立状态机。

### 5.5 `Run` 的终态规则

`Run` 只允许三种终态：

- `completed`
- `failed`
- `cancelled`

一个 `Run` 进入终态的条件：

- 已有终态事件
- 对应消息状态已经收敛

具体规则：

- `completed`：必须至少存在一条已完成的 assistant `message`，且当前 `Run` 已完成。
- `failed`：当前 `Run` 已失败，且系统不再继续在当前 Phase 1 内自动重试。
- `cancelled`：当前 `Run` 已取消，且相关流式消息状态已经收敛。

## 6. Phase 1 建议的数据模型（精简版）

这一版模型只保留“当前真的会用到”的字段。

### 6.1 `sessions`

保留字段：

- `id`
- `project_id`
- `title`
- `preferred_provider_id`
- `preferred_model_id`
- `created_at`
- `updated_at`

说明：

- `Session` 本身不持有顺序号字段。
- `conversation_seq` 的业务真相只存在于 `events` / `messages`。
- 如果后续实现中需要为分配序号加入缓存字段，也应作为内部优化处理，而不是当前 Phase 1 的业务模型字段。

### 6.2 `turns`

保留字段：

- `id`
- `session_id`
- `root_message_id`
- `created_at`

说明：

- `root_message_id` 指向该轮的根 user `message`
- 当前 Phase 1 中，可通过 `unique (session_id, root_message_id)` 保证一条根 user `message` 对应一个 `Turn`
- 当前 Phase 1 中，一个 `Turn` 最多只有一个 `Run`
- 后续如果需要支持 regenerate / retry，可在不推翻 `Turn` 语义的前提下扩展为一个 `Turn` 多个 `Run`
- `Turn` 当前只作为轮次 identity boundary，不持久化独立终态

### 6.3 `runs`

保留字段：

- `id`
- `session_id`
- `turn_id`
- `status`
- `provider_id`
- `model_id`
- `workspace_root`
- `created_at`
- `finished_at`

说明：

- `turn_id` 指向本次执行所属的 `Turn`
- 当前 Phase 1 中，可通过 `unique (turn_id)` 保证一个 `Turn` 最多只有一个 `Run`
- 暂不保留 `attempt_no`
- 暂不保留 `error_summary`
- 这些都可以在后续 `retry` / `regenerate` 阶段再引入

### 6.4 `events`

保留字段：

- `id`
- `session_id`
- `turn_id`
- `run_id`
- `message_id`
- `conversation_seq`
- `event_type`
- `payload_json`
- `created_at`

约束：

- `unique (session_id, conversation_seq)`

说明：

- 不保留 `idempotency_key`
- `Event` 的写入方式是 append-only，但允许由后台策略异步清理
- `Event` 默认不是长期持久化层，而是运行期同步层
- 成功完成的 `Turn` 可在短暂保留窗口后清理；失败或取消的 `Turn` 可保留更久
- `Event` 是服务端内部事实流，不需要额外再引一个幂等字段

### 6.5 `messages`

保留字段：

- `id`
- `session_id`
- `turn_id`
- `run_id`
- `role`
- `message_type`
- `status`
- `conversation_seq`
- `content_text`
- `metadata_json`
- `created_at`
- `updated_at`

说明：

- 不保留 `parent_message_id`
- 不保留 `collapsed_by_default`
- 不保留 `completed_at`
- 不保留 `deleted_at`

其中：

- 是否默认折叠，前端可按 `message_type === "tool_trace"` 推导
- `completed_at` 当前不需要单独存，`status + updated_at` 足够
- `conversation_seq` 表示该 `Message` 首次进入前端消息列表的顺序，只在创建时分配一次，后续 delta / status 更新不改写它

## 7. 事件协议设计

前端不应该直接消费原始事件：

- `llm:start`
- `llm:content`
- `tool:start`
- `tool:result`

Phase 1 统一只保留一套标准化 `ConversationEvent`。

这套 `ConversationEvent`：

- 持久化到 `events`
- 作为 `Projection` 输入
- 作为 WebSocket live 广播输出
- 作为 `afterSeq` replay 输出

### 7.1 前端命令

#### `turn.start`

前端发送：

- `user_message_id`
- `message`
- `project_id`
- `provider_id`
- `model_id`

说明：

- 这里不再发送 `idempotency_key`
- `user_message_id` 由客户端提议，服务端校验并接受
- 一次 `turn.start` 会在服务端创建新的 `Turn`
- 同一事务内创建根 user `message`
- 服务端是最终权威；客户端不能绕过服务端自行落库 user `message`

#### `run.cancel`

前端发送：

- `run_id`

### 7.2 后端对前端广播的事件

Phase 1 保留这些事件即可。

`Turn` 事件：

- `turn.created`

`Run` 事件：

- `run.started`
- `run.completed`
- `run.failed`
- `run.cancelled`

`Message` 事件：

- `message.created`
- `message.delta`
- `message.updated`
- `message.completed`
- `message.failed`

### 7.3 事件包络

所有 replay 和 live 事件共享同一结构：

```json
{
  "event_id": "evt_xxx",
  "session_id": "session_xxx",
  "turn_id": "turn_xxx",
  "run_id": "run_xxx",
  "message_id": "msg_xxx",
  "conversation_seq": 42,
  "event_type": "message.delta",
  "occurred_at": "2026-04-24T10:00:00Z",
  "data": {}
}
```

关键规则：

- `conversation_seq` 是顺序真相
- 前端按 `conversation_seq` 线性消费
- replay 和 WebSocket live 必须使用同一事件结构
- Phase 1 的 replay 和 live 使用同一套 `ConversationEvent`
- 历史 `Event` 不要求永久可重放，超出保留窗口后允许回退到 snapshot
- 所有 `message.*` 事件必须带顶层 `message_id`
- `run.*` / `turn.*` 事件可以没有 `message_id`，或显式为 `null`

## 8. 前端 `messageViewModel` 显示策略

Phase 1 中，不再定义后端 `Transcript` 层。

前端展示只依赖：

- `Message`
- 当前 `Turn` / `Run` 状态
- `ConversationEvent` 增量更新

并在前端派生出 `messageViewModel`。

### 8.1 assistant 的流式策略

正确做法是：

- `run.started` 后先创建一条空的 streaming assistant `message`
- `llm:content` / `summary:token` 只追加到这条 `message`
- 完成时只发 `message.completed`
- 不再新建第二条 final assistant `message`

所以 assistant 的 identity 从头到尾都不变。

### 8.2 “正在思考中”状态策略

如果当前 `Run` 已开始，但 assistant `message` 还是空内容：

- 前端显示 `assistant-status`

文案例如：

- 正在思考中
- 正在执行中
- 正在整理回答

当 assistant `message` 真正收到第一段正文后：

- 隐藏 `assistant-status`
- 切换成正文流式显示

### 8.3 中间探索过程显示策略

中间过程通过 `tool_trace` `message` 表达。

前端渲染规则：

- `message_type === "tool_trace"`
- 默认折叠
- 展开后展示 `details`

这样：

- 当前执行时可以看
- 重开旧会话后也能回看

## 9. 读路径设计

### 9.1 Snapshot

首次打开会话：

`GET /api/sessions/{session_id}/state`

返回：

- `session` 信息
- `last_conversation_seq`
- `turn` 状态摘要
- `run` 状态摘要
- `message` 列表

说明：

- `last_conversation_seq` 是当前会话中最新已分配的顺序号，可由 `events` 或 `messages` 推导得到。
- 历史会话展示以后端返回的状态快照为主，不依赖旧 `Event` 长期存在。
- 前端使用这些状态派生 `messageViewModel`，而不是依赖服务端返回单独的 `Transcript` 结构。

### 9.2 Replay

断线恢复或补齐缺口：

`GET /api/sessions/{session_id}/events?afterSeq=...`

说明：

- `Replay` 只保证当前活动窗口内的增量补齐，不承诺长期历史重放。
- 如果 `afterSeq` 已落在被清理的 `Event` 窗口之前，服务端返回 `410 Gone`，并附带 `resync_required: true`。
- 客户端收到 `resync_required` 后，应重新拉取 `/state` 完成全量对齐。

### 9.3 Live

活动会话实时更新：

`WS /ws/sessions/{session_id}/events?afterSeq=...`

说明：

- WebSocket 重连时，如果请求的 `afterSeq` 已落后于当前保留窗口，服务端应通知客户端执行全量 resync，而不是尝试补发已删除事件。

### 9.4 `Event` 生命周期与清理策略

`Event` 的保留单位以 `Turn` 为准，而不是以整个 `Session` 为准。

建议策略：

- 进行中的 `Turn`：保留该 `Turn` 的全部 `Event`
- `completed` 的 `Turn`：在对应 `Message` 状态收敛后，保留短暂窗口后清理，建议 `10` 分钟到 `1` 小时
- `failed` 或 `cancelled` 的 `Turn`：保留更久用于排障，建议 `7` 天，可按环境配置

关键约束：

- 清理 `Event` 不影响历史会话展示，因为历史展示依赖的是 `Message`
- 清理 `Event` 不影响 `Turn` / `Run` / `Message` 的稳定主键关系
- `conversation_seq` 始终单调递增，即使旧 `Event` 已被清理

## 10. Phase 1 不做的事

明确不做：

- `memory`
- `llm_usage` 独立落表
- `summary pipeline`
- `focus state`
- `branch conversation`
- `edit message`
- 编辑历史消息后重新发送，并让后续消息直接截断消失
- `regenerate`
- `embeddings`
- `RAG`
- 后端 `Transcript` / `messageViewModel` 持久化单独落表

这些都等 `Conversation` 底座稳定后再做。

对于“编辑某条历史消息后从这里重新发送”的需求，后续更适合通过：

- `supersede`：旧后续消息标记为失效，保留可审计历史
- `branch`：从指定消息开始生成新的后续链

而不是在 Phase 1 中直接物理删除后续消息。

## 11. 状态不变量

以下不变量必须在实现中保持成立：

- 每个 `Turn` 只属于一个 `Session`
- 每个 `Turn` 只绑定一条根 user `message`
- 每个 `Run` 只属于一个 `Session`
- 每个 `Run` 只属于一个 `Turn`
- 每条 `Message` 只属于一个 `Session`
- 每条 `Message` 只属于一个 `Turn`
- 每条 `Message` 最多只属于一个 `Run`
- 根用户消息 `run_id = null`
- assistant / `tool_trace` 消息必须绑定一个 `Run`
- 当前 Phase 1 中，同一条根 user `message` 对应一个 `Turn`
- 当前 Phase 1 中，一个 `Turn` 最多只有一个 `Run`
- 相同文本的两次发送，如果 `user_message_id` 不同，必须是两个不同的根 user `message`
- `Message` 的身份只能靠 `id`，不允许靠内容做去重或匹配
- 同一 `Session` 内的 `events.conversation_seq` 必须单调递增且不复用
- `messages.conversation_seq` 只在该消息首次进入前端消息列表时分配，后续更新不得改写
- Phase 1 只保留一套标准化 `ConversationEvent`

## 12. 最终结论

我建议这次统一文档后的总体设计主轴就是：

```text
后端：Session / Turn / Run / Event / Projection / Message
前端：SessionStateStore / messageViewModel / Chat UI
```

并且坚持：

```text
后端：Event -> Projection -> Message
前端：state / event -> messageViewModel -> Chat UI
```

而不是：

```text
后端单独维护 Transcript 作为独立数据层
```

同时进一步简化表结构：

- 删掉 `idempotency_key`
- 删掉一批不是当前闭环必需的冗余字段
- 保留最小稳定事实层
- 把 `Event` 明确收敛为短生命周期的运行期同步层
- 把 `Projection` 明确为 `Message` 的唯一合法写入口
- Phase 1 统一只保留一套 `ConversationEvent`

这样做的好处是：

- 模型更轻
- 边界更清楚
- 前端流式更稳定
- 中间过程能保留
- 以后接 `memory` 不会推倒重来
