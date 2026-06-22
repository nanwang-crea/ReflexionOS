# Working Memory 实施计划

**日期**: 2026-06-22
**状态**: 待实施
**依赖**: `2026-06-21-working-memory-design.md`

## 概览

基于设计文档，分两个 Phase 实施。Phase 1 做最小可用版本（自动提取 + 注入），Phase 2 做模型主动写入 + 语义化占位符。

---

## Phase 1：最小可用版本（3-5 天）

只做三件事：WorkingMemory 数据模型、读文件自动摘要、LoopMessageBuilder 注入。效果：agent 读过的每个文件都有摘要，压缩后仍可见。

### Step 1.1：创建 `backend/app/memory/` 包

**新建文件**：`backend/app/memory/__init__.py`

```python
# 空文件，标记为 Python 包
```

无需其他内容，子模块按需导入。

### Step 1.2：创建 WorkingMemory 数据模型

**新建文件**：`backend/app/memory/working_memory.py`

按设计文档 Section 1 实现，包含：
- `MemoryEntryType` 枚举（5 种类型）
- `MemoryEntry` dataclass
- `WorkingMemory` dataclass，含 4 个存储字段 + 写入接口 + 读取接口 + Token 预算淘汰

**关键实现细节**：
- `file_index: dict[str, MemoryEntry]` — key 为文件路径，天然去重
- `decisions: list[MemoryEntry]` — 保留时序
- `variables: dict[str, MemoryEntry]` — key 为变量名，天然去重
- `errors: list[MemoryEntry]` — 保留时序
- `to_prompt_section()` 返回空字符串时不注入，零开销
- `_evict_to_fit()` 淘汰优先级：errors > variables > file_index(最旧) > decisions
- Token 预算估算：`1 token ≈ 1.5 字符`，`max_tokens=2000` → `max_chars=3000`

**自审注意点**：
- ✅ 生命周期 docstring 已明确 per-Turn，非 per-Run
- ✅ `to_prompt_section()` 的 emoji 前缀（📂🎯⚙️⚠️）需确认 LLM 不会误解，设计文档已确认
- ⚠️ `_evict_to_fit` 中 `self.file_index = dict(items[-15:])` 会丢失 dict 的插入顺序语义吗？不会，Python 3.7+ dict 保持插入顺序，`items()` 也是有序的

### Step 1.3：创建 MemoryExtractor（Phase 1 只实现 file read）

**新建文件**：`backend/app/memory/memory_extractor.py`

按设计文档 Section 2 实现，Phase 1 只需要：
- `MemoryExtractor.__init__(memory: WorkingMemory)`
- `extract(tool_name, tool_args, tool_result)` 统一入口
- `_extract_from_file_read()` — 最高频场景
- `_summarize_file_content()` — 纯规则文件摘要

Phase 1 暂不实现的提取器（方法存在但 pass）：
- `_extract_from_file_search`
- `_extract_from_file_list`
- `_extract_from_edit`
- `_extract_from_shell`
- `_extract_from_grep`
- `_extract_from_recall`
- `_extract_from_explore`

**关键实现细节**：
- `extract()` 外层 try/except，提取失败静默处理，不影响主流程
- `_summarize_file_content()` 提取 class/function/struct 定义 + 关键注释 + 行数，控制在 ~100 字符
- 支持 Python/JS/TS/Go/Rust 符号提取
- 错误结果（`result.startswith("Error")` 或 `"文件不存在"` in result）不提取

### Step 1.4：LoopContext 持有 WorkingMemory

**修改文件**：`backend/app/execution/context_manager.py`

**改动位置**：`__init__` 方法，第 44 行之后（`self.compressor = ...` 之后）

```python
# 新增导入（文件顶部）
from app.memory.working_memory import WorkingMemory
from app.memory.memory_extractor import MemoryExtractor

# 在 __init__ 中，self.compressor 赋值之后添加：
self.working_memory = WorkingMemory()
self.memory_extractor = MemoryExtractor(self.working_memory)
```

**改动范围**：仅新增 2 行导入 + 2 行字段赋值，不修改任何现有逻辑。

**自审注意点**：
- ✅ WorkingMemory 绑定到 LoopContext，而 LoopContext 的生命周期由调用方管理。设计文档要求 Turn 级共享——同一 Turn 内多次 Run 应复用同一个 LoopContext。需确认调用方是否已如此实现。
- 🔍 需检查 `rapid_loop.py` 和 `agent_service.py` 中 LoopContext 的创建时机，确认是否已经是 Turn 级而非 Run 级

### Step 1.5：LoopMessageBuilder 注入 Working Memory

**修改文件**：`backend/app/execution/loop_message_builder.py`

**改动位置**：`build()` 方法中，system prompt 之后、Tier 3 之前

在 `messages = [LLMMessage(role=MessageRole.SYSTEM, content=system_prompt)]` 之后插入：

```python
# Working Memory 注入
wm_section = context.working_memory.to_prompt_section()
if wm_section:
    messages.append(LLMMessage(role=MessageRole.SYSTEM, content=wm_section))
```

同样在 `build_final_summary()` 方法中做相同注入（设计文档 Section 4.2 明确要求）。

**自审注意点**：
- 🔍 需确认 `build()` 和 `build_final_summary()` 的具体行号和消息组装逻辑
- ✅ 注入位置：system prompt 之后、Tier 3 之前，这是设计文档明确要求的
- ✅ `to_prompt_section()` 返回空字符串时不注入，零开销

### Step 1.6：tool_call_executor 中自动提取

**修改文件**：`backend/app/execution/tool_call_executor.py`

**改动位置**：`_execute_single_tool()` 方法中，tool 执行成功后、结果写入 context 之后

在 `context.update_history()` 和 `context.add_message()` 之后插入：

```python
# 自动提取到 Working Memory
context.memory_extractor.extract(
    tool_name=tool_call.name,
    tool_args=tool_call.arguments,
    tool_result=tool_output,
)
```

**自审注意点**：
- 🔍 需确认 `tool_call.arguments` 的实际类型——设计文档假设是 `dict`，需验证
- 🔍 需确认 `tool_output` 变量名和格式
- ✅ 只在 tool 执行成功时提取（FAILED 状态跳过）
- ✅ MemoryExtractor.extract 内部已有 try/except，不影响主流程

### Step 1.7：单元测试

**新建文件**：`backend/tests/test_working_memory.py`

测试用例（来自设计文档测试策略）：

1. **WorkingMemory 数据模型**
   - `test_upsert_file_new` — 新增文件摘要
   - `test_upsert_file_update` — 更新已有文件摘要（验证覆盖）
   - `test_add_decision` — 添加决策
   - `test_set_variable` — 设置变量
   - `test_add_error` — 添加错误
   - `test_to_prompt_section_empty` — 空 Working Memory 返回空字符串
   - `test_to_prompt_section_format` — 格式化输出包含正确的 emoji 标记和内容
   - `test_evict_to_fit` — Token 预算超限时淘汰
   - `test_evict_priority` — 淘汰优先级正确（errors 先淘汰，decisions 最后淘汰）

2. **MemoryExtractor（Phase 1 部分）**
   - `test_extract_read_file` — 读文件自动提取摘要
   - `test_extract_read_file_error` — 错误结果不提取
   - `test_extract_failure_silent` — 提取失败不影响主流程

3. **集成测试**
   - `test_loop_context_has_working_memory` — LoopContext 初始化时包含 working_memory 和 memory_extractor
   - `test_message_builder_injects_working_memory` — LoopMessageBuilder 正确注入非空 Working Memory
   - `test_message_builder_skips_empty_working_memory` — 空 Working Memory 不注入

---

## Phase 2：模型主动写入 + 语义化占位符（3-5 天）

### Step 2.1：创建 working_memory_update 工具

**新建文件**：`backend/app/tools/working_memory_tool.py`

继承 `BaseTool`，实现 `name`、`description`、`execute()`、`get_schema()`。

**关键设计**：
- `execute()` 是占位实现，实际逻辑在 `tool_call_executor` 中拦截处理（因为需要访问 `context.working_memory`）
- Schema 定义 3 个 action：`decide`、`note`、`set_var`

**新建文件**：`backend/app/memory/working_memory_tool.py`

包含 `handle_working_memory_update(memory, action, key, value) -> str` 函数，供 `tool_call_executor` 调用。

### Step 2.2：tool_call_executor 拦截 working_memory_update

**修改文件**：`backend/app/execution/tool_call_executor.py`

在 `_execute_single_tool()` 中，`tool.execute()` 之前拦截：

```python
if tool_call.name == "working_memory_update":
    from app.memory.working_memory_tool import handle_working_memory_update
    result_msg = handle_working_memory_update(
        memory=context.working_memory,
        action=tool_call.arguments.get("action", ""),
        key=tool_call.arguments.get("key", ""),
        value=tool_call.arguments.get("value", ""),
    )
    # ... 设置 step 状态、写入 context、返回
```

### Step 2.3：注册工具

**修改文件**：`backend/app/execution/runtime_tool_definitions.py`

在 `ToolSetConfig` 的 `tool_order`、`exploration_tools`、`plan_mode_tools` 中添加 `"working_memory_update"`。

**修改文件**：`backend/app/services/agent_service.py`

在工具注册位置添加 `registry.register(WorkingMemoryTool())`。

### Step 2.4：MemoryExtractor 扩展

**修改文件**：`backend/app/memory/memory_extractor.py`

实现 Phase 1 中留空的方法：
- `_extract_from_file_search` — 追加搜索关键词到已有摘要
- `_extract_from_file_list` — 目录结构概览
- `_extract_from_edit` — 标记 `[MODIFIED]`
- `_extract_from_shell` — 命令错误/环境变量提取
- `_extract_from_grep` — 搜索结果提取文件路径
- `_extract_from_recall` — recall 结果提取关键信息
- `_extract_from_explore` — 探索结果提取结构信息

### Step 2.5：Tier 2 语义化占位符（可选，设计文档标注 Phase 2 但实现较复杂）

**修改文件**：`backend/app/execution/context_compressor.py`

将 `[Old tool result content cleared]` 替换为包含 Working Memory 文件摘要的语义化占位符。

**自审注意点**：
- ⚠️ 设计文档自己标注"需要更精细的设计——需要从消息上下文中确定哪个 tool call 对应哪个文件"，Phase 2 可以先跳过，优先保证核心功能稳定

### Step 2.6：Phase 2 单元测试

- `test_handle_decide` / `test_handle_note` / `test_handle_set_var` / `test_handle_unknown_action`
- MemoryExtractor 扩展方法测试
- 工具注册集成测试

---

## 自审清单

### ✅ 已确认正确

1. **生命周期**：WorkingMemory 绑定到 LoopContext，Turn 级共享，不持久化。设计文档已充分论证。
2. **注入位置**：system prompt 之后、Tier 3 之前，优先级正确。
3. **零开销**：`to_prompt_section()` 返回空字符串时不注入。
4. **容错**：MemoryExtractor.extract() 外层 try/except，提取失败不影响主流程。
5. **纯规则**：`_summarize_file_content` 不调 LLM，零延迟零成本。

### ⚠️ 需要在实施时确认的问题

1. **LoopContext 的创建时机**：需确认 `agent_service.py` / `rapid_loop.py` 中 LoopContext 是否已经是 Turn 级创建（同一 Turn 的反思循环复用同一个 context）。如果不是，需要调整调用方逻辑。这是设计文档 Section 4.1 明确要求的。

2. **tool_call.arguments 的类型**：设计文档假设是 `dict`，需在 `tool_call_executor.py` 中确认实际类型。如果是 JSON 字符串需要先 parse。

3. **tool_output 的变量名和格式**：需在 `_execute_single_tool()` 中确认 tool 执行结果的变量名（可能是 `result`、`output`、`tool_output` 等）。

4. **build_final_summary() 的注入**：设计文档要求在 `build_final_summary()` 中也注入 Working Memory，需确认该方法是否存在以及其消息组装逻辑。

5. **WorkingMemoryTool 的 execute() 与拦截的关系**：工具注册到 ToolRegistry 后，LLM 会生成 tool_call，但实际执行在 `tool_call_executor` 中被拦截。需确认 `tool_call_executor` 的拦截点在 `tool.execute()` 之前，这样 `WorkingMemoryTool.execute()` 永远不会被调用。

6. **tool_name 映射**：MemoryExtractor 中硬编码的 tool_name（如 `"file"`, `"edit"`, `"shell"`）需与 ToolRegistry 中的注册名一致。需在实施时核对。

### 📋 实施顺序

```
Step 1.1 (创建包) → Step 1.2 (数据模型) → Step 1.3 (提取器) → Step 1.4 (LoopContext)
                                                                      ↓
Step 1.7 (单元测试) ← Step 1.6 (tool_call_executor) ← Step 1.5 (消息注入)
```

每个 Step 完成后立即运行相关测试，确保不破坏现有功能。Phase 1 全部完成后做一次端到端验证，再开始 Phase 2。
