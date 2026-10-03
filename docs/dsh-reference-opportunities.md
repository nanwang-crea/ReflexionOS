# DeepSeek Harness 对照分析与借鉴清单

> 记录日期：2026-10-02
> 来源仓库：[deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（`dsh`，TypeScript，MIT，一切皆插件 + Cordis 框架）
> 对照方式：逐条核实 ReflexionOS 当前代码（`backend/app/`），标注「✅ 已做 / 🟡 半做 / ❌ 空白」，只记录真实差距，不虚构。

---

## 一、总体判断

dsh 与 ReflexionOS 是同赛道竞品（本地 agent harness：任务循环 + 工具编排 + 沙箱 + 审批 + 可观察管线）。路线不同：dsh 走「纯 TypeScript + Cordis 插件化 + 配置驱动组合」，ReflexionOS 走「Python + 安全合规侧重点」。

**重要修正**：对照前以为 ReflexionOS 多处空白，实际核实后发现底子比预想成熟——事件溯源、schema 版本化、显式状态机主循环都已存在。真正的差距集中在**事件语义的规范化、测试保障、插件化的配置驱动程度**三块。

---

## 二、逐条对照结果

### 1. Turn/Step 形式化 + 事件链 — 🟡 半做（底子好，契约未文档化）

**dsh 的做法**：严格定义 step（一次模型请求 + 其工具调用）/ turn（0~N 个 step），并画出完整事件链 `turn/start → agent/pre-step → step/start → agent/request → llm/stream → tools/pre-execute → tools/execute → tools/post-execute → step/end → turn/end`。`agent/pre-step` 可在 input 认领前改写或拒绝。

**ReflexionOS 现状**：

- `app/execution/rapid_loop.py`：显式状态机（`LoopPhase`：PLANNING / TOOL_EXECUTION / ERROR_RECOVERY / FINAL_SUMMARY / DONE）驱动主循环，每个 phase handler 返回下一个 phase —— 这与 dsh 的 turn 形式化是**同级设计，甚至更偏状态机**。
- `app/execution/tool_call_executor.py`：单工具调用生命周期已归一化为三态（成功/失败/等待审批），事件 `tool:start` / `tool:result` 存在。
- **差距**：没有一份「事件链 + 每个事件产出契约」的权威文档；事件类型是字符串散落各处（`run:start`、`tool:start`、`run:error` 等），没有 waterfall/serial 语义区分，也没有 input 认领前的「改写/拒绝」hook 点。

**可借鉴**：

- [x] 写一份 `docs/` 下的「执行事件地图」：列出每个事件类型、生产者、消费者、负载契约（对照 dsh 的 `event-producer-consumer.md`）。**→ 已完成 2026-10-02：[event-map.md](event-map.md)（15 种事件），并有 test_event_map.py 活性保障**
- [x] 评估是否需要在消息认领环节加一个 pre-step hook（允许审批策略/脱敏策略在 input 进入循环前改写或拒绝），目前审批是在工具执行侧做的，input 侧没有拦截点。**→ 评估结论：暂缓，归入 🟢5，等执行链路大改窗口**

### 2. Session 日志 append-only + schema 版本化 — ✅ 已做（可小幅增强）

**dsh 的做法**：append-only `SessionEvent` 日志 + 内存 store；SQLite `SCHEMA_VERSION` 单调递增；破坏性变更走升级指南，老版本不动不删。

**ReflexionOS 现状**：

- `app/storage/models.py`：`ConversationEventModel` 事件表存在。
- `app/services/conversation_projection.py`：完整的事件溯源投影层（ConversationEvent → Session/Turn/Run/Message 读模型），与 dsh「Session events = 持久事实」是**同一模式**。
- `backend/alembic/`：5 个迁移版本，schema 版本化已落地。

**可借鉴**（锦上添花，非刚需）：

- [ ] 明确「老事件格式永不被破坏」的纪律：新字段只加不改，事件 payload 变更要配套迁移策略文档。
- [x] 检查投影层对「未知事件类型」的容错（重放老日志时遇到新事件应跳过而非崩溃）——需实测确认。**→ 已核查 2026-10-03：① match 无 default 分支，合法但未覆盖的枚举成员（APPROVAL_*×4、MESSAGES_TRUNCATED）静默跳过，安全；② 真实风险：DB 含当前枚举没有的 event_type 字符串时，`ConversationEvent` pydantic 反序列化直接 ValidationError 会崩（场景：版本回滚或枚举成员被删/改名）。纪律：EventType 只增不删不改名；读取层容错加固另立 spec**

### 3. 三类事件域划分（持久事实 / 在途状态 / 策略挂载）— ❌ 空白

**dsh 的做法**：Session 事件（写日志扛 reload）、Agent 事件（live，观察/拦截在途工作）、Capability 事件（`fs/*` `tools/*` 给 seam 挂策略，不污染 loop）。区分 waterfall（监听器须调 `next()` 委派）与 serial 两种语义。

**ReflexionOS 现状**：`_emit(event_type, data)` 字符串事件直推 WebSocket；审批策略（`approval_flow.py`）、命令分级（`command_effect_registry.py`）是**直接编码进执行路径**，不是以监听器形式挂在事件 seam 上。

**可借鉴**：

- [ ] 大重构候选：把审批策略、命令效果分级、脱敏做成 `tools/pre-execute` 类的策略挂载点，主循环只发事件、不认识策略细节。**优先级低**——现在硬塞会撕扯代码，等下次大改执行链路时一并做。

### 4. 录制回放测试（test:snapshot）— ❌ 空白（最值得补）

**dsh 的做法**：`test:snapshot` 用真实录制的 session 做 keyless 回归测试，通过 shipped profile 回放；`test:snapshot:record` 需 API key 重录。保证「重构 agent loop 不破坏已录制行为」。

**ReflexionOS 现状**：`backend/tests/` 覆盖 API/工具/安全/存储等，但**没有会话级的录制回放测试**——重构 `rapid_loop.py` 时只能靠单测 + 手测，回归保障弱。本机测试环境当前不可用（见记忆 `broken-test-envs-this-machine`），更依赖 CI。

**可借鉴**：

- [x] 建一个 FakeLLM 适配器（实现 `UniversalLLMInterface`，按脚本返回预录响应）+ 一组录制好的任务脚本，驱动 `RapidExecutionLoop` 跑完整 turn，断言产出的事件序列与 LoopResult。**→ 已完成 2026-10-02：`tests/support/replay_llm.py` + 3 个场景夹具，34 条新用例全绿**
- [x] 收益：重构状态机、换提示词、改工具编排时有一键回归网。**→ 已兑现，另有录制器 `recording_llm.py` + 重录脚本 `backend/scripts/record_replay_fixture.py`**
- [x] 切入点：`app/llm/base.py` 的接口很干净，`openai_adapter.py` 是唯一实现，加一个 fake 实现成本低。**→ 验证属实；实现见 [plan](superpowers/plans/2026-10-02-session-replay-testing-implementation-plan.md)**

### 5. 模型适配器 / 沙箱策略的配置驱动 — 🟡 半做

**dsh 的做法**：模型适配器、沙箱、审批策略全是插件，profile + patch YAML 可替换任意一行配置，`dsh --dump-config` 可查看当前插件树。

**ReflexionOS 现状**：

- LLM：`base.py` 接口干净，但只有 `openai_adapter.py` 一个实现（OpenAI 兼容协议打天下）；provider 配置走 `llm_provider_service.py` 持久化，已是配置驱动。近期两个 commit（`8658b909`、`0988ef6c`）已加备用模型链兜底。
- 沙箱：`security/sandbox/factory.py` 按平台自动选 Seatbelt/Landlock/Windows + NullSandbox 兜底，~~但选择逻辑硬编码在工厂里，不可配置~~ **已支持配置覆盖（2026-10-03）**：`config.json` 的 `sandbox.provider` 可强制指定后端或 `null`（排障无隔离模式），默认 `auto` 保持自动探测。

**可借鉴**：

- [x] 沙箱工厂加配置覆盖：允许配置文件指定后端优先级/强制禁用某后端（排查问题时有价值，改动小）。**→ 已完成 2026-10-03：`SandboxSettings.provider`（auto/windows/seatbelt/landlock/null）+ 工厂分支（指定后端不可用时降级 NullSandbox + warning，不静默换后端），7 条新用例；顺带修复 alembic `fileConfig` 禁用全部 app logger 的隐患**
- [ ] 模型侧暂不需要动——OpenAI 兼容协议 + 配置驱动 provider 已够用，近期兜底链也已落地。

### 6. Profile/Bundle 多形态（同一运行时多种 launch）— ❌ 空白（暂缓）

**dsh 的做法**：web/headless/sdk/sdk-minimal/acp 五种 profile 共享 `dsh-base` 层，桌面应用打包同一生产运行时。

**ReflexionOS 现状**：FastAPI 后端 + 前端 + Electron 打包（`packaging/`），是否多形态分裂未深查。

**可借鉴**：等真的出现「桌面 vs CLI vs SDK 各跑一份 agent loop」的分裂压力再考虑，现在不动。

---

## 三、落地优先级（按性价比排序）

| 优先级 | 事项 | 成本 | 收益 |
|---|---|---|---|
| 🔴 1 | 执行事件地图文档化（§1）**✅ 2026-10-02 完成** | 低（纯文档） | 事件契约清晰，排查/协作/面试讲述都受益 |
| 🔴 2 | 录制回放测试 + FakeLLM（§4）**✅ 2026-10-02 完成** | 中 | 重构主循环的回归保障，当前最缺的测试能力 |
| 🟡 3 | 沙箱工厂配置覆盖（§5）**✅ 2026-10-03 完成** | 低 | 排查环境问题更快 |
| 🟡 4 | 投影层未知事件容错核查（§2） | 低（核查） | 防老会话回放炸 |
| 🟢 5 | pre-step input 拦截 hook（§1） | 中 | 审批/脱敏前置，等下次执行链路大改时做 |
| 🟢 6 | 三类事件域划分（§3） | 高 | 架构收益，需大重构窗口 |
| 🟢 7 | Profile/Bundle 多形态（§6） | 高 | 等分裂压力出现再说 |

**明确不抄**：Cordis 框架本身（TS 时空可组合范式，Python 移植不现实）。只抄设计思想——可逆效应、依赖声明、插件卸载自动清理。

---

## 四、面试素材角度（顺带）

这次对照本身是很好的面试谈资：

- 「我研究过 DeepSeek 官方开源的 agent harness（23.8 万 star），对照自己的项目做了架构差距分析」——展示**技术视野与自我评估能力**。
- 能说清「我们的显式状态机主循环 vs dsh 的事件链形式化」是同级的两种设计取舍：状态机利于审批暂停/恢复的显式表达，事件链利于扩展点解耦。
- 能说清「事件溯源投影层我们独立做出来过，和 dsh 的 Session 事件模式殊途同归」。
