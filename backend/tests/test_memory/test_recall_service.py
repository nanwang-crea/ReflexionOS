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
    user_message = next(message for message in snapshot.messages if message.id == started.user_message.id)

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

