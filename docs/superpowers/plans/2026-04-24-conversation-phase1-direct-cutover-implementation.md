# Conversation Phase 1 Direct Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy `executions + conversations + rounds` conversation flow with the Phase 1 `Session + Turn + Run + Event + Projection + Message` architecture defined in the approved design spec.

**Architecture:** The backend becomes event-first: session-scoped `ConversationEvent` entries are the only runtime write truth, a deterministic projection updates `Session / Turn / Run / Message`, and the frontend reads `snapshot + afterSeq` instead of `history + overlay`. The cutover is direct: old execution persistence, transcript aggregation, execution websocket, and `rounds`-based frontend state are removed in the same rollout.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, React 18, Zustand, Axios, WebSocket, pytest, Vitest, pnpm

---

## Inputs

- Spec: `docs/superpowers/specs/2026-04-24-conversation-phase1-direct-cutover-design.md`
- Existing backend entrypoints: `backend/app/services/agent_service.py`, `backend/app/execution/rapid_loop.py`, `backend/app/api/routes/sessions.py`, `backend/app/api/routes/websocket.py`
- Existing frontend entrypoints: `frontend/src/pages/AgentWorkspace.tsx`, `frontend/src/hooks/useExecutionRuntime.ts`, `frontend/src/hooks/useCurrentSessionViewModel.ts`, `frontend/src/features/sessions/sessionApi.ts`

## Preflight

Execute the plan in a dedicated worktree before touching product code:

```bash
git worktree add ../ReflexionOS-conversation-phase1 -b codex/conversation-phase1
cd ../ReflexionOS-conversation-phase1
```

Capture the current baseline before starting:

```bash
cd backend && pytest tests/test_api/test_sessions_api.py tests/test_services/test_agent_service.py -q
cd ../frontend && pnpm test -- src/hooks/useExecutionRuntime.test.ts src/hooks/useSendMessage.test.ts
```

## File Structure

### Backend create

- `backend/app/models/conversation.py`: `Turn` / `Run` / `Message` / `ConversationEvent` domain models and enums
- `backend/app/models/conversation_snapshot.py`: snapshot DTOs for `GET /api/sessions/{session_id}/conversation`
- `backend/app/storage/repositories/turn_repo.py`: CRUD for `Turn`
- `backend/app/storage/repositories/run_repo.py`: CRUD for `Run`
- `backend/app/storage/repositories/message_repo.py`: CRUD for `Message`
- `backend/app/storage/repositories/conversation_event_repo.py`: append/list logic for `ConversationEvent`
- `backend/app/services/conversation_projection.py`: deterministic `Event -> Session / Turn / Run / Message` projector
- `backend/app/services/conversation_service.py`: start turn, list snapshot, list events after seq, cancel run
- `backend/app/services/conversation_runtime_adapter.py`: translate raw `rapid_loop` callbacks into standard conversation events
- `backend/tests/test_storage/test_conversation_repositories.py`: repository and schema regression tests
- `backend/tests/test_services/test_conversation_projection.py`: projector behavior tests
- `backend/tests/test_services/test_conversation_service.py`: snapshot and lifecycle tests
- `backend/tests/test_services/test_conversation_runtime_adapter.py`: raw runtime event translation tests
- `backend/tests/test_api/test_conversation_api.py`: snapshot endpoint tests
- `backend/tests/test_api/test_conversation_websocket.py`: session websocket tests

### Backend modify

- `backend/app/models/session.py`: add `last_event_seq` and `active_turn_id`
- `backend/app/models/__init__.py`: export new conversation models
- `backend/app/storage/models.py`: replace `ExecutionModel` / `ConversationModel` with `TurnModel` / `RunModel` / `MessageModel` / `ConversationEventModel`; extend `SessionModel`
- `backend/app/storage/database.py`: direct schema reset for legacy execution/transcript tables
- `backend/app/storage/repositories/session_repo.py`: persist new session fields
- `backend/app/storage/repositories/__init__.py`: export new repositories
- `backend/app/services/agent_service.py`: replace execution persistence with run lifecycle and conversation service integration
- `backend/app/execution/rapid_loop.py`: stop building transcript history; emit raw runtime events keyed by `run_id`
- `backend/app/api/routes/sessions.py`: add `GET /api/sessions/{session_id}/conversation`, remove `/history`
- `backend/app/api/routes/websocket.py`: replace execution websocket with session conversation websocket
- `backend/app/api/websocket.py`: session-scoped connection manager and broadcast helpers
- `backend/app/main.py`: remove legacy agent router, keep sessions + websocket + project + settings routes
- `backend/tests/test_api/test_sessions_api.py`: retain session CRUD tests, drop history assertions, add snapshot field assertions
- `backend/tests/test_services/test_agent_service.py`: replace `ExecutionCreate` scenarios with `start_turn` / `cancel_run` scenarios
- `backend/tests/test_execution/test_rapid_loop.py`: update callback expectations from `execution:*` to raw runtime callback contract

### Backend delete

- `backend/app/models/execution.py`
- `backend/app/models/transcript.py`
- `backend/app/models/session_history.py`
- `backend/app/storage/repositories/execution_repo.py`
- `backend/app/storage/repositories/conversation_repo.py`
- `backend/app/services/transcript_service.py`
- `backend/app/api/routes/agent.py`

### Frontend create

- `frontend/src/types/conversation.ts`: snapshot, event, entity, and UI-facing conversation types
- `frontend/src/features/conversation/conversationApi.ts`: `GET /conversation` request mapping
- `frontend/src/features/conversation/conversationReducer.ts`: snapshot import + event apply functions
- `frontend/src/features/conversation/conversationStore.ts`: Zustand store for normalized conversation state
- `frontend/src/features/conversation/conversationSelectors.ts`: derived ordering and render helpers
- `frontend/src/services/sessionConversationWebSocket.ts`: session-scoped websocket client
- `frontend/src/hooks/useConversationData.ts`: load snapshot when session changes
- `frontend/src/hooks/useConversationRuntime.ts`: manage websocket sync/start/cancel/resync behavior
- `frontend/src/components/workspace/ToolTraceCard.tsx`: collapsed tool trace renderer
- `frontend/src/features/conversation/conversationReducer.test.ts`
- `frontend/src/features/conversation/conversationStore.test.ts`
- `frontend/src/features/conversation/conversationApi.test.ts`
- `frontend/src/hooks/useConversationRuntime.test.ts`
- `frontend/src/components/workspace/ToolTraceCard.test.tsx`

### Frontend modify

- `frontend/src/services/apiClient.ts`: remove `agentApi.cancel`, add conversation cancel helper
- `frontend/src/services/runtimeConfig.ts`: add session conversation websocket URL builder
- `frontend/src/types/workspace.ts`: keep `SessionSummary` and session payloads only; remove round/history item types
- `frontend/src/features/sessions/sessionApi.ts`: keep session CRUD only, remove history loader
- `frontend/src/features/sessions/sessionStore.ts`: store session summaries only
- `frontend/src/hooks/useSendMessage.ts`: call `startTurn` instead of `startExecutionRun`
- `frontend/src/hooks/useCurrentSessionViewModel.ts`: derive render items from normalized conversation entities
- `frontend/src/components/workspace/WorkspaceTranscript.tsx`: render `user_message` / `assistant_message` / `tool_trace` / `system_notice`
- `frontend/src/pages/AgentWorkspace.tsx`: swap `useExecutionRuntime` for `useConversationRuntime`
- `frontend/src/hooks/useSendMessage.test.ts`: update to `startTurn`

### Frontend delete

- `frontend/src/features/sessions/sessionHistoryRound.ts`
- `frontend/src/features/sessions/sessionLoader.ts`
- `frontend/src/hooks/useExecutionRuntime.ts`
- `frontend/src/hooks/useExecutionWebSocket.ts`
- `frontend/src/hooks/useExecutionDraftRound.ts`
- `frontend/src/hooks/useExecutionOverlay.ts`
- `frontend/src/hooks/useExecutionOverlayUi.ts`
- `frontend/src/hooks/executionOverlayHelpers.ts`
- `frontend/src/hooks/executionOverlayState.ts`
- `frontend/src/services/websocketClient.ts`
- `frontend/src/hooks/useSessionRenderItems.ts`

## Task 1: Build Conversation Schema and Repositories

**Files:**
- Create: `backend/app/models/conversation.py`
- Create: `backend/app/storage/repositories/turn_repo.py`
- Create: `backend/app/storage/repositories/run_repo.py`
- Create: `backend/app/storage/repositories/message_repo.py`
- Create: `backend/app/storage/repositories/conversation_event_repo.py`
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/storage/models.py`
- Modify: `backend/app/storage/database.py`
- Modify: `backend/app/storage/repositories/session_repo.py`
- Modify: `backend/app/storage/repositories/__init__.py`
- Test: `backend/tests/test_storage/test_conversation_repositories.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from datetime import datetime
from pathlib import Path

from app.models.conversation import (
    ConversationEvent,
    EventType,
    Message,
    MessageType,
    Run,
    RunStatus,
    StreamState,
    Turn,
    TurnStatus,
)
from app.models.project import Project
from app.models.session import Session
from app.storage.database import Database
from app.storage.repositories.conversation_event_repo import ConversationEventRepository
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository


def test_session_repo_persists_last_event_seq_and_active_turn_id(tmp_path):
    db = Database(str(tmp_path / "conversation-schema.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))

    created = session_repo.create(
        Session(
            id="session-1",
            project_id="project-1",
            title="会话",
            last_event_seq=4,
            active_turn_id="turn-1",
        )
    )

    loaded = session_repo.get("session-1")

    assert created.last_event_seq == 4
    assert loaded is not None
    assert loaded.last_event_seq == 4
    assert loaded.active_turn_id == "turn-1"


def test_conversation_repositories_round_trip_turn_run_message_and_events(tmp_path):
    db = Database(str(tmp_path / "conversation-repos.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    event_repo = ConversationEventRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-user-1",
            status=TurnStatus.CREATED,
        )
    )
    run_repo.create(
        Run(
            id="run-1",
            session_id="session-1",
            turn_id="turn-1",
            attempt_index=1,
            status=RunStatus.CREATED,
            provider_id="provider-a",
            model_id="model-a",
        )
    )
    message_repo.create(
        Message(
            id="msg-user-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="hello",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 0, 0),
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
            completed_at=datetime(2026, 4, 24, 10, 0, 0),
        )
    )

    first = event_repo.append(
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            seq=0,
            turn_id="turn-1",
            run_id="run-1",
            message_id="msg-user-1",
            event_type=EventType.MESSAGE_CREATED,
            payload_json={"message_id": "msg-user-1"},
        )
    )
    second = event_repo.append(
        ConversationEvent(
            id="evt-2",
            session_id="session-1",
            seq=0,
            turn_id="turn-1",
            run_id="run-1",
            message_id="msg-user-1",
            event_type=EventType.MESSAGE_COMPLETED,
            payload_json={"message_id": "msg-user-1"},
        )
    )

    assert first.seq == 1
    assert second.seq == 2
    assert [event.id for event in event_repo.list_after_seq("session-1", after_seq=0)] == ["evt-1", "evt-2"]
    assert turn_repo.get("turn-1").root_message_id == "msg-user-1"
    assert run_repo.get("run-1").status == RunStatus.CREATED
    assert message_repo.list_by_turn("turn-1")[0].content_text == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_storage/test_conversation_repositories.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.conversation'` and missing repository imports.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/session.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str = "新建聊天"
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    last_event_seq: int = 0
    active_turn_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def default_updated_at_to_created_at(self):
        if self.updated_at is None:
            self.updated_at = self.created_at
        return self
```

```python
# backend/app/models/conversation.py
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TurnStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_TRACE = "tool_trace"
    SYSTEM_NOTICE = "system_notice"


class StreamState(str, Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    TURN_CREATED = "turn.created"
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    MESSAGE_CREATED = "message.created"
    MESSAGE_DELTA_APPENDED = "message.delta_appended"
    MESSAGE_PAYLOAD_UPDATED = "message.payload_updated"
    MESSAGE_COMPLETED = "message.completed"
    MESSAGE_FAILED = "message.failed"
    SYSTEM_NOTICE_EMITTED = "system.notice_emitted"


class Turn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_index: int
    root_message_id: str
    status: TurnStatus
    active_run_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    attempt_index: int
    status: RunStatus
    provider_id: str | None = None
    model_id: str | None = None
    workspace_ref: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    message_index: int
    role: str
    message_type: MessageType
    stream_state: StreamState
    display_mode: str
    content_text: str = ""
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class ConversationEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    seq: int = 0
    turn_id: str | None = None
    run_id: str | None = None
    message_id: str | None = None
    event_type: EventType
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
```

```python
# backend/app/storage/models.py (new conversation tables only)
class SessionModel(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="新建聊天")
    preferred_provider_id = Column(String)
    preferred_model_id = Column(String)
    last_event_seq = Column(Integer, nullable=False, default=0)
    active_turn_id = Column(String)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class TurnModel(Base):
    __tablename__ = "turns"
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    turn_index = Column(Integer, nullable=False)
    root_message_id = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    active_run_id = Column(String)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at = Column(DateTime)


class RunModel(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    turn_id = Column(String, nullable=False, index=True)
    attempt_index = Column(Integer, nullable=False)
    status = Column(String, nullable=False, index=True)
    provider_id = Column(String)
    model_id = Column(String)
    workspace_ref = Column(String)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error_code = Column(String)
    error_message = Column(Text)


class MessageModel(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    turn_id = Column(String, nullable=False, index=True)
    run_id = Column(String, index=True)
    message_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    message_type = Column(String, nullable=False, index=True)
    stream_state = Column(String, nullable=False)
    display_mode = Column(String, nullable=False)
    content_text = Column(Text, nullable=False, default="")
    payload_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at = Column(DateTime)


class ConversationEventModel(Base):
    __tablename__ = "conversation_events"
    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    turn_id = Column(String, index=True)
    run_id = Column(String, index=True)
    message_id = Column(String, index=True)
    event_type = Column(String, nullable=False)
    payload_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
```

```python
# backend/app/storage/database.py (legacy reset)
def _reset_legacy_schema_if_needed(self) -> None:
    inspector = inspect(self.engine)
    table_names = set(inspector.get_table_names())
    if "executions" in table_names or "conversations" in table_names:
        logger.warning("检测到旧版 conversation schema，直接重建数据库以切到 Phase 1 会话模型")
        Base.metadata.drop_all(self.engine)
```

```python
# backend/app/storage/repositories/conversation_event_repo.py
from app.models.conversation import ConversationEvent
from app.storage.models import ConversationEventModel


class ConversationEventRepository:
    def __init__(self, db):
        self.db = db

    def append(self, event: ConversationEvent) -> ConversationEvent:
        with self.db.get_session() as db_session:
            max_seq = (
                db_session.query(ConversationEventModel.seq)
                .filter_by(session_id=event.session_id)
                .order_by(ConversationEventModel.seq.desc())
                .limit(1)
                .scalar()
            ) or 0
            model = ConversationEventModel(
                **event.model_dump(mode="json", exclude={"seq"}),
                seq=max_seq + 1,
            )
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return ConversationEvent.model_validate(model)

    def list_after_seq(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(ConversationEventModel)
                .filter(
                    ConversationEventModel.session_id == session_id,
                    ConversationEventModel.seq > after_seq,
                )
                .order_by(ConversationEventModel.seq.asc())
                .all()
            )
            return [ConversationEvent.model_validate(model) for model in models]
```

```python
# backend/app/storage/repositories/turn_repo.py, run_repo.py, and message_repo.py helper methods
class TurnRepository:
    model_type = Turn

    def __init__(self, db):
        self.db = db

    def create(self, turn: Turn) -> Turn:
        with self.db.get_session() as db_session:
            model = TurnModel(**turn.model_dump(mode="json"))
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Turn.model_validate(model)

    def get(self, turn_id: str) -> Turn | None:
        with self.db.get_session() as db_session:
            model = db_session.query(TurnModel).filter_by(id=turn_id).first()
            return Turn.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Turn]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return [Turn.model_validate(model) for model in models]

    def update(self, turn: Turn) -> Turn:
        with self.db.get_session() as db_session:
            model = db_session.query(TurnModel).filter_by(id=turn.id).first()
            model.status = turn.status.value
            model.active_run_id = turn.active_run_id
            model.updated_at = turn.updated_at
            model.completed_at = turn.completed_at
            db_session.flush()
            db_session.refresh(model)
            return Turn.model_validate(model)

    def next_turn_index(self, session_id: str) -> int:
        with self.db.get_session() as db_session:
            current = (
                db_session.query(TurnModel.turn_index)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.desc())
                .limit(1)
                .scalar()
            ) or 0
            return current + 1


class RunRepository:
    model_type = Run

    def __init__(self, db):
        self.db = db

    def create(self, run: Run) -> Run:
        with self.db.get_session() as db_session:
            model = RunModel(**run.model_dump(mode="json"))
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Run.model_validate(model)

    def get(self, run_id: str) -> Run | None:
        with self.db.get_session() as db_session:
            model = db_session.query(RunModel).filter_by(id=run_id).first()
            return Run.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Run]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter_by(session_id=session_id)
                .order_by(RunModel.id.asc())
                .all()
            )
            return [Run.model_validate(model) for model in models]

    def update(self, run: Run) -> Run:
        with self.db.get_session() as db_session:
            model = db_session.query(RunModel).filter_by(id=run.id).first()
            model.status = run.status.value
            model.started_at = run.started_at
            model.finished_at = run.finished_at
            model.error_code = run.error_code
            model.error_message = run.error_message
            db_session.flush()
            db_session.refresh(model)
            return Run.model_validate(model)


class MessageRepository:
    model_type = Message

    def __init__(self, db):
        self.db = db

    def create(self, message: Message) -> Message:
        with self.db.get_session() as db_session:
            model = MessageModel(**message.model_dump(mode="json"))
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Message.model_validate(model)

    def get(self, message_id: str) -> Message | None:
        with self.db.get_session() as db_session:
            model = db_session.query(MessageModel).filter_by(id=message_id).first()
            return Message.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(session_id=session_id)
                .order_by(MessageModel.created_at.asc(), MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def list_by_turn(self, turn_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def update(self, message: Message) -> Message:
        with self.db.get_session() as db_session:
            model = db_session.query(MessageModel).filter_by(id=message.id).first()
            model.stream_state = message.stream_state.value
            model.content_text = message.content_text
            model.payload_json = message.payload_json
            model.updated_at = message.updated_at
            model.completed_at = message.completed_at
            db_session.flush()
            db_session.refresh(model)
            return Message.model_validate(model)

    def next_message_index(self, turn_id: str) -> int:
        with self.db.get_session() as db_session:
            current = (
                db_session.query(MessageModel.message_index)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.message_index.desc())
                .limit(1)
                .scalar()
            ) or 0
            return current + 1

    def list_by_run(self, run_id: str) -> list[Message]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(run_id=run_id)
                .order_by(MessageModel.message_index.asc())
                .all()
            )
            return [Message.model_validate(model) for model in models]

    def from_payload(self, *, session_id: str, payload: dict) -> Message:
        return Message(
            id=payload["message_id"],
            session_id=session_id,
            turn_id=payload["turn_id"],
            run_id=payload.get("run_id"),
            message_index=payload["message_index"],
            role=payload["role"],
            message_type=MessageType(payload["message_type"]),
            stream_state=StreamState.IDLE if payload["message_type"] != "user_message" else StreamState.COMPLETED,
            display_mode=payload["display_mode"],
            content_text=payload.get("content_text", ""),
            payload_json=payload.get("payload_json", {}),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_storage/test_conversation_repositories.py -q`
Expected: PASS with repository round-trip coverage for sessions, turns, runs, messages, and monotonic event seq.

- [ ] **Step 5: Commit**

```bash
git add \
  backend/app/models/conversation.py \
  backend/app/models/session.py \
  backend/app/models/__init__.py \
  backend/app/storage/models.py \
  backend/app/storage/database.py \
  backend/app/storage/repositories/session_repo.py \
  backend/app/storage/repositories/turn_repo.py \
  backend/app/storage/repositories/run_repo.py \
  backend/app/storage/repositories/message_repo.py \
  backend/app/storage/repositories/conversation_event_repo.py \
  backend/app/storage/repositories/__init__.py \
  backend/tests/test_storage/test_conversation_repositories.py
git commit -m "feat: add conversation storage foundation"
```

## Task 2: Implement Projection and Snapshot Service

**Files:**
- Create: `backend/app/models/conversation_snapshot.py`
- Create: `backend/app/services/conversation_projection.py`
- Create: `backend/app/services/conversation_service.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/__init__.py`
- Test: `backend/tests/test_services/test_conversation_projection.py`
- Test: `backend/tests/test_services/test_conversation_service.py`

- [ ] **Step 1: Write the failing projection and service tests**

```python
from datetime import datetime

from app.models.conversation import ConversationEvent, EventType
from app.models.session import Session
from app.services.conversation_projection import ConversationProjection
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def test_projection_updates_turn_run_message_and_session_terminal_state(tmp_path):
    db = Database(str(tmp_path / "projection.db"))
    service = ConversationService(db=db)

    session = service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    events = [
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={"turn_id": "turn-1", "turn_index": 1, "root_message_id": "msg-user-1"},
        ),
        ConversationEvent(
            id="evt-2",
            session_id="session-1",
            event_type=EventType.MESSAGE_CREATED,
            turn_id="turn-1",
            message_id="msg-user-1",
            payload_json={
                "message_id": "msg-user-1",
                "turn_id": "turn-1",
                "run_id": None,
                "role": "user",
                "message_type": "user_message",
                "message_index": 1,
                "display_mode": "default",
                "content_text": "hello",
                "payload_json": {},
            },
        ),
        ConversationEvent(
            id="evt-3",
            session_id="session-1",
            event_type=EventType.RUN_CREATED,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={"run_id": "run-1", "turn_id": "turn-1", "attempt_index": 1},
        ),
        ConversationEvent(
            id="evt-4",
            session_id="session-1",
            event_type=EventType.RUN_COMPLETED,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={"run_id": "run-1", "finished_at": datetime(2026, 4, 24, 10, 0, 5).isoformat()},
        ),
    ]

    service.append_events("session-1", events)
    snapshot = service.get_snapshot("session-1")

    assert snapshot.session.last_event_seq == 4
    assert snapshot.session.active_turn_id is None
    assert snapshot.turns[0].status == "completed"
    assert snapshot.runs[0].status == "completed"
    assert snapshot.messages[0].content_text == "hello"


def test_service_start_turn_creates_turn_user_message_and_run(tmp_path):
    db = Database(str(tmp_path / "start-turn.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    started = service.start_turn(
        session_id="session-1",
        content="请检查项目结构",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref="/tmp/reflexion",
    )

    assert started.turn.id.startswith("turn-")
    assert started.run.id.startswith("run-")
    assert started.user_message.message_type == "user_message"
    assert service.get_snapshot("session-1").session.active_turn_id == started.turn.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_services/test_conversation_projection.py tests/test_services/test_conversation_service.py -q`
Expected: FAIL with missing `ConversationProjection`, missing `ConversationService`, and missing snapshot DTO imports.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/conversation_snapshot.py
from pydantic import BaseModel

from app.models.conversation import Message, Run, Turn
from app.models.session import Session


class ConversationSnapshot(BaseModel):
    session: Session
    turns: list[Turn]
    runs: list[Run]
    messages: list[Message]


class StartTurnResult(BaseModel):
    turn: Turn
    run: Run
    user_message: Message
```

```python
# backend/app/services/conversation_projection.py
from datetime import datetime

from app.models.conversation import ConversationEvent, EventType, RunStatus, StreamState, TurnStatus


class ConversationProjection:
    def __init__(self, session_repo, turn_repo, run_repo, message_repo):
        self.session_repo = session_repo
        self.turn_repo = turn_repo
        self.run_repo = run_repo
        self.message_repo = message_repo

    def apply(self, session_id: str, event: ConversationEvent) -> None:
        session = self.session_repo.get(session_id)
        if session is None:
            raise ValueError("会话不存在")

        payload = event.payload_json

        match event.event_type:
            case EventType.TURN_CREATED:
                self.turn_repo.create(
                    self.turn_repo.model_type(
                        id=payload["turn_id"],
                        session_id=session_id,
                        turn_index=payload["turn_index"],
                        root_message_id=payload["root_message_id"],
                        status=TurnStatus.CREATED,
                    )
                )
                self.session_repo.update(session.model_copy(update={"active_turn_id": payload["turn_id"]}))

            case EventType.RUN_CREATED:
                self.run_repo.create(
                    self.run_repo.model_type(
                        id=payload["run_id"],
                        session_id=session_id,
                        turn_id=payload["turn_id"],
                        attempt_index=payload["attempt_index"],
                        status=RunStatus.CREATED,
                        provider_id=payload.get("provider_id"),
                        model_id=payload.get("model_id"),
                        workspace_ref=payload.get("workspace_ref"),
                    )
                )
                turn = self.turn_repo.get(payload["turn_id"])
                self.turn_repo.update(
                    turn.model_copy(
                        update={
                            "status": TurnStatus.RUNNING,
                            "active_run_id": payload["run_id"],
                            "updated_at": datetime.now(),
                        }
                    )
                )

            case EventType.RUN_STARTED:
                run = self.run_repo.get(event.run_id)
                self.run_repo.update(
                    run.model_copy(
                        update={
                            "status": RunStatus.RUNNING,
                            "started_at": datetime.fromisoformat(payload["started_at"]) if payload.get("started_at") else datetime.now(),
                        }
                    )
                )

            case EventType.MESSAGE_CREATED:
                self.message_repo.create(self.message_repo.from_payload(session_id=session_id, payload=payload))

            case EventType.MESSAGE_DELTA_APPENDED:
                message = self.message_repo.get(event.message_id)
                self.message_repo.update(
                    message.model_copy(
                        update={
                            "content_text": f"{message.content_text}{payload['delta']}",
                            "stream_state": StreamState.STREAMING,
                            "updated_at": datetime.now(),
                        }
                    )
                )

            case EventType.MESSAGE_PAYLOAD_UPDATED:
                message = self.message_repo.get(event.message_id)
                next_payload = dict(message.payload_json)
                next_payload.update(payload["payload_json"])
                self.message_repo.update(message.model_copy(update={"payload_json": next_payload, "updated_at": datetime.now()}))

            case EventType.MESSAGE_COMPLETED:
                message = self.message_repo.get(event.message_id)
                self.message_repo.update(
                    message.model_copy(
                        update={
                            "stream_state": StreamState.COMPLETED,
                            "completed_at": datetime.fromisoformat(payload["completed_at"]) if payload.get("completed_at") else datetime.now(),
                            "updated_at": datetime.now(),
                        }
                    )
                )

            case EventType.MESSAGE_FAILED:
                message = self.message_repo.get(event.message_id)
                next_payload = dict(message.payload_json)
                next_payload.update(
                    {
                        "error_code": payload.get("error_code"),
                        "error_message": payload.get("error_message"),
                    }
                )
                self.message_repo.update(
                    message.model_copy(
                        update={
                            "stream_state": StreamState.FAILED,
                            "payload_json": next_payload,
                            "updated_at": datetime.now(),
                        }
                    )
                )

            case EventType.RUN_COMPLETED | EventType.RUN_FAILED | EventType.RUN_CANCELLED:
                run = self.run_repo.get(event.run_id)
                next_status = {
                    EventType.RUN_COMPLETED: RunStatus.COMPLETED,
                    EventType.RUN_FAILED: RunStatus.FAILED,
                    EventType.RUN_CANCELLED: RunStatus.CANCELLED,
                }[event.event_type]
                finished_at = payload.get("finished_at")
                self.run_repo.update(
                    run.model_copy(
                        update={
                            "status": next_status,
                            "finished_at": datetime.fromisoformat(finished_at) if finished_at else datetime.now(),
                            "error_code": payload.get("error_code"),
                            "error_message": payload.get("error_message"),
                        }
                    )
                )
                turn = self.turn_repo.get(run.turn_id)
                self.turn_repo.update(
                    turn.model_copy(
                        update={
                            "status": {
                                RunStatus.COMPLETED: TurnStatus.COMPLETED,
                                RunStatus.FAILED: TurnStatus.FAILED,
                                RunStatus.CANCELLED: TurnStatus.CANCELLED,
                            }[next_status],
                            "active_run_id": None,
                            "completed_at": datetime.now(),
                            "updated_at": datetime.now(),
                        }
                    )
                )
                self.session_repo.update(session.model_copy(update={"active_turn_id": None}))

            case EventType.SYSTEM_NOTICE_EMITTED:
                self.message_repo.create(
                    self.message_repo.from_payload(
                        session_id=session_id,
                        payload={
                            "message_id": payload["message_id"],
                            "turn_id": payload["turn_id"],
                            "run_id": payload.get("related_run_id"),
                            "role": "system",
                            "message_type": "system_notice",
                            "message_index": payload["message_index"],
                            "display_mode": "default",
                            "content_text": payload["content_text"],
                            "payload_json": {
                                "notice_code": payload["notice_code"],
                                "related_run_id": payload.get("related_run_id"),
                                "retryable": payload.get("retryable", False),
                            },
                        },
                    )
                )
```

```python
# backend/app/services/conversation_service.py
from uuid import uuid4

from app.models.conversation import ConversationEvent, EventType
from app.models.conversation_snapshot import ConversationSnapshot, StartTurnResult


class ConversationService:
    def __init__(self, *, db, session_repo=None, turn_repo=None, run_repo=None, message_repo=None, event_repo=None):
        self.db = db
        self.session_repo = session_repo or SessionRepository(db)
        self.turn_repo = turn_repo or TurnRepository(db)
        self.run_repo = run_repo or RunRepository(db)
        self.message_repo = message_repo or MessageRepository(db)
        self.event_repo = event_repo or ConversationEventRepository(db)
        self.projection = ConversationProjection(self.session_repo, self.turn_repo, self.run_repo, self.message_repo)

    def append_events(self, session_id: str, events: list[ConversationEvent]) -> list[ConversationEvent]:
        persisted = []
        for event in events:
            saved = self.event_repo.append(event)
            self.projection.apply(session_id, saved)
            persisted.append(saved)
        session = self.session_repo.get(session_id)
        self.session_repo.update(session.model_copy(update={"last_event_seq": persisted[-1].seq if persisted else session.last_event_seq}))
        return persisted

    def get_snapshot(self, session_id: str) -> ConversationSnapshot:
        session = self.session_repo.get(session_id)
        if session is None:
            raise ValueError("会话不存在")
        return ConversationSnapshot(
            session=session,
            turns=self.turn_repo.list_by_session(session_id),
            runs=self.run_repo.list_by_session(session_id),
            messages=self.message_repo.list_by_session(session_id),
        )

    def list_events_after(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        return self.event_repo.list_after_seq(session_id, after_seq)

    def start_turn(self, *, session_id: str, content: str, provider_id: str, model_id: str, workspace_ref: str | None) -> StartTurnResult:
        turn_id = f"turn-{uuid4().hex[:8]}"
        run_id = f"run-{uuid4().hex[:8]}"
        user_message_id = f"msg-{uuid4().hex[:8]}"
        next_turn_index = self.turn_repo.next_turn_index(session_id)

        events = self.append_events(
            session_id,
            [
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type=EventType.TURN_CREATED,
                    payload_json={"turn_id": turn_id, "turn_index": next_turn_index, "root_message_id": user_message_id},
                ),
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    message_id=user_message_id,
                    event_type=EventType.MESSAGE_CREATED,
                    payload_json={
                        "message_id": user_message_id,
                        "turn_id": turn_id,
                        "run_id": None,
                        "role": "user",
                        "message_type": "user_message",
                        "message_index": 1,
                        "display_mode": "default",
                        "content_text": content,
                        "payload_json": {},
                    },
                ),
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    event_type=EventType.RUN_CREATED,
                    payload_json={
                        "run_id": run_id,
                        "turn_id": turn_id,
                        "attempt_index": 1,
                        "provider_id": provider_id,
                        "model_id": model_id,
                        "workspace_ref": workspace_ref,
                    },
                ),
            ],
        )
        return StartTurnResult(
            turn=self.turn_repo.get(turn_id),
            run=self.run_repo.get(run_id),
            user_message=self.message_repo.get(user_message_id),
        )

    def cancel_run(self, run_id: str):
        run = self.run_repo.get(run_id)
        if run is None:
            raise ValueError("运行不存在")
        turn = self.turn_repo.get(run.turn_id)
        notice_id = f"msg-{uuid4().hex[:8]}"
        self.append_events(
            run.session_id,
            [
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=run.session_id,
                    turn_id=run.turn_id,
                    run_id=run.id,
                    event_type=EventType.RUN_CANCELLED,
                    payload_json={"run_id": run.id, "finished_at": datetime.now().isoformat()},
                ),
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=run.session_id,
                    turn_id=run.turn_id,
                    run_id=run.id,
                    message_id=notice_id,
                    event_type=EventType.SYSTEM_NOTICE_EMITTED,
                    payload_json={
                        "message_id": notice_id,
                        "turn_id": turn.id,
                        "message_index": self.message_repo.next_message_index(turn.id),
                        "notice_code": "run_cancelled",
                        "content_text": "本次执行已取消",
                        "related_run_id": run.id,
                        "retryable": True,
                    },
                ),
            ],
        )
        return self.run_repo.get(run_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_services/test_conversation_projection.py tests/test_services/test_conversation_service.py -q`
Expected: PASS with projection terminal-state coverage and `start_turn` snapshot coverage.

- [ ] **Step 5: Commit**

```bash
git add \
  backend/app/models/conversation_snapshot.py \
  backend/app/models/__init__.py \
  backend/app/services/conversation_projection.py \
  backend/app/services/conversation_service.py \
  backend/app/services/__init__.py \
  backend/tests/test_services/test_conversation_projection.py \
  backend/tests/test_services/test_conversation_service.py
git commit -m "feat: add conversation projection and snapshot service"
```

## Task 3: Translate Runtime Events Into Conversation Events

**Files:**
- Create: `backend/app/services/conversation_runtime_adapter.py`
- Modify: `backend/app/services/agent_service.py`
- Modify: `backend/app/execution/rapid_loop.py`
- Modify: `backend/tests/test_services/test_agent_service.py`
- Modify: `backend/tests/test_execution/test_rapid_loop.py`
- Test: `backend/tests/test_services/test_conversation_runtime_adapter.py`

- [ ] **Step 1: Write the failing runtime adapter tests**

```python
import pytest

from app.models.session import Session
from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter
from app.services.conversation_service import ConversationService
from app.storage.database import Database


@pytest.mark.asyncio
async def test_runtime_adapter_maps_llm_and_tool_events_into_messages(tmp_path):
    db = Database(str(tmp_path / "runtime-adapter.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    started = service.start_turn(
        session_id="session-1",
        content="检查项目结构",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref="/tmp/project",
    )
    adapter = ConversationRuntimeAdapter(conversation_service=service)

    await adapter.handle_raw_event(
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        event_type="llm:content",
        data={"content": "先读取 README"},
    )
    await adapter.handle_raw_event(
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        event_type="tool:start",
        data={"tool_name": "shell", "arguments": {"cmd": "pwd"}, "step_number": 1},
    )
    await adapter.handle_raw_event(
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
        event_type="tool:result",
        data={"tool_name": "shell", "success": True, "output": "/tmp/project", "duration": 0.1},
    )

    snapshot = service.get_snapshot("session-1")

    assert snapshot.messages[1].message_type == "assistant_message"
    assert snapshot.messages[1].content_text == "先读取 README"
    assert snapshot.messages[2].message_type == "tool_trace"
    assert snapshot.messages[2].payload_json["tool_status"] == "success"


@pytest.mark.asyncio
async def test_agent_service_start_turn_uses_conversation_service_and_tracks_running_tasks(monkeypatch, tmp_path):
    from app.models.project import Project
    from app.services.agent_service import AgentService

    service = AgentService()
    service.project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(tmp_path)))
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    started = await service.start_turn(
        session_id="session-1",
        project_id="project-1",
        task="inspect repo",
        provider_id="provider-a",
        model_id="model-a",
    )

    assert started.run.id.startswith("run-")
    assert started.turn.id.startswith("turn-")
    assert started.run.id in service.running_tasks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_services/test_conversation_runtime_adapter.py tests/test_services/test_agent_service.py -q`
Expected: FAIL because `ConversationRuntimeAdapter` and `AgentService.start_turn` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/conversation_runtime_adapter.py
from datetime import datetime
from uuid import uuid4

from app.models.conversation import ConversationEvent, EventType


class ConversationRuntimeAdapter:
    def __init__(self, conversation_service):
        self.conversation_service = conversation_service
        self.assistant_message_ids: dict[str, str] = {}
        self.tool_message_ids: dict[tuple[str, int], str] = {}

    async def handle_raw_event(self, *, session_id: str, turn_id: str, run_id: str, event_type: str, data: dict) -> None:
        if event_type == "llm:content":
            message_id = self.assistant_message_ids.setdefault(run_id, f"msg-{uuid4().hex[:8]}")
            events = []
            if not self.conversation_service.message_repo.list_by_run(run_id):
                events.append(
                    ConversationEvent(
                        id=f"evt-{uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": message_id,
                            "turn_id": turn_id,
                            "run_id": run_id,
                            "role": "assistant",
                            "message_type": "assistant_message",
                            "message_index": 2,
                            "display_mode": "default",
                            "content_text": "",
                            "payload_json": {},
                        },
                    )
                )
            events.append(
                ConversationEvent(
                    id=f"evt-{uuid4().hex[:8]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=message_id,
                    event_type=EventType.MESSAGE_DELTA_APPENDED,
                    payload_json={"message_id": message_id, "delta": data["content"]},
                )
            )
            self.conversation_service.append_events(session_id, events)
            return

        if event_type == "tool:start":
            step_number = data["step_number"]
            message_id = f"msg-{uuid4().hex[:8]}"
            self.tool_message_ids[(run_id, step_number)] = message_id
            self.conversation_service.append_events(
                session_id,
                [
                    ConversationEvent(
                        id=f"evt-{uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": message_id,
                            "turn_id": turn_id,
                            "run_id": run_id,
                            "role": "tool",
                            "message_type": "tool_trace",
                            "message_index": self.conversation_service.message_repo.next_message_index(turn_id),
                            "display_mode": "collapsed",
                            "content_text": f"执行 {data['tool_name']}",
                            "payload_json": {
                                "trace_kind": "tool_call",
                                "summary": f"执行 {data['tool_name']}",
                                "tool_name": data["tool_name"],
                                "tool_status": "running",
                                "input_preview": str(data.get("arguments")),
                                "output_preview": None,
                                "error_preview": None,
                                "started_at": datetime.now().isoformat(),
                                "finished_at": None,
                            },
                        },
                    )
                ],
            )
            return

        if event_type == "tool:result":
            step_number = max(index for (raw_run_id, index) in self.tool_message_ids if raw_run_id == run_id)
            message_id = self.tool_message_ids[(run_id, step_number)]
            next_payload = {
                "trace_kind": "tool_result",
                "summary": f"{data['tool_name']} 执行完成",
                "tool_name": data["tool_name"],
                "tool_status": "success" if data["success"] else "failed",
                "input_preview": None,
                "output_preview": data.get("output"),
                "error_preview": data.get("error"),
                "started_at": None,
                "finished_at": datetime.now().isoformat(),
            }
            self.conversation_service.append_events(
                session_id,
                [
                    ConversationEvent(
                        id=f"evt-{uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=message_id,
                        event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                        payload_json={"message_id": message_id, "payload_json": next_payload},
                    ),
                    ConversationEvent(
                        id=f"evt-{uuid4().hex[:8]}",
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=message_id,
                        event_type=EventType.MESSAGE_COMPLETED,
                        payload_json={"message_id": message_id, "completed_at": datetime.now().isoformat()},
                    ),
                ],
            )
            return

        if event_type == "summary:token":
            await self.handle_raw_event(
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                event_type="llm:content",
                data={"content": data["token"]},
            )
            return

        if event_type == "execution:error":
            assistant_id = self.assistant_message_ids.get(run_id)
            if assistant_id:
                self.conversation_service.append_events(
                    session_id,
                    [
                        ConversationEvent(
                            id=f"evt-{uuid4().hex[:8]}",
                            session_id=session_id,
                            turn_id=turn_id,
                            run_id=run_id,
                            message_id=assistant_id,
                            event_type=EventType.MESSAGE_FAILED,
                            payload_json={
                                "message_id": assistant_id,
                                "error_code": "runtime_error",
                                "error_message": data["error"],
                            },
                        )
                    ],
                )
            return
```

```python
# backend/app/services/agent_service.py (new public lifecycle)
class AgentService:
    def __init__(
        self,
        project_repo: ProjectRepository | None = None,
        session_repo: SessionRepository | None = None,
        conversation_service: ConversationService | None = None,
    ):
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.project_repo = project_repo or ProjectRepository(db)
        self.session_repo = session_repo or SessionRepository(db)
        self.conversation_service = conversation_service or ConversationService(db=db)
        self.runtime_adapter = ConversationRuntimeAdapter(self.conversation_service)
        self.tool_registry = self._init_tool_registry()
        self.llm_settings = self._load_llm_settings()

    async def start_turn(self, *, session_id: str, project_id: str, task: str, provider_id: str | None, model_id: str | None):
        project = self.project_repo.get(project_id)
        if not project:
            raise ValueError("项目不存在")
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("会话不存在")
        if session.project_id != project.id:
            raise ValueError("会话不属于当前项目")
        started = self.conversation_service.start_turn(
            session_id=session_id,
            content=task,
            provider_id=provider_id or "",
            model_id=model_id or "",
            workspace_ref=project.path,
        )
        task_handle = asyncio.create_task(
            self._run_turn(
                turn_id=started.turn.id,
                run_id=started.run.id,
                session_id=session_id,
                project_id=project_id,
                project_path=project.path,
                task=task,
                provider_id=provider_id,
                model_id=model_id,
            )
        )
        self.running_tasks[started.run.id] = task_handle
        task_handle.add_done_callback(lambda _: self.running_tasks.pop(started.run.id, None))
        return started

    async def cancel_run(self, run_id: str):
        task = self.running_tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        self.conversation_service.cancel_run(run_id)
        return self.conversation_service.run_repo.get(run_id)
```

```python
# backend/app/execution/rapid_loop.py (callback contract only)
async def _emit(self, event_type: str, data: dict) -> None:
    if self.event_callback:
        await self.event_callback(event_type, data)

async for chunk in self.llm.stream_complete(messages, tools):
    if chunk.type == "content" and chunk.content:
        content_parts.append(chunk.content)
        await self._emit("llm:content", {"content": chunk.content})
    elif chunk.type == "tool_calls":
        tool_calls = chunk.tool_calls
        finish_reason = chunk.finish_reason or "tool_calls"
        break

await self._emit(
    "tool:start",
    {"tool_name": tool_call.name, "arguments": tool_call.arguments, "step_number": step_number},
)
await self._emit(
    "tool:result",
    {
        "tool_name": tool_call.name,
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "duration": step.duration,
    },
)
await self._emit("summary:token", {"token": chunk.content})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_services/test_conversation_runtime_adapter.py tests/test_services/test_agent_service.py tests/test_execution/test_rapid_loop.py -q`
Expected: PASS with runtime-event mapping coverage and `run_id`-based task scheduling.

- [ ] **Step 5: Commit**

```bash
git add \
  backend/app/services/conversation_runtime_adapter.py \
  backend/app/services/agent_service.py \
  backend/app/execution/rapid_loop.py \
  backend/tests/test_services/test_conversation_runtime_adapter.py \
  backend/tests/test_services/test_agent_service.py \
  backend/tests/test_execution/test_rapid_loop.py
git commit -m "feat: stream conversation events from runtime"
```

## Task 4: Expose Session Conversation API and WebSocket

**Files:**
- Modify: `backend/app/api/websocket.py`
- Modify: `backend/app/api/routes/websocket.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api/test_sessions_api.py`
- Test: `backend/tests/test_api/test_conversation_api.py`
- Test: `backend/tests/test_api/test_conversation_websocket.py`

- [ ] **Step 1: Write the failing API and websocket tests**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_get_conversation_snapshot_returns_normalized_entities(client):
    response = client.get("/api/sessions/session-1/conversation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == "session-1"
    assert payload["session"]["last_event_seq"] >= 0
    assert isinstance(payload["turns"], list)
    assert isinstance(payload["runs"], list)
    assert isinstance(payload["messages"], list)


def test_history_endpoint_is_removed(client):
    response = client.get("/api/sessions/session-1/history")

    assert response.status_code == 404


def test_session_conversation_websocket_supports_sync_and_start_turn(client):
    with client.websocket_connect("/ws/sessions/session-1/conversation") as websocket:
        websocket.send_json({"type": "conversation.sync", "data": {"after_seq": 0}})
        synced = websocket.receive_json()
        assert synced["type"] == "conversation.synced"

        websocket.send_json(
            {
                "type": "conversation.start_turn",
                "data": {
                    "content": "inspect repo",
                    "provider_id": "provider-a",
                    "model_id": "model-a",
                },
            }
        )
        created = websocket.receive_json()
        assert created["type"] == "conversation.event"
        assert created["data"]["event_type"] == "turn.created"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api/test_conversation_api.py tests/test_api/test_conversation_websocket.py -q`
Expected: FAIL because `/api/sessions/{session_id}/conversation` and `/ws/sessions/{session_id}/conversation` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/api/websocket.py
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections.setdefault(session_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast_event(self, session_id: str, event: ConversationEvent):
        payload = json.dumps(
            {
                "type": "conversation.event",
                "data": event.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        for websocket in self.active_connections.get(session_id, set()):
            await websocket.send_text(payload)
```

```python
# backend/app/api/routes/sessions.py
@router.get("/sessions/{session_id}/conversation", response_model=ConversationSnapshot)
async def get_conversation_snapshot(session_id: str):
    try:
        return conversation_service.get_snapshot(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

```python
# backend/app/api/routes/websocket.py
@router.websocket("/ws/sessions/{session_id}/conversation")
async def websocket_conversation(websocket: WebSocket, session_id: str):
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            msg_type = message.get("type")
            data = message.get("data", {})

            if msg_type == "conversation.sync":
                after_seq = data.get("after_seq", 0)
                events = conversation_service.list_events_after(session_id, after_seq)
                for event in events:
                    await ws_manager.broadcast_event(session_id, event)
                await websocket.send_json(
                    {
                        "type": "conversation.synced",
                        "data": {
                            "session_id": session_id,
                            "last_event_seq": conversation_service.get_snapshot(session_id).session.last_event_seq,
                        },
                    }
                )
                continue

            if msg_type == "conversation.start_turn":
                started = await agent_service.start_turn(
                    session_id=session_id,
                    project_id=conversation_service.get_snapshot(session_id).session.project_id,
                    task=data["content"],
                    provider_id=data.get("provider_id"),
                    model_id=data.get("model_id"),
                )
                initial_events = conversation_service.list_events_after(session_id, after_seq=0)[-3:]
                for event in initial_events:
                    await ws_manager.broadcast_event(session_id, event)
                continue

            if msg_type == "conversation.cancel_run":
                await agent_service.cancel_run(data["run_id"])
                continue

            await websocket.send_json({"type": "conversation.error", "data": {"code": "invalid_request", "message": f"未知消息类型: {msg_type}"}})
    finally:
        ws_manager.disconnect(websocket, session_id)
```

```python
# backend/app/main.py
from app.api.routes import llm, projects, sessions, skills, websocket

app.include_router(projects.router)
app.include_router(sessions.router)
app.include_router(llm.router)
app.include_router(skills.router)
app.include_router(websocket.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_api/test_sessions_api.py tests/test_api/test_conversation_api.py tests/test_api/test_conversation_websocket.py -q`
Expected: PASS with session CRUD still intact, snapshot endpoint available, websocket sync/start-turn behavior covered, and old `/history` route removed.

- [ ] **Step 5: Commit**

```bash
git add \
  backend/app/api/websocket.py \
  backend/app/api/routes/websocket.py \
  backend/app/api/routes/sessions.py \
  backend/app/main.py \
  backend/tests/test_api/test_sessions_api.py \
  backend/tests/test_api/test_conversation_api.py \
  backend/tests/test_api/test_conversation_websocket.py
git commit -m "feat: expose session conversation api and websocket"
```

## Task 5: Build Frontend Conversation Data Layer

**Files:**
- Create: `frontend/src/types/conversation.ts`
- Create: `frontend/src/features/conversation/conversationApi.ts`
- Create: `frontend/src/features/conversation/conversationReducer.ts`
- Create: `frontend/src/features/conversation/conversationStore.ts`
- Create: `frontend/src/features/conversation/conversationSelectors.ts`
- Modify: `frontend/src/services/apiClient.ts`
- Modify: `frontend/src/features/sessions/sessionApi.ts`
- Modify: `frontend/src/features/sessions/sessionStore.ts`
- Modify: `frontend/src/types/workspace.ts`
- Test: `frontend/src/features/conversation/conversationReducer.test.ts`
- Test: `frontend/src/features/conversation/conversationStore.test.ts`
- Test: `frontend/src/features/conversation/conversationApi.test.ts`

- [ ] **Step 1: Write the failing frontend data-layer tests**

```ts
import { describe, expect, it } from 'vitest'
import { applyConversationEvent, applyConversationSnapshot } from './conversationReducer'

describe('conversationReducer', () => {
  it('imports snapshot entities and keeps message order stable', () => {
    const state = applyConversationSnapshot(undefined, {
      session: {
        id: 'session-1',
        projectId: 'project-1',
        title: '会话',
        preferredProviderId: 'provider-a',
        preferredModelId: 'model-a',
        lastEventSeq: 2,
        activeTurnId: 'turn-1',
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:02Z',
      },
      turns: [{ id: 'turn-1', sessionId: 'session-1', turnIndex: 1, rootMessageId: 'msg-1', status: 'running', activeRunId: 'run-1', createdAt: '2026-04-24T10:00:00Z', updatedAt: '2026-04-24T10:00:01Z', completedAt: null }],
      runs: [{ id: 'run-1', sessionId: 'session-1', turnId: 'turn-1', attemptIndex: 1, status: 'running', providerId: 'provider-a', modelId: 'model-a', workspaceRef: '/tmp/reflexion', startedAt: null, finishedAt: null, errorCode: null, errorMessage: null }],
      messages: [{ id: 'msg-1', sessionId: 'session-1', turnId: 'turn-1', runId: null, messageIndex: 1, role: 'user', messageType: 'user_message', streamState: 'completed', displayMode: 'default', contentText: 'hello', payloadJson: {}, createdAt: '2026-04-24T10:00:00Z', updatedAt: '2026-04-24T10:00:00Z', completedAt: '2026-04-24T10:00:00Z' }],
    })

    expect(state.messageOrder).toEqual(['msg-1'])
    expect(state.lastEventSeq).toBe(2)
  })

  it('appends delta events to existing assistant messages', () => {
    const base = applyConversationSnapshot(undefined, {
      session: { id: 'session-1', projectId: 'project-1', title: '会话', preferredProviderId: undefined, preferredModelId: undefined, lastEventSeq: 3, activeTurnId: 'turn-1', createdAt: '2026-04-24T10:00:00Z', updatedAt: '2026-04-24T10:00:00Z' },
      turns: [{ id: 'turn-1', sessionId: 'session-1', turnIndex: 1, rootMessageId: 'msg-1', status: 'running', activeRunId: 'run-1', createdAt: '2026-04-24T10:00:00Z', updatedAt: '2026-04-24T10:00:00Z', completedAt: null }],
      runs: [{ id: 'run-1', sessionId: 'session-1', turnId: 'turn-1', attemptIndex: 1, status: 'running', providerId: 'provider-a', modelId: 'model-a', workspaceRef: null, startedAt: null, finishedAt: null, errorCode: null, errorMessage: null }],
      messages: [{ id: 'msg-1', sessionId: 'session-1', turnId: 'turn-1', runId: null, messageIndex: 1, role: 'user', messageType: 'user_message', streamState: 'completed', displayMode: 'default', contentText: 'hello', payloadJson: {}, createdAt: '2026-04-24T10:00:00Z', updatedAt: '2026-04-24T10:00:00Z', completedAt: '2026-04-24T10:00:00Z' }, { id: 'msg-2', sessionId: 'session-1', turnId: 'turn-1', runId: 'run-1', messageIndex: 2, role: 'assistant', messageType: 'assistant_message', streamState: 'streaming', displayMode: 'default', contentText: '正在', payloadJson: {}, createdAt: '2026-04-24T10:00:01Z', updatedAt: '2026-04-24T10:00:01Z', completedAt: null }],
    })

    const next = applyConversationEvent(base, {
      id: 'evt-4',
      sessionId: 'session-1',
      seq: 4,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.delta_appended',
      payloadJson: { message_id: 'msg-2', delta: '分析项目结构' },
      createdAt: '2026-04-24T10:00:02Z',
    })

    expect(next.messagesById['msg-2'].contentText).toBe('正在分析项目结构')
    expect(next.lastEventSeq).toBe(4)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/features/conversation/conversationReducer.test.ts src/features/conversation/conversationApi.test.ts src/features/conversation/conversationStore.test.ts`
Expected: FAIL because the `conversation` feature directory does not exist.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/types/conversation.ts
export interface ConversationSessionDto {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  lastEventSeq: number
  activeTurnId: string | null
  createdAt: string
  updatedAt: string
}

export interface ConversationTurnEntity {
  id: string
  sessionId: string
  turnIndex: number
  rootMessageId: string
  status: 'created' | 'running' | 'completed' | 'failed' | 'cancelled'
  activeRunId: string | null
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface ConversationRunEntity {
  id: string
  sessionId: string
  turnId: string
  attemptIndex: number
  status: 'created' | 'running' | 'completed' | 'failed' | 'cancelled'
  providerId?: string | null
  modelId?: string | null
  workspaceRef?: string | null
  startedAt?: string | null
  finishedAt?: string | null
  errorCode?: string | null
  errorMessage?: string | null
}

export interface ConversationMessageEntity {
  id: string
  sessionId: string
  turnId: string
  runId: string | null
  messageIndex: number
  role: 'user' | 'assistant' | 'tool' | 'system'
  messageType: 'user_message' | 'assistant_message' | 'tool_trace' | 'system_notice'
  streamState: 'idle' | 'streaming' | 'completed' | 'failed' | 'cancelled'
  displayMode: 'default' | 'collapsed'
  contentText: string
  payloadJson: Record<string, unknown>
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface ConversationEventDto {
  id: string
  sessionId: string
  seq: number
  turnId: string | null
  runId: string | null
  messageId: string | null
  eventType: string
  payloadJson: Record<string, unknown>
  createdAt: string
}

export interface ConversationSnapshot {
  session: ConversationSessionDto
  turns: ConversationTurnEntity[]
  runs: ConversationRunEntity[]
  messages: ConversationMessageEntity[]
}

export interface ConversationState {
  sessionId: string | null
  lastEventSeq: number
  session: ConversationSessionDto | null
  turnOrder: string[]
  turnsById: Record<string, ConversationTurnEntity>
  runsById: Record<string, ConversationRunEntity>
  messageOrder: string[]
  messagesById: Record<string, ConversationMessageEntity>
}
```

```ts
// frontend/src/features/conversation/conversationReducer.ts
import type { ConversationEventDto, ConversationMessageEntity, ConversationSnapshot, ConversationState } from '@/types/conversation'

export function createEmptyConversationState(): ConversationState {
  return {
    sessionId: null,
    lastEventSeq: 0,
    session: null,
    turnOrder: [],
    turnsById: {},
    runsById: {},
    messageOrder: [],
    messagesById: {},
  }
}

export function applyConversationSnapshot(
  previous: ConversationState | undefined,
  snapshot: ConversationSnapshot
): ConversationState {
  const state = createEmptyConversationState()
  state.sessionId = snapshot.session.id
  state.lastEventSeq = snapshot.session.lastEventSeq
  state.session = snapshot.session
  state.turnOrder = snapshot.turns
    .slice()
    .sort((left, right) => left.turnIndex - right.turnIndex)
    .map((turn) => turn.id)
  state.turnsById = Object.fromEntries(snapshot.turns.map((turn) => [turn.id, turn]))
  state.runsById = Object.fromEntries(snapshot.runs.map((run) => [run.id, run]))
  state.messageOrder = snapshot.messages
    .slice()
    .sort((left, right) => {
      const leftTurn = state.turnsById[left.turnId]?.turnIndex ?? 0
      const rightTurn = state.turnsById[right.turnId]?.turnIndex ?? 0
      return leftTurn - rightTurn || left.messageIndex - right.messageIndex
    })
    .map((message) => message.id)
  state.messagesById = Object.fromEntries(snapshot.messages.map((message) => [message.id, message]))
  return state
}

export function applyConversationEvent(state: ConversationState, event: ConversationEventDto): ConversationState {
  const next = {
    ...state,
    lastEventSeq: event.seq,
    messagesById: { ...state.messagesById },
    turnsById: { ...state.turnsById },
    runsById: { ...state.runsById },
  }

  if (event.eventType === 'message.delta_appended' && event.messageId) {
    const current = next.messagesById[event.messageId]
    next.messagesById[event.messageId] = {
      ...current,
      contentText: `${current.contentText}${String(event.payloadJson.delta ?? '')}`,
      streamState: 'streaming',
      updatedAt: event.createdAt,
    }
  }

  if (event.eventType === 'message.payload_updated' && event.messageId) {
    const current = next.messagesById[event.messageId]
    next.messagesById[event.messageId] = {
      ...current,
      payloadJson: {
        ...current.payloadJson,
        ...(event.payloadJson.payload_json as Record<string, unknown>),
      },
      updatedAt: event.createdAt,
    }
  }

  return next
}
```

```ts
// frontend/src/features/conversation/conversationStore.ts
import { create } from 'zustand'
import { applyConversationEvent, applyConversationSnapshot, createEmptyConversationState } from './conversationReducer'
import type { ConversationEventDto, ConversationSnapshot, ConversationState } from '@/types/conversation'

interface ConversationStoreState {
  conversationsBySessionId: Record<string, ConversationState>
  setSnapshot: (sessionId: string, snapshot: ConversationSnapshot) => void
  applyEvent: (sessionId: string, event: ConversationEventDto) => void
  clearConversation: (sessionId: string) => void
}

export const useConversationStore = create<ConversationStoreState>((set) => ({
  conversationsBySessionId: {},
  setSnapshot: (sessionId, snapshot) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationSnapshot(state.conversationsBySessionId[sessionId], snapshot),
    },
  })),
  applyEvent: (sessionId, event) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationEvent(
        state.conversationsBySessionId[sessionId] || createEmptyConversationState(),
        event
      ),
    },
  })),
  clearConversation: (sessionId) => set((state) => ({
    conversationsBySessionId: Object.fromEntries(
      Object.entries(state.conversationsBySessionId).filter(([id]) => id !== sessionId)
    ),
  })),
}))
```

```ts
// frontend/src/features/conversation/conversationApi.ts
import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type { ConversationSnapshot } from '@/types/conversation'

interface ConversationSnapshotDto {
  session: {
    id: string
    project_id: string
    title: string
    preferred_provider_id?: string | null
    preferred_model_id?: string | null
    last_event_seq: number
    active_turn_id: string | null
    created_at: string
    updated_at: string
  }
  turns: ConversationSnapshot['turns']
  runs: ConversationSnapshot['runs']
  messages: ConversationSnapshot['messages']
}

function toConversationSnapshot(dto: ConversationSnapshotDto): ConversationSnapshot {
  return {
    session: {
      id: dto.session.id,
      projectId: dto.session.project_id,
      title: dto.session.title,
      preferredProviderId: dto.session.preferred_provider_id ?? undefined,
      preferredModelId: dto.session.preferred_model_id ?? undefined,
      lastEventSeq: dto.session.last_event_seq,
      activeTurnId: dto.session.active_turn_id,
      createdAt: dto.session.created_at,
      updatedAt: dto.session.updated_at,
    },
    turns: dto.turns,
    runs: dto.runs,
    messages: dto.messages,
  }
}

async function mapConversationResponse(
  request: Promise<AxiosResponse<ConversationSnapshotDto>>
): Promise<AxiosResponse<ConversationSnapshot>> {
  const response = await request
  return {
    ...response,
    data: toConversationSnapshot(response.data),
  }
}

export const conversationApi = {
  getConversation: (sessionId: string) =>
    mapConversationResponse(apiClient.get<ConversationSnapshotDto>(`/api/sessions/${sessionId}/conversation`)),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/features/conversation/conversationReducer.test.ts src/features/conversation/conversationApi.test.ts src/features/conversation/conversationStore.test.ts`
Expected: PASS with snapshot import and delta append coverage.

- [ ] **Step 5: Commit**

```bash
git add \
  frontend/src/types/conversation.ts \
  frontend/src/features/conversation/conversationApi.ts \
  frontend/src/features/conversation/conversationReducer.ts \
  frontend/src/features/conversation/conversationStore.ts \
  frontend/src/features/conversation/conversationSelectors.ts \
  frontend/src/services/apiClient.ts \
  frontend/src/features/sessions/sessionApi.ts \
  frontend/src/features/sessions/sessionStore.ts \
  frontend/src/types/workspace.ts \
  frontend/src/features/conversation/conversationReducer.test.ts \
  frontend/src/features/conversation/conversationStore.test.ts \
  frontend/src/features/conversation/conversationApi.test.ts
git commit -m "feat: add frontend conversation store"
```

## Task 6: Cut Workspace Runtime and UI Over to Conversation Entities

**Files:**
- Create: `frontend/src/services/sessionConversationWebSocket.ts`
- Create: `frontend/src/hooks/useConversationData.ts`
- Create: `frontend/src/hooks/useConversationRuntime.ts`
- Create: `frontend/src/components/workspace/ToolTraceCard.tsx`
- Modify: `frontend/src/services/runtimeConfig.ts`
- Modify: `frontend/src/hooks/useSendMessage.ts`
- Modify: `frontend/src/hooks/useCurrentSessionViewModel.ts`
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/hooks/useSendMessage.test.ts`
- Test: `frontend/src/hooks/useConversationRuntime.test.ts`
- Test: `frontend/src/components/workspace/ToolTraceCard.test.tsx`

- [ ] **Step 1: Write the failing runtime/UI tests**

```ts
import { describe, expect, it, vi } from 'vitest'
import { createSendMessage } from './useSendMessage'

describe('createSendMessage', () => {
  it('creates a session when needed and starts a conversation turn instead of an execution run', async () => {
    const startTurn = vi.fn().mockResolvedValue(undefined)
    const createSession = vi.fn().mockResolvedValue({
      id: 'session-1',
      projectId: 'project-1',
      title: '新建聊天',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      createdAt: '2026-04-24T10:00:00Z',
      updatedAt: '2026-04-24T10:00:00Z',
    })

    const sendMessage = createSendMessage({
      currentProject: { id: 'project-1', name: 'Project', path: '/tmp/project' },
      currentSession: null,
      configured: true,
      selection: { providerId: 'provider-a', modelId: 'model-a' },
      createSession,
      writeSessionPreferences: vi.fn(),
      startTurn,
      notify: vi.fn(),
    })

    await sendMessage('hello')

    expect(startTurn).toHaveBeenCalledWith({
      sessionId: 'session-1',
      message: 'hello',
      projectId: 'project-1',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
  })
})
```

```tsx
import { render, screen } from '@testing-library/react'
import { WorkspaceTranscript } from '@/components/workspace/WorkspaceTranscript'

it('renders tool traces as collapsed cards and system notices inline', () => {
  render(
    <WorkspaceTranscript
      loaded
      configured
      currentProject={{ id: 'project-1', name: 'ReflexionOS', path: '/tmp/reflexion', language: 'ts' }}
      currentSession={{ id: 'session-1', projectId: 'project-1', title: '会话', createdAt: '', updatedAt: '' }}
      items={[
        { id: 'msg-1', role: 'user', messageType: 'user_message', contentText: 'hello' },
        { id: 'msg-2', role: 'tool', messageType: 'tool_trace', contentText: '执行 shell', payloadJson: { tool_status: 'success', output_preview: '/tmp/reflexion' } },
        { id: 'msg-3', role: 'system', messageType: 'system_notice', contentText: '本次执行已取消' },
      ]}
      messagesEndRef={{ current: null }}
    />
  )

  expect(screen.getByText('执行 shell')).toBeInTheDocument()
  expect(screen.getByText('本次执行已取消')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- src/hooks/useConversationRuntime.test.ts src/hooks/useSendMessage.test.ts src/components/workspace/ToolTraceCard.test.tsx`
Expected: FAIL because `useConversationRuntime` and `ToolTraceCard` do not exist and `useSendMessage` still expects `startExecutionRun`.

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/services/sessionConversationWebSocket.ts
type SessionConversationEvent =
  | { type: 'conversation.synced'; data: { session_id: string; last_event_seq: number } }
  | { type: 'conversation.event'; data: ConversationEventDto }
  | { type: 'conversation.resync_required'; data: { reason: string; expected_after_seq: number } }
  | { type: 'conversation.error'; data: { code: string; message: string } }

export class SessionConversationWebSocket {
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<(payload: unknown) => void>>()

  connect(sessionId: string) {
    this.ws = new WebSocket(getSessionConversationWebSocketUrl(sessionId))
    this.ws.onopen = () => {
      this.handlers.get('connection:open')?.forEach((handler) => handler({}))
    }
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data) as SessionConversationEvent
      this.handlers.get(message.type)?.forEach((handler) => handler(message.data))
    }
  }

  sync(afterSeq: number) {
    this.ws?.send(JSON.stringify({ type: 'conversation.sync', data: { after_seq: afterSeq } }))
  }

  startTurn(content: string, providerId: string, modelId: string) {
    this.ws?.send(JSON.stringify({ type: 'conversation.start_turn', data: { content, provider_id: providerId, model_id: modelId } }))
  }

  cancelRun(runId: string) {
    this.ws?.send(JSON.stringify({ type: 'conversation.cancel_run', data: { run_id: runId } }))
  }

  on(event: SessionConversationEvent['type'] | 'connection:open', handler: (payload: unknown) => void) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }
    this.handlers.get(event)!.add(handler)
  }
}
```

```ts
// frontend/src/services/runtimeConfig.ts
export function getSessionConversationWebSocketUrl(sessionId: string) {
  return `${getWebSocketBaseUrl()}/ws/sessions/${encodeURIComponent(sessionId)}/conversation`
}
```

```ts
// frontend/src/hooks/useConversationRuntime.ts
export function useConversationRuntime(currentSessionId: string | null) {
  const setSnapshot = useConversationStore((state) => state.setSnapshot)
  const applyEvent = useConversationStore((state) => state.applyEvent)
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected')
  const wsRef = useRef<SessionConversationWebSocket | null>(null)

  const loadConversation = useCallback(async (sessionId: string) => {
    const response = await conversationApi.getConversation(sessionId)
    setSnapshot(sessionId, response.data)
    return response.data
  }, [setSnapshot])

  const connect = useCallback(async (sessionId: string) => {
    const snapshot = await loadConversation(sessionId)
    const ws = new SessionConversationWebSocket()
    ws.connect(sessionId)
    ws.on('conversation.event', (event) => applyEvent(sessionId, event))
    ws.on('conversation.resync_required', async () => {
      const refreshed = await loadConversation(sessionId)
      ws.sync(refreshed.session.lastEventSeq)
    })
    ws.on('connection:open', () => {
      setConnectionStatus('connected')
      ws.sync(snapshot.session.lastEventSeq)
    })
    wsRef.current = ws
  }, [applyEvent, loadConversation])

  const startTurn = useCallback(async (payload: { sessionId: string; message: string; providerId: string; modelId: string }) => {
    if (!wsRef.current || currentSessionId !== payload.sessionId) {
      await connect(payload.sessionId)
    }
    wsRef.current?.startTurn(payload.message, payload.providerId, payload.modelId)
  }, [connect, currentSessionId])

  const cancelRun = useCallback((runId: string) => {
    wsRef.current?.cancelRun(runId)
  }, [])

  return { connectionStatus, loadConversation, startTurn, cancelRun }
}
```

```ts
// frontend/src/hooks/useSendMessage.ts
interface SendMessageDependencies {
  currentProject: { id: string; name?: string; path?: string } | null
  currentSession: SessionSummary | null
  configured: boolean
  selection: { providerId: string | null; modelId: string | null }
  createSession: (
    projectId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<SessionSummary>
  writeSessionPreferences: (
    sessionId: string,
    payload: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => Promise<unknown>
  startTurn: (payload: {
    sessionId: string
    message: string
    projectId: string
    providerId: string
    modelId: string
  }) => Promise<void>
  notify: (message: string) => void
}

if (!dependencies.currentProject) {
  dependencies.notify('请先选择一个项目')
  return
}

await dependencies.startTurn({
  sessionId: targetSession.id,
  message,
  projectId: dependencies.currentProject.id,
  providerId: dependencies.selection.providerId!,
  modelId: dependencies.selection.modelId!,
})
```

```tsx
// frontend/src/components/workspace/WorkspaceTranscript.tsx
if (item.messageType === 'user_message') {
  return <UserBubble key={item.id} content={item.contentText} />
}

if (item.messageType === 'assistant_message') {
  return (
    <MarkdownRenderer
      key={item.id}
      content={item.contentText}
      variant="plain"
      isStreaming={item.streamState === 'streaming'}
      className={transcriptClassName}
    />
  )
}

if (item.messageType === 'tool_trace') {
  return <ToolTraceCard key={item.id} item={item} />
}

if (item.messageType === 'system_notice') {
  return <div key={item.id} className="mb-6 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">{item.contentText}</div>
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- src/hooks/useConversationRuntime.test.ts src/hooks/useSendMessage.test.ts src/components/workspace/ToolTraceCard.test.tsx`
Expected: PASS with `startTurn` wiring coverage, websocket resync coverage, and transcript rendering for `tool_trace` + `system_notice`.

- [ ] **Step 5: Commit**

```bash
git add \
  frontend/src/services/sessionConversationWebSocket.ts \
  frontend/src/services/runtimeConfig.ts \
  frontend/src/hooks/useConversationData.ts \
  frontend/src/hooks/useConversationRuntime.ts \
  frontend/src/components/workspace/ToolTraceCard.tsx \
  frontend/src/components/workspace/WorkspaceTranscript.tsx \
  frontend/src/hooks/useSendMessage.ts \
  frontend/src/hooks/useCurrentSessionViewModel.ts \
  frontend/src/pages/AgentWorkspace.tsx \
  frontend/src/hooks/useSendMessage.test.ts \
  frontend/src/hooks/useConversationRuntime.test.ts \
  frontend/src/components/workspace/ToolTraceCard.test.tsx
git commit -m "feat: cut workspace ui over to conversation entities"
```

## Task 7: Remove Legacy Execution/Transcript Flow and Verify the Whole Cutover

**Files:**
- Delete: `backend/app/models/execution.py`
- Delete: `backend/app/models/transcript.py`
- Delete: `backend/app/models/session_history.py`
- Delete: `backend/app/storage/repositories/execution_repo.py`
- Delete: `backend/app/storage/repositories/conversation_repo.py`
- Delete: `backend/app/services/transcript_service.py`
- Delete: `backend/app/api/routes/agent.py`
- Delete: `frontend/src/features/sessions/sessionHistoryRound.ts`
- Delete: `frontend/src/features/sessions/sessionLoader.ts`
- Delete: `frontend/src/hooks/useExecutionRuntime.ts`
- Delete: `frontend/src/hooks/useExecutionWebSocket.ts`
- Delete: `frontend/src/hooks/useExecutionDraftRound.ts`
- Delete: `frontend/src/hooks/useExecutionOverlay.ts`
- Delete: `frontend/src/hooks/useExecutionOverlayUi.ts`
- Delete: `frontend/src/hooks/executionOverlayHelpers.ts`
- Delete: `frontend/src/hooks/executionOverlayState.ts`
- Delete: `frontend/src/services/websocketClient.ts`
- Delete: `frontend/src/hooks/useSessionRenderItems.ts`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/__init__.py`
- Modify: `backend/app/storage/repositories/__init__.py`
- Modify: `frontend/src/types/workspace.ts`
- Modify: `frontend/src/features/sessions/sessionStore.ts`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`

- [ ] **Step 1: Write the failing cleanup regressions**

```python
def test_legacy_agent_routes_are_not_registered():
    route_paths = {route.path for route in app.routes}

    assert "/api/agent/status/{execution_id}" not in route_paths
    assert "/api/agent/history/{project_id}" not in route_paths
    assert "/api/agent/cancel/{execution_id}" not in route_paths


def test_legacy_history_route_is_not_registered():
    route_paths = {route.path for route in app.routes}

    assert "/api/sessions/{session_id}/history" not in route_paths
```

```ts
import { describe, expect, it } from 'vitest'
import type { SessionSummary } from '@/types/workspace'

describe('workspace types', () => {
  it('keeps session summary but drops round history types from runtime usage', () => {
    const summary: SessionSummary = {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      createdAt: '2026-04-24T10:00:00Z',
      updatedAt: '2026-04-24T10:00:00Z',
    }

    expect(summary.title).toBe('会话')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_api/test_conversation_api.py tests/test_services/test_cleanup.py -q`
Expected: FAIL until the legacy route files and exports are actually removed.

- [ ] **Step 3: Remove legacy modules and update imports**

```python
# backend/app/models/__init__.py
from app.models.conversation import ConversationEvent, Message, Run, Turn
from app.models.conversation_snapshot import ConversationSnapshot, StartTurnResult
from app.models.project import Project
from app.models.session import Session

__all__ = [
    "ConversationEvent",
    "ConversationSnapshot",
    "Message",
    "Project",
    "Run",
    "Session",
    "StartTurnResult",
    "Turn",
]
```

```ts
// frontend/src/types/workspace.ts
export interface SessionSummary {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  createdAt: string
  updatedAt: string
}

export interface SessionCreatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export interface SessionUpdatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}
```

```bash
rm backend/app/models/execution.py
rm backend/app/models/transcript.py
rm backend/app/models/session_history.py
rm backend/app/storage/repositories/execution_repo.py
rm backend/app/storage/repositories/conversation_repo.py
rm backend/app/services/transcript_service.py
rm backend/app/api/routes/agent.py
rm frontend/src/features/sessions/sessionHistoryRound.ts
rm frontend/src/features/sessions/sessionLoader.ts
rm frontend/src/hooks/useExecutionRuntime.ts
rm frontend/src/hooks/useExecutionWebSocket.ts
rm frontend/src/hooks/useExecutionDraftRound.ts
rm frontend/src/hooks/useExecutionOverlay.ts
rm frontend/src/hooks/useExecutionOverlayUi.ts
rm frontend/src/hooks/executionOverlayHelpers.ts
rm frontend/src/hooks/executionOverlayState.ts
rm frontend/src/services/websocketClient.ts
rm frontend/src/hooks/useSessionRenderItems.ts
```

- [ ] **Step 4: Run tests to verify the direct cutover passes**

Run: `cd backend && pytest -q`
Expected: PASS with no imports of `Execution`, `TranscriptRecord`, `SessionHistoryResponse`, or legacy agent routes.

Run: `cd frontend && pnpm test`
Expected: PASS with no imports of `historyBySessionId`, `WorkspaceSessionRound`, or `ExecutionWebSocket`.

Run: `cd frontend && pnpm build`
Expected: PASS and emit a production bundle without TypeScript errors from removed legacy types.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy execution and transcript flows"
```

## Final Verification Checklist

- [ ] `GET /api/sessions/{session_id}/conversation` returns normalized snapshot data.
- [ ] `WS /ws/sessions/{session_id}/conversation` supports `conversation.sync`, `conversation.start_turn`, and `conversation.cancel_run`.
- [ ] Assistant streaming updates an existing `assistant_message` instead of creating transient overlay-only items.
- [ ] Tool calls persist as `tool_trace` messages and are visible after page reload.
- [ ] Cancelling a run emits `run.cancelled` and appends a `system_notice`.
- [ ] No runtime code imports `ExecutionModel`, `ConversationModel`, `TranscriptRecord`, `SessionHistoryResponse`, `ExecutionWebSocket`, `historyBySessionId`, or `WorkspaceSessionRound`.

## Execution Notes

- Keep the rollout branch focused on this cutover only. Do not mix unrelated cleanup.
- Because the workspace is already dirty, stage only the files listed per task when committing.
- If the database gets stuck on legacy tables during local verification, delete the local SQLite file and re-run `Base.metadata.create_all`.
- Prefer landing backend tasks 1-4 before frontend tasks 5-7 so the frontend always has a stable snapshot/event contract to target.
