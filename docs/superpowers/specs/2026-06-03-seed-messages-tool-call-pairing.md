# Seed Messages 方案 F：恢复 tool_call ↔ tool_result 配对

## 问题

当前 seed_messages 从上一轮传递到下一轮时，tool_trace 被转成 `role=assistant, content=[tool_trace]...`，导致：

1. **角色混淆**：模型把工具执行日志当成自己"说过的话"
2. **结构混乱**：对话内容和工具输出混在同一个消息流
3. **格式低效**：`[tool_trace] tool_name=file\narguments=...` 是机器格式，浪费 token 且模型需要额外理解

## 目标

和 OpenCode 一致——上一轮的工具执行以标准 OpenAI tool call 格式传递：
```
assistant: "我来读一下文件" + tool_calls: [{id, name, arguments}]
tool: "文件内容是..." (tool_call_id 匹配)
```

## DB 存储现状

| 消息类型 | 存储字段 | 关键信息 |
|---------|---------|---------|
| ASSISTANT_MESSAGE | content_text, payload_json (reasoning_text) | ❌ 没有 tool_calls |
| TOOL_TRACE | content_text (空), payload_json (tool_name, arguments, tool_call_id, output, error, success, step_number, status) | ✅ 有 tool_call_id |
| USER_MESSAGE | content_text | - |

## 改动方案

### 核心思路

不再把 tool_trace 当成独立的"文本消息"传给下一轮，而是利用 tool_trace 的 payload 信息，重构为标准的 assistant+tool_calls + tool role 消息对。

### 改动 1：`context_assembly.py` — `_message_to_seed_dict` 改为生成配对消息

```python
def _message_to_seed_dict(message: Any) -> list[dict[str, str]]:
    """将一条 DB 消息转为 seed_messages 条目列表。
    
    TOOL_TRACE 生成 3 条消息：assistant(含 tool_calls) + tool(结果)
    其他消息生成 1 条。
    """
    if message.message_type == MessageType.TOOL_TRACE:
        return _tool_trace_to_paired_seeds(message)
    return [{"role": str(message.role), "content": str(message.content_text)}]


def _tool_trace_to_paired_seeds(message: Any) -> list[dict[str, str]]:
    """将 TOOL_TRACE 重构为 assistant(tool_calls) + tool(result) 配对。"""
    from app.memory.payload_utils import as_payload_dict
    payload = as_payload_dict(message.payload_json)
    
    tool_name = payload.get("tool_name", "")
    arguments = payload.get("arguments", {})
    tool_call_id = payload.get("tool_call_id", f"prev_{uuid4().hex[:8]}")
    output = payload.get("output", "")
    error = payload.get("error", "")
    success = payload.get("success", True)
    
    # 1. assistant 消息：带 tool_calls
    assistant_msg = {
        "role": "assistant",
        "content": "",  # 无文本，只有 tool_calls
        "tool_calls": [{
            "id": tool_call_id,
            "name": tool_name,
            "arguments": arguments,
        }],
    }
    
    # 2. tool 消息：工具结果
    tool_content = output if success else (error or "Tool execution failed")
    tool_msg = {
        "role": "tool",
        "content": _compact_tool_output(tool_content),
        "tool_call_id": tool_call_id,
    }
    
    return [assistant_msg, tool_msg]
```

### 改动 2：`context_assembly.py` — `build_context_assembly` 支持新字段

`recent_messages` 的每条消息现在可能有 `tool_calls` 和 `tool_call_id` 字段：

```python
def build_context_assembly(...) -> ContextAssemblyResult:
    return ContextAssemblyResult(
        system_sections=...,
        recent_messages=[
            {
                "role": str(message.get("role") or ""),
                "content": str(message.get("content") or ""),
                "tool_calls": message.get("tool_calls"),        # 新增
                "tool_call_id": message.get("tool_call_id"),    # 新增
            }
            for message in recent_messages
            if str(message.get("role") or "").strip() and (
                str(message.get("content") or "").strip() or message.get("tool_calls")
            )
        ],
        supplemental_block=...,
    )
```

### 改动 3：`message_repo.py` — `list_recent_seed_candidates` 合并排序

当前返回 `text_candidates + tool_traces`，tool_trace 追加在末尾。
改为按时间排序，tool_trace 展开 为配对消息后插入正确位置：

```python
def list_recent_seed_candidates(self, ...) -> list[dict]:
    # 1. 查询对话消息 (user/assistant)
    text_models = ...
    # 2. 查询 tool_trace
    tool_trace_models = ...
    # 3. 合并：把 tool_trace 的 created_at 用于排序
    #    返回 dict 列表，每条带 message_type 标记
    all_items = []
    for m in text_models:
        all_items.append({"type": "text", "message": self._to_domain(m)})
    for m in tool_trace_models:
        all_items.append({"type": "tool_trace", "message": self._to_domain(m)})
    # 按 created_at 排序
    all_items.sort(key=lambda x: x["message"].created_at)
    return all_items
```

### 改动 4：`context_assembly.py` — `build_for_session` 处理展开

```python
# 4) Recent seed candidates — 展开 tool_trace 为配对消息
candidates = self.conversation_service.list_recent_seed_candidates(...)
recent_messages = []
for item in candidates:
    if item["type"] == "tool_trace":
        recent_messages.extend(_tool_trace_to_paired_seeds(item["message"]))
    else:
        recent_messages.extend(_message_to_seed_dict(item["message"]))
```

### 改动 5：`context_manager.py` — `from_run_input` 处理 tool_calls

```python
allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}

for seeded in seed_messages or []:
    role = str(seeded.get("role") or "").strip().lower()
    if role not in allowed_seed_roles:
        continue
    content = seeded.get("content")
    tool_calls = seeded.get("tool_calls")  # 新增
    tool_call_id = seeded.get("tool_call_id")  # 新增
    
    # tool role 消息必须有 tool_call_id
    if role == "tool" and not tool_call_id:
        continue  # 跳过无法配对的 tool 消息
    
    # assistant 带 tool_calls 时，content 可以为空
    if role == "assistant" and not tool_calls:
        if not isinstance(content, str) or not content.strip():
            continue  # 跳过空 assistant 消息（无文本也无 tool_calls）
    
    context.add_message(
        role, 
        content=content if isinstance(content, str) and content.strip() else None,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    )
```

## 数据流（改造后）

```
上一轮对话 (DB)
    │
    ├── list_recent_seed_candidates()
    │   ├── USER_MESSAGE → {"type": "text", ...}
    │   ├── ASSISTANT_MESSAGE → {"type": "text", ...}
    │   └── TOOL_TRACE → {"type": "tool_trace", ...}
    │        └── 按 created_at 统一排序
    │
    ├── build_for_session() 展开
    │   ├── text → {"role": "user/assistant", "content": "原文"}
    │   └── tool_trace → [
    │         {"role": "assistant", "tool_calls": [{id, name, arguments}]},
    │         {"role": "tool", "content": "结果", "tool_call_id": id},
    │       ]
    │
    └── LoopContext.from_run_input()
        ├── user/assistant/tool 三种 role 都支持
        ├── assistant 的 tool_calls 正确配对
        └── tool 的 tool_call_id 关联到 assistant 的 tool_calls
        
模型看到的：
    [USER] 帮我修一下prompt
    [ASSISTANT] tool_calls: [{name: "file", arguments: {action: "read", path: "a.py"}}]
    [TOOL] 文件内容是...
    [ASSISTANT] tool_calls: [{name: "edit", arguments: {action: "str_replace", ...}}]
    [TOOL] 编辑成功
    [ASSISTANT] 我已经修复了这个问题
    [USER] 不要英文混合
```

## 不改动的部分

- continuation artifact 机制不变（4行摘要继续作为 supplemental_block）
- midrun compaction 不变
- 运行时 LoopContext 内部的消息处理不变
- 前端 tool_trace 展示逻辑不变（conversation_runtime_adapter 不变）

## 风险

1. **tool_call_id 匹配**：如果上一轮的 tool_trace 没有存 tool_call_id（旧数据），需要生成一个 fallback id
2. **assistant 空文本**：当 assistant 只有 tool_calls 没有文本时，OpenAI API 允许 content=null，但需要确认所有 provider 都支持
3. **消息顺序**：tool_trace 的 created_at 必须和 assistant/USER 消息的 created_at 正确交叉排序

## 新增依赖

- `uuid4`（已在项目中使用）
- `app.memory.payload_utils.as_payload_dict`（已存在）
