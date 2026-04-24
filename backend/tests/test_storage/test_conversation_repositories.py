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
    assert message_repo.list_by_run("run-1") == []


def test_conversation_event_append_assigns_monotonic_seq_per_session(tmp_path):
    db = Database(str(tmp_path / "conversation-events.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    event_repo = ConversationEventRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    session_repo.create(Session(id="session-2", project_id="project-1", title="会话 2"))

    seqs = [
        event_repo.append(
            ConversationEvent(
                id="evt-1",
                session_id="session-1",
                event_type=EventType.TURN_CREATED,
                payload_json={"turn_id": "turn-1"},
            )
        ).seq,
        event_repo.append(
            ConversationEvent(
                id="evt-2",
                session_id="session-1",
                event_type=EventType.RUN_CREATED,
                payload_json={"run_id": "run-1"},
            )
        ).seq,
        event_repo.append(
            ConversationEvent(
                id="evt-3",
                session_id="session-2",
                event_type=EventType.TURN_CREATED,
                payload_json={"turn_id": "turn-2"},
            )
        ).seq,
        event_repo.append(
            ConversationEvent(
                id="evt-4",
                session_id="session-1",
                event_type=EventType.RUN_COMPLETED,
                payload_json={"run_id": "run-1"},
            )
        ).seq,
    ]

    assert seqs == [1, 2, 1, 3]
