# ReflexionOS Session 正式化与 Transcript 边界收敛设计

> 状态：已确认的设计文档。
> 该文档用于把 workspace 当前的本地 session 模式收敛为后端正式 session 资源，并统一 realtime、history、cancelled、failed 的边界语义。
> 这份文档同时覆盖后端 session 接管、transcript round 模型、执行提交流程，以及前端职责拆分方案。

**版本**: v1.0  
**日期**: 2026-04-20  
**语言**: 中文  
**关联文档**: `docs/superpowers/specs/2026-04-20-workspace-message-streaming-and-storage-design.md`

---

## 一、目标

本次改造要解决的不是单一接口问题，而是 workspace 当前会话系统的三个结构性问题：

1. `session` 主要由前端本地定义，后端只被动接受 `session_id`
2. realtime 事件和 history 回放不是同一套核心语义模型
3. 页面、布局组件、overlay hook 承担了过多本应属于后端或 feature/application 层的职责

本次设计的目标明确为：

1. 让 `session` 成为后端正式资源，并严格隶属于某个 `project`
2. 让 session history 以统一的 `round -> items` 模型存在，而不是前端自行重组
3. 让 execution 运行期只维护当前未提交轮次，完成时提交、取消时整轮丢弃、失败时可保留
4. 收缩前端 store、page、layout、hook 的职责，让正式历史与临时执行态分离

---

## 二、已确认的设计决策

本节只记录已经和产品语义对齐、后续实现必须遵守的规则。

### 2.1 Session 的正式定义

- `session` 是某个 `project` 下的一个正式会话资源
- session 不是前端本地临时容器
- session 必须由后端创建、更新、删除和查询

### 2.2 旧本地 session 数据处理方式

- 直接放弃旧 localStorage 中的 session 主数据
- 不做本地 session 到后端 session 的自动迁移
- 升级后以前端本地 session 数据失效为代价，换取明确边界和后续可维护性

### 2.3 History 语义

- history 必须直接由后端以 `round -> items` 结构返回
- 前端不再根据平铺 archive 自己推导 round
- realtime draft round 与 persisted history round 使用同一套核心 item 语义

### 2.4 Cancelled 语义

- `cancelled` 表示当前轮次被用户主动撤销
- 当前轮次前后端都不保留
- cancelled 不是失败，不应在 history 中留下痕迹

### 2.5 Failed 语义

- `failed` 不等于 `cancelled`
- failed 轮次可以保留到 history 中
- 用户应能看到该轮在失败前已发生的过程及最终失败结果

### 2.6 前端收到 complete event 后的固定顺序

前端必须遵守以下顺序，避免草稿和正式历史重复显示：

1. `complete event`
2. `clear draft`
3. `refresh history`
4. `render persisted rounds`

该顺序在实现中视为硬规则，而不是建议顺序。

---

## 三、问题定义

当前 workspace 会话系统的混乱不在于“代码写得不优雅”，而在于职责边界本身不成立。

### 3.1 Session 所有权不清

当前前端 `workspaceStore` 本地生成 `sessionId`，持久化 session 元数据和最近轮次；后端仅把 `session_id` 当作历史分组键使用。

这导致：

- session 在前端像正式资源
- 在后端又像一个被动标签
- 会话标题、偏好、轮次与后端真实历史没有单一事实源

### 3.2 Realtime 与 History 协议分裂

当前运行时是细粒度事件流，history 又是另一套平铺 archive 记录。前端必须在 `useExecutionOverlay` 与 `buildRoundsFromTranscriptArchive()` 中承担大量语义拼装工作。

这导致：

- 刚执行完和刷新后看到的内容不一定完全一致
- 前端 hook 事实上承担了历史语义的定义工作
- history 不是协议层稳定产物，而是前端重建结果

### 3.3 前端职责过载

当前至少有三个地方承担了过多业务编排：

- `AgentWorkspace.tsx`
- `WorkspaceSidebar.tsx`
- `useExecutionOverlay.ts`

此外，`SettingsPage.tsx` 也承载了大量 provider/model 领域规则。

结果是：

- 页面既做展示，又做应用编排，又直接写 store，又直接调 API
- overlay hook 同时管理 transient UI 和正式历史持久化
- 布局组件同时承担导航、CRUD、过滤和跨 store 协调

---

## 四、设计原则

### 4.1 后端是真相源，前端是展示层与轻缓存层

后端负责：

- session 主数据
- session history
- execution 到 round 的提交规则

前端负责：

- UI 状态
- 会话展示
- 当前执行中的 draft round

前端不再承担正式 history 与 session 主数据的长期持久化职责。

### 4.2 正式历史与临时执行态必须分离

persisted history 和 draft round 在语义上不是一回事。

- persisted history：已提交的正式 round
- draft round：当前执行中、尚未提交的临时结果

两者可以共享 item 结构，但不能共用持久化入口。

### 4.3 Cancelled 按未提交事务处理

`cancelled` 的本质不是一条带状态的历史记录，而是一轮未提交事务的直接丢弃。

因此 cancelled 不应在 session history 中出现。

### 4.4 小步拆分前端职责

这次不是为了抽象而抽象，而是把明显不该放在 page/layout/hook 内的职责拿走。

拆分的判断标准只有一个：

某段逻辑如果定义了领域规则、持久化规则、API 编排或工作流收尾规则，就不应继续留在单一页面组件或 overlay hook 里。

### 4.5 新结构落地后必须清除旧代码路径

这次改造不是“新旧并存”的过渡架构，而是明确的结构替换。

因此在新结构完成后，必须清除以下旧路径，而不是继续保留兼容分支：

- 前端本地生成 `sessionId` 的逻辑
- `workspaceStore` 中保存 session 主数据与 `recentRounds` 的逻辑
- 前端根据平铺 archive 重建 round 的逻辑
- overlay hook 直接写正式 history 或 session title 的逻辑
- 页面、布局组件中遗留的旧 session/history 直写逻辑

判断标准只有一个：

如果某段旧代码仍然在定义 session、拼装正式 history、或让前端继续扮演真相源，它就必须被删除，而不是保留为兜底路径。

---

## 五、目标架构

### 5.1 后端职责

后端成为以下三类数据的唯一事实源：

1. `Session`
2. `SessionHistory`
3. `ExecutionDraftRound -> Commit / Discard`

### 5.2 前端职责

前端只负责：

1. 展示 session 列表与当前 session history
2. 发起 session 创建、更新、删除
3. 在执行期渲染当前 draft round 与 overlay UI
4. 根据 execution 事件清空 draft 并刷新 history

### 5.3 目标链路

目标链路统一为：

```text
用户选择 project
  ↓
前端加载 project 下的正式 sessions
  ↓
用户选择或创建 session
  ↓
前端加载 session history（rounds）
  ↓
用户发送消息，后端基于正式 session 创建 execution
  ↓
realtime 事件驱动前端 draft round 渲染
  ↓
若 completed：提交 round -> clear draft -> refresh history
  ↓
若 cancelled：discard round -> clear draft -> 不刷新新增历史
  ↓
若 failed：提交失败 round -> clear draft -> refresh history
```

---

## 六、领域模型设计

### 6.1 Session

`Session` 是项目下的正式会话资源，建议字段如下：

```text
id
project_id
title
preferred_provider_id
preferred_model_id
created_at
updated_at
```

约束：

- `session.project_id` 必须存在且合法
- `session` 删除时，其 history 一并删除
- execution 创建时，`session.project_id` 必须与 `execution.project_id` 一致

### 6.2 TranscriptRound

`TranscriptRound` 表示一次用户发送触发的一整轮正式会话结果。

建议字段：

```text
id
session_id
project_id
execution_id
created_at
```

语义约束：

- 一个 round 对应一次用户请求
- history 中只保存已提交 round
- cancelled round 不存在于 history 中

### 6.3 TranscriptItem

`TranscriptItem` 是 round 内的顺序消息项，realtime draft 和 persisted history 共享该核心结构。

首版建议保持最小集合：

- `user-message`
- `agent-update`
- `action-receipt`
- `assistant-message`

建议结构：

```text
id
type
content
receipt_status
details
created_at
sequence
```

其中：

- `action-receipt` 使用 `receipt_status` 与 `details`
- 其他 item 主要使用 `content`

### 6.4 DraftRound

`DraftRound` 不作为正式 history 存在，而是 execution 生命周期中的临时结果聚合器。

它至少应包含：

```text
execution_id
session_id
project_id
created_at
items[]
```

DraftRound 只存在于运行期，完成时提交、取消时丢弃。

---

## 七、后端 API 设计

### 7.1 Session API

新增正式 session 路由：

1. `POST /api/projects/{project_id}/sessions`
2. `GET /api/projects/{project_id}/sessions`
3. `GET /api/sessions/{session_id}`
4. `PATCH /api/sessions/{session_id}`
5. `DELETE /api/sessions/{session_id}`
6. `GET /api/sessions/{session_id}/history`

### 7.2 History 返回格式

`GET /api/sessions/{session_id}/history` 必须直接返回 rounds，而不是前端需要再拼装的 archive。

建议返回形态：

```json
{
  "session_id": "session-123",
  "project_id": "project-456",
  "rounds": [
    {
      "id": "round-1",
      "created_at": "2026-04-20T12:00:00Z",
      "items": [
        {
          "id": "item-1",
          "type": "user-message",
          "content": "请分析这个项目"
        },
        {
          "id": "item-2",
          "type": "agent-update",
          "content": "我先检查目录结构"
        },
        {
          "id": "item-3",
          "type": "action-receipt",
          "receipt_status": "completed",
          "details": []
        },
        {
          "id": "item-4",
          "type": "assistant-message",
          "content": "我已经完成初步分析"
        }
      ]
    }
  ]
}
```

### 7.3 Execution 创建约束

execution 创建时必须满足：

- `session_id` 存在
- `session.project_id == request.project_id`
- provider/model 在后端完成最终校验和 fallback

execution 不再承担“顺便定义 session”的职责。

---

## 八、Execution 与 Transcript 提交规则

### 8.1 总体规则

execution 运行期只维护 draft round，不直接写 session history。

history 的写入只发生在以下情况：

- `completed`：提交 round
- `failed`：提交失败 round
- `cancelled`：不提交

### 8.2 Completed

当 execution 成功完成时：

1. 根据 execution 期间累计的统一 item 构建 round
2. 提交 round 到 session history
3. 更新 session `updated_at`
4. 若 session title 仍为默认标题，则按首条 user message 派生标题

### 8.3 Cancelled

当 execution 被取消时：

1. 丢弃 draft round
2. 不写 transcript item
3. 不写 conversation history
4. 不更新 session `updated_at`

cancelled 必须对用户呈现为“本轮未发生持久化”。

### 8.4 Failed

当 execution 失败时：

1. 提交当前 round
2. round 中保留已经发生的 `agent-update` 与 `action-receipt`
3. 用最终失败消息结束该轮
4. 更新 session `updated_at`

原因是 failed 属于有结果的系统状态，不应与用户主动取消混淆。

### 8.5 建议的后端内部拆分

建议新增两个后端内部组件：

1. `ExecutionDraftRoundBuilder`
2. `TranscriptCommitService`

职责分别为：

- builder：把 execution 期间的事件、上下文、step 汇总为统一 draft round
- commit service：负责 completed/failed 的提交，以及 cancelled 的 discard

这样可以避免继续在 `rapid_loop.py finally` 中无条件推导 transcript。

---

## 九、前端架构调整

### 9.1 `workspaceStore` 收缩为纯 UI Store

`frontend/src/stores/workspaceStore.ts` 改造后只保留 UI 状态：

- `currentSessionId`
- `expandedProjectIds`
- `expandedSessionProjectIds`
- `searchQuery`
- `searchOpen`

必须移除的职责：

- 本地保存 session 主体
- 本地生成 `sessionId`
- 本地保存 `recentRounds`
- 本地更新 session title
- 本地更新 session preference

### 9.2 新增 Session Feature 层

建议新增目录：

- `frontend/src/features/sessions/`

建议文件：

- `sessionApi.ts`
- `sessionLoader.ts`
- `sessionStore.ts`
- `sessionActions.ts`

职责划分：

- `sessionApi.ts`：纯 API 封装
- `sessionStore.ts`：缓存后端返回的 session 与 history 数据
- `sessionLoader.ts`：负责加载与刷新
- `sessionActions.ts`：负责 create/update/delete 等业务动作编排

### 9.3 `AgentWorkspace.tsx` 拆分

目标是让页面回归“装配层”。

建议拆出：

1. `useCurrentSessionViewModel`
2. `useSessionActions`
3. `useSendMessage`

页面保留：

- 取 view model
- 绑定 actions
- 渲染 header / transcript / input

页面移除：

- 直接拉 history
- 直接创建 session
- 直接更新 session preference
- 直接写正式 rounds

### 9.4 `useExecutionOverlay.ts` 拆分

现有 overlay hook 混合了：

- realtime 事件解释
- transient UI 状态
- 正式历史持久化
- session 标题派生

改造后建议拆为：

1. `useExecutionDraftRound`
2. `useExecutionOverlayUi`
3. `draftRoundAssembler` 或等价纯函数模块

新的职责边界：

- draft round hook：只维护当前执行中的临时轮次
- overlay ui hook：只维护 loading、status bubble、streaming 表现
- history 刷新：由 execution 完成后统一触发，不在 overlay hook 中持久化

### 9.5 `WorkspaceSidebar.tsx` 拆分

建议拆为：

1. `ProjectSidebarSection`
2. `SessionSidebarSection`
3. `useSidebarProjectActions`
4. `useSidebarSessionActions`
5. `useSidebarSearch`

目标是让 sidebar 从“布局控制器”退回到“展示壳 + 轻量组合层”。

### 9.6 `SettingsPage.tsx` 拆分

虽然它不属于 session 改造核心，但它是当前职责过重最明显的页面之一，建议一并收口。

建议拆出：

- `features/llm/providerDraft.ts`
- `features/llm/providerActions.ts`

页面只保留表单和交互绑定，不再承担 provider/model 规则定义与多 API 编排。

---

## 十、前端渲染链路设计

### 10.1 渲染数据来源

页面最终渲染源应拆分为三部分：

1. `persistedRounds`
2. `draftRoundItems`
3. `overlayItems`

其中：

- `persistedRounds` 来自 `sessionStore.historyBySessionId`
- `draftRoundItems` 来自 `useExecutionDraftRound`
- `overlayItems` 来自 `useExecutionOverlayUi`

### 10.2 完成顺序

执行完成后必须严格按以下顺序处理：

1. 收到 `complete event`
2. `clear draft`
3. `refresh history`
4. `render persisted rounds`

### 10.3 取消顺序

执行取消后按以下顺序处理：

1. 收到 `cancelled event`
2. `clear draft`
3. 保留现有 persisted history 不变
4. 页面不追加任何新的 round

### 10.4 失败顺序

执行失败后按以下顺序处理：

1. 收到 `failed/error event`
2. `clear draft`
3. `refresh history`
4. 渲染失败 round 的 persisted history

---

## 十一、实施顺序

建议按以下顺序落地，以便每一步都可验证。

### 阶段 1：后端正式接管 Session

实现内容：

- 新增 session model / repository / service / routes
- execution 创建强依赖正式 session
- `GET /sessions/{id}/history` 返回 rounds

阶段目标：

- 前端已经可以基于后端 session 拉取正式会话列表与历史

### 阶段 2：调整 Execution 提交语义

实现内容：

- completed commit
- cancelled discard
- failed retain

阶段目标：

- 历史与取消语义收口
- 不再在 finally 中无条件持久化 transcript

### 阶段 3：前端迁移到正式 Session 模式

实现内容：

- `workspaceStore` 去 session 主数据
- 新增 sessions feature 层
- 页面接入 session API / history API
- 放弃旧 localStorage session 数据

阶段目标：

- 前端不再本地生成 session
- history 完全来自后端

### 阶段 4：拆前端过重入口

实现内容：

- 拆 `AgentWorkspace.tsx`
- 拆 `useExecutionOverlay.ts`
- 拆 `WorkspaceSidebar.tsx`
- 拆 `SettingsPage.tsx`

阶段目标：

- 页面与 hook 的职责边界收拢到可维护状态

---

## 十二、兼容性与迁移策略

### 12.1 本地旧 Session 数据

本次方案明确不兼容旧本地 session 数据。

处理方式：

- 新版本发布后，前端 localStorage 中旧 session 数据直接失效
- 不做自动导入
- 以边界清晰和后续维护稳定性优先

### 12.2 版本切换预期

用户升级后的预期变化：

- 原本 localStorage 中的会话列表不再可见
- 新创建的 session 统一走后端
- 新 history 行为遵守 completed/failed/cancelled 的新规则

### 12.3 旧代码清理策略

本次改造明确要求在新结构可用后，完全移除旧代码路径，不保留双轨并行。

必须清理的内容包括：

1. 前端本地 session 主体持久化逻辑
2. `createSessionId()` 及等价本地 session id 生成逻辑
3. `buildRoundsFromTranscriptArchive()` 及等价 history 重建逻辑
4. overlay hook 内直接写正式 rounds/title 的逻辑
5. 页面与 sidebar 中面向旧 session store 的业务写操作

验收标准不是“新代码能跑”，而是：

- 新链路已接管
- 旧链路已删除
- 仓库中不存在继续依赖旧 session 本地真相源的运行路径

---

## 十三、验证标准

### 13.1 Session 资源验证

- session 创建后，刷新页面仍能看到
- session 删除后，history 一并消失
- execution 不能绑定不存在或跨 project 的 session

### 13.2 History 语义验证

- history 接口直接返回 rounds
- 前端不再使用本地 round 重建逻辑作为真相源
- 刷新前后同一轮显示语义一致

### 13.3 Cancelled 语义验证

- 运行中取消后，当前 draft 清空
- history 中无新 round
- 刷新后也看不到该轮

### 13.4 Failed 语义验证

- 运行失败后，history 中新增失败 round
- 用户能看到失败前已发生的过程和失败结果

### 13.5 前端职责验证

- `workspaceStore` 不再存 session 主数据
- `AgentWorkspace.tsx` 不再直接负责正式历史持久化
- `useExecutionOverlay.ts` 不再直接写 session history 或 session title
- `WorkspaceSidebar.tsx` 不再直接承担完整 session/project 控制器职责

---

## 十四、非目标

本次设计不包含以下内容：

1. 多端同步冲突解决
2. session/history 分页能力
3. transcript 搜索能力
4. 更复杂的消息类型扩展
5. 记忆系统长期结构化建模

这些能力可以在 session 正式化完成后继续演进，但不属于本次改造范围。

---

## 十五、结论

本次方案的核心不是“把 session 从一个 store 挪到另一个 store”，而是：

**把 session、history 和 execution commit/discard 语义收敛为后端正式边界，把前端退回到展示、组合与临时执行态管理的位置。**

在该方案下：

- session 是正式项目资源
- history 是后端 round 真相源
- completed 会提交
- cancelled 会丢弃
- failed 会保留
- 前端不再同时承担 session 定义者、history 组装者和执行收尾持久化者三种角色

这是后续继续扩展 session 搜索、分页、多端同步、结构化上下文的必要前提。
