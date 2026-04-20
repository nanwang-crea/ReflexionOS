# ReflexionOS 记忆一期落地基线文档

> 状态：当前落地基线文档。
> 该文档用于把“记忆系统第一期”与当前代码实现对齐，明确已落地能力、未落地能力、现实边界与下一步推进顺序。
> 这不是总体架构文档，也不是详细实现任务清单，而是一份面向当前代码现实的落地说明文档。

**版本**: v1.0  
**日期**: 2026-04-20  
**语言**: 中文  
**对应上位架构文档**: `docs/superpowers/specs/2026-04-19-memory-architecture-v1.md`  
**对应第一期主文档**: `docs/plans/2026-04-19-memory-phase-1.md`

---

## 一、文档目标与适用范围

这份文档回答的不是“记忆系统最终应该长什么样”，而是：

1. 记忆系统第一期在当前仓库中已经具备了哪些真实基础
2. 当前实现与第一期目标之间已经对齐到什么程度
3. 哪些能力已经有代码支撑，哪些还停留在方案层
4. 下一步如果继续推进，最合理的收敛顺序是什么

因此，这份文档同时服务两类读者：

- 项目负责人：快速判断“现在到底做到哪一步了”
- 协作开发者：快速找到代码入口、边界和后续实施切口

本文档的核心原则只有一个：

**一切判断以当前代码仓库中的真实实现为准，不把上位设计中的目标能力误写为已落地能力。**

---

## 二、上位目标回顾：记忆一期到底要解决什么

根据第一期主文档 `docs/plans/2026-04-19-memory-phase-1.md`，记忆系统第一期并不是完整长期记忆系统，而是一个最小连续性闭环。

它的唯一目标可以压缩为一句话：

**让 agent 在同一个项目里持续推进任务时，不会“失忆式重启”。**

第一期重点解决三类连续性问题：

1. `Thread continuity`
   用户说“刚刚我们在聊什么”“继续刚才的话题”时，系统要能接上。
2. `Task continuity`
   用户说“继续上次那个问题”“按刚才说的方向继续推进”时，系统不要每次都从头分析。
3. `Commitment continuity`
   用户说“你刚才答应我的那个事”“那个待办继续做”时，系统不能把承诺和 follow-up 丢掉。

根据第一期方案，并结合上位架构文档，第一期只应落地以下最小子集：

- `Active Workspace` 的最小工作记忆能力
- `Archive` 的最小记录能力
- `Candidate` 的极简入口
- 极弱项目级长期记忆能力
- 一个降级版的 `State Assembler`，而不是完整 `Memory Compiler`

---

## 三、当前代码基线：仓库里已经有什么

基于当前代码仓库，记忆一期并没有以独立的 `memory` 子系统存在。当前更接近三类能力的组合：

1. 后端执行上下文能力
2. 后端执行与会话持久化能力
3. 前端工作区会话状态持久化能力

### 3.1 后端执行上下文

关键入口：`backend/app/execution/context_manager.py`

当前 `ExecutionContext` 已经提供以下基础能力：

- 保存当前任务 `task`
- 绑定当前项目路径 `project_path`
- 记录执行历史 `history`
- 记录执行步骤 `steps`
- 记录对话消息 `messages`
- 生成一个简单的工作区上下文字符串 `get_workspace_context()`

这说明当前系统已经具备“当前执行期的局部工作上下文”能力，但它的粒度仍然是：

- 面向单次执行
- 面向运行时
- 面向执行过程

它还不是一个稳定的“Active Workspace 记忆层”。

### 3.2 后端执行历史与项目维度持久化

关键入口包括：

- `backend/app/services/agent_service.py`
- `backend/app/storage/repositories/execution_repo.py`
- `backend/app/storage/models.py`
- `backend/app/api/routes/agent.py`
- `backend/app/api/routes/websocket.py`

当前后端已经具备：

- 项目维度的执行创建与运行
- execution 的数据库存储
- 按项目查询 execution history
- 会话/对话相关表结构基础
- execution 与 project 的关联

这部分能力构成了记忆体系里最接近 `Archive` 的现实基础。

但它当前仍然更偏“执行记录系统”，而不是“可治理的记忆归档系统”。

### 3.3 前端工作区会话状态

关键入口包括：

- `frontend/src/stores/workspaceStore.ts`
- `frontend/src/types/workspace.ts`
- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`

当前前端已经具备：

- 项目下创建多个聊天 session
- 为 session 保存最近 `10` 轮 `recentRounds`
- 按项目组织 session
- 使用 `zustand persist` 将工作区状态落在本地存储
- 当前运行轮通过 overlay 内存态承载
- 按 session 从后端拉取 transcript history 进行恢复

这说明前端侧已经具备“工作区会话连续性”的表层承载能力。

但当前保存的是 UI 会话与消息列表，不是结构化的线程状态、任务状态、承诺状态或反思状态。

更准确地说，当前前端 store 更适合承载：

- 当前项目下有哪些聊天 session
- 当前 session 正在展示哪些 render items
- 当前 UI 选择状态和局部连续性

而不适合直接承载：

- 完整工作记忆
- 承诺历史真相源
- 全量反思历史
- 全量 execution / receipt 原始记录

这意味着前端可以保存一部分连续性信息，但不应成为记忆一期的唯一真相源。

### 3.4 当前现实结论

如果把当前仓库压缩成一句话：

**ReflexionOS 现在已经有了记忆一期所需的若干基础设施，但还没有形成一个显式、结构化、可治理的记忆一期闭环。**

同时，前端和后端在“连续性”上的职责也需要进一步明确：

- 前端更适合做 UI 会话层与轻量快照缓存
- 后端更适合做 Active Workspace 真相源与 Archive 真相源

---

## 四、目标到实现的映射表

下表用于回答一个核心问题：第一期方案中的每个核心目标，在当前代码里对应到了什么，缺了什么。

| 第一期开工目标 | 当前代码中对应的现实基础 | 当前状态判断 |
| --- | --- | --- |
| Thread continuity | 前端 recentRounds、本地持久化、session transcript history | 部分具备表层能力，但缺少结构化线程状态 |
| Task continuity | `ExecutionContext.task`、执行历史、execution history | 部分具备，但主要停留在单次执行上下文 |
| Commitment continuity | 暂无专门数据结构或持久化入口 | 基本未落地 |
| Active Workspace | `ExecutionContext` + workspaceStore 的组合基础 | 仅有雏形，未形成统一工作记忆层 |
| Archive | execution 持久化、session transcript archive、receipt/agent-update 回放 | 已具备最小可回放 transcript 归档能力，但尚未形成完整记忆治理层 |
| Candidate | 无明确候选区模型或写入入口 | 未落地 |
| Durable Memory | 无稳定项目级长期记忆模型 | 未落地 |
| State Assembler | `get_workspace_context()` 仅提供极简上下文拼接 | 极弱雏形，不足以承担一期目标 |

这个映射表的意义在于：

- 当前不是“从零开始”
- 但也不能说“记忆一期已经完成”
- 更准确的表述是“基础设施已经存在，记忆层编排与结构化治理尚未建立”

---

## 五、当前已落地能力

本节只描述能够在当前代码中找到明确支撑的能力。

### 5.1 项目级执行记录已存在

当前系统已经能把一次 agent 执行与某个项目关联起来，并将 execution 进行存储和查询。

这意味着：

- 同一项目下的历史执行不是完全丢失的
- 系统已经具备“后查历史”的最小入口
- 后续若要做 `Archive`，并不需要从零开始设计持久化层

这是记忆一期里“先做到不丢”的关键基础。

### 5.2 当前执行期间的上下文已有最小容器

`ExecutionContext` 已经承载：

- 当前任务
- 最近操作历史
- 消息列表
- 步骤状态

虽然它还不是完整工作记忆，但它至少说明：

- 系统已经接受“执行需要上下文容器”这一前提
- 运行时并非完全无状态
- 后续可以在此基础上升级为更明确的 `Active Workspace` 结构

### 5.3 工作区聊天会话具备本地连续性与后端历史恢复能力

前端 `workspaceStore` 当前会把会话元信息、最近 `10` 轮、当前会话、项目展开状态等信息通过本地存储持久化；更早的历史则由后端 transcript history 提供。

这部分能力直接支撑了用户感知层面的最小连续性：

- 刷新后会话列表不丢
- 同项目下历史聊天入口还在
- 聊天消息不会因为 UI 切换全部消失

虽然这不是“记忆系统”的完整实现，但它已经解决了体验上最粗糙的断片问题。

但也必须明确：

**前端当前这层连续性更接近“渲染连续性”和“会话连续性”，而不是结构化工作记忆连续性。**

### 5.4 工具执行轨迹与 session transcript 具有可回放基础

当前系统本身强调透明 agent 体验，工具调用、执行步骤、消息流与回执都已经进入现有执行链路，并且已开始沉淀为 session 级 transcript archive。

这意味着后续要补记忆体系时，有天然的证据来源可依赖：

- 工具调用历史
- 执行结果
- 会话 transcript
- receipt / agent-update / assistant / user 的可回放记录
- 项目维度 execution 记录

这对于后续构建 `Archive` 和候选记忆来源非常重要。

---

## 六、当前未落地或仅部分落地的能力

本节是当前文档最重要的部分之一，用于明确边界，避免误判项目成熟度。

### 6.1 没有显式的 Active Workspace 数据模型

第一期设计里最核心的是 `Active Workspace`，它应该显式承载：

- 当前线程
- 当前任务
- 当前承诺
- 最近反思
- 下一步动作

但当前代码里没有统一的数据结构来表达这些内容。

目前只有：

- `ExecutionContext` 中的 task/history/messages
- 前端 session items 的消息数组

这两者都不能等价替代第一期所需的结构化工作记忆层。

这也意味着，如果继续把完整消息历史和工作记忆状态都堆进当前前端 store：

- 职责会继续混淆
- 数据边界会继续模糊
- UI 渲染模型和记忆模型会彼此污染

### 6.2 没有 Commitment continuity 的落地承载

一期目标中“承诺不丢”是核心之一，但当前没有看到专门承载以下内容的结构：

- agent 已答应用户的事项
- follow-up 列表
- 未完成承诺
- 承诺状态变化

这意味着：

- 用户感知中的“你刚才答应我的那个事”仍然容易断片
- 即使会话消息被保存，也没有结构化承诺提取与持续注入能力

这是当前与第一期目标之间最直接的缺口之一。

### 6.3 没有 Recent Reflection 机制

第一期方案明确要求保留“最近反思”，即：

- 最近失败点
- 有效策略
- 注意事项

当前代码里虽然有 execution history 和消息记录，但没有看到专门的 reflection 数据结构、生成流程或注入逻辑。

因此当前系统仍然缺少：

- 从一次执行中提炼经验
- 在下一次推进中带入经验
- 避免重复犯错的最小闭环

### 6.4 Archive 已具备最小 transcript 回放能力，但仍不是完整记忆归档层

当前后端已经不只是 execution 持久化基础，而是具备了 session 级 transcript archive 的最小闭环：

- `session_id` 已贯通到执行与历史查询链路
- session history API 已可拉取历史
- transcript archive 已可回放 `user-message / agent-update / action-receipt / assistant-message`

但它仍然没有完全形成一期期望中的完整归档区行为模型。

当前欠缺的包括：

- 明确的 archive 读写边界
- transcript / tool result / execution log 的统一归档抽象
- 面向记忆回查的稳定查询语义
- 归档到工作视图之间的编排关系

因此当前更准确的说法是：

**Archive 作为最小可回放 transcript 归档已经成立，但还没有上升为完整的记忆治理与提炼层。**

### 6.5 Candidate 与 Durable Memory 基本未进入实现层

在一期设计中，`Candidate` 至少要支持“用户明确要求记住”的内容进入候选区，`Durable Memory` 至少要承载最小项目级长期记忆。

当前代码中未见：

- 候选记忆模型
- 记忆写入 API
- 审核或提升入口
- 项目级长期记忆存储结构
- 长期记忆查询与注入流程

因此这两部分当前仍属于设计层，而非落地层。

### 6.6 State Assembler 只有极弱雏形

一期设计中，完整 `Memory Compiler` 被降级为 `State Assembler`，其职责是把当前工作区整理成稳定可用的工作视图。

当前最接近这一角色的实现，是 `ExecutionContext.get_workspace_context()` 输出的简单字符串上下文。

但这仍有几个明显问题：

- 输出结构过弱
- 只覆盖 task 和最近工具调用
- 不覆盖承诺
- 不覆盖反思
- 不覆盖明确的 next step
- 不具备统一可消费的工作视图协议

因此它只能算“上下文拼接函数”，还不能算真正的一期 `State Assembler`。

### 6.7 前端当前持久化策略的主要风险已从“全量历史”收缩为“recentRounds + transcript 渲染压力”

当前前端的 `workspaceStore` 使用 `zustand persist + localStorage` 保存 workspace 状态，但已经不再长期持久化全量消息历史，而是保存 session 元信息与 `recentRounds`。

这在消息较少时问题不大，但随着会话增长，会出现三个叠加风险：

1. `sessions` 整体序列化与写回仍会随着 session 数量和 recentRounds 增长而变重
2. rehydrate 时仍需要恢复 recentRounds 与 UI 状态
3. UI 层仍会对较长 transcript 做渲染与 markdown 解析

因此，如果继续在当前 store 里堆更多结构化状态，而不维持“前端缓存、后端真相源”的边界，后续仍然容易出现：

- 启动变慢
- 切换 session 变重
- 长消息场景下滚动和输入反馈变差

这个问题的根因不是单纯“localStorage 空间会不会不够”，而是：

**当前持久化模型和渲染模型都在放大大消息、长会话和全量历史带来的成本。**

---

## 七、差距清单与现实风险

如果以“形成记忆一期最小连续性闭环”为目标，当前主要差距可以压缩为以下五项。

### 7.1 差距一：缺少统一的工作记忆对象

没有统一对象，就意味着：

- 线程状态散落在消息里
- 任务状态散落在 task/history 里
- 承诺状态几乎不存在
- 反思状态没有稳定归属

这会直接导致第一期最重要的“连续协作不断片”难以成立。

### 7.2 差距二：缺少结构化提取，而不仅仅是原始保存

当前系统更擅长保存“发生了什么”，但还不擅长抽取“下一轮推进需要保留什么”。

这两者的区别非常关键：

- 原始记录解决“不丢”
- 结构化提取才解决“不断片”

如果只有原始记录，没有结构化状态，那么系统还是会在下一轮推进时重新阅读、重新分析、重新组织。

### 7.3 差距三：缺少承诺层，会直接影响协作可信度

从用户体验看，承诺连续性是“这个 agent 靠不靠谱”的核心指标之一。

当前如果没有：

- 明确承诺列表
- 承诺完成状态
- follow-up 入口

那么即使线程能续上，用户仍会觉得 agent 容易“答应了但没接着做”。

### 7.4 差距四：前后端状态没有汇聚成统一记忆视图

当前前端保存会话，后端保存 execution，但两边没有汇聚成一个统一的“当前工作视图”。

这会导致两个后果：

- UI 连续性和运行时连续性是分裂的
- 用户看到的上下文与运行时真正注入给 agent 的上下文可能不一致

更具体地说，当前前端更像“展示层状态容器”，后端更像“执行层记录容器”，但两边之间还缺一个明确的结构化工作视图协议。

### 7.5 差距五：若直接跳到长期记忆，会放大系统复杂度

当前最容易犯的错误不是“做得太少”，而是“在工作记忆层还没站稳时，过早引入 Candidate、Durable Memory、复杂 recall 和自动晋升”。

那样会带来：

- 结构不清
- 闭环不稳
- 调试困难
- 用户难以理解记忆到底怎么生效

这与一期“最小连续性闭环”的目标相冲突。

### 7.6 差距六：前端尚未从“完整历史持久化思路”切换到“轻量快照缓存思路”

当前如果不主动收敛前端职责，后续很容易自然滑向一种错误方向：

- 前端既存 UI session
- 又存完整消息历史
- 又存 thread/task/commitment/reflection
- 甚至继续存更多 receipt 与执行状态

这样做短期看似方便，长期会带来两个问题：

1. 前端 store 变成事实上的真相源，破坏后端记忆系统边界
2. 前端性能成本随历史规模线性放大，最终影响 workspace 体验

---

## 八、下一步推进顺序

下面的推进顺序不是详细实现计划，而是站在当前代码现实上，给出最合理的收敛路径。

### 8.1 第一步：先收敛 Active Workspace 最小结构

第一步不应该先做长期记忆，而应该先定义并落地一个显式的最小工作记忆对象，至少覆盖：

- 当前线程
- 当前任务
- 当前承诺
- 最近反思
- 下一步

这是一期真正的系统中轴。

只要这一层没有成型，后面的 Archive、Candidate、Durable Memory 都会缺乏稳定挂点。

### 8.2 第二步：把现有 execution/session 数据映射进工作记忆层

当前仓库并不缺原始信息，而是缺“从已有信息到工作视图”的整理层。

因此第二步的重点应该是：

- 利用现有 execution history
- 利用现有消息记录
- 利用前端 session
- 抽取出稳定的工作记忆字段

这一步本质上是在补第一版 `State Assembler`。

同时需要明确前后端分工：

- 后端负责生成结构化 Active Workspace
- 前端负责消费和缓存一个小型 snapshot，而不是复制完整真相源

### 8.3 第三步：补上 Commitment continuity

如果只补线程和任务，而不补承诺，一期目标仍然不完整。

因此需要尽早引入最小承诺模型，例如：

- 承诺内容
- 来源
- 当前状态
- 是否待继续

这样系统才能真正支撑“你刚才答应我的那个事”。

### 8.4 第四步：补上 Recent Reflection 最小闭环

当工作记忆层基本稳定后，再引入最小反思能力会更自然。

重点不是做复杂复盘系统，而是最小化地保留：

- 最近失败点
- 有效策略
- 下一次要避免什么

这能显著提升“继续推进同一件事”时的稳定性。

### 8.5 第五步：最后再接 Candidate 与项目级长期记忆

只有当工作记忆层稳定之后，才适合把“用户明确要求记住”的内容引入 `Candidate`，再逐步过渡到最小项目级长期记忆。

这是因为：

- 一期价值主要来自 Active Workspace
- 长期记忆不是一期主价值来源
- 先把当前会话和当前任务连续性打通，收益最大、风险最小

### 8.6 第六步：重构前端存储职责，切到“前端缓存，后端真相源”

在工作记忆层初步成型后，前端应明确切换为两层结构：

1. `workspaceStore`
   继续负责：
   - UI session
   - 当前会话选择
   - render items
   - 搜索、展开等纯界面状态

2. `activeWorkspaceSnapshotStore`
   只负责保存轻量结构化快照，例如：
   - `threadSummary`
   - `threadStatus`
   - `currentTask`
   - `nextStep`
   - `openCommitments`
   - `recentReflections`
   - `updatedAt`
   - `version`

这层 snapshot 应被视为：

- 可丢失
- 可重建
- 体积可控
- 不承担完整真相源职责

相对应地，完整消息历史与原始执行归档应更多由后端负责。

### 8.7 第七步：继续巩固“后端拉取 + 前端有限缓存”边界

在消息历史层，这条方向当前已经完成了最小落地，后续需要继续巩固，而不是回退到前端全量历史持久化：

- 后端负责历史消息和执行记录的真实存储
- 前端按当前 session 拉取所需消息用于渲染
- 前端只缓存最近有限条消息，例如最近 `10` 条，作为切换和短时恢复优化

这条策略的重点不是节省一点存储空间，而是控制：

- localStorage 体积
- store 重序列化成本
- session 切换成本
- 长消息场景下的 UI 卡顿风险

---

## 九、前后端职责边界建议

为了让记忆一期真正可落地，当前最需要补清楚的不是更多能力点，而是边界。

建议的职责划分如下：

### 9.1 前端负责什么

前端负责：

- 工作区 UI 状态
- session 选择与展示
- render items 的渲染
- 小型 Active Workspace snapshot 缓存
- 最近少量消息缓存

前端不负责：

- 完整工作记忆真相源
- 完整承诺历史
- 完整反思历史
- 状态变迁事件流
- 全量 tool receipt / execution log 原始归档

### 9.2 后端负责什么

后端负责：

- `Archive` 真相源
- `Active Workspace` 真相源
- 历史消息与执行轨迹存储
- 结构化工作视图生成
- 后续 Candidate / Durable Memory 的真实承载

### 9.3 这条边界的价值

这样切分后，系统会同时获得两方面收益：

1. 结构收益
   - 真相源集中在后端
   - 前端不再混合渲染模型与记忆模型
   - 记忆系统后续扩展更清晰

2. 性能收益
   - 前端持久化数据体积可控
   - session 切换成本下降
   - rehydrate 成本下降
   - 长消息场景下 UI 压力更可控

---

## 十、结论

对当前项目最准确的判断不是“记忆一期已经完成”，也不是“还完全没开始”，而是：

**ReflexionOS 已经具备了记忆一期所需的执行上下文、执行归档和工作区持久化基础，但还没有把这些基础设施组织成一个显式、结构化、可持续注入的最小记忆闭环。**

如果继续推进，一期的正确落地方向不是直接扩展长期记忆能力，而是先把：

- `Active Workspace`
- `Commitment continuity`
- `Recent Reflection`
- `State Assembler`

这几个最小核心件补齐。

一旦这一层成立，当前仓库中已经存在的执行记录、会话持久化和项目维度历史就可以自然汇入一期闭环；否则，这些能力仍然只是“记录存在”，而不是“记忆生效”。

---

## 十一、附录：关键代码入口索引

### 10.1 后端执行上下文

- `backend/app/execution/context_manager.py`

### 10.2 后端执行存储与查询

- `backend/app/services/agent_service.py`
- `backend/app/storage/repositories/execution_repo.py`
- `backend/app/storage/models.py`
- `backend/app/api/routes/agent.py`
- `backend/app/api/routes/websocket.py`

### 10.3 前端工作区与会话状态

- `frontend/src/stores/workspaceStore.ts`
- `frontend/src/types/workspace.ts`
- `frontend/src/pages/AgentWorkspace.tsx`
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`

### 10.4 已有相关文档

- `docs/plans/2026-04-19-memory-phase-1.md`
- `docs/superpowers/specs/2026-04-19-memory-architecture-v1.md`
