# Agent Memory Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不推翻现有 conversation 架构的前提下，落地一个以 `messages` 为主读取面的 Phase 1 记忆系统，支持项目级 curated memory、message-centric recall、以及由文本压缩直接生成的 continuation artifact。

**Architecture:** 这次实现不新增第二套事实源，所有运行时工作记忆都围绕 `messages` 展开，`turns / runs / sessions` 只做状态补充，`conversation_events` 只保留为同步日志。运行时上下文装配严格分为三层：`Static Context Pack`、`Recent Conversation Pack`、`Supplemental Context Pack`，其中 supplemental 只来自 `continuation artifact` 或 `recall result`。

**Tech Stack:** FastAPI, Python, SQLAlchemy, SQLite, Pydantic, pytest

---

## Planned File Structure

### New files

- `backend/app/memory/__init__.py`
  - memory 模块导出
- `backend/app/memory/message_normalizer.py`
  - 将不同 `message_type` 规范化成可检索、可压缩、可审阅文本
- `backend/app/memory/curated_store.py`
  - 项目级 `USER.md / MEMORY.md` entry store、序列化、drift check
- `backend/app/memory/context_assembly.py`
  - 三层上下文装配：static/recent/supplemental
- `backend/app/memory/continuation.py`
  - continuation artifact 生成与读取约定
- `backend/app/memory/recall_service.py`
  - 基于 `messages` 的 recall 查询、ranking、结果格式化
- `backend/app/tools/memory_tool.py`
  - 写 curated memory 的 LLM tool
- `backend/app/tools/recall_tool.py`
  - 按需触发 conversation recall 的 LLM tool
- `backend/tests/test_memory/test_message_normalizer.py`
- `backend/tests/test_memory/test_curated_store.py`
- `backend/tests/test_memory/test_context_assembly.py`
- `backend/tests/test_memory/test_continuation.py`
- `backend/tests/test_memory/test_recall_service.py`
- `backend/tests/test_tools/test_memory_tool.py`
- `backend/tests/test_tools/test_recall_tool.py`

### Modified files

- `backend/app/storage/models.py`
  - 新增 `message_search_documents` 派生索引表
- `backend/app/storage/repositories/message_repo.py`
  - 提供按 `turn.turn_index + turn_message_index` 排序的读取接口
- `backend/app/services/conversation_projection.py`
  - 在 message create/update 时同步 recall 派生索引
- `backend/app/execution/context_manager.py`
  - 支持 session history / supplemental context 注入
- `backend/app/execution/rapid_loop.py`
  - 接入三层 memory assembly、continuation 生成、recall tool
- `backend/app/execution/prompt_manager.py`
  - system prompt 增加 memory/recall 使用规则
- `backend/app/services/agent_service.py`
  - 在 `_run_turn()` 中为 loop 装配历史 message、静态 memory、supplemental context
- `backend/app/tools/registry.py`
  - 注册新的 `memory` / `recall` 工具
- `backend/app/config/settings.py`
  - 增加记忆系统阈值与路径设置
- `backend/tests/test_execution/test_rapid_loop.py`
- `backend/tests/test_services/test_agent_service.py`
- `backend/tests/test_services/test_conversation_projection.py`
- `backend/tests/test_storage/test_conversation_repositories.py`

---

### Task 1: Message-Centric Reading Foundation

**Files:**
- Create: `backend/app/memory/message_normalizer.py`
- Modify: `backend/app/storage/repositories/message_repo.py`
- Test: `backend/tests/test_memory/test_message_normalizer.py`
- Test: `backend/tests/test_storage/test_conversation_repositories.py`

- [ ] **Step 1: Write the failing tests for message normalization and ordering**

```python
from app.memory.message_normalizer import normalize_message_text
from app.models.conversation import Message, MessageType, StreamState


def build_message(**overrides):
    payload = {
        "id": "msg-1",
        "session_id": "session-1",
        "turn_id": "turn-1",
        "run_id": "run-1",
        "turn_message_index": 1,
        "role": "assistant",
        "message_type": MessageType.ASSISTANT_MESSAGE,
        "stream_state": StreamState.COMPLETED,
        "display_mode": "default",
        "content_text": "hello",
        "payload_json": {},
    }
    payload.update(overrides)
    return Message(**payload)


def test_normalize_message_text_uses_content_for_assistant_messages():
    message = build_message(content_text="最终答案")
    assert normalize_message_text(message) == "最终答案"


def test_normalize_message_text_expands_tool_trace_payload():
    message = build_message(
        message_type=MessageType.TOOL_TRACE,
        content_text="",
        payload_json={
            "tool_name": "shell",
            "arguments": {"cmd": "pytest -q"},
            "success": False,
            "output": "",
            "error": "exit status 1",
        },
    )
    normalized = normalize_message_text(message)
    assert "shell" in normalized
    assert "pytest -q" in normalized
    assert "exit status 1" in normalized


def test_list_by_session_orders_by_turn_then_turn_message_index(conversation_db):
    messages = conversation_db.seed_two_turns_out_of_timestamp_order()
    ordered_ids = [message.id for message in conversation_db.message_repo.list_by_session("session-1")]
    assert ordered_ids == ["msg-turn1-1", "msg-turn1-2", "msg-turn2-1"]
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_message_normalizer.py tests/test_storage/test_conversation_repositories.py -q
```

Expected:

- `ModuleNotFoundError: No module named 'app.memory.message_normalizer'`
- or ordering assertion failure because `list_by_session()` still sorts by `created_at`

- [ ] **Step 3: Implement the normalizer and deterministic session ordering**

```python
# backend/app/memory/message_normalizer.py
from __future__ import annotations

import json

from app.models.conversation import Message, MessageType


def normalize_message_text(message: Message) -> str:
    if message.message_type in {MessageType.USER_MESSAGE, MessageType.ASSISTANT_MESSAGE}:
        return message.content_text.strip()

    if message.message_type == MessageType.SYSTEM_NOTICE:
        notice_code = message.payload_json.get("notice_code")
        parts = [message.content_text.strip()]
        if notice_code:
            parts.append(f"notice_code={notice_code}")
        return "\n".join(part for part in parts if part)

    if message.message_type == MessageType.TOOL_TRACE:
        payload = message.payload_json
        lines = [f"tool_name={payload.get('tool_name', '')}"]
        if payload.get("arguments") is not None:
            lines.append(f"arguments={json.dumps(payload['arguments'], ensure_ascii=False, sort_keys=True)}")
        if payload.get("success") is not None:
            lines.append(f"success={payload['success']}")
        if payload.get("output"):
            lines.append(f"output={payload['output']}")
        if payload.get("error"):
            lines.append(f"error={payload['error']}")
        return "\n".join(line for line in lines if line.strip())

    return message.content_text.strip()
```

```python
# backend/app/storage/repositories/message_repo.py
def list_by_session(self, session_id: str) -> list[Message]:
    with self.db.get_session() as db_session:
        models = (
            db_session.query(MessageModel, TurnModel.turn_index)
            .join(TurnModel, TurnModel.id == MessageModel.turn_id)
            .filter(MessageModel.session_id == session_id)
            .order_by(TurnModel.turn_index.asc(), MessageModel.turn_message_index.asc(), MessageModel.created_at.asc())
            .all()
        )
        return [Message.model_validate(model) for model, _turn_index in models]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_message_normalizer.py tests/test_storage/test_conversation_repositories.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit the foundation**

```bash
git add backend/app/memory/message_normalizer.py backend/app/storage/repositories/message_repo.py backend/tests/test_memory/test_message_normalizer.py backend/tests/test_storage/test_conversation_repositories.py
git commit -m "feat: add message-centric normalization foundation"
```

### Task 2: Add Derived Recall Search Documents

**Files:**
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/services/conversation_projection.py`
- Test: `backend/tests/test_services/test_conversation_projection.py`
- Test: `backend/tests/test_memory/test_recall_service.py`

- [ ] **Step 1: Write the failing tests for derived search document sync**

```python
def test_message_created_populates_search_document(conversation_service):
    started = conversation_service.start_turn(
        session_id="session-1",
        content="请检查 memory 设计",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref="/tmp/project",
    )
    snapshot = conversation_service.get_snapshot("session-1")
    user_message = next(message for message in snapshot.messages if message.id == started.user_message.id)

    document = conversation_service.message_search_repo.get(user_message.id)

    assert document is not None
    assert document.session_id == "session-1"
    assert "请检查 memory 设计" in document.search_text


def test_message_payload_update_refreshes_tool_trace_search_text(service, runtime_adapter):
    runtime_adapter.handle_event("tool:start", {"tool_name": "shell", "arguments": {"cmd": "pytest -q"}, "step_number": 1})
    runtime_adapter.handle_event("tool:error", {"tool_name": "shell", "step_number": 1, "error": "exit status 1"})

    trace = next(message for message in service.get_snapshot("session-1").messages if message.message_type.value == "tool_trace")
    document = service.message_search_repo.get(trace.id)
    assert "pytest -q" in document.search_text
    assert "exit status 1" in document.search_text
```

- [ ] **Step 2: Run the tests and verify they fail because the derived index does not exist**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_services/test_conversation_projection.py tests/test_memory/test_recall_service.py -q
```

Expected:

- repository/model import failure for `message_search_repo`
- or `AttributeError` because projection does not maintain derived search documents

- [ ] **Step 3: Add the derived search document table and projection sync**

```python
# backend/app/storage/models.py
class MessageSearchDocumentModel(Base):
    __tablename__ = "message_search_documents"

    message_id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    turn_id = Column(String, nullable=False, index=True)
    run_id = Column(String, index=True)
    role = Column(String, nullable=False, index=True)
    message_type = Column(String, nullable=False, index=True)
    turn_index = Column(Integer, nullable=False, index=True)
    turn_message_index = Column(Integer, nullable=False)
    search_text = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
```

```python
# backend/app/services/conversation_projection.py
from app.memory.message_normalizer import normalize_message_text

def _upsert_search_document(self, message: Message, turn: Turn, *, db_session=None) -> None:
    self.message_search_repo.upsert(
        message_id=message.id,
        session_id=message.session_id,
        turn_id=message.turn_id,
        run_id=message.run_id,
        role=message.role,
        message_type=message.message_type.value,
        turn_index=turn.turn_index,
        turn_message_index=message.turn_message_index,
        search_text=normalize_message_text(message),
        db_session=db_session,
    )
```

- [ ] **Step 4: Run the tests and confirm the derived search documents stay in sync**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_services/test_conversation_projection.py tests/test_memory/test_recall_service.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit the derived index layer**

```bash
git add backend/app/storage/models.py backend/app/services/conversation_projection.py backend/tests/test_services/test_conversation_projection.py backend/tests/test_memory/test_recall_service.py
git commit -m "feat: add derived message search documents"
```

### Task 3: Implement Curated Memory Store and Drift Checker

**Files:**
- Create: `backend/app/memory/curated_store.py`
- Create: `backend/app/tools/memory_tool.py`
- Modify: `backend/app/tools/registry.py`
- Modify: `backend/app/config/settings.py`
- Test: `backend/tests/test_memory/test_curated_store.py`
- Test: `backend/tests/test_tools/test_memory_tool.py`

- [ ] **Step 1: Write the failing tests for entry schema, file rendering, and drift detection**

```python
from app.memory.curated_store import CuratedEntry, CuratedMemoryStore


def test_add_user_preference_renders_markdown(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    store.add_entry(
        project_id="project-1",
        entry=CuratedEntry(
            target="user",
            type="preference",
            scope="project",
            source="user_explicit",
            confidence="high",
            status="active",
            source_refs=["msg-1"],
            summary="默认使用中文回复。",
        ),
    )

    rendered = (tmp_path / "projects" / "project-1" / "USER.md").read_text(encoding="utf-8")
    assert "默认使用中文回复。" in rendered


def test_add_entry_returns_conflict_when_active_rule_disagrees(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    first = CuratedEntry(
        target="memory",
        type="constraint",
        scope="project",
        source="derived",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认不要直接写入用户仓库。",
    )
    store.add_entry(project_id="project-1", entry=first)

    second = first.model_copy(update={"summary": "默认直接写入用户仓库。", "source_refs": ["msg-2"]})
    result = store.add_entry(project_id="project-1", entry=second)

    assert result.conflict is True
    assert result.conflicting_entry.summary == "默认不要直接写入用户仓库。"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_curated_store.py tests/test_tools/test_memory_tool.py -q
```

Expected:

- `ModuleNotFoundError` for curated store / memory tool modules

- [ ] **Step 3: Implement entry-based curated memory with markdown rendering**

```python
# backend/app/memory/curated_store.py
class CuratedEntry(BaseModel):
    target: Literal["user", "memory"]
    type: Literal["preference", "rule", "constraint", "fact"]
    scope: Literal["project", "global"]
    source: Literal["user_explicit", "user_implied", "derived"]
    confidence: Literal["high", "medium"]
    status: Literal["active", "superseded"] = "active"
    source_refs: list[str] = Field(default_factory=list)
    summary: str
    updated_at: datetime = Field(default_factory=datetime.now)


class CuratedMemoryStore:
    def add_entry(self, *, project_id: str, entry: CuratedEntry) -> CuratedWriteResult:
        conflict = self._find_conflict(project_id=project_id, entry=entry)
        if conflict:
            return CuratedWriteResult(success=False, conflict=True, conflicting_entry=conflict)
        entries = self.load_entries(project_id=project_id, target=entry.target)
        entries.append(entry)
        self.save_entries(project_id=project_id, target=entry.target, entries=entries)
        self.render_to_markdown(project_id=project_id, target=entry.target, entries=entries)
        return CuratedWriteResult(success=True, conflict=False, conflicting_entry=None)

    def render_markdown(self, *, project_id: str, target: str) -> str:
        entries = self.load_entries(project_id=project_id, target=target)
        title = "USER" if target == "user" else "MEMORY"
        lines = [f"# {title}", ""]
        for entry in entries:
            if entry.status != "active":
                continue
            lines.append(f"- [{entry.type}] {entry.summary}")
        return "\n".join(lines).strip() + "\n"
```

```python
# backend/app/tools/memory_tool.py
class MemoryTool(BaseTool):
    @property
    def name(self) -> str:
        return "memory"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args["action"]
        if action == "add":
            result = self.store.add_entry(
                project_id=args["project_id"],
                entry=CuratedEntry(**args["entry"]),
            )
            return ToolResult(success=result.success, data=result.model_dump(mode="json"))
        if action == "replace":
            result = self.store.replace_entry(
                project_id=args["project_id"],
                target=args["target"],
                old_summary=args["old_summary"],
                entry=CuratedEntry(**args["entry"]),
            )
            return ToolResult(success=result.success, data=result.model_dump(mode="json"))
        if action == "remove":
            removed = self.store.remove_entry(
                project_id=args["project_id"],
                target=args["target"],
                summary=args["summary"],
            )
            return ToolResult(success=removed, data={"removed": removed})
        return ToolResult(success=False, error=f"unsupported memory action: {action}")
```

- [ ] **Step 4: Run the tests and confirm the store and tool behavior**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_curated_store.py tests/test_tools/test_memory_tool.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit curated memory support**

```bash
git add backend/app/memory/curated_store.py backend/app/tools/memory_tool.py backend/app/tools/registry.py backend/app/config/settings.py backend/tests/test_memory/test_curated_store.py backend/tests/test_tools/test_memory_tool.py
git commit -m "feat: add curated memory store and drift checker"
```

### Task 4: Implement Recall Service and Recall Tool

**Files:**
- Create: `backend/app/memory/recall_service.py`
- Create: `backend/app/tools/recall_tool.py`
- Modify: `backend/app/tools/registry.py`
- Test: `backend/tests/test_memory/test_recall_service.py`
- Test: `backend/tests/test_tools/test_recall_tool.py`

- [ ] **Step 1: Write the failing tests for ranking and scope filtering**

```python
def test_recall_service_prefers_recent_user_decision_messages(recall_service):
    recall_service.seed_document(
        message_id="msg-old",
        project_id="project-1",
        session_id="session-old",
        role="assistant",
        message_type="assistant_message",
        search_text="memory design used event replay",
        turn_index=1,
        turn_message_index=2,
        created_at="2026-04-01T10:00:00",
    )
    recall_service.seed_document(
        message_id="msg-new",
        project_id="project-1",
        session_id="session-new",
        role="user",
        message_type="user_message",
        search_text="当前记忆部分应该是从messages表里面拿数据",
        turn_index=3,
        turn_message_index=1,
        created_at="2026-04-28T10:00:00",
    )

    results = recall_service.search(project_id="project-1", query="messages 表 记忆", limit=3)

    assert results[0].message_id == "msg-new"


def test_recall_tool_returns_summary_and_evidence(recall_tool):
    result = asyncio.run(recall_tool.execute({"query": "messages 表", "project_id": "project-1", "limit": 3}))
    assert result.success is True
    assert "results" in result.data
    assert "evidence" in result.data["results"][0]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_recall_service.py tests/test_tools/test_recall_tool.py -q
```

Expected:

- missing recall service/tool implementations

- [ ] **Step 3: Implement recall search, ranking, and tool output contract**

```python
# backend/app/memory/recall_service.py
class RecallResult(BaseModel):
    message_id: str
    session_id: str
    score: float
    summary: str
    evidence: list[str]


class RecallService:
    def search(self, *, project_id: str, query: str, limit: int = 3) -> list[RecallResult]:
        documents = self.message_search_repo.search(project_id=project_id, query=query, limit=50)
        ranked = sorted(documents, key=self._score_document, reverse=True)
        return [self._to_result(document) for document in ranked[:limit]]

    def _score_document(self, document) -> float:
        role_boost = 2.0 if document.role == "user" else 1.0
        type_boost = 1.5 if document.message_type in {"user_message", "system_notice"} else 1.0
        age_days = max((self.now() - document.created_at).days, 0)
        recency_boost = max(0.5, 1.5 - min(age_days, 30) * 0.03)
        return document.match_score * role_boost * type_boost * recency_boost
```

```python
# backend/app/tools/recall_tool.py
class RecallTool(BaseTool):
    @property
    def name(self) -> str:
        return "recall"

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        results = self.recall_service.search(
            project_id=args["project_id"],
            query=args["query"],
            limit=args.get("limit", 3),
        )
        return ToolResult(
            success=True,
            data={"results": [result.model_dump(mode="json") for result in results]},
            output="\n\n".join(result.summary for result in results),
        )
```

- [ ] **Step 4: Run the recall tests and confirm they pass**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_recall_service.py tests/test_tools/test_recall_tool.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit recall support**

```bash
git add backend/app/memory/recall_service.py backend/app/tools/recall_tool.py backend/app/tools/registry.py backend/tests/test_memory/test_recall_service.py backend/tests/test_tools/test_recall_tool.py
git commit -m "feat: add message-centric recall service"
```

### Task 5: Implement Continuation Artifact Generation

**Files:**
- Create: `backend/app/memory/continuation.py`
- Modify: `backend/app/services/conversation_projection.py`
- Modify: `backend/app/models/conversation.py`
- Test: `backend/tests/test_memory/test_continuation.py`
- Test: `backend/tests/test_services/test_conversation_projection.py`

- [ ] **Step 1: Write the failing tests for continuation artifact creation and exclusion from recall**

```python
def test_build_continuation_artifact_from_messages():
    artifact = build_continuation_artifact(
        messages=[
            build_user_message("继续设计 memory 系统"),
            build_assistant_message("先把 runtime 三层收敛"),
            build_tool_trace("shell", {"cmd": "rg memory"}, success=True, output="docs/spec.md"),
        ],
        active_goal="把 message-centric 设计写清楚",
    )

    assert "当前目标" in artifact.content_text
    assert "继续设计 memory 系统" in artifact.content_text
    assert artifact.payload_json["kind"] == "continuation_artifact"
    assert artifact.payload_json["exclude_from_recall"] is True


def test_continuation_message_is_not_indexed_for_recall(projection_service):
    artifact = build_continuation_artifact(
        session_id="session-1",
        turn_id="turn-1",
        messages=[build_user_message("继续设计 memory 系统")],
        active_goal="继续设计 recall",
    )
    projection_service.append_continuation_artifact(artifact)
    assert projection_service.message_search_repo.get("msg-cont-1") is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_continuation.py tests/test_services/test_conversation_projection.py -q
```

Expected:

- continuation builder missing
- or projection still indexes derived continuation messages

- [ ] **Step 3: Implement continuation artifacts as derived system notices**

```python
# backend/app/memory/continuation.py
def build_continuation_artifact(*, session_id: str, turn_id: str, messages: list[Message], active_goal: str) -> Message:
    content = "\n".join([
        "当前目标: " + active_goal,
        "已确认事实: " + summarize_confirmed_facts(messages),
        "未解决点: " + summarize_open_items(messages),
        "下一步建议: " + summarize_next_action(messages),
    ])
    return Message(
        id=f"msg-cont-{uuid4().hex[:8]}",
        session_id=session_id,
        turn_id=turn_id,
        run_id=None,
        turn_message_index=9999,
        role="system",
        message_type=MessageType.SYSTEM_NOTICE,
        stream_state=StreamState.COMPLETED,
        display_mode="collapsed",
        content_text=content,
        payload_json={
            "kind": "continuation_artifact",
            "derived": True,
            "exclude_from_recall": True,
            "exclude_from_memory_promotion": True,
        },
    )
```

- [ ] **Step 4: Run the continuation tests and verify they pass**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_continuation.py tests/test_services/test_conversation_projection.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit continuation support**

```bash
git add backend/app/memory/continuation.py backend/app/services/conversation_projection.py backend/app/models/conversation.py backend/tests/test_memory/test_continuation.py backend/tests/test_services/test_conversation_projection.py
git commit -m "feat: add continuation artifact generation"
```

### Task 6: Wire Three-Layer Context Assembly into Agent Execution

**Files:**
- Create: `backend/app/memory/context_assembly.py`
- Modify: `backend/app/execution/context_manager.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/app/execution/prompt_manager.py`
- Modify: `backend/app/services/agent_service.py`
- Test: `backend/tests/test_memory/test_context_assembly.py`
- Test: `backend/tests/test_execution/test_rapid_loop.py`
- Test: `backend/tests/test_services/test_agent_service.py`

- [ ] **Step 1: Write the failing tests for static/recent/supplemental assembly**

```python
def test_context_assembly_builds_static_recent_and_supplemental_layers():
    result = build_context_assembly(
        static_blocks=["AGENTS", "USER", "MEMORY"],
        recent_messages=[{"role": "user", "content": "最近消息"}],
        supplemental_block="当前目标: 继续实现 recall",
    )

    assert "AGENTS" in result.system_sections[0]
    assert result.recent_messages[0]["content"] == "最近消息"
    assert result.supplemental_block == "当前目标: 继续实现 recall"


@pytest.mark.asyncio
async def test_rapid_loop_includes_seeded_history_before_current_user_message(execution_loop, mock_llm):
    captured = {}

    async def mock_stream(messages, tools=None):
        captured["messages"] = messages
        async for chunk in TestRapidExecutionLoop._stream_response(content="ok"):
            yield chunk

    mock_llm.stream_complete = mock_stream

    await execution_loop.run(
        "继续处理",
        seed_messages=[
            {"role": "user", "content": "上一轮需求"},
            {"role": "assistant", "content": "上一轮结论"},
        ],
        supplemental_context="当前目标: 修 memory",
    )

    contents = [message.content for message in captured["messages"] if message.content]
    assert contents.index("上一轮需求") < contents.index("继续处理")
    assert any("当前目标: 修 memory" in content for content in contents)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_context_assembly.py tests/test_execution/test_rapid_loop.py tests/test_services/test_agent_service.py -q
```

Expected:

- `run()` does not accept `seed_messages` / `supplemental_context`
- no context assembly module exists

- [ ] **Step 3: Implement context assembly and loop integration**

```python
# backend/app/memory/context_assembly.py
class ContextAssemblyResult(BaseModel):
    system_sections: list[str]
    recent_messages: list[dict[str, str]]
    supplemental_block: str | None = None


def build_context_assembly(*, static_blocks: list[str], recent_messages: list[dict], supplemental_block: str | None) -> ContextAssemblyResult:
    return ContextAssemblyResult(
        system_sections=[block for block in static_blocks if block.strip()],
        recent_messages=recent_messages,
        supplemental_block=supplemental_block.strip() if supplemental_block else None,
    )
```

```python
# backend/app/execution/rapid_loop.py
async def run(
    self,
    task: str,
    project_path: str | None = None,
    run_id: str | None = None,
    created_at: datetime | None = None,
    seed_messages: list[dict[str, str]] | None = None,
    supplemental_context: str | None = None,
    system_sections: list[str] | None = None,
) -> LoopResult:
    loop_result = LoopResult(
        id=run_id or f"run-{uuid.uuid4().hex[:8]}",
        task=task,
        status=LoopStatus.RUNNING,
        created_at=created_at or datetime.now(),
    )
    context = LoopContext(task=task, project_path=project_path, run_id=loop_result.id)
    for seeded in seed_messages or []:
        context.add_message(seeded["role"], seeded.get("content"))
    context.supplemental_context = supplemental_context
    context.system_sections = system_sections or []
    context.add_message("user", task)
    await self._emit("run:start", {"run_id": loop_result.id, "task": task})
    response = await self._call_llm(context)
```

```python
# backend/app/services/agent_service.py
assembly = self.context_assembler.build_for_session(session_id=session_id, current_user_input=task)

await execution_loop.run(
    task=task,
    project_path=project_path,
    run_id=run_id,
    seed_messages=assembly.recent_messages,
    supplemental_context=assembly.supplemental_block,
    system_sections=assembly.system_sections,
)
```

- [ ] **Step 4: Run the integration tests and confirm the three-layer assembly works**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest tests/test_memory/test_context_assembly.py tests/test_execution/test_rapid_loop.py tests/test_services/test_agent_service.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit the execution integration**

```bash
git add backend/app/memory/context_assembly.py backend/app/execution/context_manager.py backend/app/execution/rapid_loop.py backend/app/execution/prompt_manager.py backend/app/services/agent_service.py backend/tests/test_memory/test_context_assembly.py backend/tests/test_execution/test_rapid_loop.py backend/tests/test_services/test_agent_service.py
git commit -m "feat: wire three-layer memory assembly into execution"
```

### Task 7: End-to-End Verification and Documentation

**Files:**
- Modify: `backend/README.md`
- Modify: `docs/README.md`
- Test: `backend/tests/test_api/test_conversation_websocket.py`
- Test: `backend/tests/test_api/test_conversation_api.py`

- [ ] **Step 1: Write the failing end-to-end test for resumed session context**

```python
@pytest.mark.asyncio
async def test_resumed_session_rehydrates_recent_messages_and_curated_memory(client_with_services):
    service = client_with_services.agent_service
    await service.start_turn(
        project_id="project-1",
        session_id="session-1",
        content="请记住默认使用中文回复",
        provider_id="provider-a",
        model_id="model-a",
    )

    snapshot = client_with_services.conversation_service.get_snapshot("session-1")
    assert any(message.content_text for message in snapshot.messages)
    assert client_with_services.curated_memory_store.load_user_markdown("project-1")
```

- [ ] **Step 2: Run the full targeted suite and confirm failures identify the remaining gaps**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest \
  tests/test_memory \
  tests/test_tools/test_memory_tool.py \
  tests/test_tools/test_recall_tool.py \
  tests/test_execution/test_rapid_loop.py \
  tests/test_services/test_agent_service.py \
  tests/test_api/test_conversation_api.py \
  tests/test_api/test_conversation_websocket.py -q
```

Expected:

- Any remaining failures should point to missing wiring only, not missing architecture pieces

- [ ] **Step 3: Update backend docs for the new memory pipeline**

```markdown
## Memory Phase 1

- `messages` is the primary reading surface for runtime memory
- `conversation_events` remains the append-only sync log
- curated memory lives under `~/.reflexion/memories/projects/<project_id>/`
- recall reads from normalized message search documents
- continuation artifacts are derived system notices created from compaction
```

- [ ] **Step 4: Re-run the full targeted suite and confirm green**

Run:

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend
pytest \
  tests/test_memory \
  tests/test_tools/test_memory_tool.py \
  tests/test_tools/test_recall_tool.py \
  tests/test_execution/test_rapid_loop.py \
  tests/test_services/test_agent_service.py \
  tests/test_api/test_conversation_api.py \
  tests/test_api/test_conversation_websocket.py -q
```

Expected:

- All tests PASS

- [ ] **Step 5: Commit the verified Phase 1 slice**

```bash
git add backend/README.md docs/README.md backend/tests/test_api/test_conversation_api.py backend/tests/test_api/test_conversation_websocket.py
git commit -m "docs: document phase1 agent memory pipeline"
```

---

## Self-Review

### Spec coverage check

- `messages` 作为主读取面：Task 1、Task 2、Task 4、Task 6
- `USER.md / MEMORY.md` 作为 curated memory：Task 3
- `continuation artifact = 文本压缩产物`：Task 5、Task 6
- `recall` 只从 `messages` 派生索引读取：Task 2、Task 4
- 三层 runtime assembly：Task 6
- drift checker：Task 3

### Placeholder scan

- 没有使用 `TBD` / `TODO`
- 每个代码步骤都给了目标代码片段
- 每个测试步骤都给了具体命令和预期

### Type consistency check

- 主表读取统一围绕 `Message`
- 规范化接口统一使用 `normalize_message_text(message)`
- recall 统一通过 `RecallService.search(project_id, query, limit)`
- curated memory 统一通过 `CuratedEntry / CuratedMemoryStore`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-agent-memory-phase1-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
