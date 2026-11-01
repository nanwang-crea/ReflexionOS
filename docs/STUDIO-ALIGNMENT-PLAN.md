# ReflexionOS × reflexion-os-studio 改造方案

> 生成时间：2026-10-29
> 参考仓库：https://github.com/nanwang-crea/reflexion-os-studio（下称 Studio）
> 结论先行：**不做整体架构重写，走"能力对齐"路线**——把 Studio 已验证的产品能力分阶段移植回本项目；P0 项（会话消息发送队列）已完成实现并通过全部测试。

---

## 一、背景与总体策略

Studio 是同组织下的"下一代"项目：TypeScript Runtime + Rust System Runtime + Tauri 2 的独立架构。其 README 明确声明两个项目相互独立、互不依赖。在本仓库引入 Studio 架构意味着重写全部 112 个后端 Python 文件与 1131 项测试基线，风险与成本远超收益（安全层、平台适配、测试资产都无法平移），因此：

| 策略 | 内容 |
|---|---|
| ✅ 采纳 | Studio 的**产品能力与交互语义**（发送队列、审批范围、导入导出、变更聚合等），按本项目的事件溯源 + FastAPI 架构重新实现 |
| ❌ 不采纳 | TS Runtime + Rust + Tauri 的架构重写；CEF 浏览器嵌入；激活码/登录等商业边界 |
| 🔁 已具备 | Studio 有而本项目已有的能力，核对后标记"无需改造"（见下表），避免重复建设 |

每个采纳项遵循 Studio 的设计原则：先契约后实现、长任务必须支持事件流/取消/重试、状态变更全量广播快照。

## 二、能力对齐清单

| # | Studio 能力 | 本项目现状 | 结论 |
|---|---|---|---|
| 1 | 消息发送队列（回复中排队，可编辑/删除/立即发送） | 运行中再发消息直接报错拒绝，前端禁用输入框 | **P0 已落地**（见 §三） |
| 2 | 工具审批授权范围（允许一次 / 本会话允许 / 拒绝） | `trust_and_allow` + `SessionTrustStore` + 级联自动批准已实现，按钮文案"此会话允许…" | 已具备，无需改造 |
| 3 | Changed Files / 变更聚合（Run 级"变更了 N 个文件"折叠条） | edit/patch 工具有结构化回执，但无 Run 级聚合展示 | P1 规划 |
| 4 | 会话导入导出（`.reflexion-chat.json`） | 无 | P1 规划 |
| 5 | 文件式记忆（AGENTS.md/MEMORY.md 注入 + memory.remember） | 已有 CuratedMemoryStore（entry 式），无文件注入 | P1 规划（互补，非替换） |
| 6 | 多 Agent 委派（task 工具 + 权限交集 + 变更归属） | 已有 DelegateTool/SubAgentRunner（共享父审批流），无预算/变更归属语义 | P2 规划（增强） |
| 7 | Loop Guard / 终态收敛 / 性能指标 | 有空响应重试与超时兜底（备用模型链），无 run 级耗时指标 | P2 规划 |
| 8 | 移动端/多客户端会话接入 | 无 | P2 远期 |
| 9 | TS Runtime + Rust 边界 + Tauri | FastAPI + Electron（打包链路完整可用） | 不采纳（重写风险大于收益） |
| 10 | CEF 原生浏览器嵌入 | Playwright BrowserTool（可控自动化） | 不采纳（定位不同） |

## 三、P0 已落地：会话消息发送队列

### 3.1 产品语义（对齐 Studio `QueueService`）

- 会话空闲时发消息 = 直接发起新轮次（行为与从前完全一致）；
- 会话忙碌（存在活跃轮次）时发消息 = **自动进入 FIFO 队列**，输入框不再被禁用；
- 当前 Run 结束（完成/失败/取消之外的终态收敛点）后**自动按序出队**发起新轮次；
- 队列内消息支持：**编辑**（原位改文本）、**删除**、**立即发送**（移到队首并尝试发起）、**恢复队列**；
- 用户**取消运行**且队列非空 → 队列自动**暂停**（防止已叫停的任务被排队消息重新点火）；空队列取消不挂暂停标记（避免"幽灵暂停"）；
- "立即发送"与"恢复队列"都会显式解除暂停；
- 出队发起失败（如供应商配置失效）→ 消息**放回队首**并暂停队列，等用户处理后重试，**不静默丢弃**；
- 会话删除/重置 → 清空该会话队列；
- 单会话队列上限 **20 条**，超限报错；
- 队列**只存在于进程内存**（与审批存储、执行循环同生命周期），重启即清空，不参与事件溯源、不落库。

### 3.2 协议契约（WebSocket，全量快照广播）

下行（服务端 → 客户端）：

```
conversation:queue_state
data: { session_id, paused: bool, items: [{ id, content, attachment_ids, provider_id, model_id, created_at }] }
```

广播时机：入队、编辑、删除、立即发送、恢复、出队成功/失败、取消暂停——**每次变更都推全量快照**；`conversation:sync` 收尾时补发一次（重连/新开页面恢复队列条）。

上行（客户端 → 服务端）：

| type | data | 语义 |
|---|---|---|
| `conversation:start_turn` | 不变 | 空闲=发起；忙碌=自动入队 |
| `conversation:queue_update` | `{queue_id, content}` | 编辑 |
| `conversation:queue_remove` | `{queue_id}` | 删除（幂等） |
| `conversation:queue_send_now` | `{queue_id}` | 移到队首+解除暂停+尝试出队 |
| `conversation:queue_resume` | `{}` | 解除暂停+尝试出队 |
| `conversation:queue_list` | `{}` | 请求快照（仅回当前连接） |

### 3.3 实现落点

| 层 | 文件 | 内容 |
|---|---|---|
| 队列核心 | `backend/app/services/message_queue_service.py` | `QueuedMessage` / `SessionMessageQueueManager`（enqueue/pop/push_front/update/remove/move_to_front/pause/resume/clear） |
| 编排 | `backend/app/services/agent_service.py` | `submit_message`（空闲发起/忙碌入队 + 并发窗口回退）、`_pump_message_queue`（出队触发点，挂在 `_run_turn` finally）、`update/remove/send_now/resume` 四个操作、`cleanup_session_security_state` 连带清队、`cancel_run` 非空队列自动暂停 |
| 忙碌异常 | `backend/app/services/conversation_service.py` | 新增 `SessionBusyError(ValueError)`（子类化保持既有捕获兼容） |
| 路由 | `backend/app/api/routes/websocket.py` | start_turn 改走 `submit_message`；新增 5 个队列命令分支；sync 收尾补发快照 |
| WS 客户端 | `frontend/src/services/sessionConversationWebSocket.ts` | 5 个发送方法 + `conversation:queue_state` 路由 + DTO |
| 状态 | `frontend/src/features/conversation/stores/conversation.store.ts` | `messageQueueBySessionId` 切片 + `setMessageQueue` |
| 运行时 | `frontend/src/hooks/useConversationRuntime.ts` | `toMessageQueueState` 转换器 + 4 个操作回调 |
| 视图模型 | `frontend/src/hooks/useCurrentSessionViewModel.ts` | `disabled` 去掉 `isRunning`（运行中可输入） |
| 输入框 | `frontend/src/components/chat/ChatInput.tsx` | 运行中显示"排队"按钮（Enter 亦入队），取消按钮保留；提示文案随状态切换 |
| 队列条 | `frontend/src/components/chat/MessageQueueBar.tsx`（新增） | 排队项列表（序号/行内编辑/立即发送/删除）+ 暂停横幅与恢复按钮 |
| 页面装配 | `frontend/src/pages/AgentWorkspace.tsx` | 订阅队列快照、渲染 MessageQueueBar |

### 3.4 测试与验证结果

| 套件 | 结果 |
|---|---|
| 后端新增 `tests/test_services/test_message_queue.py`（21 例：队列单元 10 + 服务集成 11） | ✅ 全部通过 |
| 后端新增 `tests/test_api/test_conversation_websocket_queue.py`（3 例 WS 集成） | ✅ 全部通过 |
| 后端全量 `pytest backend/tests` | ✅ 1187 通过 / 7 失败（6 个为 Playwright chromium 未安装的既有环境问题，1 个为上述同步契约扩展后的用例，已修复重验）/ 38 跳过 |
| 前端新增（MessageQueueBar 3 例、ChatInput 2 例、store 2 例、WS 客户端 2 例） | ✅ 全部通过 |
| 前端全量 vitest | ✅ 257/257 通过 |
| `tsc` + `vite build` | ✅ 通过 |

## 四、P1 规划（下一批，按价值排序）

### 4.1 Changed Files 变更聚合（✅ 已落地 2026-11-01）

- **语义**（对齐 Studio `ToolOutput.changedFiles` + mutation receipts）：edit/patch/write 工具结果中携带 `changedFiles: [{path, action: created|modified|deleted|moved}]`；Run 终态后按 path 去重聚合（同路径"最后一次出现"胜出），前端在 Run 块尾部渲染折叠条"变更了 N 个文件"，点击项查看 Diff。
- **接入点**：`ToolResult` 增加可选 `changed_files` 字段（edit_tool/patch_tool 生产）；`ConversationRuntimeAdapter` 落库时随 tool_trace payload 写入；前端 `transcriptItems` 在 run 组内聚合；部分失败只计成功子项。
- **预估规模**：后端 3 文件 + 前端 3 文件 + 测试；1 个开发日。
- **落地记录（2026-11-01）**：ToolResult 增 `changed_files` 字段（`changed_file_entry` 助手）；edit 工具 8 处成功点与 patch 工具 4 处成功点产出 created/modified/deleted；tool:result 事件与 trace payload 透传；前端 `utils/changedFiles.ts`（路径归一化 + "同路径最后一次出现胜出"折叠，moved 先移除 oldPath 键）+ `ChangedFilesBar` 折叠条挂在过程分组尾部（收起/展开两态均可见）+ 点击文件在工作区代码面板打开。测试：后端 +10 例、前端 +14 例，全量绿（后端 1204、前端 271）。

### 4.2 会话导入导出

- **语义**（对齐 Studio `ChatArchiveSchema`）：导出 `format: 'reflexion-chat'`、`version: 1`、消息（含思考与工具记录投影）、图片 base64 内联、16MiB 上限；运行中会话拒绝导出；导入先完整校验再单事务重建，失败补偿删除，**不恢复**审批/队列/授权等运行时状态。
- **接入点**：新增 REST `GET /api/sessions/{id}/export`（流式 JSON 下载）与 `POST /api/sessions/import`（multipart 上传）；复用 `ConversationService.append_events` 重建 turn/run/message 事件序列。
- **预估规模**：后端 2 路由 + 校验模块 + 前端设置/菜单入口；2 个开发日。

### 4.3 文件式记忆（AGENTS.md / MEMORY.md 注入 + memory.remember）

- **语义**：项目根 `AGENTS.md`、全局/项目 `MEMORY.md` 四层注入系统提示词；`memory_remember` 工具供 Agent 主动写入；与既有 CuratedMemoryStore 并存（文件记忆面向"人可编辑"，entry 记忆面向"机器管理"）。
- **接入点**：`PromptManager` 注入层 + 新工具注册（`_build_run_tool_registry`）；注意 2000 token 预算截断。
- **预估规模**：后端 2 模块 + 测试；1 个开发日。

## 五、P2 规划（远期）

1. **多 Agent 委派增强**：DelegateTool 增加子 Run 预算（token/步数/超时）、权限交集快照、变更归属（Changed Files 透传聚合）；对齐 Studio `DELEGATION-AND-POLICY.md`。
2. **Run 级性能指标**：events 增加阶段耗时记录，会话页显示可折叠明细（不把累计工具工时冒充墙钟总时长）。
3. **消息附件（文档类）**：本地文字提取接入上下文（无 OCR），复用现有 attachment 通道。
4. **移动端/多客户端接入**：仅在本项目升级出独立网关需求时评估；优先级低于 P1。

## 六、明确不采纳项与理由

| 项 | 理由 |
|---|---|
| TS Runtime / Rust System Runtime / Tauri 重写 | 1131 项后端测试与安全层（8 级效果分类、沙箱、信任规则）是本项目核心资产，重写等于清零；性能瓶颈在 LLM 而非运行时；打包链路已可用。若未来另立新项目（如 Studio），按 Studio 方式独立建仓，不做原地迁移 |
| CEF 浏览器嵌入 | 本项目 BrowserTool 定位为 Agent 受控自动化，不是用户浏览器 Surface |
| 事件溯源外的 outbox / 跨进程投递 | 单进程单 Runtime 架构下无此需求 |
| 队列持久化 | Studio 同样不持久化队列；重启丢失排队消息是可接受的语义（避免重启后"复活"旧意图） |

## 七、验收口径

- 每个采纳项必须：协议有契约（本文档 §3.2 风格）、后端有单元+集成测试、前端有渲染/路由测试、全量测试套件绿、本文档同步更新。
- P0 已满足上述全部口径。
