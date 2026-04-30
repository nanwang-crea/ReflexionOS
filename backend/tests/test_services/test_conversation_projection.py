from datetime import datetime

from app.memory.continuation import build_continuation_artifact
from app.models.conversation import ConversationEvent, EventType, RunStatus, StreamState, TurnStatus
from app.models.session import Session
from app.services.conversation_projection import ConversationProjection
from app.storage.database import Database
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.message_search_document_repo import MessageSearchDocumentRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository


def _build_projection(tmp_path, db_name: str = "conversation-projection.db"):
    db = Database(str(tmp_path / db_name))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    projection = ConversationProjection(
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
    )
    return projection, session_repo, turn_repo, run_repo


def _create_running_run(projection, session_repo, session_id: str = "session-1"):
    session_repo.create(Session(id=session_id, project_id="project-1", title="会话"))
    projection.apply(
        session_id,
        ConversationEvent(
            id="evt-turn",
            session_id=session_id,
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={
                "turn_id": "turn-1",
                "turn_index": 1,
                "root_message_id": "msg-user-1",
            },
        ),
    )
    projection.apply(
        session_id,
        ConversationEvent(
            id="evt-run",
            session_id=session_id,
            event_type=EventType.RUN_CREATED,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={
                "run_id": "run-1",
                "turn_id": "turn-1",
                "attempt_index": 1,
            },
        ),
    )


def test_projection_run_waiting_for_approval_keeps_turn_active(tmp_path):
    projection, session_repo, turn_repo, run_repo = _build_projection(
        tmp_path, "conversation-projection-waiting.db"
    )
    _create_running_run(projection, session_repo)

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-waiting",
            session_id="session-1",
            event_type=EventType.RUN_WAITING_FOR_APPROVAL,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={},
        ),
    )

    session = session_repo.get("session-1")
    turn = turn_repo.get("turn-1")
    run = run_repo.get("run-1")

    assert session is not None
    assert turn is not None
    assert run is not None
    assert run.status == RunStatus.WAITING_FOR_APPROVAL
    assert turn.status == TurnStatus.RUNNING
    assert turn.active_run_id == "run-1"
    assert session.active_turn_id == "turn-1"


def test_projection_run_resuming_sets_run_resuming_and_keeps_turn_active(tmp_path):
    projection, session_repo, turn_repo, run_repo = _build_projection(
        tmp_path, "conversation-projection-resuming.db"
    )
    _create_running_run(projection, session_repo)

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-resuming",
            session_id="session-1",
            event_type=EventType.RUN_RESUMING,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={},
        ),
    )

    session = session_repo.get("session-1")
    turn = turn_repo.get("turn-1")
    run = run_repo.get("run-1")

    assert session is not None
    assert turn is not None
    assert run is not None
    assert run.status == RunStatus.RESUMING
    assert turn.status == TurnStatus.RUNNING
    assert turn.active_run_id == "run-1"
    assert session.active_turn_id == "turn-1"


def test_projection_run_completed_marks_turn_completed_and_clears_session_active_turn(tmp_path):
    db = Database(str(tmp_path / "conversation-projection.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    projection = ConversationProjection(
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={
                "turn_id": "turn-1",
                "turn_index": 1,
                "root_message_id": "msg-user-1",
            },
        ),
    )
    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-2",
            session_id="session-1",
            event_type=EventType.RUN_CREATED,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={
                "run_id": "run-1",
                "turn_id": "turn-1",
                "attempt_index": 1,
            },
        ),
    )
    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-3",
            session_id="session-1",
            event_type=EventType.RUN_COMPLETED,
            turn_id="turn-1",
            run_id="run-1",
            payload_json={"finished_at": datetime(2026, 4, 24, 10, 0, 5).isoformat()},
        ),
    )

    session = session_repo.get("session-1")
    turn = turn_repo.get("turn-1")
    run = run_repo.get("run-1")

    assert session is not None
    assert turn is not None
    assert run is not None
    assert session.active_turn_id is None
    assert turn.status == TurnStatus.COMPLETED
    assert turn.active_run_id is None
    assert run.status == RunStatus.COMPLETED


def test_projection_message_content_committed_sets_full_message_text(tmp_path):
    db = Database(str(tmp_path / "conversation-projection-message-content.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    projection = ConversationProjection(
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={
                "turn_id": "turn-1",
                "turn_index": 1,
                "root_message_id": "msg-user-1",
            },
        ),
    )
    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-2",
            session_id="session-1",
            event_type=EventType.MESSAGE_CREATED,
            turn_id="turn-1",
            run_id="run-1",
            message_id="msg-assistant-1",
            payload_json={
                "message_id": "msg-assistant-1",
                "turn_id": "turn-1",
                "run_id": "run-1",
                "role": "assistant",
                "message_type": "assistant_message",
                "turn_message_index": 2,
                "display_mode": "default",
                "content_text": "",
                "payload_json": {},
            },
        ),
    )
    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-3",
            session_id="session-1",
            event_type=EventType.MESSAGE_CONTENT_COMMITTED,
            turn_id="turn-1",
            run_id="run-1",
            message_id="msg-assistant-1",
            payload_json={"content_text": "最终回答"},
        ),
    )

    message = message_repo.get("msg-assistant-1")

    assert message is not None
    assert message.content_text == "最终回答"
    assert message.stream_state == StreamState.STREAMING


def test_projection_message_created_populates_search_document(tmp_path):
    db = Database(str(tmp_path / "conversation-projection-message-search.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    message_search_repo = MessageSearchDocumentRepository(db)
    projection = ConversationProjection(
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
        message_search_repo=message_search_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={
                "turn_id": "turn-1",
                "turn_index": 1,
                "root_message_id": "msg-user-1",
            },
        ),
    )
    projection.apply(
        "session-1",
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
                "turn_message_index": 1,
                "display_mode": "default",
                "content_text": "请检查 memory 设计",
                "payload_json": {},
            },
        ),
    )

    document = message_search_repo.get("msg-user-1")

    assert document is not None
    assert document.session_id == "session-1"
    assert document.turn_id == "turn-1"
    assert document.turn_index == 1
    assert "请检查 memory 设计" in document.search_text


def test_projection_skips_indexing_when_message_excluded_from_recall(tmp_path):
    db = Database(str(tmp_path / "conversation-projection-message-search-exclude.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    message_search_repo = MessageSearchDocumentRepository(db)
    projection = ConversationProjection(
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
        message_search_repo=message_search_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-1",
            session_id="session-1",
            event_type=EventType.TURN_CREATED,
            turn_id="turn-1",
            payload_json={
                "turn_id": "turn-1",
                "turn_index": 1,
                "root_message_id": "msg-user-1",
            },
        ),
    )

    artifact = build_continuation_artifact(
        session_id="session-1",
        turn_id="turn-1",
        content_text="当前目标: 继续设计 recall\n已确认事实: \n未解决点: \n下一步建议: ",
    )

    projection.apply(
        "session-1",
        ConversationEvent(
            id="evt-2",
            session_id="session-1",
            event_type=EventType.MESSAGE_CREATED,
            turn_id="turn-1",
            message_id=artifact.id,
            payload_json={
                "message_id": artifact.id,
                "turn_id": "turn-1",
                "run_id": None,
                "role": artifact.role,
                "message_type": artifact.message_type.value,
                "turn_message_index": artifact.turn_message_index,
                "display_mode": artifact.display_mode,
                "content_text": artifact.content_text,
                "payload_json": artifact.payload_json,
            },
        ),
    )

    assert message_search_repo.get(artifact.id) is None
