# ReflexionOS Agent 记忆系统整体设计

> 日期：2026-04-28  
> 状态：已在对话中确认，可作为后续 Phase 1 实施计划的唯一设计依据  
> 适用范围：ReflexionOS Agent 记忆系统整体架构  
> 来源：基于当前 `conversation/event` 会话底座、现有数据库事实层，以及对 `hermes-agent` 记忆设计的对照分析后重新收敛出的方案  
> 核心结论：不要再把“长期记忆”“长上下文续航”“跨 session 回忆”混成一个系统；它们必须拆层设计

## 1. 背景与结论

当前 ReflexionOS 已经具备一套稳定的会话事实层：

- `sessions`
- `turns`
- `runs`
- `messages`
- `conversation_events`

这些数据已经足够承载“发生过什么”的原始事实，因此记忆系统的核心问题并不是“再造一份事实库”，而是：

1. 如何让同一个 session 在离开、重开应用后仍能继续工作。
2. 如何让项目级稳定偏好、协作规则、长期约束可持续累积。
3. 如何在需要时找回过去 session 的具体上下文，而不是把所有旧历史塞进 prompt。

这轮设计前半段的两条思路都被明确否掉：

- 只靠滚动摘要承载记忆。
- 让模型维护一大组结构化 checkpoint 字段。

原因很清楚：

- 摘要不是事实源，容易漂移。
- 多字段 checkpoint 过重，会把简单的续航问题做成一套脆弱的“伪状态机”。

对 `hermes-agent` 的对照分析说明，更稳的做法是把记忆拆成不同职责：

- `MEMORY.md / USER.md` 承载小而硬的长期 curated memory。
- context compression 承载长会话续航。
- `session_search` 承载跨 session 的历史回忆。
- 外部 memory provider 作为更深长期记忆的扩展层。

因此 ReflexionOS 的整体结论是：

- **长期记忆** 不负责 session 续航。
- **续航层** 不负责成为长期事实。
- **回忆层** 不预先注入全部历史，而是按需检索。
- **数据库 transcript** 始终是事实源。

## 2. 设计目标

本设计优先服务 `1 > 2 > 3` 的收敛顺序，即：

1. 先解决当前 session 的连续工作能力。
2. 再解决当前项目下稳定偏好、约束、协作习惯的沉淀。
3. 最后再为全局用户级长期记忆和外部 provider 留扩展位。

具体目标如下：

1. 同一个 session 在切走、关闭应用、重开后仍能恢复工作上下文。
2. 项目级长期记忆可持续累积，并且可审阅、可修改、可追溯。
3. 模型默认不吞整段历史，而是通过分层装配上下文降低 token 压力。
4. 跨 session 回忆依赖 transcript 检索，而不是把 task 历史写进长期记忆。
5. 第一阶段可直接落在当前代码架构上，不要求先重建整套 memory 子系统。
6. 第二阶段可以无缝扩展到用户全局级 memory 和外部 provider。

## 3. 非目标

本轮明确不做以下内容：

- 不做“什么都自动记住”的广义自动长期记忆。
- 不做强依赖 embedding / vector DB 的第一阶段方案。
- 不默认把长期记忆直接写进用户仓库里的 `MEMORY.md` 或 `AGENTS.md`。
- 不把任务进度、完成日志、临时 TODO 当成长久记忆。
- 不在第一阶段解决多用户协作下的复杂记忆冲突治理。
- 不让 continuation artifact 取代 transcript 事实层。

## 4. 设计原则

### 4.1 事实源唯一

用户、assistant、tool、run 相关的原始事实只以数据库 transcript 为准。任何 memory、handoff、summary 都只是派生层。

### 4.2 不同问题，不同层解决

- 长期偏好与规则：`curated memory`
- 长对话续航：`continuation / compaction`
- 历史工作回忆：`transcript recall`

一个层不去偷另一个层的职责。

### 4.3 运行时读取必须极简

存储层可以复杂，但模型运行时只读经过裁剪的 memory context，而不是直接看到底层所有记录。

### 4.4 长期记忆必须可审阅

长期记忆不能只存在于不可见的内部状态里。用户需要知道系统“记住了什么”，并能随时修正或删除。

### 4.5 默认不污染代码仓库

项目级长期记忆应默认放在 ReflexionOS 自己管理的 app data 目录下，而不是直接写进用户仓库。后续可以补“导出/同步到 workspace”的能力，但不是第一阶段默认路径。

### 4.6 用户优先级最高

冲突处理遵循：

1. 当前对话中的用户明确指令
2. 项目指令文件
3. curated memory
4. transcript recall 结果
5. continuation artifact

低层永远不能覆盖高层。

## 5. 总体架构

记忆系统整体采用六层结构：

```text
Instruction Layer
-> Curated Memory Layer
-> Transcript Layer
-> Continuation Layer
-> Recall Layer
-> Provider Seam
```

它们不是并列“都叫 memory”，而是不同职责的上下文部件。

### 5.1 Instruction Layer

这一层是项目的显式指令与规则来源，包含：

- `AGENTS.md`
- `README.md`
- 当前项目长期设计文档
- 未来可能加入的 `.reflexion.md` 一类上下文文件

职责：

- 提供 workspace 级行为约束。
- 作为 prompt 中的高优先级指令来源。
- 不由长期记忆自动写入逻辑维护。

这层是“怎么协作”的主约束，不属于 memory 工具的写入目标。

### 5.2 Curated Memory Layer

这一层承载稳定、长期有效、值得跨 session 保留的记忆，但只限于 curated memory。

第一阶段只保留两类文件视图：

- `MEMORY.md`
  - 项目环境事实
  - 项目约束与约定
  - 工具/流程 quirks
  - 已长期成立的协作规则
- `USER.md`
  - 用户偏好
  - 输出风格要求
  - 反复出现的纠正与禁忌
  - 稳定的工作习惯

默认存储位置采用 app-managed file store：

```text
~/.reflexion/memories/projects/<project_id>/MEMORY.md
~/.reflexion/memories/projects/<project_id>/USER.md
```

后续预留全局级路径：

```text
~/.reflexion/memories/global/USER.md
```

第一阶段中：

- 项目级记忆为主。
- 全局级只预留读取合并与优先级规则，不强推主流程。
- 默认不直接改用户仓库里的文件。

这层的关键约束：

1. 对用户暴露为 Markdown 文件。
2. 对系统内部表现为“有边界的 entry store”，而不是自由增长的长文。
3. 必须支持 `add / replace / remove` 语义，而不是整份文件自由重写。
4. 必须有容量上限与 consolidation 策略，避免变成第二份 transcript。

### 5.3 Transcript Layer

这一层就是当前已经存在的数据库事实源：

- `sessions`
- `turns`
- `runs`
- `messages`
- `conversation_events`

职责：

- 承载真实发生过的交互和执行过程。
- 作为 recall 的唯一原始语料。
- 作为 continuation artifact 的生成输入。

这一层不承担“总结成长期记忆”的职责，也不要求模型读完整层。

### 5.4 Continuation Layer

这一层解决的是“长会话不断片”和“重回同一 session 时如何接上”，而不是长期记忆。

它的产物叫 `continuation artifact`，不是 memory entry。

建议在后端新增独立实体，而不是塞进长期 memory 文件：

- `continuation_artifacts`
  - `id`
  - `session_id`
  - `artifact_type`
  - `based_on_seq`
  - `content_text`
  - `created_at`
  - `superseded_at`

`artifact_type` 第一阶段只需要两类：

- `context_handoff`
- `resume_handoff`

这层的约束：

1. 只服务当前 session。
2. 是低权威、可被后续 artifact 覆盖的运行时产物。
3. 不晋升为长期记忆，除非模型显式写入 curated memory。
4. 生成时必须面向“下一次继续工作”，而不是编写完整历史摘要。

### 5.5 Recall Layer

这一层负责“过去我们有没有做过这个”。

它不预注入所有历史，而是按需检索 transcript，再返回聚焦结果。

第一阶段建议提供类似 `session_search` 的能力：

1. 先对 `messages` 建 FTS 检索能力。
2. 以当前 `project_id` 为默认作用域。
3. 召回匹配 session 的原始片段。
4. 返回“精确片段 + 聚焦总结”的组合结果。

这层处理的是：

- 跨 session 的任务历史
- 以前修过的 bug
- 做过的设计选择
- 某次对话里提到但不适合放进长期记忆的细节

这层不是长期 memory，也不是 context compaction。

### 5.6 Provider Seam

这一层不是第一阶段主能力，而是扩展缝。

它允许第二阶段接入：

- Honcho
- Hindsight
- Mem0
- 其他外部长期记忆后端

扩展原则：

1. provider 只能是加法，不替代本地 transcript。
2. provider 只能增强 recall / profiling / semantic memory，不接管项目指令层。
3. provider 写回不能绕过用户优先级与本地 curated memory 审阅机制。

## 6. 权威性与冲突模型

不同层之间的权威性顺序如下：

1. 当前用户显式指令
2. 项目指令文件（如 `AGENTS.md`）
3. 项目级 `USER.md / MEMORY.md`
4. 全局级 `USER.md`
5. transcript recall 返回的历史事实
6. continuation artifact

解释：

- `AGENTS.md` 约束的是 workspace 行为规则，因此比 memory 更高。
- `USER.md / MEMORY.md` 承载的是长期稳定结论，因此比 recall 更高。
- recall 结果可以提供证据，但不能自动改写 curated memory。
- continuation artifact 只服务续航，因此权重最低。

冲突处理规则：

1. 若用户当前回合明确推翻旧记忆，以当前用户输入为准。
2. 若 curated memory 与 recall 历史冲突，以 curated memory 为当前默认结论，但需要保留 recall 作为证据来源。
3. 若项目指令文件与 memory 冲突，以项目指令文件为准。

## 7. 运行时读路径

### 7.1 正常新回合

默认上下文装配顺序：

1. system prompt
2. Instruction Layer
3. 项目级 curated memory snapshot
4. 全局级 `USER.md` snapshot（若存在）
5. 当前 session 的最近 continuation artifact（若存在）
6. 当前 session 最近的精确 transcript window
7. 当前用户输入

关键约束：

- 默认不自动注入跨 session recall 结果。
- 默认不自动把旧 session 全量历史塞进 prompt。
- recall 只在需要时由工具显式触发。

### 7.2 恢复已存在 session

当用户重新打开某个 session 时：

1. 从数据库恢复该 session 的 `snapshot + events`。
2. 重新读取项目级 curated memory snapshot。
3. 若该 session 存在未过期的 continuation artifact，则一并装配。
4. 再附加最近精确 transcript window。

因此“恢复 session”依赖的不是一份长摘要，而是：

- 原始事实层
- 最新 handoff
- 长期 curated memory

### 7.3 上下文接近阈值时

当上下文压力过高时，不直接把旧消息粗暴截断，而执行：

1. `curated memory review`
   - 让模型在仅开放 memory 写入工具的情况下，判断是否有值得晋升的长期记忆。
   - 只允许写稳定偏好、长期约束、持久规则。
2. `context compaction`
   - 对将被压缩/折叠的消息生成 `context_handoff` continuation artifact。
3. 保留最近精确窗口。

这一步的核心目标不是写摘要归档，而是：

- 先把该晋升的长期信息晋升出去。
- 再为当前 session 留一个可继续接力的 handoff。

### 7.4 跨 session 回忆

当用户说出如下意图时，优先触发 recall：

- “上次我们做过这个”
- “之前是不是修过类似问题”
- “你还记得那个设计吗”
- “我们上周怎么处理的”

流程：

1. 先在当前项目的 transcript 中检索。
2. 返回匹配 session 的精确片段。
3. 对片段做聚焦总结。
4. 将 recall 结果作为临时上下文块注入当前回合。

这一步是按需 recall，不写入长期 memory，除非模型或用户随后明确要求。

## 8. 写路径与触发策略

### 8.1 Curated Memory 写入

第一阶段建议只保留三种写入触发：

1. 用户显式要求“记住这个”
2. 当前回合出现高置信度稳定偏好/约束/纠正
3. compaction 前的 `curated memory review`

不做以下激进策略：

- 每轮自动写 memory
- 大量后台抽取 facts
- 自动把任务进度写进 memory

第一阶段的 memory 工具只处理：

- `add`
- `replace`
- `remove`

不开放“自由重写整份 memory 文件”的模式。

### 8.2 Transcript 写入

继续沿用现有 `ConversationEvent -> Projection` 持久化路径。

记忆系统不会改写 transcript 真相，只会消费 transcript。

### 8.3 Continuation Artifact 写入

第一阶段只在以下时机写 continuation artifact：

1. context compaction 前后
2. 用户离开 session、系统需要生成 resume handoff 时

不在每个 turn 都写，不把它升级成新的事实源。

### 8.4 Recall 结果写入

recall 结果默认只作为临时上下文，不自动落长期记忆。

只有满足以下条件时才允许晋升：

- 用户明确确认该结论长期有效
- 或模型在 compaction review 中有足够证据且写入目标属于稳定规则

## 9. 第一阶段落地范围

第一阶段只做最小闭环：

1. 项目级 app-managed `MEMORY.md / USER.md`
2. 当前 session 的 continuation artifact
3. transcript recall（默认按项目 scope）
4. 运行时 memory assembly
5. provider seam 的接口预留

第一阶段不做：

- 用户全局级自动记忆主流程
- provider 的真实接入
- embeddings / rerank / graph memory
- memory UI 编辑器的完整产品化
- 仓库内 `MEMORY.md` 双向同步

## 10. 对当前代码的映射

这套设计与当前代码的对应关系如下：

### 10.1 可直接复用的部分

- `ConversationService` 已经提供稳定的会话事实读写。
- `ConversationSnapshot` 已经足以恢复 session 当前长期可见状态。
- `messages + conversation_events` 已经是 recall 的天然原始语料。
- `~/.reflexion/` 已经存在数据库和配置目录，可作为 memory 文件默认根目录。

### 10.2 需要新增的部分

- `backend/app/memory/` 的正式源码与服务边界
- curated memory store
- continuation artifact store
- transcript recall service / FTS index
- prompt assembly 中的 memory layering

### 10.3 需要替换的思路

当前 `RapidExecutionLoop` 主要依赖最近消息组回放，这还不是完整的 memory assembly。后续应把“只取最近消息”改成“分层装配上下文”。

## 11. 为什么这版更稳

这版方案比“统一摘要型记忆系统”更稳，原因有三点：

1. 它不要求摘要承担事实源职责。
2. 它不要求模型每回合维护沉重的状态字段。
3. 它把真正长期有效的东西，和只服务当前 session 的东西彻底分开了。

最终效果应该是：

- 模型在同一个 session 里更不容易断片。
- 用户的稳定偏好和协作习惯会逐步沉淀。
- 过去做过的事情可以按需找回。
- 系统扩展到 Honcho / Hindsight 时不需要推翻本地架构。

## 12. 下一步

这份文档之后，下一步应单独产出一份 Phase 1 实施计划，重点拆解：

1. curated memory store 的文件格式与服务接口
2. continuation artifact 的数据模型与生成时机
3. transcript recall 的检索接口与返回协议
4. `RapidExecutionLoop` / prompt assembly 的接入改造
5. 最小 UI / API 暴露面
