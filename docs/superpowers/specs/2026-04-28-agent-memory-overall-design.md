# ReflexionOS Agent 记忆系统整体设计

> 日期：2026-04-28  
> 状态：评审中  
> 适用范围：ReflexionOS Agent 记忆系统整体架构  
> 核心结论：第一阶段不要把系统做成“统一 memory 大仓库”，而要做成“基于 conversation 事实层的三层上下文装配系统”

## 1. 背景与结论

当前 ReflexionOS 已经具备稳定的会话事实层：

- `sessions`
- `turns`
- `runs`
- `messages`
- `conversation_events`

这意味着系统已经有了真正的原始事实源。记忆系统的工作重点，不应再是“额外创造一套事实库”，而应是回答三个不同的问题：

1. 同一个 session 在长对话、压缩上下文、切走、重开之后，怎么继续工作。
2. 项目级稳定偏好、协作规则、长期约束，怎么以小而硬的形式留下来。
3. 跨 session 时，怎么按需找回历史，而不是把旧对话全塞进 prompt。

这三个问题不能混在一起做。它们分别对应：

- `continuation`
- `curated memory`
- `recall`

本设计的第一原则是：

> transcript 永远是事实源；memory、continuation、recall 都只能是它的上层衍生能力。

但对第一阶段来说，还需要再往下落一层：

> **memory / continuation / recall 真正读取的主表，应当是 `messages`。**

原因来自当前实现本身，而不是抽象偏好：

- 用户输入已经稳定落在 `messages.content_text`
- assistant 输出已经稳定落在 `messages.content_text`
- `tool_trace` 的关键结果已经稳定落在 `messages.payload_json`
- `system_notice` 已经稳定落在 `messages.content_text + payload_json`

因此：

- `messages` 应当成为第一阶段记忆读取主面
- `turns / runs / sessions` 只作为作用域、排序和状态补充
- `conversation_events` 主要保留为 append-only 同步日志和投影来源，不进入记忆读取主链路

## 2. 核心判断

这套系统从根上讲，不应该被理解成“做一个复杂的 memory system”，而应该被理解成：

> **做一个三层运行时上下文系统，再加两个轻量治理机制。**

### 2.1 运行时真正有用的主干只有一条

第一阶段里，真正实用的“工作记忆主干”就是 **以 `messages` 为中心的 conversation 事实视图**。

也就是说：

- 最近发生了什么
- 当前 run 到哪一步了
- 最近有哪些工具输出和错误
- 过去某次 session 具体做过什么

这些最有价值的信息，几乎都应该从 `messages` 取出，再按需结合 `turns / runs / sessions` 做补充，而不是额外存成另一套 memory。

### 2.2 额外能力只保留两类薄层

在 conversation 主干之外，只保留两类薄层：

1. `curated memory`
   - 小而硬的稳定偏好、规则、约束
2. `continuation artifact`
   - 文本压缩后的 handoff note

除此之外，不再额外引入沉重的 memory taxonomy。

## 3. 运行时三层模型

运行时上下文直接按三层表达，不再使用很多概念层并列描述：

```text
Static Context Pack
-> Recent Conversation Pack
-> Supplemental Context Pack
```

### 3.1 Static Context Pack

这是 session 级常驻上下文，默认进入 cached prompt。

它包含：

- system prompt
- `AGENTS.md`
- `USER.md`
- `MEMORY.md`

它解决的问题：

- 项目规则是什么
- 用户稳定偏好是什么
- 当前项目有哪些长期成立的环境事实、约束和约定

它不解决的问题：

- 当前长会话最近几轮的具体细节
- 历史 session 的具体处理过程

### 3.2 Recent Conversation Pack

这是当前 session 的最近精确历史窗口，直接来自 `messages` 表。

它包含：

- 最近几轮 `messages`
- 通过 `turn_id / run_id / session_id` 关联出来的当前 `turn/run` 关键状态
- 最近的关键 tool trace / error / assistant 输出

它是第一阶段最重要的运行时层，因为它承载真实工作现场。

这里必须强调一个与当前代码强相关的现实：

- `user_message` 与 `assistant_message` 的主要文本在 `content_text`
- `tool_trace` 的很多关键内容不在 `content_text`，而在 `payload_json`
- `system_notice` 则可能同时依赖 `content_text` 与 `payload_json`

因此第一阶段不能把“读取 messages”错误简化成“只读 `content_text`”。

另外，基于当前表结构，memory 读取时的逻辑顺序也应明确：

- `messages` 表只有 `turn_message_index`
- 全 session 范围内没有独立 `global message index`

因此在记忆、continuation、recall 处理中，建议按以下逻辑排序：

1. `turn.turn_index`
2. `message.turn_message_index`
3. `message.created_at` 作为兜底 tie-breaker

而不是只按 `created_at` 直接扫表。

### 3.3 Supplemental Context Pack

这是按需补充层，只在需要时进入当前回合。

它只包含两类块：

- `Continuation Artifact`
- `Recall Result`

使用原则：

1. 默认情况下，不注入 supplemental context。
2. 长会话压缩或恢复时，优先用 `Continuation Artifact`。
3. 用户显式要求“回忆以前做过什么”时，优先用 `Recall Result`。
4. 第一阶段尽量避免一个回合里同时注入很多补充块。

## 4. 四个核心对象

这套系统的治理对象，实际只需要四个核心对象：

- `AGENTS.md`
- `USER.md`
- `MEMORY.md`
- `Continuation Artifact`

conversation 事实层是底座，不是“记忆对象”；recall 是 `messages` 主表上的读取能力，不是独立存储对象。

### 4.1 AGENTS.md

`AGENTS.md` 是项目规则文件，不是 memory。

它只承载：

- 架构约束
- 协作方式
- coding convention
- 项目内显式流程要求

规则：

- 默认由人维护
- 不作为 memory 工具自动写入目标
- 权威性高于 `USER.md / MEMORY.md`

### 4.2 USER.md

`USER.md` 只承载稳定用户偏好。

典型内容：

- 默认输出语言
- 解释风格偏好
- 是否喜欢先解释再执行
- 反复出现的纠正与禁忌

不应写入：

- 一次性的当前任务要求
- 某次 debug 现场
- 历史任务记录

### 4.3 MEMORY.md

`MEMORY.md` 只承载项目级稳定事实与长期约束。

典型内容：

- 已验证的环境事实
- 长期成立的项目约束
- 工具 quirks
- 团队长期工作约定

不应写入：

- task diary
- bug 修复流水账
- 历史聊天摘要
- 临时 TODO

### 4.4 Continuation Artifact

`Continuation Artifact` 本质上就是：

> **conversation 文本压缩之后，为了继续当前 session 而留下的 handoff note**

第一阶段里，不应同时存在：

- 一份“压缩摘要”
- 一份“continuation artifact”

这两者必须是同一个对象。

它的作用只有一个：

- 让被压缩掉的上下文，仍能以短的接力形式继续服务当前 session

关键约束：

1. 它是 derived，不是事实。
2. 它来自 conversation 压缩，不来自独立的 memory 生成逻辑。
3. 它只服务当前 session，不服务跨 session 的历史回忆。
4. 它不能自动晋升为 `USER.md / MEMORY.md`。
5. recall 默认不检索它。

## 5. 存储与作用域

### 5.1 Session / Project / User 三种作用域

这里必须明确写死：

- `session` 是执行连续性单元
- `project` 是长期认知单元
- `user` 是跨项目偏好单元

因此：

- continuation 绑定 `session`
- `MEMORY.md` 绑定 `project`
- `USER.md` 第一阶段以 `project` 为主，后续可扩展 `global`
- recall 默认按 `project` scope 搜 conversation 历史

### 5.2 Curated Memory 的默认存储位置

第一阶段默认不污染用户仓库，使用 app-managed file store：

```text
~/.reflexion/memories/projects/<project_id>/USER.md
~/.reflexion/memories/projects/<project_id>/MEMORY.md
```

后续预留：

```text
~/.reflexion/memories/global/USER.md
```

### 5.3 Continuation Artifact 的默认存储策略

第一阶段优先不新建重型 memory 表，而是直接复用现有 conversation 体系，尤其是 `messages`。

建议实现方式：

- 作为特殊的派生 `message`
- 或作为特殊的 `system_notice`
- 并在 `payload_json` 中明确标记：
  - `derived=true`
  - `kind=continuation_artifact`
  - `source_seq_from`
  - `source_seq_to`
  - `exclude_from_recall=true`
  - `exclude_from_memory_promotion=true`

这样做好处很直接：

- 不新增新的主存储重心
- 继续围绕 conversation 表做恢复与同步
- 明确把 continuation 限制为“可看见但低权威的派生对象”

## 6. 权威性与冲突模型

系统内不同来源的权威性排序如下：

1. 当前用户显式指令
2. `AGENTS.md`
3. 项目级 `USER.md / MEMORY.md`
4. 全局级 `USER.md`
5. conversation recall 结果
6. continuation artifact

解释：

- `AGENTS.md` 约束项目行为，因此高于 memory。
- `USER.md / MEMORY.md` 是系统已经沉淀下来的稳定结论，因此高于 recall。
- recall 只提供历史证据，不能直接改写 curated memory。
- continuation 只为续航服务，因此权重最低。

## 7. 运行时读路径

### 7.1 正常新回合

默认装配顺序：

1. `Static Context Pack`
   - system prompt
   - `AGENTS.md`
   - 项目级 `USER.md / MEMORY.md`
   - 全局级 `USER.md`（若存在）
2. `Recent Conversation Pack`
   - 当前 session 最近的精确 `messages` 历史窗口
   - 当前活跃 `turn/run` 的关键状态
3. `Supplemental Context Pack`
   - continuation artifact，或
   - 本次按需触发的 recall result

关键约束：

- 默认不自动把旧 session 全量历史塞进 prompt。
- 默认不自动注入 recall。
- 最近精确历史始终优先于 continuation。

### 7.2 恢复已存在 session

恢复时依赖：

1. conversation snapshot
2. 项目级 `USER.md / MEMORY.md`
3. 最近精确 `messages` window
4. 如果当前 session 已发生压缩，则补一个最近的 continuation artifact

其中：

- snapshot 是恢复记忆读取面的主来源
- after-seq `events` 只用于增量同步，不作为 memory 读取主源

也就是说，恢复 session 依赖的不是一份大摘要，而是：

- conversation 真相
- 最新 handoff
- 常驻静态上下文

### 7.3 上下文接近阈值时

当上下文压力过高时，顺序应为：

1. `curated memory review`
   - 让模型判断有没有真正值得晋升的稳定规则
2. `context compaction`
   - 将将被折叠的 conversation 区段压成一个 continuation artifact
3. 保留最近精确窗口

重点：

- 先决定什么应该进入长期记忆
- 再把剩余需要续航的信息压成 handoff

### 7.4 跨 session 回忆

当用户表达以下意图时，优先触发 recall：

- “上次我们做过这个”
- “之前是不是修过类似问题”
- “你还记得那个设计吗”
- “我们上周怎么处理的”

流程：

1. 先在当前项目作用域内，以 `messages` 为主表检索
2. 返回匹配 session 的精确片段
3. 对片段生成聚焦总结
4. 将 recall 结果作为 Supplemental Context Pack 注入当前回合

默认不把 recall 结果写入长期 memory。

## 8. 写路径与治理机制

### 8.1 Curated Memory 写入触发

第一阶段建议只保留三种触发：

1. 用户显式要求“记住这个”
2. 当前回合出现高置信度稳定偏好 / 规则 / 约束 / 纠正
3. compaction 前的 `curated memory review`

不做：

- 每轮自动大规模抽取
- 自动把任务进度写入 memory
- 把历史 session 流水账写入 `MEMORY.md`

### 8.2 Memory Entry Schema

为了避免 `USER.md / MEMORY.md` 膨胀成半 transcript，必须定义最小 entry schema。

建议最小结构：

- `target`: `user | memory`
- `type`: `preference | rule | constraint | fact`
- `scope`: `project | global`
- `source`: `user_explicit | user_implied | derived`
- `confidence`: `high | medium`
- `status`: `active | superseded`
- `source_refs`: `message_id[]`
- `summary`
- `updated_at`

关键要求：

- Markdown 文件是用户可审阅视图
- 内部管理必须以 entry 为单位，而不是自由文本整文件重写
- 第一阶段只开放 `add / replace / remove`

### 8.3 Continuation Artifact 生成规则

Continuation Artifact 直接由文本压缩产出，不单独再定义另一套摘要对象。

触发时机：

1. context compaction 前后
2. session 恢复前需要 handoff 时

生成输入：

- 将被折叠的 `messages` 区段
- 当前 tail exact window
- 当前活跃 run / tool trace 的关键状态

输出必须短，并且格式固定，建议只保留：

1. 当前目标
2. 已确认的关键事实
3. 当前未解决点
4. 下一步建议动作
5. 关键引用指针

硬约束：

- 不引入新事实
- 不进入 recall 检索源
- 不直接进入 curated memory 晋升源

### 8.4 Message 规范化读取

由于当前代码里不同 `message_type` 的信息分布不同，第一阶段应明确一套统一的 message normalization 逻辑，用于：

- continuation 生成
- recall 检索
- curated memory review

建议规则如下：

1. `user_message`
   - 主文本来源：`content_text`
2. `assistant_message`
   - 主文本来源：`content_text`
3. `tool_trace`
   - 主文本来源：`payload_json`
   - 至少展开：
     - `tool_name`
     - `arguments`
     - `success`
     - `output`
     - `error`
4. `system_notice`
   - 主文本来源：`content_text`
   - 辅助来源：`payload_json.notice_code` 等结构化字段

也就是说，memory/retrieval 的真实输入应是：

> `normalized_message_text(message)`

而不是：

> `message.content_text`

### 8.5 Recall Ranking

为了避免 recall 变成噪音源，第一阶段必须至少有一套轻量 ranking 规则：

1. `relevance`
2. `recency`
3. `authority/type boost`

最小建议：

- 用户明确决策、约束类消息优先级最高
- assistant 普通解释类中等
- 大段工具输出默认降权
- 越新的 session 有 recency boost

为了贴合当前表结构，第一阶段建议建立一层派生索引：

- 源：`messages`
- 键：`message_id`
- 内容：`normalized_message_text`

这层索引可以是：

- FTS 虚拟表
- 或应用层维护的搜索文本表

但无论使用哪种技术，它的事实来源都应是 `messages`，而不是 `conversation_events`。

### 8.6 Memory Drift Checker

第一阶段应加入轻量冲突检测：

1. 新 memory entry 写入前，检查同 target 下是否存在冲突 active entry
2. 如果冲突，不直接 silent overwrite
3. 默认转为 `replace` 候选或 `superseded` 流程

目的：

- 防止 `USER.md / MEMORY.md` 长期累积自相矛盾的规则
- 让系统逐步学会“替换旧规则”，而不是无限叠加

## 9. 第一阶段落地范围

第一阶段只做最小闭环：

1. 项目级 app-managed `USER.md / MEMORY.md`
2. 基于 `messages` 表的 recent exact window
3. 由文本压缩直接生成的 continuation artifact
4. 基于 `messages` 表与规范化索引的 transcript recall
5. 运行时三层 context assembly
6. 轻量 drift checker
7. provider interface 预留

第一阶段不做：

- 用户全局级自动记忆主流程
- provider 真实接入
- embeddings / rerank / graph memory
- memory UI 编辑器完整产品化
- 仓库内 `MEMORY.md` 双向同步

## 10. 对当前代码的映射

### 10.1 可直接复用

- `ConversationService` 已经提供稳定的会话事实读写
- `ConversationSnapshot` 已经足以恢复当前 session 状态
- `messages` 已经是 memory / recall / continuation 的最佳主读取面
- `~/.reflexion/` 已经存在数据库和配置目录，可作为 memory 文件默认根目录

当前代码里的几个关键信号是：

- `MessageModel` 已经有稳定的 `content_text` 与 `payload_json`
- `ConversationProjection` 已经把 runtime 事件投影成稳定 message
- `ConversationRuntimeAdapter` 已经把 tool 结果写入 `tool_trace.payload_json`

这说明 Phase 1 最合理的策略不是“从 events 回放出记忆”，而是“直接消费已投影好的 messages”。

### 10.2 需要新增

- `backend/app/memory/` 的正式服务边界
- curated memory store
- continuation artifact 的 message/payload 约定
- 基于 `messages` 的 transcript recall service / FTS index
- 三层 context assembly
- drift checker

### 10.3 需要替换的思路

当前 `RapidExecutionLoop` 主要还是“最近消息组回放”。后续需要改成：

- static context
- recent exact conversation
- supplemental context

三层装配，而不是只依赖最近消息截断。

## 11. 为什么这版更稳

这版方案比“统一摘要型 memory 系统”更稳，原因有四点：

1. transcript 永远是事实源
2. continuation 只是压缩产物，不是第二份 transcript
3. recall 只按需触发，不常驻上下文
4. runtime 只保留三层，复杂度可控

最终效果应该是：

- 同一个 session 里更不容易断片
- 用户稳定偏好和项目长期约束会逐步沉淀
- 历史工作过程可以按需找回
- 第二阶段扩展 provider 时不需要推翻本地架构

## 12. 下一步

这份整体设计之后，下一步应单独产出一份 Phase 1 实施计划，重点拆解：

1. `USER.md / MEMORY.md` 的文件格式与 entry 管理接口
2. continuation artifact 的 message/payload 约定
3. transcript recall 的 ranking 与 API contract
4. `RapidExecutionLoop` / prompt assembly 的三层装配改造
5. drift checker 与 supersede 规则
