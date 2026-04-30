import sqlite3
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


def _create_legacy_conversation_schema(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE projects (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                path VARCHAR NOT NULL UNIQUE,
                language VARCHAR,
                config JSON,
                created_at DATETIME,
                updated_at DATETIME
            );

            CREATE TABLE sessions (
                id VARCHAR PRIMARY KEY,
                project_id VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                preferred_provider_id VARCHAR,
                preferred_model_id VARCHAR,
                last_event_seq INTEGER NOT NULL,
                active_turn_id VARCHAR,
                created_at DATETIME,
                updated_at DATETIME
            );

            CREATE TABLE turns (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                turn_index INTEGER NOT NULL,
                root_message_id VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                active_run_id VARCHAR,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                completed_at DATETIME
            );

            CREATE TABLE runs (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                turn_id VARCHAR NOT NULL,
                attempt_index INTEGER NOT NULL,
                status VARCHAR NOT NULL,
                provider_id VARCHAR,
                model_id VARCHAR,
                workspace_ref VARCHAR,
                started_at DATETIME,
                finished_at DATETIME,
                error_code VARCHAR,
                error_message TEXT
            );

            CREATE TABLE messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                turn_id VARCHAR NOT NULL,
                run_id VARCHAR,
                message_index INTEGER NOT NULL,
                role VARCHAR NOT NULL,
                message_type VARCHAR NOT NULL,
                stream_state VARCHAR NOT NULL,
                display_mode VARCHAR NOT NULL,
                content_text TEXT NOT NULL,
                payload_json JSON NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                completed_at DATETIME
            );

            CREATE TABLE conversation_events (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR NOT NULL,
                seq INTEGER NOT NULL,
                turn_id VARCHAR,
                run_id VARCHAR,
                message_id VARCHAR,
                event_type VARCHAR NOT NULL,
                payload_json JSON NOT NULL,
                created_at DATETIME NOT NULL
            );

            CREATE UNIQUE INDEX uq_conversation_events_session_seq
                ON conversation_events (session_id, seq);
            """
        )
        timestamp = "2026-04-25 10:00:00"
        cursor.execute(
            """
            INSERT INTO projects (id, name, path, language, config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("project-1", "ReflexionOS", "/tmp/reflexion", None, "{}", timestamp, timestamp),
        )
        cursor.execute(
            """
            INSERT INTO sessions (
                id, project_id, title, preferred_provider_id, preferred_model_id,
                last_event_seq, active_turn_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "session-1",
                "project-1",
                "会话",
                None,
                None,
                1,
                "turn-1",
                timestamp,
                timestamp,
            ),
        )
        cursor.execute(
            """
            INSERT INTO turns (
                id, session_id, turn_index, root_message_id, status, active_run_id,
                created_at, updated_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("turn-1", "session-1", 1, "msg-1", "created", "run-1", timestamp, timestamp, None),
        )
        cursor.execute(
            """
            INSERT INTO runs (
                id, session_id, turn_id, attempt_index, status, provider_id, model_id,
                workspace_ref, started_at, finished_at, error_code, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "session-1",
                "turn-1",
                1,
                "created",
                "provider-a",
                "model-a",
                None,
                None,
                None,
                None,
                None,
            ),
        )
        cursor.execute(
            """
            INSERT INTO messages (
                id, session_id, turn_id, run_id, message_index, role, message_type,
                stream_state, display_mode, content_text, payload_json,
                created_at, updated_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-1",
                "session-1",
                "turn-1",
                None,
                1,
                "user",
                "user_message",
                "completed",
                "default",
                "hello",
                "{}",
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        cursor.execute(
            """
            INSERT INTO conversation_events (
                id, session_id, seq, turn_id, run_id, message_id,
                event_type, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-1",
                "session-1",
                1,
                "turn-1",
                "run-1",
                "msg-1",
                "message.created",
                "{}",
                timestamp,
            ),
        )
        connection.commit()
    finally:
        connection.close()


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
            turn_message_index=1,
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

    first = event_repo.append_many(
        [
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
        ]
    )[0]
    second = event_repo.append_many(
        [
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
        ]
    )[0]

    assert first.seq == 1
    assert second.seq == 2
    assert [event.id for event in event_repo.list_after_seq("session-1", after_seq=0)] == [
        "evt-1",
        "evt-2",
    ]
    assert turn_repo.get("turn-1").root_message_id == "msg-user-1"
    assert run_repo.get("run-1").status == RunStatus.CREATED
    assert message_repo.list_by_turn("turn-1")[0].content_text == "hello"


def test_conversation_event_append_assigns_monotonic_seq_per_session(tmp_path):
    db = Database(str(tmp_path / "conversation-events.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    event_repo = ConversationEventRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    session_repo.create(Session(id="session-2", project_id="project-1", title="会话 2"))

    seqs = [
        event_repo.append_many(
            [
                ConversationEvent(
                    id="evt-1",
                    session_id="session-1",
                    event_type=EventType.TURN_CREATED,
                    payload_json={"turn_id": "turn-1"},
                )
            ]
        )[0].seq,
        event_repo.append_many(
            [
                ConversationEvent(
                    id="evt-2",
                    session_id="session-1",
                    event_type=EventType.RUN_CREATED,
                    payload_json={"run_id": "run-1"},
                )
            ]
        )[0].seq,
        event_repo.append_many(
            [
                ConversationEvent(
                    id="evt-3",
                    session_id="session-2",
                    event_type=EventType.TURN_CREATED,
                    payload_json={"turn_id": "turn-2"},
                )
            ]
        )[0].seq,
        event_repo.append_many(
            [
                ConversationEvent(
                    id="evt-4",
                    session_id="session-1",
                    event_type=EventType.RUN_COMPLETED,
                    payload_json={"run_id": "run-1"},
                )
            ]
        )[0].seq,
    ]

    assert seqs == [1, 2, 1, 3]


def test_session_repo_delete_cascades_conversation_rows(tmp_path):
    db = Database(str(tmp_path / "conversation-cascade.db"))
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
            root_message_id="msg-1",
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
            id="msg-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
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
    event_repo.append_many(
        [
            ConversationEvent(
                id="evt-1",
                session_id="session-1",
                event_type=EventType.MESSAGE_CREATED,
                payload_json={"message_id": "msg-1"},
            )
        ]
    )

    deleted = session_repo.delete("session-1")

    assert deleted is True
    assert session_repo.get("session-1") is None
    assert turn_repo.list_by_session("session-1") == []
    assert run_repo.list_by_session("session-1") == []
    assert message_repo.list_by_session("session-1") == []
    assert event_repo.list_after_seq("session-1", after_seq=0) == []


def test_database_resets_incompatible_conversation_schema(tmp_path):
    db_path = tmp_path / "legacy-conversation-schema.db"
    _create_legacy_conversation_schema(db_path)

    db = Database(str(db_path))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    event_repo = ConversationEventRepository(db)

    with sqlite3.connect(db_path) as connection:
        message_columns = {
            row[1] for row in connection.execute('PRAGMA table_info("messages")').fetchall()
        }
        unique_indexes = connection.execute('PRAGMA index_list("messages")').fetchall()
        unique_index_columns = {
            tuple(
                column_row[2]
                for column_row in connection.execute(
                    f'PRAGMA index_info("{index_row[1]}")'
                ).fetchall()
            )
            for index_row in unique_indexes
            if index_row[2]
        }

    assert "message_index" not in message_columns
    assert "turn_message_index" in message_columns
    assert ("turn_id", "turn_message_index") in unique_index_columns
    assert session_repo.get("session-1") is None
    assert turn_repo.list_by_session("session-1") == []
    assert run_repo.list_by_session("session-1") == []
    assert message_repo.list_by_session("session-1") == []
    assert event_repo.list_after_seq("session-1", after_seq=0) == []


def test_list_by_session_orders_by_turn_then_turn_message_index(tmp_path):
    db = Database(str(tmp_path / "message-ordering.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-turn1-1",
            status=TurnStatus.CREATED,
        )
    )
    turn_repo.create(
        Turn(
            id="turn-2",
            session_id="session-1",
            turn_index=2,
            root_message_id="msg-turn2-1",
            status=TurnStatus.CREATED,
        )
    )

    message_repo.create(
        Message(
            id="msg-turn2-1",
            session_id="session-1",
            turn_id="turn-2",
            run_id=None,
            turn_message_index=1,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="turn2",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 0, 0),
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
            completed_at=datetime(2026, 4, 24, 10, 0, 0),
        )
    )
    message_repo.create(
        Message(
            id="msg-turn1-2",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=2,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="turn1-2",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 1, 0),
            updated_at=datetime(2026, 4, 24, 10, 1, 0),
            completed_at=datetime(2026, 4, 24, 10, 1, 0),
        )
    )
    message_repo.create(
        Message(
            id="msg-turn1-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="turn1-1",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 2, 0),
            updated_at=datetime(2026, 4, 24, 10, 2, 0),
            completed_at=datetime(2026, 4, 24, 10, 2, 0),
        )
    )

    ordered_ids = [message.id for message in message_repo.list_by_session("session-1")]
    assert ordered_ids == ["msg-turn1-1", "msg-turn1-2", "msg-turn2-1"]


def test_list_by_session_keeps_message_when_turn_row_is_missing(tmp_path):
    db = Database(str(tmp_path / "message-ordering-missing-turn.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-turn1-1",
            status=TurnStatus.CREATED,
        )
    )

    message_repo.create(
        Message(
            id="msg-turn1-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="turn1-1",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 0, 0),
            updated_at=datetime(2026, 4, 24, 10, 0, 0),
            completed_at=datetime(2026, 4, 24, 10, 0, 0),
        )
    )
    message_repo.create(
        Message(
            id="msg-missing-turn",
            session_id="session-1",
            turn_id="turn-missing",
            run_id=None,
            turn_message_index=1,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="orphan message",
            payload_json={},
            created_at=datetime(2026, 4, 24, 10, 1, 0),
            updated_at=datetime(2026, 4, 24, 10, 1, 0),
            completed_at=datetime(2026, 4, 24, 10, 1, 0),
        )
    )

    ordered_ids = [message.id for message in message_repo.list_by_session("session-1")]
    assert ordered_ids == ["msg-turn1-1", "msg-missing-turn"]


def test_message_repo_from_payload_normalizes_payload_json_shapes():
    message_repo = MessageRepository(db=None)

    base_payload = {
        "message_id": "msg-1",
        "turn_id": "turn-1",
        "turn_message_index": 1,
        "role": "assistant",
        "message_type": MessageType.TOOL_TRACE.value,
        "display_mode": "default",
        "content_text": "",
    }

    message_none = message_repo.from_payload(
        session_id="session-1",
        payload={**base_payload, "payload_json": None},
    )
    assert message_none.payload_json == {}

    message_json_object = message_repo.from_payload(
        session_id="session-1",
        payload={**base_payload, "payload_json": '{"tool_name":"shell"}'},
    )
    assert message_json_object.payload_json == {"tool_name": "shell"}

    message_non_dict_json = message_repo.from_payload(
        session_id="session-1",
        payload={**base_payload, "payload_json": "[]"},
    )
    assert message_non_dict_json.payload_json == {}
