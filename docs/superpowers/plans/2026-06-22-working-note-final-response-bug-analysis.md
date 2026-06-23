# working_note 吞掉最终回答问题分析与修复方案

## 1. 问题背景

本次分析针对以下实际问题：

- 用户观察到“有一个回答结果出现在思考过程里，而不是正式回答区”
- 对应会话：
  - `session-fb01ea46b3c9`
  - `turn-e15942a902ea`
  - `run-a4c218b5d4f9`
- 发生时间：
  - `2026-06-21 22:14:30` 到 `2026-06-21 22:26:46`

相关代码位置：

- `backend/app/services/conversation_runtime_adapter.py`
- `backend/app/execution/rapid_loop.py`
- `backend/app/tools/plan_tool.py`

相关数据来源：

- 外部数据库 `reflexion.db`
- 该 turn 的 `messages`、`runs`、`turns` 记录

---

## 2. 问题现象

### 2.1 用户可见现象

用户应该看到一条正式的 assistant 最终答复，但实际看到的是：

- 大段完整回答内容出现在思考区
- 正式回答区没有对应的最终消息

通俗理解：

- 系统已经“写出了答案”
- 但没有把它作为最终回答提交给用户
- 而是把它错误地记成了执行过程中的工作笔记

### 2.2 数据层现象

在 `turn-e15942a902ea` 中：

- 总消息数：`77`
- assistant 消息数：`24`
- 这 `24` 条 assistant 消息全部是 `display_mode='working_note'`
- 没有任何一条 `display_mode='default'` 的 assistant 最终消息

其中后段存在明显已经是正式答复内容的 assistant 消息，例如：

- `msg-bba53a97f59a`
- `msg-8f9686eb7c76`

这两条内容已经不是简短思考，而是完整评审报告，但依然被保存为 `working_note`。

### 2.3 时序层现象

该 turn 最后一个 tool trace 的完成时间：

- `2026-06-21 22:26:46.938767`

run 完成时间：

- `2026-06-21 22:26:46.938796`

turn 完成时间：

- `2026-06-21 22:26:46.938796`

差值只有：

- `0.029 ms`

这说明最后一个 tool 完成后，run 几乎立刻结束，没有再经历一次有效的“最终答复落库”过程。

---

## 3. 相关名词说明

### 3.1 session

一个完整聊天会话，相当于一个聊天窗口。

### 3.2 turn

会话中的一轮交互，一般对应“用户发一次消息，系统处理并回复”的整轮过程。

### 3.3 run

某一轮 turn 的一次实际执行过程，内部会经过：

- LLM 推理
- 工具调用
- 状态更新
- 最终收尾

### 3.4 working_note

表示中间工作笔记、阶段性输出、执行过程中的临时内容。

它本意不是最终答复。

### 3.5 default

表示正式展示给用户的默认 assistant 消息模式。

用户最终应该看到的是 `default` 模式的 assistant 消息。

### 3.6 plan_tool

不是最终回答工具，而是计划管理工具，用来：

- 创建计划
- 更新步骤状态
- 标记完成/阻塞
- 驱动多步骤任务执行

---

## 4. 本次问题的直接结论

本次问题的本质不是“模型没有回答”，而是：

1. 模型在执行过程中已经生成了很像最终答复的大段内容
2. 这些内容在下一个 tool 开始前，被系统落成了 `working_note`
3. 随后 run 很快结束
4. 结束时没有再补一条 `default` 的最终 assistant 消息

因此用户看到的结果是：

- 正式答案“掉进了思考过程”
- 最终答复区为空

---

## 5. 根因分析

## 5.1 plan_tool 不是根因，但暴露了执行链不稳定

`backend/app/tools/plan_tool.py:192`

`_parse_steps()` 要求：

- `steps` 必须是数组

但本次首个失败的 `plan` 调用中，模型传入的是：

- JSON 字符串形式的 `steps`

因此报错：

- `steps must be an array`

这说明模型在该 run 中的工具调用格式并不稳定，但这不是“最终回答掉进 working_note”的直接根因。

### 5.2 第一层根因：中间内容在 tool 边界被刷成 working_note

`backend/app/services/conversation_runtime_adapter.py:614`

`_assistant_segment_events()` 的行为是：

- 只要当前有 assistant 内容
- 且下一个 `tool:start` 到来
- 就把当前 assistant 内容创建成一条消息
- 且固定写成 `display_mode="working_note"`

关键点在于：

- 这里没有区分“这段内容只是中间思考”还是“这段内容已经像最终回答”
- 因此大段完整答复也会被无条件落成 `working_note`

### 5.3 第二层根因：working_note 刷出后，assistant 终态上下文被清空

同一个函数在写完 segment 后会清理内部状态：

- `self.assistant_message_id = None`
- `self._assistant_content = ""`
- `self._assistant_reasoning = ""`

这意味着：

- 当前 assistant 输出已经被当成一个“阶段性片段”处理完毕
- 后续 `run:complete` 如果没有新的 assistant 缓冲内容，就无法继续将其升级为正式最终消息

### 5.4 第三层根因：run 完成时 `_assistant_terminal_events()` 直接短路

`backend/app/services/conversation_runtime_adapter.py:566`

`_assistant_terminal_events()` 一开始就有如下条件：

- 如果 `assistant_message_id is None`
- 或该消息已经是 terminal
- 则直接返回空列表

这在本次场景下的后果是：

1. 前面 `_assistant_segment_events()` 已经把内容刷成了 `working_note`
2. 并且清掉了 `assistant_message_id`
3. 最后 `run:complete` 到来时
4. `_assistant_terminal_events()` 发现 `assistant_message_id is None`
5. 于是直接 `return []`
6. 因而没有创建任何 `default` 的最终 assistant 消息

### 5.5 第四层现象：RapidExecutionLoop 没能补出最终 summary

`backend/app/execution/rapid_loop.py:159`

`_validate_stop_decision()` 的设计本意是：

- 如果执行过工具但没有最终内容
- 应进入 `FINAL_SUMMARY`

`backend/app/execution/rapid_loop.py:578`

`_handle_final_summary()` 会尝试获取最终总结。

但从本次数据库结果看，最终没有落出 `default` assistant 消息，说明至少存在以下一种情况：

- 最终 summary 没有产出新的 assistant content
- 或产出的 content 在后续又被当作 segment 刷成了 `working_note`
- 或 run 收尾过快，没有形成可持久化的最终答复消息

无论具体是哪种，最终表现一致：

- `default` assistant 最终消息缺失

---

## 6. 问题形成的完整链路

可简化为以下时序：

1. 用户发起一个多步骤任务
2. 系统进入有计划执行模式
3. 模型多次调用 `plan/file/edit` 等工具
4. 执行过程中，模型已经生成出较完整的回答内容
5. 下一个 `tool:start` 到来
6. `ConversationRuntimeAdapter._assistant_segment_events()` 将该内容落成 `working_note`
7. 适配器内部 assistant 状态被清空
8. 后续工具继续执行
9. 最后一个工具刚结束，run 立即完成
10. `ConversationRuntimeAdapter._assistant_terminal_events()` 因 `assistant_message_id is None` 直接返回空
11. 最终没有 `default` assistant 消息
12. 用户只看到了思考区中的“答案”

---

## 7. 修复目标

修复后必须满足以下目标：

1. 即使执行过程中出现 tool 边界切换，也不能丢失最终答复
2. `working_note` 与最终答复必须明确分离
3. run 完成时必须保证存在可落库的 `default` assistant 终态消息，除非本轮确实没有任何回答内容

---

## 8. 修复方案

### 方案 A：最小止血方案

修改 `conversation_runtime_adapter._assistant_terminal_events()`：

- 当 `assistant_message_id is None` 时，不要立刻返回空
- 如果此时 `_assistant_content` 或 `_assistant_reasoning` 非空：
  - 新建一个 assistant message
  - 使用 `display_mode='default'`
  - 补发 `MESSAGE_CONTENT_COMMITTED`
  - 补发 `MESSAGE_COMPLETED`

#### 优点

- 改动小
- 风险低
- 可以立即避免“完全没有最终答复”

#### 缺点

- 只能兜底
- 不能解决“本该是正式答复的内容先被写成 working_note”的分类错误

### 方案 B：根因修复方案

修改 `conversation_runtime_adapter._assistant_segment_events()`：

- 不要在每次 `tool:start` 时无条件把当前 assistant 内容刷成 `working_note`

可选策略：

1. 仅当内容明显属于中间说明时，才写成 `working_note`
2. 对接近完整答复的内容，保留到 `run:complete` 再终态化
3. 至少不要在 segment 刷出后立刻清空全部 assistant 终态状态

#### 优点

- 能解决“答案被归类到思考区”的根因
- `working_note` 与最终答复职责更清晰

#### 缺点

- 改动行为模型更大
- 需要补更多测试覆盖边界场景

### 方案 C：推荐落地方案

采用“两层修复”：

1. 先实现方案 A，确保不会再丢最终答复
2. 再实现方案 B，纠正 `working_note` 与 `default` 的分类逻辑

推荐原因：

- 先止血，再治本
- 风险可控
- 便于分阶段验证

---

## 9. 具体修改建议

### 9.1 conversation_runtime_adapter.py

重点修改：

- `_assistant_terminal_events()`
- `_assistant_segment_events()`

建议调整：

1. `_assistant_terminal_events()` 增加兜底建消息逻辑
2. `_assistant_segment_events()` 重新审视 `display_mode="working_note"` 的触发条件
3. 避免在 segment 刷出后无条件清空所有 assistant 终态上下文

### 9.2 rapid_loop.py

重点检查：

- `FINAL_SUMMARY` 阶段是否真正产生了新的 assistant 输出
- `run:complete` 与最后 tool 完成之间是否存在过快收尾导致的竞态

这里不一定要改主逻辑，但需要确认：

- final summary 产物能否稳定流入 conversation runtime adapter

### 9.3 测试用例

需要新增回归测试，至少覆盖以下场景：

#### 场景 1：assistant 内容在 tool:start 前已存在

步骤：

1. 产生一段 assistant content
2. 触发 `tool:start`
3. 再触发 `run:complete`

断言：

- 最终必须存在一条 `display_mode='default'` 的 assistant 消息

#### 场景 2：中间 working_note + 最终 default 共存

断言：

- 中间说明可以保留为 `working_note`
- 最终总结必须单独存在为 `default`

#### 场景 3：没有任何 assistant 内容时 run:complete

断言：

- 不应凭空创建空的默认消息

#### 场景 4：summary 阶段直接产出最终内容

断言：

- 最终内容不能再被错误刷成 `working_note`

---

## 10. 风险与注意事项

### 10.1 风险 1：working_note 数量减少或行为变化

修复后某些原本会被写成 `working_note` 的内容，可能改为延迟到最终消息中出现。

这属于预期变化，但需要确认前端是否依赖旧行为。

### 10.2 风险 2：重复消息

如果兜底补 final message 的逻辑处理不好，可能出现：

- 一份内容先以 `working_note` 保存
- 又被重复生成一份 `default`

因此实现时需要避免简单复制整段内容。

### 10.3 风险 3：前端展示逻辑与后端消息语义不一致

即使后端修好了，如果前端把 `working_note` 也当“正式答复内容”渲染，仍可能造成认知混乱。

因此修复后需要联动确认前端消息分区语义。

---

## 11. 建议实施顺序

### 第一阶段

仅做兜底修复：

- 保证 run 结束时不会丢失最终答复

### 第二阶段

修正 `working_note` 的刷出逻辑：

- 保证正式回答不再混入思考区

### 第三阶段

补充回归测试并验证前端展示：

- 确保后续不会复发

---

## 12. 最终结论

本问题的核心不是模型没回答，而是消息分类与收尾逻辑存在缺陷：

- 本该作为最终答复的内容
- 在 tool 边界被提前落成了 `working_note`
- 之后 run 收尾时又因为 `assistant_message_id` 已被清空
- 导致没有生成 `default` 的最终 assistant 消息

因此修复重点应放在：

1. run 完成时的最终消息兜底
2. `working_note` 与正式答复的边界重构

在文档评审通过前，本次只提交分析与方案，不改代码。
