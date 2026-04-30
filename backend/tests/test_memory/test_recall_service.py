import pytest

from app.memory.recall_service import RecallService
from app.models.conversation import MessageType
from app.models.session import Session
from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def build_started_turn(tmp_path):
    db = Database(str(tmp_path / "recall-service-search-docs.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    started = service.start_turn(
        session_id="session-1",
        content="请检查 memory 设计",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref="/tmp/project",
    )
    return service, started


def test_message_created_populates_search_document(tmp_path):
    service, started = build_started_turn(tmp_path)
    snapshot = service.get_snapshot("session-1")
    user_message = next(
        message for message in snapshot.messages if message.id == started.user_message.id
    )

    document = service.message_search_repo.get(user_message.id)

    assert document is not None
    assert document.session_id == "session-1"
    assert "请检查 memory 设计" in document.search_text


def test_message_payload_update_refreshes_tool_trace_search_text(tmp_path):
    service, started = build_started_turn(tmp_path)
    runtime_adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    runtime_adapter.handle_event(
        "tool:start",
        {"tool_name": "shell", "arguments": {"cmd": "pytest -q"}, "step_number": 1},
    )
    runtime_adapter.handle_event(
        "tool:error",
        {"tool_name": "shell", "step_number": 1, "error": "exit status 1"},
    )

    trace = next(
        message
        for message in service.get_snapshot("session-1").messages
        if message.message_type == MessageType.TOOL_TRACE
    )
    document = service.message_search_repo.get(trace.id)

    assert document is not None
    assert "pytest -q" in document.search_text
    assert "exit status 1" in document.search_text


@pytest.fixture
def recall_service(tmp_path) -> RecallService:
    db = Database(str(tmp_path / "recall-service.db"))
    return RecallService(db=db)


def test_recall_service_prefers_recent_user_decision_messages(recall_service: RecallService):
    recall_service.seed_document(
        message_id="msg-old",
        project_id="project-1",
        session_id="session-old",
        role="assistant",
        message_type="assistant_message",
        search_text="memory design used event replay messages table",
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


def test_recall_service_excludes_other_projects(recall_service: RecallService):
    recall_service.seed_document(
        message_id="msg-p1",
        project_id="project-1",
        session_id="session-p1",
        role="user",
        message_type="user_message",
        search_text="messages 表 记忆 设计",
        turn_index=1,
        turn_message_index=1,
        created_at="2026-04-28T10:00:00",
    )
    recall_service.seed_document(
        message_id="msg-p2",
        project_id="project-2",
        session_id="session-p2",
        role="user",
        message_type="user_message",
        search_text="messages 表 记忆 设计",
        turn_index=1,
        turn_message_index=1,
        created_at="2026-04-28T10:00:00",
    )

    results = recall_service.search(project_id="project-1", query="messages 表", limit=10)

    assert {result.message_id for result in results} == {"msg-p1"}
