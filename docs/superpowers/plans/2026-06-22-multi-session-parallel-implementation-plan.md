# 多会话并行实现计划

## 目标

基于已确认的需求规范，为 ReflexionOS 落地“多会话并行”第一阶段最小闭环：

- 不同 `session` 可独立运行
- 用户可在运行中切换会话
- 当前会话和后台活跃会话状态可持续同步
- 侧边栏可显示运行中 / 等待审批 / 未读活动
- 切回会话后可恢复正确 transcript、run、plan、审批状态

本计划只覆盖第一阶段交付，不扩展到多窗口、同会话多 run 并发、通知中心或复杂会话管理。

## 当前实现判断

从现有代码看，当前阻塞点主要在前端：

- `useConversationRuntime` 是单连接模型，只绑定 `currentSessionId`
- `WorkspaceSidebar` 只使用当前会话的 `isConversationBusy`，没有多会话派生状态
- `workspace.store` 使用 `persist()`，但 `partialize()` 只持久化 5 个基础 UI 字段，不包含任何对话未读或会话同步状态
- `conversation.store` 已按 `sessionId` 存多份快照，是可复用基础
- 当前没有全局 `runId -> sessionId` 反向索引
- 现有 `useConversationRuntime.test.ts` WebSocket mock 是单连接 handlers map，无法直接覆盖多连接并行行为
- 后端 `session_id`、conversation snapshot、WebSocket 路由、run 状态机都已具备多会话并行的数据基础

结论：
第一阶段主要是前端 runtime / store / sidebar 的重构，后端原则上不需要新增接口，只需要复用现有会话快照与事件流。

## 范围控制

### 本期必须完成

- 多会话实时连接管理
- `lastSeenEventSeq` 持久化与未读基线
- `runId -> sessionId` 反向索引
- 侧边栏多会话状态显示
- 当前会话操作绑定纠偏
- 切回补拉与连接降级
- 多连接测试基础设施与测试补齐

### 本期不做

- 同一会话多 run 并发
- 后端新增 `pending` 语义
- 会话列表摘要预览
- 跨会话直接审批
- 全局通知中心
- 拖拽排序 / pin / 分组

## 实现阶段

## Phase 1: 固化状态模型、持久化和全局索引

**目标**
先把“要存什么状态、如何持久化、如何按 run 反查 session”这些基础设施固化下来，避免后续 runtime 和 sidebar 在错误假设上继续生长。

**文件**

- `frontend/src/types/conversation.ts`
- `frontend/src/features/workspace/stores/workspace.store.ts`
- `frontend/src/features/conversation/stores/conversation.store.ts`
- 可能新增：
  - `frontend/src/features/workspace/types/sidebarSessionState.ts`
  - `frontend/src/utils/sessionActivity.ts`

**任务**

- 明确前端内部使用的“活跃 run 状态集合”，只包含：
  - `created`
  - `running`
  - `waiting_for_approval`
  - `resuming`
- 不把 `pending` 纳入本期运行逻辑分支
- 在 `workspace.store` 增加会话级持久化字段，至少包含：
  - `lastSeenEventSeqBySessionId`
  - 可选的 `sessionSyncHealthBySessionId`
  - 可选的 `sessionScrollStateBySessionId`
- 修改 `workspace.store.ts` 的 `partialize()` 白名单，显式把 `lastSeenEventSeqBySessionId` 纳入持久化
- 设计 sidebar 需要的派生字段结构，至少包含：
  - `hasActiveRun`
  - `activeRunStatus`
  - `hasPendingApproval`
  - `hasUnreadActivity`
  - `lastActivityAt`
  - `sidebarStatus`
- 在 `conversation.store` 或其配套 selector 层补充全局反向索引：
  - `runIdToSessionId`
  - 如有需要再补 `approvalIdToSessionId`
- 明确索引更新时机：
  - `setSnapshot`
  - `applyEvent`
  - `clearConversation`

**产出**

- 明确的前端状态结构
- `lastSeenEventSeq` 的真实持久化方案
- sidebar 展示状态映射的工具函数或类型
- 多连接路由可用的 `runId -> sessionId` 基础设施

**风险**

- 如果这里不先定好，后面 runtime 和 sidebar 会继续各自派生状态，最终又会出现两套真值
- 如果不先补 `runId -> sessionId`，后面的多连接动作路由会全部卡住

---

## Phase 2: 重构 useConversationRuntime 为多连接运行时

**目标**
把现有 `useConversationRuntime` 从“单会话单连接控制器”改为“当前会话 + 后台活跃会话”的多连接运行时管理器。

**文件**

- `frontend/src/hooks/useConversationRuntime.ts`
- 可能新增：
  - `frontend/src/hooks/runtime/sessionConnectionManager.ts`
  - `frontend/src/hooks/runtime/sessionRuntimeRegistry.ts`
  - `frontend/src/utils/sessionConnectionPriority.ts`

**任务**

- 把单个 `wsRef` / `connectedSessionIdRef` 改为按 `sessionId` 管理的连接表
- 每个会话独立维护：
  - websocket 实例
  - 连接状态
  - 重连计数
  - reconnect timer
  - live event flush 缓冲
- 把当前全局单份状态拆成按 `sessionId` 存储：
  - `connectionStatusBySessionId`
  - `isCancellingBySessionId`
  - `retryInfoBySessionId`
- 对 UI 暴露时，只返回当前会话对应的：
  - `connectionStatus`
  - `isCancelling`
  - `retryInfo`
- 保留当前会话的完整交互能力：
  - `startTurn`
  - `cancelRun`
  - `approveTool`
  - `denyTool`
  - `trustTool`
  - `editAndRerun`
  - `setMode`
- 明确动作路由链路：
  - `runId / approvalId`
  - 先反查 `sessionId`
  - 再找到对应 `sessionId` 的 websocket 连接
  - 最后在那条连接上发送消息
- 不采用“只给动作参数追加一个 `sessionId` 就解决”的实现思路；真正的路由关键是选对已绑定该 `sessionId` 的 websocket 连接
- 连接调度规则：
  - 当前会话必须连接
  - 活跃后台会话尽量连接
  - 上限 `5`
  - 超限后低优先级会话降级为补拉模式
- 连接分配优先级与侧边栏排序优先级使用同一套排序函数

**产出**

- 可按 `sessionId` 管理多连接的 runtime
- `runId / approvalId -> sessionId -> ws` 的清晰路由链路
- 独立会话级重连与降级逻辑
- 当前会话操作不串会话

**风险**

- 如果 `approveTool` / `denyTool` 只知道 `runId` 却找不到 `sessionId`，多连接模型会立刻失效
- 如果 `isCancelling` / `retryInfo` 不拆成 bySessionId，当前 UI 可以勉强工作，但 sidebar 和后台会话状态一定会不完整

---

## Phase 3: 接入未读基线和同步恢复

**目标**
把 `last_event_seq` 与 `lastSeenEventSeq` 接起来，形成稳定的未读和恢复逻辑。

**文件**

- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/features/workspace/stores/workspace.store.ts`
- 可能新增：
  - `frontend/src/hooks/useSessionUnreadState.ts`

**任务**

- 在快照写入 `conversation.store` 后，确保 `session.lastEventSeq` 始终是最新值
- 当用户切入某会话，且最新快照已完成同步时：
  - 更新 `lastSeenEventSeqBySessionId[sessionId]`
- 当用户不在某会话中，而该会话 `lastEventSeq` 增长时：
  - 自动派生 `hasUnreadActivity = true`
- 应用刷新后：
  - 从持久化的 `lastSeenEventSeqBySessionId` 恢复未读基线
  - 重新连接允许范围内的活跃会话
  - 对未连接但有缓存的会话，在重新进入时补拉快照

**产出**

- 稳定的未读活动行为
- 刷新后不会丢失 `lastSeenEventSeq`

**风险**

- “何时算成功查看会话”必须收敛成单一点更新，否则未读标记会抖动
- 如果 `partialize()` 白名单漏掉 `lastSeenEventSeqBySessionId`，这一阶段全部目标都会失效

---

## Phase 4: Sidebar 多会话状态展示

**目标**
让 `WorkspaceSidebar` 从“只知道当前会话忙不忙”升级为“知道所有会话的运行、审批、未读状态”。

**文件**

- `frontend/src/components/layout/WorkspaceSidebar.tsx`
- `frontend/src/components/layout/sidebarBusy.ts`
- `frontend/src/features/sessions/stores/session.store.ts`
- 可能新增：
  - `frontend/src/components/layout/sidebarSessionState.ts`
  - `frontend/src/components/layout/SessionStatusBadge.tsx`

**任务**

- 基于 `conversation.store + workspace.store + session.store.ts` 为每个会话派生 sidebar 状态
- 替换当前仅针对 `currentConversation` 的 `busy` 判断
- 会话项支持展示：
  - `waiting_for_approval`
  - `running`
  - `failed_with_unread_activity`
  - `completed_with_unread_activity`
  - `idle`
- 列表排序按规范执行：
  - `waiting_for_approval`
  - `running / resuming / created`
  - 最近活动时间倒序
  - 同优先级内稳定排序
- 确保“后台失败”和“后台待审批”有可见提示，不要求展示全文流式
- 如需要显示“正在取消”或“同步异常”，从 bySessionId 的 runtime 状态读取，而不是依赖当前会话单份状态

**产出**

- 真实可用的多会话 sidebar 状态
- 用户可从列表直接感知后台会话变化

**风险**

- 如果把所有派生逻辑都写进 `WorkspaceSidebar.tsx`，组件会继续膨胀，建议抽工具函数或 hook

---

## Phase 5: 当前会话操作与 UI 绑定纠偏

**目标**
消除当前单连接模型遗留的错绑风险，确保输入框、取消按钮、审批、plan 都只作用于正确会话。

**文件**

- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/hooks/useConversationData.ts`
- `frontend/src/hooks/useCurrentSessionViewModel.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/features/conversation/hooks/useImageUpload.ts`

**任务**

- 确保 `AgentWorkspace` 中所有会话相关操作都显式绑定 `currentSessionId`
- `cancelRun` 不再依赖“当前唯一连接”
- 审批与重跑统一通过 `runId -> sessionId -> ws` 路由
- 附件队列不能跨会话残留
- 切会话时不保留上一个会话的 streaming UI 残影
- 当前会话为空闲时，输入区应恢复可发送，即使别的会话在后台运行

**产出**

- 操作不串会话
- 切换和发送行为符合规范

**风险**

- 如果这里自己再造一套 `runId -> sessionId` 查找逻辑，就会和 Phase 1 的索引重复

---

## Phase 6: 失败降级与恢复兜底

**目标**
处理多连接场景下最容易被忽略的异常路径：重连失败、降级补拉、后台结束后状态收敛。

**文件**

- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/utils/sessionConnectionPriority.ts`

**任务**

- 后台会话重连失败时：
  - 不改 run 业务状态
  - 标记为同步异常
  - 降级为补拉模式
- 被降级会话重新进入时：
  - 强制补拉快照
- 后台会话在离线或降级期间终态变化：
  - 恢复后状态能正确收敛
- toast 去重：
  - 同一会话同一失败事件不重复轰炸

**产出**

- 多会话 runtime 的异常恢复闭环

**风险**

- 如果没有“同步异常”这一层轻量状态，用户会误以为 run 已失败，但其实只是 websocket 断了

---

## Phase 7: 测试基础设施与测试补齐

**目标**
为第一阶段交付建立可回归的自动化保障，并先补齐多连接测试前置 mock 能力。

**文件**

- `frontend/src/hooks/__tests__/useConversationRuntime.test.ts`
- `frontend/src/hooks/__tests__/useSessionData.test.ts`
- `frontend/src/pages/__tests__/AgentWorkspace.test.tsx`
- 可能新增：
  - `frontend/src/components/layout/__tests__/WorkspaceSidebar.multi-session.test.tsx`
  - `frontend/src/features/workspace/stores/__tests__/workspace.store.test.ts`

**任务**

- 扩展 `useConversationRuntime.test.ts` 中现有单连接 WebSocket mock
- mock 必须支持：
  - 多个 `SessionConversationWebSocket` 实例
  - 按 `sessionId` 区分 handlers
  - 针对不同会话独立触发 `conversation:event` / `conversation:live_event` / `connection:closed`
- 覆盖测试点：
  - 会话 A 运行中切换到会话 B
  - A、B 两个会话独立运行
  - `lastSeenEventSeq` 更新与未读判定
  - sidebar 状态映射与排序
  - 超过 `5` 个活跃会话时的降级行为
  - 重连失败进入补拉模式
  - 切回降级会话时强制补拉
  - 审批 / 取消 / 重跑不串会话

**产出**

- 支持多连接并行场景的测试基础设施
- 第一阶段关键行为的前端测试覆盖

**风险**

- 如果仍沿用当前单连接 handlers map，后续多连接测试会产生大量假阳性

---

## 文件变更预估

### 高风险核心文件

- `frontend/src/hooks/useConversationRuntime.ts`
- `frontend/src/components/layout/WorkspaceSidebar.tsx`
- `frontend/src/features/workspace/stores/workspace.store.ts`
- `frontend/src/features/conversation/stores/conversation.store.ts`

### 中风险配套文件

- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/hooks/useConversationData.ts`
- `frontend/src/hooks/useCurrentSessionViewModel.ts`
- `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/features/conversation/hooks/useImageUpload.ts`
- `frontend/src/features/sessions/stores/session.store.ts`

### 可能新增的辅助文件

- `frontend/src/utils/sessionActivity.ts`
- `frontend/src/utils/sessionConnectionPriority.ts`
- `frontend/src/components/layout/SessionStatusBadge.tsx`
- `frontend/src/components/layout/sidebarSessionState.ts`
- `frontend/src/features/workspace/types/sidebarSessionState.ts`

## 实施顺序建议

建议严格按下面顺序推进，避免返工：

1. 先收敛状态模型、持久化字段和全局反向索引
2. 再改多连接 runtime
3. 再接未读与恢复
4. 再改 sidebar 展示
5. 再修当前会话操作绑定
6. 最后做异常兜底和测试

原因：

- runtime 改造是主干，sidebar 和未读都依赖它
- `runId -> sessionId` 是多连接动作路由的前置基础设施
- 如果不先修改 `partialize()` 白名单，未读恢复目标根本无法成立
- 如果不先扩展测试 mock，多连接测试无法可信落地

## 第一阶段完成定义

满足以下条件即可视为第一阶段完成：

- 用户可在会话运行中切到其他会话
- 不同会话可独立发起 run
- 当前会话和后台活跃会话状态正确同步
- sidebar 可显示运行中 / 待审批 / 未读
- 切回会话后 transcript / run / 审批 / plan 状态正确恢复
- 活跃后台连接数不超过 `5`
- 超限会话能降级补拉且切回恢复正确
- `lastSeenEventSeq` 在刷新后正确恢复
- 动作路由基于 `runId / approvalId -> sessionId -> ws` 正确运行
- 对应自动化测试通过
