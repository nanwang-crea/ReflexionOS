# 项目开发日志 · 2026-06-23 起

> 追加式记录。每条记录代表一件已验证完成的事（bug 修复 / 新功能 / 重构）。
> 本文件达到约 1000KB 时封存，并新建后续文件继续记录。

---

## [2026-06-23] [新功能] 多会话并行：运行中切换、独立运行、侧边栏状态与未读基线

- **类型**: 新功能
- **涉及文件**: frontend/src/hooks/useConversationRuntime.ts, frontend/src/features/workspace/stores/workspace.store.ts, frontend/src/features/conversation/stores/conversation.store.ts, frontend/src/components/layout/WorkspaceSidebar.tsx, frontend/src/components/layout/sidebarSessionState.ts, frontend/src/components/layout/SessionStatusBadge.tsx, frontend/src/utils/sessionActivity.ts, frontend/src/hooks/useSessionUnreadState.ts, frontend/src/features/conversation/hooks/useImageUpload.ts, frontend/src/pages/AgentWorkspace.tsx
- **关联**: 分支 feature/multi-session-parallel（尚未提交）；需求见 docs/superpowers/specs/2026-06-22-multi-session-parallel-requirements.md

### 问题/需求
原前端是"单激活会话运行时"模型：workspace 只有一个 currentSessionId，useConversationRuntime 只维护当前会话的一条 WebSocket 连接。用户在会话 A 运行中切到 B 时，A 虽在后端继续执行，但前端对 A 的状态感知、列表提示、后台更新和未读判定都不完整。需要补齐成真正可用的多会话并行体验：运行中可切换、不同会话各自独立运行、切回能恢复正确状态、侧边栏能识别哪些会话在运行/等待审批/有未读。

### 原因
（新功能，无 bug 根因。）背景动机：项目数据层（后端按 session_id 隔离、conversation.store 已按 sessionId 缓存多份状态）早已具备多会话基础，缺的是前端运行时与交互层的并行支持。

### 修复/实现方法
1. 连接模型从"单连接跟随 currentSessionId"升级为"按 sessionId 管理多连接"，对活跃会话（created/running/waiting_for_approval/resuming）维持后台实时连接，终态会话允许断连只留缓存摘要；活跃后台连接数上限 5，超出按优先级降级为"切回补拉快照"。
2. 未读活动以事件序号为基线而非时间戳：新增纯函数 hasUnreadActivity(lastEventSeq, lastSeenEventSeq)（sessionActivity.ts），lastSeenEventSeq 持久化在 workspace.store，进入会话并完成快照同步后更新基线、清除未读。
3. 侧边栏派生状态集中在 sidebarSessionState.ts：deriveSidebarSessionState 按"同步异常 > 待审批 > 运行中 > 失败带未读 > 完成带未读 > 空闲"派生 SidebarSessionStatus；sortSidebarSessionStates 按规范稳定排序，避免逐 token 事件频繁重排。
4. 关键操作（发送/取消/审批/上传附件等）严格绑定当前会话，输入区附件队列与会话绑定不跨会话残留。

### 过程
1. 阅读需求规范，确认本期范围（不同 session 间并行，非同一 session 内多 run）与验收标准。
2. 检查工作区改动统计：8 个已跟踪文件改动 + 多个新增文件（sidebarSessionState.ts、sessionActivity.ts、useSessionUnreadState.ts、SessionStatusBadge.tsx 及对应测试）。
3. 通读核心实现：未读派生纯函数、侧边栏状态派生与排序逻辑、运行时多连接 hook。
4. 运行相关单元测试验证。

### 测试验证及结果
- npx vitest run（多会话相关 4 个测试文件）：
  - sessionActivity.test.ts（5）✅
  - sidebarSessionState.test.ts（11）✅
  - workspace.store.test.ts（4）✅
  - useConversationRuntime.multi-session.test.ts（5）✅
- 合计 **25 passed**，0 失败。
- **结论**: 单元层面已验证通过。注：浏览器端的端到端手动验证（运行中切换、双会话并行、刷新恢复）尚未在本次记录中执行。

### 经验教训/待办
- 经验：未读基线必须用 last_event_seq 而非时间戳/临时 UI 标志，刷新后才稳定；sidebar 状态必须由派生计算得出，不另存独立真值，避免多处不一致。
- 待办：补浏览器端到端手动验证（切换/并行/刷新/降级）；本期未做 transcript 滚动位置按会话记忆与列表摘要预览；改动尚未提交，需走 git-commit。
