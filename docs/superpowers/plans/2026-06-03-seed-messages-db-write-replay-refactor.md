# Seed Messages DB + 写入 + 回放层工程化重构

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从工程层面彻底重构 TOOL_TRACE 的 DB 存储、事件写入、回放组装，使其和 OpenAI 标准 tool_call/tool_result 配对格式完全一致——不再修补，而是让 DB 存的就是对的格式。

**Architecture:** 三层联动：①DB 写入层把 TOOL_TRACE 的 role 从 `assistant` 改为 `tool`，ASSISTANT_MESSAGE 的 payload_json 记录 tool_calls；②DB 迁移刷旧数据；③回放层直接按 role 读出配对结构，无需运行时重构。

**Tech Stack:** SQLAlchemy (Alembic migration), Pydantic, Python 3.12

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/conversation_runtime_adapter.py` | 修改 | TOOL_TRACE 写入 role=`"tool"`；assistant segment 事件写入 tool_calls |
| `backend/app/memory/context_assembly.py` | 修改 | `_message_to_seed_dict` 按 role 输出，TOOL_TRACE 不再伪装 assistant；`build_context_assembly` 支持 tool_calls/tool_call_id |
| `backend/app/memory/message_normalizer.py` | 修改 | `normalize_message_text_for_seed` TOOL_TRACE 按 tool role 格式化 |
| `backend/app/memory/continuation_builder.py` | 修改 | `_format_tool_trace` 使用 role=`tool` 而非 `assistant/tool_trace` |
| `backend/app/execution/context_manager.py` | 修改 | `from_run_input` 支持 tool_calls 和 tool_call_id 字段 |
| `backend/app/storage/repositories/message_repo.py` | 修改 | `list_recent_seed_candidates` 合并排序+返回 typed dict |
| `backend/app/models/conversation.py` | 无变更 | Message role 是 str，值域自然支持 `"tool"` |
| `backend/app/storage/models.py` | 无变更 | MessageModel role 是 String，值域自然支持 `"tool"` |
| `backend/app/services/conversation_service.py` | 无变更 | 只是透传 message_repo |
| `backend/alembic/versions/XXXX_tool_trace_role_to_tool.py` | 新增 | 迁移旧数据：TOOL_TRACE role `assistant` → `tool`；ASSISTANT_MESSAGE payload 加 tool_calls |
| `backend/tests/test_memory/test_context_assembly.py` | 修改 | 更新断言：TOOL_TRACE seed role 为 `tool`，有 tool_calls/tool_call_id |
| `backend/tests/test_execution/test_context_manager.py` | 修改 | 新增 tool_calls/tool_call_id seed 测试 |
| `frontend/src/types/conversation.ts` | 无变更 | ConversationMessageRole 已包含 `'tool'` |
| `frontend/src/features/conversation/conversationReducer.ts` | 无变更 | 按 messageType 渲染，不按 role |

---

## Task 1: 写入层 — TOOL_TRACE role 改为 `"tool"`

**Files:**
- Modify: `backend/app/services/conversation_runtime_adapter.py:178`

- [ ] **Step 1: 修改 `_tool_start_events` 中 TOOL_TRACE 的 role**

当前代码 (line 178):
```python
"role": MessageRole.ASSISTANT,
```

改为:
```python
"role": MessageRole.TOOL,
```

- [ ] **Step 2: 运行测试确认**

Run: `cd backend && python -m pytest tests/ -x -q 2>&1 | tail -20`
Expected: 部分测试可能因 seed 断言失败（后续 Task 修复），但写入逻辑本身不应出错

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/conversation_runtime_adapter.py
git commit -m "refactor: TOOL_TRACE role from assistant to tool"
```

---

## Task 2: 写入层 — ASSISTANT_MESSAGE 记录 tool_calls

**Files:**
- Modify: `backend/app/services/conversation_runtime_adapter.py`

当前问题：`_assistant_segment_events()` 刷新 assistant 文本时，不记录 tool_calls。LLM 返回 tool_calls 后，rapid_loop 调用 `context.add_message("assistant", tool_calls=[...])`，但 adapter 只收到 `tool:start` 事件——此时 assistant segment 已被 flush（`_assistant_segment_events`），tool_calls 信息丢失。

解决方案：在 `tool:start` 事件处理中，先 flush assistant segment（带 tool_calls），再创建 TOOL_TRACE。

- [ ] **Step 1: 修改 adapter 接收 tool:start 时的处理**

当前代码 (line 67-73):
```python
if event_type == "tool:start":
    return self._append_events(
        [
            *self._assistant_segment_events(),
            *self._tool_start_events(data),
        ]
    )
```

改为:
```python
if event_type == "tool:start":
    return self._append_events(
        [
            *self._assistant_segment_events(tool_call_id=data.get("tool_call_id"), tool_name=data.get("tool_name"), arguments=data.get("arguments")),
            *self._tool_start_events(data),
        ]
    )
```

- [ ] **Step 2: 修改 `_assistant_segment_events` 签名，支持写入 tool_calls**

当前代码 (line 588-629):
```python
def _assistant_segment_events(self) -> list[ConversationEvent]:
    if self.assistant_message_id is None or not self._assistant_content:
        return []
    ...
```

改为:
```python
def _assistant_segment_events(
    self,
    *,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    arguments: dict | None = None,
) -> list[ConversationEvent]:
    if self.assistant_message_id is None or not self._assistant_content:
        if tool_call_id is not None and self.assistant_message_id is None:
            self.assistant_message_id = new_message_id()
        elif self.assistant_message_id is None:
            return []
    ...
```

在 `_create_assistant_message_event` 之后的 `PAYLOAD_UPDATED` 事件中，加入 tool_calls：

在 existing reasoning_text payload update 之后，添加:
```python
    if tool_call_id is not None:
        tool_calls_entry = {
            "id": tool_call_id,
            "name": tool_name or "",
            "arguments": arguments or {},
        }
        existing_payload = {}
        if self._assistant_reasoning:
            existing_payload["reasoning_text"] = self._assistant_reasoning
        existing_payload["tool_calls"] = [tool_calls_entry]
        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={"payload_json": existing_payload},
            )
        )
    elif self._assistant_reasoning:
        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={"payload_json": {"reasoning_text": self._assistant_reasoning}},
            )
        )
```

注意：合并 reasoning_text 和 tool_calls 到同一个 PAYLOAD_UPDATED 事件中，避免两个事件覆盖 payload_json。

- [ ] **Step 3: 处理 assistant 无文本但只有 tool_calls 的场景**

当 LLM 只返回 tool_calls 没有文本时，`self._assistant_content` 为空。当前 `_assistant_segment_events` 会 `return []`。

修改逻辑：如果 `tool_call_id` 不为 None，即使 `_assistant_content` 为空也要创建 assistant message。

```python
def _assistant_segment_events(
    self,
    *,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    arguments: dict | None = None,
) -> list[ConversationEvent]:
    has_content = self._assistant_content or self._assistant_reasoning
    has_tool_call = tool_call_id is not None

    if not has_content and not has_tool_call:
        return []

    if self.assistant_message_id is None:
        if has_content or has_tool_call:
            self.assistant_message_id = new_message_id()
        else:
            return []

    message_id = self.assistant_message_id
    events: list[ConversationEvent] = []

    display_mode = "working_note" if has_content else "default"
    events.append(
        self._create_assistant_message_event(
            message_id=message_id,
            turn_message_index=self._reserve_turn_message_index(),
            display_mode=display_mode,
        )
    )

    payload_update: dict = {}
    if self._assistant_reasoning:
        payload_update["reasoning_text"] = self._assistant_reasoning
    if tool_call_id is not None:
        payload_update["tool_calls"] = [
            {
                "id": tool_call_id,
                "name": tool_name or "",
                "arguments": arguments or {},
            }
        ]

    if payload_update:
        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={"payload_json": payload_update},
            )
        )

    if self._assistant_content:
        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_CONTENT_COMMITTED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={"content_text": self._assistant_content},
            )
        )

    events.append(
        self._new_event(
            event_type=EventType.MESSAGE_COMPLETED,
            message_id=message_id,
            run_id=self.run_id,
            payload_json={"completed_at": datetime.now().isoformat()},
        )
    )

    self.assistant_message_id = None
    self._assistant_content = ""
    self._assistant_reasoning = ""
    return events
```

注意：这里每次 `_assistant_segment_events` 只处理一个 tool_call。如果 LLM 返回多个 tool_calls（如 read_file + grep 并行），rapid_loop 会对每个 tool_call 依次 emit `tool:start`，每次都会调用 `_assistant_segment_events()`。第一次调用会 flush 之前累积的文本+tool_call，后续调用 `_assistant_content` 已清空，只会创建新的只有 tool_calls 的 assistant message（display_mode="default"）。

但这样会产生多条 assistant message，每条带一个 tool_call。这不标准——OpenAI API 期望一个 assistant message 带多个 tool_calls。

**修正方案**：在 adapter 中累积 tool_calls，等到第一个 TOOL_TRACE result 返回前统一 flush。

但考虑到改动复杂度和当前单 tool_call 执行模式（rapid_loop 串行执行），先采用简单方案：每个 tool_call 独立一个 assistant message。后续优化时再合并。

实际上更好的方案是：**不创建额外的 assistant message**。assistant 文本 segment 仍然按现有逻辑 flush。tool_call 信息存在 TOOL_TRACE 的 payload 中已经足够——回放时从 TOOL_TRACE 的 `tool_call_id` + `arguments` 重构 assistant tool_calls 部分。

**修正后的最终方案**：`_assistant_segment_events` 不需要改签名。tool_calls 不写入 ASSISTANT_MESSAGE 的 payload。回放层从 TOOL_TRACE payload 中重构 assistant(tool_calls) + tool(result) 配对。

这样改动最小，且和 OpenCode 的做法一致——OpenCode 的 DB 里也是每条 tool_call 单独一条记录，回放时组装。

- [ ] **Step 4: 回退 Step 1-3 的 _assistant_segment_events 改动**

`_assistant_segment_events` 保持原样不变。只有 Task 1 的 TOOL_TRACE role 改动保留。

assistant payload 中不需要存 tool_calls——回放层从 TOOL_TRACE 的 payload 中重构。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/conversation_runtime_adapter.py
git commit -m "refactor: TOOL_TRACE role from assistant to tool"
```

---

## Task 3: Alembic 迁移 — 刷旧数据

**Files:**
- Create: `backend/alembic/versions/XXXX_tool_trace_role_to_tool.py`

- [ ] **Step 1: 生成迁移文件**

Run: `cd backend && alembic revision -m "tool_trace_role_to_tool" --autogenerate`

检查生成的文件。autogenerate 可能不会检测到数据变更（只是值域变化），所以需要手动编辑。

- [ ] **Step 2: 编辑迁移文件 — 数据刷写**

```python
"""tool_trace_role_to_tool

Revision ID: <generated>
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa


revision = '<generated>'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE messages SET role = 'tool' WHERE message_type = 'tool_trace'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE messages SET role = 'assistant' WHERE message_type = 'tool_trace'"
    )
```

- [ ] **Step 3: 运行迁移**

Run: `cd backend && alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "migration: TOOL_TRACE role assistant→tool"
```

---

## Task 4: 回放层 — `message_repo.list_recent_seed_candidates` 合并排序

**Files:**
- Modify: `backend/app/storage/repositories/message_repo.py:164-220`

当前问题：返回 `text_candidates + tool_traces`，TOOL_TRACE 追加在末尾，顺序不正确。

- [ ] **Step 1: 修改查询逻辑——统一查询+按 created_at 排序**

当前代码:
```python
def list_recent_seed_candidates(
    self,
    session_id: str,
    *,
    current_turn_id: str | None = None,
    limit: int = 8,
    scan_limit: int = 200,
    max_tool_traces: int = 4,
) -> list[Message]:
    resolved_limit = max(0, int(limit)) if limit else 0
    resolved_scan = max(50, int(scan_limit)) if scan_limit else 200
    if resolved_limit <= 0:
        return []

    with self.db.get_session() as db_session:
        query = db_session.query(MessageModel).filter(
            MessageModel.session_id == session_id,
            MessageModel.message_type.in_(
                [
                    MessageType.USER_MESSAGE.value,
                    MessageType.ASSISTANT_MESSAGE.value,
                ]
            ),
            MessageModel.content_text != "",
            func.coalesce(
                func.json_extract(MessageModel.payload_json, "$.kind"),
                "",
            )
            != "continuation_artifact",
        )
        if current_turn_id:
            query = query.filter(MessageModel.turn_id != current_turn_id)

        models = query.order_by(MessageModel.created_at.desc()).limit(resolved_scan).all()

        text_candidates = self._to_domain_list(list(reversed(models)))[-resolved_limit:]

        tool_trace_models = (
            db_session.query(MessageModel)
            .filter(
                MessageModel.session_id == session_id,
                MessageModel.message_type == MessageType.TOOL_TRACE.value,
                MessageModel.stream_state == StreamState.COMPLETED.value,
            )
        )
        if current_turn_id:
            tool_trace_models = tool_trace_models.filter(
                MessageModel.turn_id != current_turn_id
            )
        tool_trace_models = (
            tool_trace_models.order_by(MessageModel.created_at.desc())
            .limit(max_tool_traces)
            .all()
        )
        tool_traces = list(reversed(self._to_domain_list(tool_trace_models)))

        return text_candidates + tool_traces
```

改为:
```python
def list_recent_seed_candidates(
    self,
    session_id: str,
    *,
    current_turn_id: str | None = None,
    limit: int = 12,
    scan_limit: int = 200,
    max_tool_traces: int = 4,
) -> list[Message]:
    resolved_limit = max(0, int(limit)) if limit else 0
    resolved_scan = max(50, int(scan_limit)) if scan_limit else 200
    if resolved_limit <= 0:
        return []

    with self.db.get_session() as db_session:
        text_query = db_session.query(MessageModel).filter(
            MessageModel.session_id == session_id,
            MessageModel.message_type.in_(
                [
                    MessageType.USER_MESSAGE.value,
                    MessageType.ASSISTANT_MESSAGE.value,
                ]
            ),
            MessageModel.content_text != "",
            func.coalesce(
                func.json_extract(MessageModel.payload_json, "$.kind"),
                "",
            )
            != "continuation_artifact",
        )
        if current_turn_id:
            text_query = text_query.filter(MessageModel.turn_id != current_turn_id)

        text_models = text_query.order_by(MessageModel.created_at.desc()).limit(resolved_scan).all()

        tool_trace_query = (
            db_session.query(MessageModel)
            .filter(
                MessageModel.session_id == session_id,
                MessageModel.message_type == MessageType.TOOL_TRACE.value,
                MessageModel.stream_state == StreamState.COMPLETED.value,
            )
        )
        if current_turn_id:
            tool_trace_query = tool_trace_query.filter(
                MessageModel.turn_id != current_turn_id
            )
        tool_trace_models = (
            tool_trace_query.order_by(MessageModel.created_at.desc())
            .limit(max_tool_traces)
            .all()
        )

        all_models = list(text_models) + list(tool_trace_models)
        all_models.sort(key=lambda m: m.created_at)
        all_models = all_models[-resolved_limit:]

        return self._to_domain_list(all_models)
```

关键变化：
1. text_models 和 tool_trace_models 合并后按 `created_at` 排序
2. 取最后 `resolved_limit` 条（而非分别截断后拼接）
3. `limit` 默认从 8 提升到 12（因为每条 TOOL_TRACE 现在会展开为 2 条 seed message）
4. 返回值仍然是 `list[Message]`（不需要 typed dict，因为 `message_type` 字段可区分）

- [ ] **Step 2: Commit**

```bash
git add backend/app/storage/repositories/message_repo.py
git commit -m "refactor: list_recent_seed_candidates unified sort by created_at"
```

---

## Task 5: 回放层 — `context_assembly.py` 重构 seed 组装

**Files:**
- Modify: `backend/app/memory/context_assembly.py`

当前问题：
1. `_message_to_seed_dict` 把 TOOL_TRACE 伪装成 `role=assistant, content=[tool_trace]...`
2. `build_context_assembly` 丢失 `tool_calls` 和 `tool_call_id` 字段
3. `build_for_session` 不处理展开

- [ ] **Step 1: 重写 `_message_to_seed_dict` — 返回 list，TOOL_TRACE 展开为配对**

当前代码:
```python
def _message_to_seed_dict(message: Any) -> dict[str, str]:
    if message.message_type == MessageType.TOOL_TRACE:
        content = normalize_message_text_for_seed(message)
        return {"role": "assistant", "content": f"[tool_trace] {content}"}
    return {"role": str(message.role), "content": str(message.content_text)}
```

改为:
```python
def _message_to_seed_dict(message: Any) -> list[dict[str, Any]]:
    if message.message_type == MessageType.TOOL_TRACE:
        return _tool_trace_to_paired_seeds(message)
    return [{"role": str(message.role), "content": str(message.content_text)}]


def _tool_trace_to_paired_seeds(message: Any) -> list[dict[str, Any]]:
    from app.memory.payload_utils import as_payload_dict
    from app.memory.text_compaction import truncate_head_tail
    from uuid import uuid4

    payload = as_payload_dict(message.payload_json)

    tool_name = payload.get("tool_name", "")
    arguments = payload.get("arguments", {})
    tool_call_id = payload.get("tool_call_id") or f"prev_{uuid4().hex[:8]}"
    output = payload.get("output", "")
    error = payload.get("error", "")
    success = payload.get("success", True)

    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call_id,
                "name": tool_name,
                "arguments": arguments,
            }
        ],
    }

    tool_content = output if success else (error or "Tool execution failed")
    tool_content = truncate_head_tail(
        str(tool_content),
        max_chars=800,
        head_chars=500,
        tail_chars=200,
        reason="seed context",
    )

    tool_msg: dict[str, Any] = {
        "role": "tool",
        "content": tool_content,
        "tool_call_id": tool_call_id,
    }

    return [assistant_msg, tool_msg]
```

- [ ] **Step 2: 修改 `build_context_assembly` — 支持 tool_calls/tool_call_id**

当前代码:
```python
def build_context_assembly(
    *,
    static_blocks: list[str],
    recent_messages: list[dict[str, Any]],
    supplemental_block: str | None,
) -> ContextAssemblyResult:
    return ContextAssemblyResult(
        system_sections=[block for block in static_blocks if str(block or "").strip()],
        recent_messages=[
            {
                "role": str(message.get("role") or ""),
                "content": str(message.get("content") or ""),
            }
            for message in recent_messages
            if str(message.get("role") or "").strip() and str(message.get("content") or "").strip()
        ],
        supplemental_block=supplemental_block.strip() if supplemental_block else None,
    )
```

改为:
```python
def build_context_assembly(
    *,
    static_blocks: list[str],
    recent_messages: list[dict[str, Any]],
    supplemental_block: str | None,
) -> ContextAssemblyResult:
    result_messages: list[dict[str, Any]] = []
    for message in recent_messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        content = str(message.get("content") or "")
        tool_calls = message.get("tool_calls")
        tool_call_id = message.get("tool_call_id")
        has_content = content.strip() or tool_calls
        if not has_content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        if tool_calls is not None:
            entry["tool_calls"] = tool_calls
        if tool_call_id is not None:
            entry["tool_call_id"] = tool_call_id
        result_messages.append(entry)

    return ContextAssemblyResult(
        system_sections=[block for block in static_blocks if str(block or "").strip()],
        recent_messages=result_messages,
        supplemental_block=supplemental_block.strip() if supplemental_block else None,
    )
```

- [ ] **Step 3: 修改 `build_for_session` — 展开 `_message_to_seed_dict` 返回的 list**

当前代码:
```python
        recent_messages = [
            _message_to_seed_dict(msg) for msg in candidates
        ]
```

改为:
```python
        recent_messages: list[dict[str, Any]] = []
        for msg in candidates:
            recent_messages.extend(_message_to_seed_dict(msg))
```

- [ ] **Step 4: 添加 import**

确保 `context_assembly.py` 顶部有:
```python
from app.memory.text_compaction import truncate_head_tail
```

如果 `truncate_head_tail` 不存在，检查 `app/memory/text_compaction.py` 确认函数名。

- [ ] **Step 5: 运行测试**

Run: `cd backend && python -m pytest tests/test_memory/test_context_assembly.py -v`
Expected: 2 个测试需要更新断言（Task 6 修复）

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/context_assembly.py
git commit -m "refactor: seed assembly TOOL_TRACE→assistant(tool_calls)+tool(result) pairs"
```

---

## Task 6: 更新测试 — `test_context_assembly.py`

**Files:**
- Modify: `backend/tests/test_memory/test_context_assembly.py`

- [ ] **Step 1: 更新 `test_context_assembler_includes_completed_tool_traces_in_seed_messages`**

当前断言:
```python
    seeded_contents = [msg["content"] for msg in result.recent_messages]
    assert any("tool_name=shell" in c for c in seeded_contents)
    assert any("2 passed" in c for c in seeded_contents)
    assert "帮我修 bug" in seeded_contents
    assert "测试通过了" in seeded_contents

    tool_seed = next(msg for msg in result.recent_messages if "[tool_trace]" in msg["content"])
    assert tool_seed["role"] == "assistant"
```

改为:
```python
    seeded = result.recent_messages

    user_msg = next(m for m in seeded if m["role"] == "user")
    assert "帮我修 bug" in user_msg["content"]

    assistant_tool_msg = next(m for m in seeded if m["role"] == "assistant" and m.get("tool_calls"))
    assert assistant_tool_msg["tool_calls"][0]["name"] == "shell"
    assert assistant_tool_msg["tool_calls"][0]["arguments"] == {"cmd": "pytest"}

    tool_result_msg = next(m for m in seeded if m["role"] == "tool")
    assert tool_result_msg["tool_call_id"] == assistant_tool_msg["tool_calls"][0]["id"]
    assert "2 passed" in tool_result_msg["content"]

    assistant_text_msg = next(m for m in seeded if m["role"] == "assistant" and not m.get("tool_calls"))
    assert "测试通过了" in assistant_text_msg["content"]
```

注意：测试中创建的 TOOL_TRACE message 没有 `tool_call_id`，所以 `_tool_trace_to_paired_seeds` 会生成 fallback id。需要在创建测试数据时加入 `tool_call_id`：

```python
    message_repo.create(
        Message(
            id="msg-tool-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=2,
            role="tool",          # 改为 tool
            message_type=MessageType.TOOL_TRACE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="",
            payload_json={
                "tool_name": "shell",
                "arguments": {"cmd": "pytest"},
                "tool_call_id": "call_abc12345",   # 新增
                "success": True,
                "output": "2 passed",
            },
        )
    )
```

- [ ] **Step 2: 更新 `test_context_assembler_excludes_non_completed_tool_traces`**

当前测试创建的 TOOL_TRACE 的 `role="assistant"`，需改为 `role="tool"`。测试断言不需要改（只是验证 running/failed 状态的 TOOL_TRACE 不出现在 seed 中）。

- [ ] **Step 3: 运行测试**

Run: `cd backend && python -m pytest tests/test_memory/test_context_assembly.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_memory/test_context_assembly.py
git commit -m "test: update context_assembly tests for tool_call pairing"
```

---

## Task 7: 回放层 — `context_manager.from_run_input` 支持 tool_calls

**Files:**
- Modify: `backend/app/execution/context_manager.py`

当前问题：`from_run_input` 只处理 `content` 字符串，丢弃 `tool_calls` 和 `tool_call_id`。

- [ ] **Step 1: 修改 `from_run_input`**

当前代码:
```python
    @classmethod
    def from_run_input(
        cls,
        *,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        agent_mode: str = "build",
        seed_messages: list[dict[str, str]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
    ) -> "LoopContext":
        context = cls(task=task, project_path=project_path, run_id=run_id, agent_mode=agent_mode)

        allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        for seeded in seed_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue
            content = seeded.get("content")
            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue
            context.add_message(role, content)

        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []
        context.add_message("user", task)
        return context
```

改为:
```python
    @classmethod
    def from_run_input(
        cls,
        *,
        task: str,
        project_path: str | None = None,
        run_id: str | None = None,
        agent_mode: str = "build",
        seed_messages: list[dict[str, Any]] | None = None,
        supplemental_context: str | None = None,
        system_sections: list[str] | None = None,
    ) -> "LoopContext":
        context = cls(task=task, project_path=project_path, run_id=run_id, agent_mode=agent_mode)

        allowed_seed_roles = {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL}
        for seeded in seed_messages or []:
            if not isinstance(seeded, dict):
                continue
            role = str(seeded.get("role") or "").strip().lower()
            if role not in allowed_seed_roles:
                continue

            content = seeded.get("content")
            tool_calls = seeded.get("tool_calls")
            tool_call_id = seeded.get("tool_call_id")

            if role == "tool" and not tool_call_id:
                continue

            if role == "assistant" and tool_calls:
                content_str = content if isinstance(content, str) else None
                context.add_message(
                    role,
                    content=content_str,
                    tool_calls=tool_calls,
                )
                continue

            if not isinstance(content, str):
                continue
            content = content.strip()
            if not content:
                continue

            context.add_message(role, content, tool_call_id=tool_call_id)

        context.supplemental_context = supplemental_context
        context.system_sections = system_sections or []
        context.add_message("user", task)
        return context
```

- [ ] **Step 2: 运行现有测试**

Run: `cd backend && python -m pytest tests/test_execution/test_context_manager.py -v`
Expected: `test_from_run_input_filters_seed_messages_and_adds_current_task` 可能需要更新

- [ ] **Step 3: Commit**

```bash
git add backend/app/execution/context_manager.py
git commit -m "feat: from_run_input supports tool_calls and tool_call_id in seeds"
```

---

## Task 8: 更新测试 — `test_context_manager.py`

**Files:**
- Modify: `backend/tests/test_execution/test_context_manager.py`

- [ ] **Step 1: 更新现有测试**

当前 `test_from_run_input_filters_seed_messages_and_adds_current_task` 中 `{"role": "tool", "content": ""}` 被跳过是因为 content 为空。新逻辑中 `{"role": "tool", "content": "", "tool_call_id": None}` 也被跳过（因为 tool role 无 tool_call_id）。

但 `{"role": "tool", "content": "tool output"}` 现在没有 `tool_call_id` 也会被跳过。需要加上 `tool_call_id`：

```python
    def test_from_run_input_filters_seed_messages_and_adds_current_task(self):
        context = LoopContext.from_run_input(
            task="继续处理",
            project_path="/tmp/reflexion",
            run_id="run-123",
            seed_messages=[
                {"role": "user", "content": "上一轮需求"},
                {"role": "assistant", "content": "  上一轮结论  "},
                {"role": "system", "content": "should be ignored"},
                {"role": "tool", "content": ""},
                {"role": "tool", "content": "tool output", "tool_call_id": "call_001"},
                "bad seed",
            ],
            supplemental_context="当前目标: 修 memory",
            system_sections=["AGENTS instructions"],
        )

        assert context.task == "继续处理"
        assert context.project_path == "/tmp/reflexion"
        assert context.run_id == "run-123"
        assert context.supplemental_context == "当前目标: 修 memory"
        assert context.system_sections == ["AGENTS instructions"]
        assert [(message["role"], message.get("content")) for message in context.messages] == [
            ("user", "上一轮需求"),
            ("assistant", "上一轮结论"),
            ("tool", "tool output"),
            ("user", "继续处理"),
        ]
```

- [ ] **Step 2: 新增测试 — tool_calls seed**

```python
    def test_from_run_input_supports_tool_calls_in_seed_messages(self):
        context = LoopContext.from_run_input(
            task="继续",
            seed_messages=[
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "call_001", "name": "file", "arguments": {"action": "read", "path": "a.py"}},
                ]},
                {"role": "tool", "content": "file content here", "tool_call_id": "call_001"},
                {"role": "assistant", "content": "已读取文件"},
            ],
        )

        msgs = context.messages
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["tool_calls"][0]["name"] == "file"
        assert msgs[0].get("content") is None

        assert msgs[1]["role"] == "tool"
        assert msgs[1]["content"] == "file content here"
        assert msgs[1]["tool_call_id"] == "call_001"

        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == "已读取文件"

        assert msgs[3]["role"] == "user"
        assert msgs[3]["content"] == "继续"
```

- [ ] **Step 3: 新增测试 — tool role 无 tool_call_id 被跳过**

```python
    def test_from_run_input_skips_tool_message_without_tool_call_id(self):
        context = LoopContext.from_run_input(
            task="继续",
            seed_messages=[
                {"role": "tool", "content": "orphan tool result"},
            ],
        )

        assert len(context.messages) == 1
        assert context.messages[0]["role"] == "user"
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_execution/test_context_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_execution/test_context_manager.py
git commit -m "test: add tool_calls/tool_call_id seed tests for context_manager"
```

---

## Task 9: 更新 `message_normalizer.py` 和 `continuation_builder.py`

**Files:**
- Modify: `backend/app/memory/message_normalizer.py`
- Modify: `backend/app/memory/continuation_builder.py`

这两个文件不是 seed 路径的关键，但它们在搜索索引和 continuation artifact 中格式化 TOOL_TRACE。更新 role 标签以保持一致性。

- [ ] **Step 1: `continuation_builder._format_tool_trace` — 使用 role 值**

当前代码 (line 114):
```python
        lines = [f"[{message.role}/{message.message_type.value}]"]
```

这段代码已经使用 `message.role`，所以当 DB 中 role 从 `assistant` 变为 `tool` 后，输出会自动变为 `[tool/tool_trace]`。**无需修改此文件。**

- [ ] **Step 2: `normalize_message_text_for_seed` — 已不再用于 seed 路径**

此函数之前被 `_message_to_seed_dict` 调用，但 Task 5 重构后不再使用它做 seed 格式化。但 `normalize_message_text` 仍用于搜索索引。

检查 `normalize_message_text_for_seed` 是否还有其他调用者：

Run: `cd backend && grep -r "normalize_message_text_for_seed" --include="*.py"`

如果只在 `context_assembly.py` 中被调用，且 Task 5 已不再使用，则该函数可以标记为废弃或保留（不删，因为其他代码可能间接引用）。

- [ ] **Step 3: Commit (如果有改动)**

仅在确认有实际代码改动时才 commit。

---

## Task 10: 全量测试验证

**Files:** 无变更

- [ ] **Step 1: 运行全部后端测试**

Run: `cd backend && python -m pytest tests/ -v 2>&1 | tail -30`
Expected: 140+ tests PASS

- [ ] **Step 2: 修复任何失败测试**

逐一排查失败原因，按以上设计意图修复。常见问题：
- 其他测试中创建 TOOL_TRACE 数据仍用 `role="assistant"` — 改为 `role="tool"`
- 其他测试断言依赖 `[tool_trace]` 文本格式 — 按 Task 5 新格式更新

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "fix: align all tests with tool_call pairing refactor"
```

---

## 数据流（改造后）

```
写入层:
  rapid_loop._call_llm()
    → context.add_message("assistant", tool_calls=[{id, name, arguments}])
    → context.add_message("tool", content=result, tool_call_id=id)
    → ToolCallExecutor.emit("tool:start", {tool_name, arguments, tool_call_id, step_number})
    → ToolCallExecutor.emit("tool:result", {output, success, tool_call_id, ...})

  conversation_runtime_adapter
    → tool:start: _tool_start_events() 创建 Message(role="tool", type=TOOL_TRACE)
    → tool:result: _tool_result_events() 更新 TOOL_TRACE payload (output, success, ...)

DB:
  messages 表:
    USER_MESSAGE:      role="user",      content_text="帮我修 bug"
    TOOL_TRACE:        role="tool",       content_text="",  payload={tool_name, arguments, tool_call_id, output, ...}
    ASSISTANT_MESSAGE: role="assistant",  content_text="已修复"

回放层:
  list_recent_seed_candidates()
    → 按 created_at 合并排序所有 USER/ASSISTANT/TOOL_TRACE

  _message_to_seed_dict()
    → USER_MESSAGE:      [{role: "user", content: "帮我修 bug"}]
    → TOOL_TRACE:        [{role: "assistant", content: "", tool_calls: [{id, name, arguments}]},
                          {role: "tool", content: "output...", tool_call_id: id}]
    → ASSISTANT_MESSAGE: [{role: "assistant", content: "已修复"}]

  LoopContext.from_run_input()
    → 支持所有三种 role + tool_calls + tool_call_id

  LoopMessageBuilder.build()
    → 标准格式发送给 LLM API
```

## 不改动的部分

- continuation artifact 机制不变
- midrun compaction 不变
- 前端渲染不变（按 messageType 不按 role）
- rapid_loop 运行时消息处理不变
