# Mid-Run Context Compaction 设计

> 日期: 2026-05-22
> 状态: Draft
> 关联: `docs/superpowers/specs/2026-04-28-agent-memory-overall-design.md` 第 7.3 节

## 1. 问题

`RapidExecutionLoop` 在单个 run 中，`context.messages` 只增不减。`LoopMessageBuilder.recent_context_messages()` 仅保留最后 10 组消息（`MAX_CONTEXT_GROUPS=10`），超出窗口的消息被硬截断丢弃。当 agent 在一个 run 中执行大量文件读取后：

1. **原始用户输入被截断丢弃**——最早的 user message 不在最近 10 组中
2. **10 组消息本身 token 超限**——大文件输出使窗口内消息总 token 仍超出 model context limit
3. **被截断的消息无法回溯**——agent 不知道自己不知道什么，也无法按需取回丢失的细节

设计规范 7.3 节要求"上下文接近阈值时先做 curated memory review，再做 context compaction，保留最近精确窗口"，但当前未实现任何运行时压缩机制，也无回溯能力。

## 2. 设计目标

1. 原始用户输入（task）始终不被截断——作为不可丢弃的 anchor
2. 运行中实时感知 token 压力，超阈值自动触发逐级压缩
3. 压缩是渐进式的：每条消息始终可见但精度递减，而非整组丢弃——agent 始终知道"发生过什么"
4. agent 可通过 Recall Tool 从 DB 按需取回被截断的完整内容——摘要提供地图，recall 提供细节
5. 压缩失败不阻塞执行循环——降级为现有截断行为
6. mid-run 压缩产出的摘要可被 post-run continuation 复用

## 3. 方案选型

| 方案 | 核心思路 | 优点 | 缺点 |
|------|----------|------|------|
| A: LoopContext 内压缩 | 压缩状态内聚在 LoopContext，add_message 后检测压力 | 改动可控，与现有逻辑复用度高 | LoopContext 职责变重 |
| B: LoopMessageBuilder 层压缩 | 仅在 build() 中做动态压缩 | 改动集中一个文件 | Builder 职责过重，无缓存 |
| C: 独立 ContextCompactor 服务 | 新建 Compactor 类作为中间层 | 职责最清晰 | 新增抽象层，间接多 |

**选定方案 A**：压缩状态与消息积累天然同处 LoopContext，不需要额外传参，与 ContinuationArtifactBuilder 复用自然。

## 4. 三级上下文模型

核心设计原则：**不是"丢弃旧组"，而是"每条消息始终可见，但精度递减"**。类似操作系统的虚拟内存：内存（context）放最近用的，磁盘（DB）放全部，缺页（recall）时按需加载。

```
Tier 1: 完整保真 —— 最近 N 组，原文不改（现有行为）
Tier 2: 截断但可见 —— 超出窗口的旧消息，逐条截断，每条仍在 context 中
Tier 3: LLM 摘要 + Recall 回溯 —— 极端压力时旧消息压缩为摘要，细节可 recall 取回
```

递进关系：

```
完整原文 → 自动截断(始终可见) → LLM摘要(压力极大时) → 全部可 recall 回溯
```

三级之间不是替代关系，而是**渐进取舍**：优先保证可见性，其次保证精度，最后保证整体不超限。

## 5. 详细设计

### 5.1 Task Anchor 注入

**问题：** 原始用户输入只存在于 `context.messages` 中，被 `recent_context_messages()` 的窗口截断。

**方案：** 在 `LoopMessageBuilder.build()` 中将 `context.task` 原文作为一条 `user` role 消息始终注入，不做任何格式化包装。位置在 context sections 之后、Tier 2/3 内容之前。

**消息构建顺序：**
```
[0]   System prompt（工具定义）
[1..N] Context sections（AGENTS.md, USER.md, MEMORY.md）→ system
[N+1] Supplemental context（continuation artifact）→ system
[N+2] Plan context（如有）→ system
[N+3] Task Anchor → user，内容 = context.task 原文，不可截断
[N+4] Tier 3 Compacted Summary → system（如有，仅极端压力时）
[N+5..K] Tier 2 截断消息（超出窗口的旧消息，逐条可见但截断）
[K+1..M] Tier 1 Recent context messages（last 10 groups，完整原文）
```

**去重：** `recent_context_messages()` 中跳过 content 等于 `context.task` 的 user 消息（可能不止一条，如用户重复发送相同指令），避免窗口内出现与 Task Anchor 重复的原始输入。

### 5.2 实时 Token 压力检测

**新增 `backend/app/llm/token_counter.py`：**
- 封装 tiktoken，按 model encoding 名计数
- 提供 `count_tokens(text: str, model: str) -> int` 和 `count_messages_tokens(messages: list[dict], model: str) -> int`

**`LoopContext` 新增字段：**
- `total_tokens: int = 0`——每次 `add_message()` 累加新消息的 token 数
- `compacted_summary: str | None = None`——Tier 3 摘要缓存
- `group_count: int = 0`——消息分组计数

**`ExecutionSettings` 新增配置：**
- `tier2_truncate_threshold_tokens: int = 50_000`——触发 Tier 2 逐条截断的阈值
- `tier3_compact_threshold_tokens: int = 100_000`——触发 Tier 3 LLM 摘要的阈值
- `tool_output_max_chars: int = 2_400`——Tier 2 中 tool output 的最大字符数

**触发逻辑（`_call_llm()` 前检查）：**
- `total_tokens > tier2_truncate_threshold_tokens` → 对窗口外消息执行 Tier 2 逐条截断
- `total_tokens > tier3_compact_threshold_tokens` → 在 Tier 2 基础上进一步执行 Tier 3 LLM 摘要压缩
- `group_count > 2 * MAX_CONTEXT_GROUPS`（20 组）→ 双保险，触发 Tier 2

### 5.3 Tier 2：逐条截断但始终可见

**核心思路：** 超出窗口的旧消息**不整组丢弃**，而是逐条缩短后保留在 context 中。agent 始终能看到"我读过 foo.py，发现了 X"，只是完整文件内容被截断了。

**截断规则：**

| 消息类型 | 截断策略 | 截断后标记 |
|----------|----------|------------|
| tool output | head+tail 截断至 `tool_output_max_chars`（复用 `truncate_head_tail()`） | `...[N chars 省略, 可 session_recall 取回]` |
| assistant message | 不截断（通常不长） | — |
| user message | 不截断（用户原话必须保留） | — |
| system notice | 截断至 `tool_output_max_chars` | 同 tool output |

**实现方式：** `LoopMessageBuilder` 中新增 `_build_tier2_messages(context)` 方法：
1. 对 `context.messages` 中窗口外的消息逐条应用截断规则
2. 返回截断后的消息列表，每条消息都是一条独立的 `system` 消息（角色改为 system 以区分于 Tier 1 的原始角色）

**关键约束：** 截断是幂等的——对同一条消息多次截断结果相同。截断不修改 `context.messages` 原始数据，仅在 `build()` 时派生。

### 5.4 Tier 3：LLM 摘要压缩

**触发时机：** Tier 2 截断后 token 量仍超 `tier3_compact_threshold_tokens`。

**关键约束：** 压缩 LLM 调用使用独立的 `llm.complete()`（非流式、无 tools），**不走 `_call_llm()` 流程**，避免递归触发压力检测。

**压缩流程：**

1. **将 Tier 2 的截断消息作为压缩输入**——复用 `ContinuationArtifactBuilder._build_items()` 和 `_fit_global_budget()` 的逻辑
2. **调用 LLM 生成摘要**——使用 `midrun_compress_system` prompt 模板，产出格式更丰富
3. **压缩结果存入 `LoopContext.compacted_summary`**
4. **修改 `context.messages`：** 将窗口外的旧消息从 `context.messages` 中移除，在 messages 开头插入一条 system 消息：`[已压缩的历史上下文] {compacted_summary}`。这是不可逆的——但 `context.steps` 和 `context.history` 仍保留完整审计记录，且 DB 中的原始 messages 不受影响，agent 可通过 session_recall tool 取回
5. **遍历 messages 重新累加 `total_tokens`**

**摘要格式（5 行 + 引用标记）：**
```
用户原始意图: {原文关键部分}
已执行的操作:
  - 读取了 src/foo.py, src/bar.py [可 session_recall 取回完整内容]
  - 执行了 npm test [可 session_recall 取回完整输出]
已确认的发现: {重要发现}
当前进度: {进行到哪一步}
未解决的问题: {仍需处理的点}
```

`[可 session_recall 取回完整内容]` 是给 agent 的信号：这些内容的完整版本可以通过 recall tool 取回。

**滚动压缩：** 如果已存在 `compacted_summary`，再次触发压缩时将旧摘要 + 新落窗消息一起压缩为更新摘要。

**压缩 prompt 模板：** 新增 `midrun_compress_system` 和 `midrun_compress_input` 到 `PromptManager`，指令更侧重保留原始意图、操作索引和当前进度，并在输出中包含可 recall 的引用标记。

### 5.5 Session 内 Recall Tool

**新增 `backend/app/tools/session_recall_tool.py`**

**名称：** `session_recall`

**作用域：** 仅当前 session 的 messages（跨 run，但同 session）

**参数：**
```json
{
  "query": "要查找的内容关键词",
  "message_type": "tool_trace | user_message | assistant_message | all（默认 all）",
  "limit": 3
}
```

**搜索方式：** 复用现有 `RecallService` 的 token 匹配 + 排序逻辑，但限定 `session_id`。

**返回内容：** 匹配 message 的完整 `content_text`（或 tool output payload），而非摘要 excerpt。agent 拿到的是可用的完整内容，可以继续基于此推理。

**关键区别与跨 session RecallService：**

| | 跨 session RecallService | Session 内 Recall Tool |
|---|---|---|
| 作用域 | project_id（跨 session） | session_id（当前 session） |
| 返回内容 | 摘要 excerpt（140 chars） | 完整内容 |
| 触发方式 | 内部 API（无 tool 入口） | Agent tool call |
| 排序侧重 | 全项目相关性 | 时间近因 + 关键词匹配 |

**注册时机：** Recall Tool 始终注册在 agent 的 tool 列表中，无论是否触发过压缩。这样 agent 在任何时候都可以主动回溯当前 session 的历史。

### 5.6 压缩失败降级

压缩是优化行为，不应阻塞执行循环：

- **Tier 2 截断**：纯文本操作，不会失败
- **Tier 3 压缩 LLM 调用超时/异常** → 跳过 Tier 3，仅保留 Tier 2 截断消息 + Tier 1 最近窗口
- **Tier 3 压缩返回空内容** → 同上
- **记录 warn 日志**，不中断 run

最差情况仅回到现有截断行为，不会比现在更差。

### 5.7 Continuation 复用 Compacted Summary

当 `_generate_and_persist_continuation_artifact()` 执行时，检测 `context.compacted_summary` 是否存在：

- **有 compacted_summary** → `ContinuationArtifactBuilder.build_prompt_input()` 的输入中，将 compacted_summary 作为已有摘要前缀注入，只需压缩 compacted_summary 之后新增的消息。transcript 输入格式：`[已有摘要]\n{compacted_summary}\n\n[新增对话]\n{新消息压缩文本}`。压缩预算只算新增消息部分。
- **无 compacted_summary** → 走现有全量压缩逻辑，不变。

**`ContinuationArtifactBuilder` 变更：**
- `build_prompt_input()` 新增 `existing_summary: str | None = None` 参数
- 当 `existing_summary` 非空时，将其作为前缀拼入 transcript 输入，预算只计算新增消息

**`agent_service.py` 变更：**
- `_generate_and_persist_continuation_artifact()` 传递 `context.compacted_summary` 给 builder

## 6. 改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/app/llm/token_counter.py` | 新建 | tiktoken 封装，按 model encoding 计数 |
| `backend/app/tools/session_recall_tool.py` | 新建 | session 内 recall tool，从 DB 取回完整内容 |
| `backend/app/execution/context_manager.py` | 修改 | LoopContext 新增 total_tokens, compacted_summary, group_count；add_message 累加 token |
| `backend/app/config/settings.py` | 修改 | ExecutionSettings 新增 tier2/tier3 阈值和截断参数 |
| `backend/app/execution/rapid_loop.py` | 修改 | _call_llm 前检查压力；新增 _compact_tier2() 和 _compact_tier3() 方法 |
| `backend/app/execution/loop_message_builder.py` | 修改 | 注入 Task Anchor + Tier 2/3 消息；recent_context_messages 去重；新增 _build_tier2_messages() |
| `backend/app/execution/prompt_manager.py` | 修改 | 新增 midrun_compress_system/input 模板 |
| `backend/app/memory/continuation_builder.py` | 修改 | build_prompt_input 新增 existing_summary 参数 |
| `backend/app/services/agent_service.py` | 修改 | 传递 compacted_summary 给 continuation builder；注册 session_recall tool |
| `backend/tests/test_execution/test_midrun_compaction.py` | 新建 | 三级上下文模型的单元测试 |

## 7. 不做的事

- 不做 curated memory review（7.3 节第 1 步）——独立 feature，后续跟进
- 不做动态 context window 预算分配（根据 model 类型调整阈值）——后续跟进
- 不改变 DB 层的 messages 存储——mid-run 压缩仅修改内存中的 `context.messages`
- 不做跨 session recall tool（现有 RecallService 已有内部 API，tool 化属于独立 feature）
