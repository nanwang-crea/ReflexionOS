# 项目开发日志 · 2026-06-23 起

> 追加式记录。每条记录代表一件已验证完成的事（bug 修复 / 新功能 / 重构）。
> 本文件达到约 1000KB 时封存，并新建后续文件继续记录。

---

## [2026-08-04] [????] ?????????????????

- **??**: ????
- **??**: ???????
- **????**: backend/app/execution/rapid_loop.py, backend/app/execution/tool_call_executor.py, backend/app/security/command_policy.py, backend/app/security/permission_mode.py, backend/app/security/shell_security.py, backend/app/services/conversation_runtime_adapter.py
- **??**: ?? ReflexionOS ? Coding Agent ???????????????????????

### ??/??
??????????????????????????????????????????????????????????????????????????????????????????????????????????????????

### ??
??????????????????????????? LLM ???????????????????????????????????????????????????????????????

### ??/????
1. ? `RapidExecutionLoop` ??????phase ???????/????????????????? `approval:required` ? `run:waiting_for_approval`?
2. ? `ToolCallExecutor` ????????tool lifecycle ?????????? Working Memory ??????????
3. ? `CommandPolicy`?`PermissionMode`?`ShellSecurity` ?? effect-based ?????Windows ???????????YOLO ?????argv/shell ?????????
4. ? `ConversationRuntimeAdapter` ?? raw runtime event -> conversation event ??????????????????????????????

### ??
1. ????????????????????????????????????
2. ?????????????????????????????????????
3. ???????????????????????shell ????????????
4. ?????????????? devlog?

### ???????
- `python -m compileall backend/app/execution/rapid_loop.py backend/app/execution/tool_call_executor.py backend/app/security/command_policy.py backend/app/security/permission_mode.py backend/app/security/shell_security.py backend/app/services/conversation_runtime_adapter.py`
- `git diff -- backend/app/execution/rapid_loop.py backend/app/execution/tool_call_executor.py backend/app/security/command_policy.py backend/app/security/permission_mode.py backend/app/security/shell_security.py backend/app/services/conversation_runtime_adapter.py docs/devlog/README.md docs/devlog/devlog-2026-06-23_to_present.md`
- **??**: ?????????????????????

### ????/??
- ????????????????????????????????????????????
- ???????/???????????????? phase?policy?projection ??????????????????????

---

## [2026-06-23] [新功能] 多会话并行：运行中切换、独立运行、侧边栏状态与未读基线

- **类型**: 新功能
- **提交**: 7d587e02 (feat: 多会话并行 - 每会话独立连接、调度、动作路由与断线降级 #4) + 786c7c2b (首次实现)
- **涉及文件**: frontend/src/hooks/useConversationRuntime.ts, frontend/src/features/workspace/stores/workspace.store.ts, frontend/src/features/conversation/stores/conversation.store.ts, frontend/src/components/layout/WorkspaceSidebar.tsx, frontend/src/components/layout/sidebarSessionState.ts, frontend/src/components/layout/SessionStatusBadge.tsx, frontend/src/utils/sessionActivity.ts, frontend/src/hooks/useSessionUnreadState.ts, frontend/src/features/conversation/hooks/useImageUpload.ts, frontend/src/pages/AgentWorkspace.tsx
- **关联**: PR #4; 需求见 docs/superpowers/specs/2026-06-22-multi-session-parallel-requirements.md

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

---

## [2026-06-23] [流程规范] 新增 spec-plan-before-coding skill 与重置对话设计

- **类型**: 流程规范 + 设计文档
- **提交**: 5f11901c (docs: 新增重置对话设计文档与 spec-plan-before-coding skill)
- **涉及文件**: .claude/skills/spec-plan-before-coding/SKILL.md, docs/superpowers/specs/2026-06-23-reset-conversation-design.md
- **关联**: commit 5f11901c

### 问题/需求
项目缺少强制性的功能开发流程约束：开发者往往直接开始编码，导致设计不完整、遗漏边界情况、实现返工。需要建立"先写 spec（需求规范）→ 再写 plan（实现计划）→ 最后编码"的强制流程。同时，重置对话功能需要明确设计文档。

### 原因
（流程改进，无 bug 根因。）背景：项目已有多个 spec 文档，但没有强制要求每次功能/修复前必须先写 spec + plan，缺少工具层面的流程保障。

### 修复/实现方法
1. **新增 spec-plan-before-coding skill**（92 行）：
   - 明确三阶段流程：spec（需求规范/设计文档）→ plan（实现计划）→ code（编码实现）
   - 禁止跳过 spec/plan 直接编码
   - spec 包含：问题陈述、目标、核心决策、边界情况、不做什么、验收标准
   - plan 包含：文件清单、步骤分解、风险点、测试策略
   - 文档存放位置：docs/superpowers/specs/ 和 docs/superpowers/plans/
   - 触发：任何新功能、重要修复、架构变更

2. **新增重置对话设计文档**（129 行）：
   - 明确"重置对话"语义：清空历史保留会话（删 message/run/action/file，保 session 记录）
   - 安全约束：先停止运行中的任务再清理，否则拒绝；删除不可恢复，需确认对话框
   - 数据库级联删除顺序：action → run → message → conversation_file
   - 前端交互：菜单入口、确认对话框、运行中禁用、成功/失败提示

### 过程
1. 设计 spec-plan-before-coding skill，明确三阶段流程与每阶段产物要求
2. 编写重置对话设计文档，覆盖需求、数据模型、API、前端交互、测试用例
3. 提交到仓库作为项目流程规范

### 测试验证及结果
- **文档质量验证**: 手动审查 skill 与 spec 文档结构完整性 ✅
- **结论**: 流程规范已就位，后续功能开发需遵循此流程。重置对话功能的实现待后续按此规范执行。

### 经验教训/待办
- 经验：强制流程需要工具层面（skill）保障，仅靠人工约定容易被忽略。
- 待办：实现重置对话功能（按已写好的 spec 执行）；确保团队成员知晓新流程。

---

## [2026-06-23] [新功能] 工作记忆（Work Memory）：分层计划与上下文重构

- **类型**: 新功能（后端架构）
- **提交**: d7cf9844 (Feature/work memory #5)
- **涉及文件**: backend/app/core/work_memory/（新增模块）、context 相关重构
- **关联**: PR #5

### 问题/需求
Agent 缺少"工作记忆"能力：对话过程中产生的临时计划、中间状态、执行进度等信息无处存放，导致长对话中 Agent 频繁遗忘已做的事、重复询问用户、无法延续之前的计划。需要引入分层的工作记忆系统，支持计划管理与上下文装配。

### 原因
（新功能，无 bug 根因。）背景：项目原有 context 管理较扁平，缺少对"计划"这一核心概念的显式建模，也缺少将工作记忆注入到 LLM 上下文的机制。

### 修复/实现方法
1. **新增 work_memory 模块**：分层计划管理（计划创建/更新/查询）、工作记忆存储
2. **重构 context 架构**：统一上下文装配接口，支持将工作记忆（计划、中间结果等）注入到 Agent 的 prompt 中
3. **修复残留引用**：清理旧代码中对废弃 context 接口的引用
4. **简化计划架构**：移除过度复杂的嵌套层级，保持计划结构扁平化

### 过程
1. 添加分层计划数据模型与 API
2. 重构 context 模块，统一上下文装配流程
3. 修复代码结构与残留引用
4. 优化工作记忆设置，修复潜在 bug
5. 经过多轮迭代（7 个内部 commit）完成架构简化

### 测试验证及结果
- **单元测试**: 工作记忆模块核心逻辑通过（具体测试数未在 PR 中列出）
- **集成验证**: 后端启动正常，context 装配无报错
- **结论**: 工作记忆基础架构已就位，后续可在此基础上扩展更丰富的记忆能力。

### 经验教训/待办
- 经验：计划架构要避免过度设计，扁平化优于深层嵌套；context 重构需谨慎处理残留引用。
- 待办：补充工作记忆的前端展示（计划面板）；补充端到端测试验证工作记忆在长对话中的效果。

---

## [2026-06-23] [配置优化] 将 .claude 目录移出版本控制

- **类型**: 配置优化
- **提交**: c5ce5087 (chore: 将 .claude 目录移出版本控制)
- **涉及文件**: .gitignore

### 问题/需求
.claude 目录包含用户的本地会话记录、临时文件、个人配置等，不应纳入版本控制。每个开发者的 .claude 内容不同，提交到 git 会导致频繁的合并冲突和隐私泄露。

### 原因
.claude 目录在项目初期被错误地纳入了版本控制（.gitignore 中未排除）。

### 修复/实现方法
在 .gitignore 中添加 `.claude/`，将其移出版本控制。已提交的 .claude 文件通过 `git rm --cached` 移除。

### 过程
1. 编辑 .gitignore，添加 `.claude/`
2. 执行 `git rm -r --cached .claude/` 移除已跟踪文件
3. 提交修改

### 测试验证及结果
- **验证**: git status 确认 .claude/ 不再被跟踪 ✅
- **结论**: .claude 目录已正确排除，不会再产生版本控制冲突。

### 经验教训/待办
- 经验：项目初期应尽早确定哪些目录是"本地专用"，避免后期清理麻烦。
- 待办：无。

---

## [2026-06-24] [新功能] 子代理（Subagent）：后台任务执行与独立会话

- **类型**: 新功能（后端 + 前端）
- **提交**: f5911b8f (Feature/subagent #6)
- **涉及文件**: backend/app/core/subagent/（新增模块）、前端子代理相关组件
- **关联**: PR #6

### 问题/需求
Agent 在处理复杂任务时，需要能够"分身"执行子任务（如并行搜索多个文件、同时调研多个方案、后台验证多个假设），而不阻塞主对话流。需要引入子代理机制：主 Agent 可以启动多个子 Agent，子 Agent 在独立的会话中运行，完成后将结果返回给主 Agent。

### 原因
（新功能，无 bug 根因。）背景：当前架构是"一个会话 = 一个 Agent 实例"，无法支持一个 Agent 启动多个并发子任务的场景。

### 修复/实现方法
1. **后端子代理核心**：
   - 新增 subagent 模块，支持子 Agent 创建、执行、状态管理
   - 子 Agent 拥有独立的 session、conversation、run，与主 Agent 隔离
   - 后台执行：子 Agent 在后台异步运行，不阻塞主对话
   - 结果返回：子 Agent 完成后将结果通过回调/事件返回给主 Agent

2. **工作记忆增强**：基于 PR #5 的工作记忆架构，子 Agent 的中间状态也纳入工作记忆管理

3. **稳定性修复**：修复工作记忆的脆弱性（阶段性提交中已修复潜在 bug）

### 过程
1. 在工作记忆基础上（PR #5）继续开发子代理功能
2. 实现子 Agent 的创建、执行、状态同步
3. 修复工作记忆的潜在 bug，优化设置
4. 子代理后台执行已实现并验证可用

### 测试验证及结果
- **后端验证**: 子 Agent 可后台执行，状态正确同步 ✅
- **前端验证**: 暂无前端展示（计划后续补充）
- **结论**: 子代理后台执行机制已就位，可支持主 Agent 启动并发子任务。

### 经验教训/待办
- 经验：子代理的会话隔离很重要，避免主子 Agent 的状态互相干扰；工作记忆架构为子代理提供了良好的基础。
- 待办：补充前端子代理展示（子任务列表、进度条）；补充主子 Agent 通信的完整示例与文档。

---

## [2026-06-24] [新功能] 重置对话 - 清空历史保留会话，先停后清

- **类型**: 新功能
- **提交**: d98beec0 (feat: 重置对话 - 清空历史保留会话，先停后清)
- **涉及文件**: backend/app/services/conversation_service.py, backend/app/services/agent_service.py, backend/app/api/routes/sessions.py, frontend/src/pages/AgentWorkspace.tsx, frontend/src/hooks/useConversationRuntime.ts, frontend/src/features/sessions/session.actions.ts, frontend/src/features/workspace/stores/workspace.store.ts
- **关联**: 需求见 docs/superpowers/specs/2026-06-23-reset-conversation-design.md; 计划见 docs/superpowers/plans/2026-06-24-reset-conversation-implementation-plan.md

### 问题/需求
工作区头部的"重置对话"按钮之前只清空前端内存缓存，后端 DB 中的对话历史（turns/runs/messages/events）完全未删除。用户切走再切回该会话，旧对话会原样恢复，按钮形同虚设。需要实现真正的重置：清空该会话的 DB 对话历史，但保留会话 ID、标题与位置；重新进入不再恢复旧对话。若重置时有 run 在执行，先停后清。

### 原因
（新功能，无 bug 根因。）背景：原 `resetConversationRuntime` 只做前端三件事（关 WebSocket、清前端缓存、清取消标志），未触及后端 DB。Agent 每次执行从 DB 重建上下文，因此旧数据残留会导致"假重置"。

### 修复/实现方法
1. **后端**：
   - `conversation_service.reset_session`：在写锁内重校验无活跃 run 后级联删除 DB 对话数据（turns/runs/messages/events/search_documents）
   - `agent_service.reset_session`：写锁外先调用 `cancel_run` 停止运行中的任务
   - 新增 API：`POST /api/sessions/{id}/reset`，冲突时返回 400 ValidationError
   
2. **前端**：
   - `session.actions.resetSession`：调用 API 后回写会话列表真值（清空 activeTurnId）
   - `workspace.store.resetSessionSeen`：回退未读基线到 0
   - `resetConversationRuntime`：成功后才清前端显示状态，失败时保持原状态不变
   - `AgentWorkspace`：二次确认对话框（"此操作不可恢复"）

3. **测试**：后端 service/agent/API 共 11 个测试用例，前端 store/action/hook 全覆盖

### 过程
1. 阅读需求 spec（2026-06-23-reset-conversation-design.md），明确"清空历史保留会话、先停后清、不可恢复"语义
2. 编写实现计划（2026-06-24-reset-conversation-implementation-plan.md），分 4 阶段：后端 service → API → 前端集成 → 测试
3. 实现后端：conversation_service 写锁级联删除 + agent_service cancel_run 前置
4. 实现前端：actions 层异步调用 + runtime hook 状态清理 + workspace 回写真值
5. 补充测试：后端 11 例、前端 store/action/hook 覆盖各场景（运行中/空会话/已取消等）
6. 手动验证：创建会话 → 发消息 → 重置 → 切走切回确认空白

### 测试验证及结果
- **后端测试**（11 例全绿）：
  - conversation_service: 重置成功、运行中拒绝、会话不存在、级联删除完整性
  - agent_service: 先停后清、无运行时直接清、cancel 异常处理
  - API: 200 成功、409 运行中冲突、404 会话不存在
- **前端测试**（全绿）：
  - session.actions: API 调用、列表真值回写
  - workspace.store: 未读基线回退
  - useConversationRuntime: 成功清理、失败保持原状
- **手动验证**: 创建会话 → 多轮对话 → 重置 → 切走切回 ✅ 确认空白
- **结论**: 重置对话功能已完整实现，先停后清逻辑正确，不可恢复语义达成。

### 经验教训/待办
- 经验：危险操作必须二次确认；先停后清的顺序很重要（写锁外 cancel，写锁内 delete）；前端需同步回写列表真值和未读基线，否则 UI 不一致。
- 待办：无。功能已完整。

---

## [2026-06-26~27] [新功能] 应用内确认弹窗系统 - 替代浏览器原生 confirm

- **类型**: 新功能（前端基础设施）
- **提交**: 59027862 → 70f54682（共 9 个提交）
  - 59027862: 新增确认弹框单例 store(状态+Promise桥接)
  - 55528b99: 新增 ConfirmDialog 展示组件与宿主
  - a2a6b0df: 补完 useEffect 依赖 + 焦点陷阱
  - 6c47b9b8: confirmAction 改为异步走应用内确认框
  - 00dbbc98: 在 App 根挂载 ConfirmDialogHost
  - 802f28e5: 重置对话改用异步应用内确认框
  - 0799ca32: 重新生成消息改用异步应用内确认框，修正测试 mock
  - 32dda77f: sidebar 删除与 LLM 删除链路改用异步确认（含 action 层 async 化）
  - 70f54682: 放宽重置/重新生成回调类型为异步友好
- **涉及文件**: frontend/src/shared/stores/confirmDialog.store.ts, frontend/src/components/common/ConfirmDialog.tsx, frontend/src/services/dialogService.ts, frontend/src/App.tsx, 以及所有使用 confirmAction 的地方
- **关联**: 替代原有的 `window.confirm()`，统一交互体验

### 问题/需求
项目多处危险操作（重置对话、删除会话、删除 LLM provider、重新生成消息）都用浏览器原生 `window.confirm()` 二次确认，但原生弹窗：
1. 样式无法定制，与应用 UI 风格不一致
2. 阻塞 JS 主线程，无法与异步流程友好配合
3. 测试时需 mock `window.confirm`，脆弱且不真实

需要实现统一的**应用内确认弹窗系统**：可定制样式、异步友好、测试友好、全局单例复用。

### 原因
（新功能，无 bug 根因。）背景：随着功能增多，危险操作越来越多，原生 confirm 的局限性暴露（样式割裂、同步阻塞、测试困难）。

### 修复/实现方法
1. **单例 store**（confirmDialog.store.ts）：
   - Zustand store 管理弹窗状态（open/title/message/confirmText/cancelText）
   - Promise 桥接：`show()` 返回 Promise，用户点击确认/取消后 resolve(true/false)
   - 支持并发调用排队（队列模式）

2. **展示组件**（ConfirmDialog.tsx）：
   - 读取 store 状态，渲染弹窗 UI（遮罩层 + 卡片 + 按钮）
   - 焦点陷阱：弹窗打开时焦点锁定在确认/取消按钮，ESC 关闭
   - 补完 useEffect 依赖，避免闭包陷阱

3. **宿主挂载**（App.tsx）：
   - 在应用根挂载 `<ConfirmDialogHost />`，全局单例
   - 任何组件调用 `confirmDialogStore.show()` 都走同一个弹窗实例

4. **统一接口**（dialogService.ts）：
   - `confirmAction()` 改为异步：`const ok = await confirmAction(...); if (!ok) return;`
   - 逐步迁移所有 `window.confirm` 调用点（重置对话、删除会话、删除 provider、重新生成消息）

5. **回调类型放宽**（70f54682）：
   - 原 `onReset/onRegenerate` 等回调是同步的，改为 `() => void | Promise<void>`
   - 支持异步确认流程，不阻塞调用方

### 过程
1. 设计单例 store + Promise 桥接模式
2. 实现 ConfirmDialog 展示组件，补完焦点陷阱与依赖
3. 在 App 根挂载宿主
4. 逐个迁移危险操作调用点：重置对话 → 重新生成 → sidebar 删除 → LLM 删除
5. 修正测试 mock（不再 mock window.confirm，改为 mock confirmDialogStore）
6. 放宽回调类型，确保异步流程友好

### 测试验证及结果
- **单元测试**：
  - confirmDialog.store.test.ts（56 行）：Promise 桥接、队列、取消逻辑 ✅
  - dialogService.test.ts：异步 confirmAction 流程 ✅
  - 各调用点测试（useCurrentSessionViewModel, useSidebarSessionActions 等）：mock 改为异步 ✅
- **手动验证**：
  - 触发重置对话 → 弹出应用内确认框（非原生）→ 确认/取消逻辑正确 ✅
  - 删除会话、删除 provider、重新生成消息 → 同样走应用内确认 ✅
  - ESC 关闭、焦点陷阱 ✅
- **结论**: 应用内确认弹窗系统已全面替代原生 confirm，统一交互体验，测试友好。

### 经验教训/待办
- 经验：Promise 桥接模式是同步 UI 与异步业务的好方案；焦点陷阱需显式补完 useEffect 依赖；渐进式迁移比一次性重写更安全。
- 待办：考虑扩展支持自定义按钮（如"删除并不再提示"）；考虑支持多弹窗并发显示（目前是队列单例）。

---

## [2026-07-12] [Bug修复] 修复 Windows 完整测试套件中的预存失败

- **类型**: Bug修复
- **涉及文件**: backend/app/tools/grep_tool.py, backend/app/tools/edit_tool.py, backend/app/execution/prompt_manager.py, backend/tests/test_security/test_sandbox.py
- **关联**: （无，尚未提交）

### 问题/需求
在验证 Windows Phase 2 沙箱改动时，相关沙箱/权限测试已通过，但完整 backend 测试套件暴露 8 个预存失败。用户要求继续排查并修复其中可确认的 Windows 预存问题，同时记录问题定位与修复过程。

### 原因
1. `grep_tool` 在 Windows 上使用 `asyncio.create_subprocess_exec` 调用 `rg/grep`。当测试或运行环境使用 Windows SelectorEventLoop 时，asyncio 子进程 API 不可用，会抛 `NotImplementedError`；同时 Git Bash `grep` 输出的 Windows 盘符路径包含冒号，原解析逻辑按 `:` 简单拆分会把 `C:` 误判成字段分隔符；`--include` 也需要使用 `--include=*.py` 形式。
2. `edit_tool` 已显式把内容转换为 CRLF 后，仍用 Windows 文本模式写文件，导致 Python 再次把 `\n` 转为 `\r\n`，最终出现 `\r\r\n`。
3. `PromptManager` 使用 `Path.home()` 查找全局 `.reflexion` overlay。Windows 下 `Path.home()` 优先 `USERPROFILE`，测试中 monkeypatch 的 `HOME` 不生效，导致读取到真实用户目录而非测试隔离目录。
4. OpenAI 兼容适配器 User-Agent 断言与当前源码不一致（测试期待 `claude-cli/`，源码为 `codex-cli/2.1.177`）。该项按用户选择本次不修改。

### 修复/实现方法
1. `grep_tool` 新增 `_run_search_command`：Windows 下通过 `asyncio.to_thread(subprocess.run)` 执行同步子进程，绕过 SelectorEventLoop 子进程限制；非 Windows 保持原 asyncio 子进程路径。
2. `grep_tool` 新增统一输出行解析，兼容 `C:\...:line:content` 这类 Windows 盘符路径，并调整 GNU grep include 参数为 `--include=PATTERN`。
3. `edit_tool` 写入已显式转换换行符的内容时加 `newline=""`，避免 Windows 文本模式二次转换。
4. `PromptManager` 增加 `_global_reflexion_dir()`，优先读取 `HOME`，未设置时再退回 `Path.home()`，保证测试隔离与跨平台一致性。
5. `test_sandbox.py` 对 macOS seatbelt 专属 `/bin/zsh` 断言加 `skipif(sys.platform != "darwin")`，避免 Windows 上的无关平台误报。

### 过程
1. 先跑完整 backend 测试套件，确认 8 个失败：4 个 grep、1 个 edit CRLF、1 个 prompt overlay、2 个 OpenAI header。
2. stash/对照后确认失败并非 Windows 沙箱改动引入，而是预存问题。
3. 复现 grep 根因：Windows SelectorEventLoop 下 `asyncio.create_subprocess_exec` 抛 `NotImplementedError`；进一步打印 Git Bash grep 原始输出，定位 Windows 盘符冒号解析和 `--include` 参数形式问题。
4. 分别修复 grep、edit、prompt_manager 三类问题；OpenAI UA 按用户选择保留现状。
5. 维护开发日志，记录根因、修法与验证结果。

### 测试验证及结果
- `python -m pytest tests/test_tools/test_grep_tool.py tests/test_tools/test_edit_tool.py::TestEditToolStrReplace::test_crlf_preserved tests/test_execution/test_prompt_manager.py::TestPromptManager::test_get_system_prompt_merges_global_and_project_overlays -q` ✅：`9 passed`
- `python -m pytest tests/test_tools/test_grep_tool.py tests/test_tools/test_edit_tool.py tests/test_execution/test_prompt_manager.py tests/test_security/test_sandbox_windows.py tests/test_security/test_sandbox_windows_acl.py tests/test_security/test_sandbox_windows_firewall.py tests/test_security/test_sandbox_windows_token.py tests/test_security/test_sandbox_windows_user.py tests/test_security/test_sandbox_windows_integration.py tests/test_security/test_sandbox_base.py tests/test_security/test_permission_mode.py tests/test_security/test_command_policy_sandbox_conditional.py tests/test_security/test_command_policy_windows_builtin.py tests/test_security/test_sandbox.py -q` ✅：`197 passed, 1 skipped`
- **结论**: grep/edit/prompt_manager 三类 Windows 预存失败已解决；OpenAI UA 失败按用户要求本次不改，完整套件仍会保留该已知失败。

### 经验教训/待办
- 经验：Windows 上不能假设 asyncio 子进程可用，涉及外部命令的工具需要像 shell_tool 一样考虑 SelectorEventLoop；解析命令行工具输出时不能按冒号简单拆 Windows 路径；已显式转换换行符时必须禁用文本模式自动 newline 转换。
- 待办：后续单独确认 OpenAI 兼容适配器 User-Agent 期望值：若 `codex-cli/2.1.177` 是故意策略，则应改测试；若是误改，则应改源码回 `claude-cli/`。


---

## [2026-07-15] [提示词优化] 系统提示词强制每次回复称呼用户为“大哥”

- **类型**: 提示词优化
- **涉及文件**: backend/app/execution/prompts/system.txt, backend/app/execution/prompts/glm/system.txt, backend/tests/test_execution/test_prompt_manager.py
- **关联**: （无，尚未提交）

### 问题/需求
用户要求在提示词中追加一条规则：每次回复必须称呼用户为“大哥”。该规则需要同时覆盖默认英文提示词族和 GLM 中文提示词族，避免不同模型族行为不一致。

### 原因
（提示词优化，无 bug 根因。）现有 system prompt 只有通用沟通风格约束，没有明确的用户称呼要求。

### 修复/实现方法
1. 在默认提示词 backend/app/execution/prompts/system.txt 的环境信息之后新增 Communication 小节，加入 “In every reply, address the user as "大哥".”。
2. 在 GLM 提示词 backend/app/execution/prompts/glm/system.txt 的环境信息之后新增“沟通要求”小节，加入“每次回复都必须称呼用户为“大哥”。”。
3. 在 backend/tests/test_execution/test_prompt_manager.py 增加默认提示词和 GLM 提示词断言，防止后续提示词改动误删该规则。

### 过程
1. 定位 PromptManager 的模型族模板加载逻辑，确认默认与 GLM system prompt 分别来自 prompts/system.txt 和 prompts/glm/system.txt。
2. 以最小范围编辑两个 system prompt，不改动 final response、plan mode 或执行链路逻辑。
3. 更新 prompt manager 测试，分别覆盖默认模型族和 GLM 模型族。
4. 顺带审阅 subagent 主链路，确认本次称呼规则属于全局 system prompt 层，不需要在 SubAgentRunner 或 DelegateTool 中做额外分支。

### 测试验证及结果
- python -m pytest tests/test_execution/test_prompt_manager.py -q ✅：33 passed
- pnpm test -- conversation.reducer.test.ts ✅：25 passed
- **结论**: 两个模型族的 system prompt 都会注入“大哥”称呼规则；现有 subagent 前端事件 reducer 测试仍通过。

### 经验教训/待办
- 经验：模型族提示词要成对更新，并用测试锁住关键行为规则。
- 待办：如果未来新增更多 prompt family，需要同步补齐同类沟通规则断言。


---

## [2026-07-13] [新功能] Windows Phase 2 沙箱与会话级权限模式

- **类型**: 新功能
- **涉及文件**: backend/app/security/sandbox/windows.py, windows_acl.py, windows_token.py, windows_firewall.py, windows_user.py, backend/app/security/permission_mode.py, backend/app/security/command_policy.py, backend/app/security/command_effect_registry.py, backend/app/execution/prompt_manager.py, backend/app/models/session.py, backend/app/services/__init__.py, backend/app/services/agent_service.py, backend/app/api/routes/websocket.py, 及配套 alembic 迁移
- **关联**: 提交 `77465b1f`

### 问题/需求
Windows 上此前 shell 命令执行只有第一阶段严格白名单（几个纯读 git 子命令），无法执行真实开发任务所需的命令。需要一套能安全放行任意命令、同时控制风险的执行机制，并允许用户按会话选择信任级别。

### 原因
- 严格白名单模式下大多数命令直接被拒绝，可用性太差，无法支撑日常开发场景。
- 需要一种不依赖 Unix 权限模型（chroot/seatbelt 等）、在 Windows 上也能生效的隔离手段。

### 修复/实现方法
1. 新增 `WindowsSandbox`：通过 `CreateProcessAsUser` + Restricted Token + 目录 ACL 执行命令，把子进程的文件系统写权限限制在允许路径内。
2. 新增 `permission_mode`（ASK/AUTO/YOLO 三档会话级权限模式），控制审批弹窗触发的严格程度。
3. `command_policy` 在检测到沙箱可用时旁路 Windows 第一阶段严格白名单，改走沙盒执行流；不可用时保留原白名单兜底。
4. 补齐 Windows 内建命令的效果分类（dir/copy/del/runas 等），并对 `runas` 提权命令单独拦截。
5. `shell_tool` 的 Windows 分支优先调用 `sandbox.run_command`/`run_shell_command`。
6. 配套修复一批 Windows 兼容性问题：`grep_tool`（SelectorEventLoop 下子进程不可用、盘符路径解析、`--include` 参数）、`edit_tool`（CRLF 二次转换）、`prompt_manager`（HOME 隔离在 Windows 下失效）、`database`（sessions 表缺 permission_mode/agent_mode 列的兼容迁移兜底）、`windows_acl`（遇到不存在的允许目录跳过而非整体失败）、`services/__init__`（懒加载避免循环导入）。

### 测试验证及结果
- 新增/覆盖测试：test_sandbox_windows.py、test_sandbox_windows_acl.py、test_sandbox_windows_token.py、test_sandbox_windows_firewall.py、test_sandbox_windows_user.py、test_sandbox_windows_integration.py、test_permission_mode.py、test_command_policy_sandbox_conditional.py、test_command_policy_windows_builtin.py 等，commit 内共新增/修改 12 个测试文件、991 行测试代码。
- **结论**: 沙箱与权限模式在提交时测试全部通过（详见 `77465b1f` 提交说明）。

### 经验教训/待办
- 经验：Windows 下要做命令级隔离，Restricted Token + ACL 是比"信任白名单"更可持续的方案，但需要配套修一批因 SelectorEventLoop/路径格式/换行符导致的周边兼容性问题。

---

## [2026-07-14] [Bug修复] Windows argv 模式对 cmd 内部命令降级走 cmd.exe /c

- **类型**: Bug修复
- **涉及文件**: backend/app/security/sandbox/windows_cmd.py（新增）, backend/app/tools/shell_tool.py, backend/tests/test_tools/test_shell_tool_cmd_fallback.py（新增）
- **关联**: 提交 `c5d96e14`

### 问题/需求
Windows Phase 2 沙箱上线后，argv 模式执行 `mkdir`/`copy`/`dir`/`echo`/`if` 等 cmd 内部命令必然失败。

### 原因
cmd 内部命令没有独立的 `.exe` 文件，`CreateProcess` 按 argv[0] 找可执行文件时必然找不到，直接报错。

### 修复/实现方法
1. 新增 `windows_cmd.py`：`CMD_INTERNAL_COMMANDS` 清单列出 cmd 内建命令，明确排除 `find`/`findstr`/`robocopy`/`where` 等本身有独立 `.exe` 的命令；配套 `is_cmd_internal_command` 判定函数。
2. `shell_tool._execute_decision` 在 Windows 下识别到 argv[0] 是 cmd 内部命令时，降级走 `_execute_shell(decision.command, ...)`，复用原始命令字符串（`list2cmdline` 重新拼接会破坏带引号路径，实测不可用，因此不能走 argv 模式重新拼接）。

### 测试验证及结果
- 新增 `test_shell_tool_cmd_fallback.py`：清单覆盖（命中 cmd 内部命令、排除有独立 exe 的命令、大小写不敏感、空值安全）+ shell_tool 分发验证（mkdir 走 shell 降级、git 走 argv 不降级、Linux 平台不触发降级）。
- **结论**: 提交时测试通过（详见 `c5d96e14` 提交说明）。

### 经验教训/待办
- 经验：Windows 下 argv 模式执行命令前，必须先判断目标命令是否是某个解释器（cmd/PowerShell）的内建命令而非独立可执行文件，否则会被 `CreateProcess` 直接拒绝。

---

## [2026-07-21] [Bug修复] 修复 PowerShell/cmd 引号残留与子agent首轮工具门禁问题

- **类型**: Bug修复
- **涉及文件**: backend/app/security/shell_security.py, backend/app/security/command_effect_registry.py, backend/app/security/command_policy.py, backend/app/execution/rapid_loop.py, backend/app/execution/approval_flow.py, backend/app/agents/sub_agent_runner.py, backend/app/config/settings.py, backend/app/execution/runtime_tool_definitions.py, backend/app/execution/prompts/system.txt, backend/app/execution/prompts/glm/system.txt, frontend/src/components/workspace/ToolGroupItem.tsx
- **关联**: 提交 `db3f8968`

### 问题/需求
端到端验证子 agent 委托执行 PowerShell 命令时发现两个问题：命令被字面回显而不是真正执行；子 agent 委托任务首轮报"没有 shell 工具"。

### 原因
1. Windows 下 `shlex.split(posix=False)` 不会剥离引号，导致 `powershell -Command "..."` 里的引号原样传给子进程，命令被当作字面字符串回显，而非真正执行。
2. `command_effect_registry` 中 `powershell`/`pwsh`/`cmd` 被注册为裸的 `ESCALATE` 类别，没有 `flag_overrides`，因此这些命令即使带 `-Command`/`/c` 也永远走不到降级判断分支，一律被拒绝（对比 `bash -c` 等 Unix 解释器已有 `flag_overrides={"-c": CODE_GEN}`）。
3. 子 agent 委托任务首轮按设计只暴露探索类工具（探索门禁），导致明确要求执行 shell 命令的委托任务首轮直接报"没有该工具"。

### 修复/实现方法
1. `shell_security.py` 修复引号剥离逻辑，确保 Windows 下解析出的参数不带残留引号。
2. `command_effect_registry.py` 给 `powershell`/`pwsh`/`cmd` 补充 `flag_overrides`（`-Command`/`-c`/`-EncodedCommand`、`/c`/`/k` 等 → `CODE_GEN`），使其与 `bash -c` 同等语义，交由 `command_policy._shell_interpreter_override` 判断降级。
3. `command_policy.py` 把 `powershell`/`pwsh`/`cmd` 纳入解释器判断路径，扩展 `INLINE_EVAL_FLAGS` 覆盖对应的 PowerShell/cmd 标志。
4. 新增 `skip_exploration_gate` 配置项，让子 agent 委托任务首轮跳过探索门禁，直接给全量工具集。
5. 配套支持并行 delegate：`ApprovalFlow` 按 `approval_id` 拆分为多槍位，避免并发审批互相覆盖 set_approval_result 的结果；`agent_service.py` 中并发子 agent 会话 id 附加唯一短后缀避免碰撞；前端 `ToolGroupItem` 按 delegate 逐项切分渲染，使同组内多个并行委托各自正确展示。

### 测试验证及结果
- 新增/覆盖测试：test_approval_flow.py（新增）、test_shell_security_quoting.py（新增）、test_rapid_loop.py、test_runtime_tool_definitions.py、test_command_policy.py、test_agent_service.py、test_prompt_manager.py。
- 已通过真实环境端到端验证：委托子 agent 执行 `powershell -NoProfile -Command "Write-Output 'hint test ok'"`，日志核实 `argv 模式执行完成: success=True, output_len=12`，命令首轮即可见 shell 工具（`tool_calls: ['delegate']` → 子 agent 内 `tool_calls: ['shell']`），审批流程正常走完。
- **结论**: 两个问题均已修复并在真实环境验证通过。

### 经验教训/待办
- 经验：新增一类 shell 解释器时，`command_effect_registry`（效果分类+flag_overrides）和 `command_policy`（解释器判断路径+INLINE_EVAL_FLAGS）必须成对更新，只改一处会导致虽然分类对了但仍然走不到降级判断，或反之。

---

## [2026-07-22] [Bug修复] 修复打包安装后启动崩溃（全局Python环境污染导致误打包重型依赖）

- **类型**: Bug修复
- **涉及文件**: backend/requirements.txt, frontend/scripts/package-backend.mjs
- **关联**: 提交 `9166da5c`

### 问题/需求
打包生成安装包并安装后，启动应用弹窗报错"Backend Startup Failed - 后端进程已退出 (code=1, signal=null)"，无法正常使用。

### 原因
1. `frontend/scripts/package-backend.mjs` 调用打包时使用的是本机全局 `pyinstaller`（全局 Python 环境），而该环境被其他项目污染，装有 torch、nltk、transformers、llama-index、modelscope 等与本项目无关的重型库。
2. `llama-index`/`modelscope`/`transformers` 都声明了对 nltk 的依赖，nltk 又依赖 scipy/numpy，PyInstaller 的依赖分析把这条无关依赖链一并收集进了 exe。
3. numpy 在同一进程内被 import 两次时会触发已知 bug（numpy/numpy#28271）：`RuntimeError: CPU dispatcher tracer already initlized`，这是 exe 启动即崩溃、进程 code=1 退出的直接原因。
4. 排查过程中还发现 `backend/requirements.txt` 长期缺失 `python-multipart`——FastAPI 的 `UploadFile`/`File()` 路由声明时才检测该依赖是否安装，import 阶段不报错，此前全局环境"意外"装了它所以从未暴露；换成干净环境后暴露为新错误 `RuntimeError: Form data requires "python-multipart" to be installed.`。

### 修复/实现方法
1. 为 backend 建立专属虚拟环境 `backend/.venv`，只安装 `requirements.txt` 声明的依赖，从根本上避免全局环境污染导致的误打包。
2. 修改 `package-backend.mjs`：优先使用 `backend/.venv` 中的 `pyinstaller`（Windows: `.venv/Scripts/pyinstaller.exe`，macOS/Linux: `.venv/bin/pyinstaller`），venv 不存在时 fallback 到全局 `pyinstaller` 保持向后兼容。
3. 在 `requirements.txt` 补齐缺失的 `python-multipart==0.0.20`。
4. 曾怀疑是 PyInstaller spec 里的 UPX 压缩导致 numpy dispatcher 重复初始化（改 `upx=False` 验证），复现同样报错后确认该假设错误，已还原 spec 文件，不保留无关改动。

### 过程
1. 用 systematic-debugging 流程排查：先假设 UPX 压缩是根因，修改 spec 验证后依然报同样错误，假设被推翻，回到 Phase 1 重新分析。
2. 检查全局 Python 环境（`where python`、`VIRTUAL_ENV` 为空），确认打包用的是全局解释器；用 `importlib.metadata` 查询确认 llama-index/modelscope/transformers 都在全局 site-packages 里且依赖 nltk。
3. 定位真正根因为环境污染，创建 `backend/.venv` 并只装 `requirements.txt` 声明的依赖，确认其中无 nltk/torch/numpy/scipy/transformers 等污染性依赖。
4. 用干净 venv 重新打包，运行 exe 又暴露出新错误（缺 `python-multipart`），补齐依赖后再次打包验证。

### 测试验证及结果
- 手动运行 `reflexion-backend.exe`，等待约 15 秒（首次启动含 skill 目录扫描），`curl http://127.0.0.1:8000/health` 返回 `{"status":"healthy"}`，HTTP 200。✅
- 跑完整 `pnpm dist:win` 重新生成安装包，COLLECT 阶段耗时从原先十几分钟压缩到约 5.6 秒，印证包体积大幅减小（去除了 torch 等无关大型依赖）。✅
- **结论**: 已解决，新安装包验证通过（`frontend/release/ReflexionOS Setup 1.1.0.exe`）。

### 经验教训/待办
- 经验：PyInstaller 打包必须用项目专属虚拟环境，不能依赖全局 Python 环境——全局环境里其他项目装的无关依赖会被静默收集进 exe，且这类问题在开发机上不会暴露（因为直接跑 `python main.py` 不受影响），只有在打包后的冻结环境里才会触发。
- 经验：隐式依赖（如 FastAPI 的 `python-multipart`）在 import 阶段不报错，只有实际触发对应代码路径时才报错，容易被全局环境"意外满足"掩盖，必须用干净环境走一遍完整功能才能发现。
- 待办：`backend/.venv` 目前只在 Windows 机器上建过，macOS/Linux 打包前需要各自在对应系统上创建 venv 并安装依赖，该过程未自动化。

## [2026-07-24] [Bug修复] Windows 下代码 tab 文件树和 diff 加载失败（SelectorEventLoop 不支持子进程）

- **类型**: Bug修复
- **涉及文件**: `backend/app/services/file_content_service.py`
- **关联**: （无）

### 问题/需求
点击"代码"tab 后，右侧文件栏一直显示"加载中..."，文件树无法加载，文件内容也不能显示。
同样操作在 macOS 上完全正常，仅 Windows 复现。

### 原因
`file_content_service.py` 的 `_get_git_status_map`（获取文件树 git 状态）和 `get_diff_content`（获取 diff 内容）两处函数内部直接调用 `asyncio.create_subprocess_exec` 跑 git 命令。

`start-dev.sh` / `start.sh` 均以 `uvicorn --reload` 启动后端；uvicorn 在 Windows + `--reload` 组合下会强制切换为 `WindowsSelectorEventLoopPolicy`（见 `uvicorn/loops/asyncio.py`），该事件循环**不支持子进程**——任何 `asyncio.create_subprocess_exec` 调用都会立即抛出 `NotImplementedError`。

`_get_git_status_map` 的异常捕获只覆盖了 `(FileNotFoundError, TimeoutError)`，`NotImplementedError` 未被拦截，导致异常冒泡到路由层，文件树接口返回 500，前端加载失败。

macOS 使用 kqueue-based 默认事件循环，天然支持子进程，故不受影响。

### 修复/实现方法
新增 `_run_git` 辅助异步方法，内部对平台做分支：
- **Windows**：用 `loop.run_in_executor(None, self._run_git_sync, ...)` 在线程池中执行同步的 `subprocess.run`，完全绕开事件循环的子进程支持限制。
- **其他平台**：保持原有 `asyncio.create_subprocess_exec` + `asyncio.wait_for` 逻辑不变。

将 `_get_git_status_map` 和 `get_diff_content` 中原有的直接子进程调用替换为统一的 `await self._run_git(...)`；同时补全异常捕获，增加 `subprocess.TimeoutExpired`。

此模式与 `shell_tool.py` 中已验证的 Windows 兼容方案完全一致（`shell_tool.py` 此前已因同样问题修复过）。

### 过程
1. 读取 `WorkspaceHeader.tsx`、`AgentWorkspace.tsx`、`CodeTab.tsx` 确认前端"代码"tab 的渲染链路，定位到 `FileSidebar` 一直处于 loading 状态。
2. 读取 `FileSidebar.tsx`，发现 `fileApi.getTree` 请求触发文件树加载，且 loading 状态依赖请求结果。
3. 读取 `file_content_service.py`，发现 `_get_git_status_map` 直接用 `asyncio.create_subprocess_exec`，且 except 只捕获 `FileNotFoundError`/`TimeoutError`。
4. 读取现有测试 `test_shell_tool_windows_eventloop.py`，发现同样的坑在 `shell_tool.py` 已有文档和修复，确认根因。
5. 在 `WindowsSelectorEventLoopPolicy` 下实测复现：`create_subprocess_exec` 立即抛 `NotImplementedError`。
6. 提取 `shell_tool.py` 的 `run_in_executor` 模式，在 `file_content_service.py` 新增 `_run_git` / `_run_git_sync`，替换两处调用。
7. 再次实测验证：selector loop 下 `_get_git_status_map` 正常返回 git 状态，`_build_tree` 正常构建文件树，`git show` 正常返回内容。

### 测试验证及结果
- 在 `WindowsSelectorEventLoopPolicy` 下直接调用 `_get_git_status_map`：不再抛 `NotImplementedError`，返回 12 条 git 状态条目 ✅
- `_run_git` 执行 `git show HEAD:CLAUDE.md`：正常返回，无异常 ✅
- 运行 `tests/test_tools/test_shell_tool_windows_eventloop.py` + `tests/test_file_content_api.py`：12 项全部通过 ✅
- **结论**: Windows 下文件树和 diff 接口已恢复正常，macOS 行为不受影响

### 经验教训/待办
- 经验：`uvicorn --reload` 在 Windows 下会切 `WindowsSelectorEventLoopPolicy`，任何在请求处理链路里调用 `asyncio.create_subprocess_exec` 的代码都会炸——必须全局改用 `run_in_executor` + 同步 `subprocess.run`。这是 Windows 平台必须统一处理的坑，不能仅修一处。
- 经验：同类问题在 `shell_tool.py` 已踩过并留下测试文件，但 `file_content_service.py` 新增 git 子进程调用时没有参照，说明跨文件的模式一致性需要 review checklist 显式覆盖。
- 待办：项目里其他地方是否还有直接用 `asyncio.create_subprocess_exec` 的调用值得做一次全局 grep 排查，避免留下同类隐患。
