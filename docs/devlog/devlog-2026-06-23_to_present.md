# 项目开发日志 · 2026-06-23 起

> 追加式记录。每条记录代表一件已验证完成的事（bug 修复 / 新功能 / 重构）。
> 本文件达到约 1000KB 时封存，并新建后续文件继续记录。

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
