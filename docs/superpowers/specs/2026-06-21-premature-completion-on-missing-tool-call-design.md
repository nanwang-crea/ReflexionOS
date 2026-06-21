# 对话在缺失工具调用时被过早结束的设计说明

**日期**: 2026-06-21  
**状态**: 设计阶段  
**作者**: Codex

## 背景

当前桌面端存在一类高频失败场景：模型在准备读取文件或切换调查手段时，先输出一段说明性文本，例如“读取失败，我改用 shell 看看”，但这一轮并没有真正发出工具调用。运行时随后把这段文本当作最终答案，直接结束本次会话。

从用户视角看，症状是“对话读取失败后就结束了”；从系统视角看，症状是“模型明明还处于探索/排查中，但 loop 已经进入 `COMPLETED`”。

这个问题会让产品表现出明显的假完成：

- 代理没有真正读取文件、执行命令或继续调查。
- UI 已经停止流式更新，用户只能手动再次发起一轮对话。
- 模型产生的“下一步打算”被误判为“最终交付结果”。

## 复现方式

一个稳定复现路径如下：

1. 用户提出需要代码排查或文件读取的任务。
2. 模型首轮响应没有发出合法 `tool_calls`，而是先输出说明性文本。
3. 文本内容类似“我先读文件”“读取失败后我改用 shell”“我继续检查一下”。
4. 后端 loop 认为这是合理停止，直接将状态置为 `COMPLETED`。

这类现象尤其容易出现在以下组合下：

- 模型使用了当前未暴露给它的工具名。
- 模型说的是“准备执行某个动作”，但没有形成真实工具调用。
- 首轮仍处于 exploration 阶段，可用工具集合比完整执行阶段更窄。

## 观察到的行为

- 前端看到 assistant 给出了一段过程性说明。
- 后端没有执行任何工具。
- 会话立即结束，没有二次追问、没有重试、没有工具 fallback。

## 期望行为

如果模型还没有执行过任何工具，而当前任务明显属于“需要继续探索 / 读取 / 调用工具”的类型，那么以下文本不应被当作最终完成：

- 行动意图
- 工具切换说明
- 失败后的调查计划
- “我接下来会……”这类过程性回复

系统应当在这类场景中继续推进执行，而不是直接结束。至少应满足以下之一：

- 重新提示模型发出合法工具调用。
- 将本轮判定为“未完成，需要继续规划”。
- 允许 runtime 对常见工具别名做纠错或兼容映射。

## 根因分析

### 1. `RapidExecutionLoop` 在“未执行过工具”时对纯文本停止过于宽松

`backend/app/execution/rapid_loop.py` 的 planning 阶段会先根据模型响应分流：

- 如果有 `tool_calls`，进入工具执行。
- 如果没有 `tool_calls`，调用 `_validate_stop_decision()`。

对应代码位置：

- [backend/app/execution/rapid_loop.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/rapid_loop.py:150)
- [backend/app/execution/rapid_loop.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/rapid_loop.py:156)

真正导致过早结束的是 `_validate_stop_decision()` 内的这段逻辑：

- 当 `not rt.has_executed_tools`
- 且 `rt.response.has_content`
- 就直接设置 `LoopStatus.COMPLETED`

对应代码位置：

- [backend/app/execution/rapid_loop.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/rapid_loop.py:177)
- [backend/app/execution/rapid_loop.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/rapid_loop.py:180)

这意味着系统当前默认认为：

> 只要模型还没调过工具，但返回了文本，那么这段文本就可以视为最终答案。

这个假设只适用于真正的纯问答场景，不适用于“明显需要继续操作”的 agent 任务。

### 2. 首轮 exploration 暴露的工具集合与模型习惯表达存在错位

`backend/app/execution/runtime_tool_definitions.py` 中，探索阶段工具集由 `exploration_tools` 控制。当前默认集合包含：

- `file`
- `grep`
- `glob`
- `memory`
- `session_recall`
- `skill`

对应代码位置：

- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:28)
- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:38)

而 `shell` 虽然在整体工具顺序里存在，但在首轮 exploration 中默认不会暴露：

- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:16)
- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:26)
- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:104)
- [backend/app/execution/runtime_tool_definitions.py](/C:/Users/ethan1.zhao/Desktop/xiangmu/ReflexionOS/backend/app/execution/runtime_tool_definitions.py:109)

这会带来两个实际问题：

- 模型可能口头说“改用 shell”，但当前阶段其实没有 `shell` 可用。
- 模型和工具 schema 的命名不一致时，容易出现“口头描述动作，但没有形成合法 tool call”的响应。

### 3. 这是 runtime 容错不足，不只是模型质量问题

如果问题只归因于“模型没调对工具”，那产品层面就没有防线了。但 agent runtime 的职责之一，本来就是在模型返回不完美决策时做执行层兜底。

当前系统在下面这条链路上缺少保护：

1. 模型返回了非最终性的过程文本。
2. runtime 没有识别这是一段“未完成动作”。
3. runtime 直接结束，而不是重试、纠正或要求明确工具调用。

因此，这个问题应定义为：

- **模型可能触发**
- **但由 runtime 设计放大**
- **最终表现为产品缺陷**

## 影响范围

该问题会影响所有依赖首轮探索的任务类型，特别是：

- 读文件
- 搜索代码
- 排查报错
- 工具切换
- 多步调查任务

受影响的不是单一模型，而是所有可能先输出“我去做 X”再补工具调用的模型。

## 设计目标

修复方案需要同时满足以下目标：

- 避免把过程性文本误判为最终答案。
- 不破坏真正的纯问答场景。
- 尽量减少对现有 loop 状态机的侵入。
- 让“工具未调用但任务显然未完成”的情况有明确兜底路径。

## 方案选项

### 方案 A：收紧首次纯文本停止条件

思路：

- 当 `not rt.has_executed_tools and rt.response.has_content` 时，不再直接 `COMPLETED`。
- 先判断当前请求是否属于需要工具推进的 agent 任务。
- 如果文本更像“行动说明”而不是“最终交付”，则回到 planning 并附加纠正提示。

优点：

- 改动集中在 `rapid_loop.py`。
- 直接针对当前错误分支。
- 不依赖具体工具名。

缺点：

- 需要定义“什么叫过程性文本”，会有启发式判断。
- 纯文本问答和 agent 执行的边界需要拿捏。

### 方案 B：为首次无工具响应增加一次强制重试

思路：

- 如果首轮没有 `tool_calls`，且任务上下文看起来需要工具，则不给 `COMPLETED`。
- 给模型补一条系统约束，例如“不要描述你将做什么，直接发出合法工具调用；如果无法继续，请明确说明已完成的最终答案”。
- 允许 1 次到 2 次纠正重试。

优点：

- 不需要复杂语义分类。
- 更符合“LLM 决策层纠偏”的设计。

缺点：

- 增加一次模型调用。
- 如果工具暴露本身不合理，重试仍可能失败。

### 方案 C：扩展 exploration 工具暴露并补工具别名兼容

思路：

- 让 exploration 阶段也能暴露 `shell`。
- 对高频别名做兼容，例如把模型常见的文件读取表达映射到实际工具。

优点：

- 减少“想做但做不了”的错位。
- 提升首轮探索成功率。

缺点：

- 不能单独解决“口头说要做但没发 tool call”的问题。
- 扩大初始工具集会提高决策复杂度与误用风险。

### 方案 D：组合方案

推荐将 A + B 作为主修复，C 作为增强项分开评估。

原因：

- A 解决“过早结束”的状态机缺陷。
- B 解决“首次响应不规范”的纠偏问题。
- C 只提高成功率，不足以作为主修复。

## 推荐方案

推荐分两步实施：

### 第一步：修正首次无工具响应的停止策略

在 `RapidExecutionLoop._validate_stop_decision()` 中新增保护：

- 若从未执行过工具，且当前上下文更像 agent 任务而非纯问答，则不能仅凭 `has_content` 就结束。
- 优先进入一次纠正重试，而不是直接 `COMPLETED`。

建议判定信号：

- 当前存在 project/workspace 上下文。
- 可用工具集合非空。
- 用户请求明显包含“看文件 / 查代码 / 修复 / 搜索 / 排查”等动作型意图。
- 模型文本包含“我先 / 我去 / 我接下来 / 我改用 / 我会继续 / let me / I'll / first”等过程性信号。

### 第二步：为首轮纠偏补充明确指令

在重试提示中要求模型二选一：

- 发出合法工具调用。
- 如果确实无需工具，则直接给出最终结论，不要描述计划。

示例约束方向：

> 如果你需要读取文件、搜索代码或执行命令，请直接调用工具，不要只描述你将执行什么动作。只有在任务已经完成时，才返回最终答案。

### 可选增强：重新评估 exploration 工具集

后续可以单独评估：

- 是否在 exploration 阶段暴露 `shell`
- 是否增加工具别名层或 schema 提示
- 是否在 prompt 中显式强调真实工具名是 `file` 而不是泛化的“read_file”

## 验收标准

修复后至少应满足以下验收条件：

1. 当模型首轮输出“我先读文件 / 我改用 shell 看看”但没有工具调用时，会话不会直接结束。
2. runtime 会触发一次纠偏重试，或者进入继续规划，而不是 `COMPLETED`。
3. 真正的纯问答任务仍然可以在首轮纯文本正常结束。
4. 首轮 exploration 的工具可用性与 prompt 指导保持一致，不再明显诱发错误动作描述。
5. 前端不会再出现“assistant 说要继续调查，但后端已结束”的体验断裂。

## 测试计划

建议补以下测试：

### 单元测试

文件建议：

- `backend/tests/test_execution/test_rapid_loop.py`
- 如需拆分，也可新增针对 stop decision 的专门测试文件。

核心用例：

1. **首轮纯文本且为过程说明**
   - 输入：无 `tool_calls`，`has_content=True`，内容是“我先读取文件看看”
   - 期望：不进入 `COMPLETED`

2. **首轮纯文本且为最终回答**
   - 输入：无 `tool_calls`，`has_content=True`，内容是明确最终答案
   - 期望：允许 `COMPLETED`

3. **首轮无工具响应后重试成功**
   - 第一次返回过程性文本
   - 第二次返回合法 `tool_calls`
   - 期望：进入工具执行

4. **已有工具执行后的正常完成不受影响**
   - 输入：`has_executed_tools=True` 且模型给出总结
   - 期望：仍可正常结束

### 集成测试

建议增加一个端到端或近集成测试，模拟：

- 用户要求“看一下某个文件为什么失败”
- 模型第一轮先输出“读取失败，我改用 shell”
- runtime 不应结束，而应继续推进

## 风险与注意事项

- 如果判定条件过于激进，可能误伤真正的纯问答任务。
- 如果只增加重试、不改停止条件，某些边界场景仍可能直接结束。
- 如果直接扩大 exploration 工具集，可能引入新的权限和误调用问题。

因此，主修复应优先落在“停止条件”和“首次纠偏”上，而不是单独放宽工具暴露。

## 结论

本问题的本质不是“模型偶尔说错一句话”，而是 runtime 把“未完成的行动说明”当成了“最终答案”。

只要这个状态机判断不改，模型哪怕只是短暂偏离最佳工具调用路径，也会被产品层放大成“对话突然结束”。因此，后续修复应优先修改 `RapidExecutionLoop` 的首次停止策略，并为首轮无工具响应增加一次明确的纠偏路径。
