from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier, BrokenBarrierError

import pytest

from app.models.conversation import ConversationEvent, EventType, MessageType, RunStatus
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def test_start_turn_creates_turn_user_message_and_run(tmp_path):
    db = Database(str(tmp_path / "conversation-service-start-turn.db"))
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
    assert started.turn.root_message_id == started.user_message.id
    assert started.run.id.startswith("run-")
    assert started.user_message.message_type == MessageType.USER_MESSAGE
    assert started.user_message.content_text == "请检查项目结构"


def test_get_snapshot_returns_session_turn_run_and_messages(tmp_path):
    db = Database(str(tmp_path / "conversation-service-snapshot.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    started = service.start_turn(
        session_id="session-1",
        content="hello",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    snapshot = service.get_snapshot("session-1")

    assert snapshot.session.id == "session-1"
    assert snapshot.session.active_turn_id == started.turn.id
    assert snapshot.session.last_event_seq == 3
    assert [turn.id for turn in snapshot.turns] == [started.turn.id]
    assert [run.id for run in snapshot.runs] == [started.run.id]
    assert [message.id for message in snapshot.messages] == [started.user_message.id]


def test_cancel_run_appends_cancel_and_system_notice(tmp_path):
    db = Database(str(tmp_path / "conversation-service-cancel-run.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    started = service.start_turn(
        session_id="session-1",
        content="hello",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    cancelled = service.cancel_run(started.run.id)
    events = service.list_events_after("session-1", after_seq=3)
    notice_messages = [
        message for message in service.message_repo.list_by_turn(started.turn.id)
        if message.message_type == MessageType.SYSTEM_NOTICE
    ]

    assert cancelled.status == RunStatus.CANCELLED
    assert [event.event_type for event in events] == [
        EventType.RUN_CANCELLED,
        EventType.SYSTEM_NOTICE_EMITTED,
    ]
    assert len(notice_messages) == 1


def test_start_turn_rejects_when_active_turn_exists(tmp_path):
    db = Database(str(tmp_path / "conversation-service-active-turn.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    service.start_turn(
        session_id="session-1",
        content="first",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    with pytest.raises(ValueError, match="已有活跃轮次"):
        service.start_turn(
            session_id="session-1",
            content="second",
            provider_id="provider-a",
            model_id="model-a",
            workspace_ref=None,
        )


def test_cancel_run_on_terminal_run_keeps_state_and_noop(tmp_path):
    db = Database(str(tmp_path / "conversation-service-cancel-terminal.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    started = service.start_turn(
        session_id="session-1",
        content="hello",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    service.append_events(
        "session-1",
        [
            ConversationEvent(
                id="evt-complete",
                session_id="session-1",
                turn_id=started.turn.id,
                run_id=started.run.id,
                event_type=EventType.RUN_COMPLETED,
                payload_json={},
            )
        ],
    )
    seq_before_cancel = service.get_snapshot("session-1").session.last_event_seq

    cancelled = service.cancel_run(started.run.id)
    snapshot = service.get_snapshot("session-1")

    assert cancelled.status == RunStatus.COMPLETED
    assert snapshot.runs[0].status == RunStatus.COMPLETED
    assert snapshot.session.last_event_seq == seq_before_cancel
    assert service.list_events_after("session-1", after_seq=seq_before_cancel) == []


def test_append_events_batch_is_atomic_when_projection_fails(tmp_path):
    db = Database(str(tmp_path / "conversation-service-atomic.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    with pytest.raises(ValueError, match="轮次不存在"):
        service.append_events(
            "session-1",
            [
                ConversationEvent(
                    id="evt-1",
                    session_id="session-1",
                    turn_id="turn-ok",
                    event_type=EventType.TURN_CREATED,
                    payload_json={
                        "turn_id": "turn-ok",
                        "turn_index": 1,
                        "root_message_id": "msg-user-1",
                    },
                ),
                ConversationEvent(
                    id="evt-2",
                    session_id="session-1",
                    turn_id="turn-missing",
                    run_id="run-1",
                    event_type=EventType.RUN_CREATED,
                    payload_json={
                        "run_id": "run-1",
                        "turn_id": "turn-missing",
                        "attempt_index": 1,
                    },
                ),
            ],
        )

    snapshot = service.get_snapshot("session-1")
    assert snapshot.session.last_event_seq == 0
    assert snapshot.turns == []
    assert snapshot.runs == []
    assert snapshot.messages == []
    assert service.list_events_after("session-1", after_seq=0) == []


def test_cleanup_events_removes_terminal_turn_events_but_keeps_snapshot_state(tmp_path):
    db = Database(str(tmp_path / "conversation-service-cleanup.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    first = service.start_turn(
        session_id="session-1",
        content="first",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    service.append_events(
        "session-1",
        [
            ConversationEvent(
                id="evt-msg-1",
                session_id="session-1",
                turn_id=first.turn.id,
                run_id=first.run.id,
                message_id="msg-assistant-1",
                event_type=EventType.MESSAGE_CREATED,
                payload_json={
                    "message_id": "msg-assistant-1",
                    "turn_id": first.turn.id,
                    "run_id": first.run.id,
                    "role": "assistant",
                    "message_type": "assistant_message",
                    "turn_message_index": 2,
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {},
                },
            ),
            ConversationEvent(
                id="evt-msg-2",
                session_id="session-1",
                turn_id=first.turn.id,
                run_id=first.run.id,
                message_id="msg-assistant-1",
                event_type=EventType.MESSAGE_CONTENT_COMMITTED,
                payload_json={"content_text": "done"},
            ),
            ConversationEvent(
                id="evt-msg-3",
                session_id="session-1",
                turn_id=first.turn.id,
                run_id=first.run.id,
                message_id="msg-assistant-1",
                event_type=EventType.MESSAGE_COMPLETED,
                payload_json={"completed_at": datetime.now().isoformat()},
            ),
            ConversationEvent(
                id="evt-run-1",
                session_id="session-1",
                turn_id=first.turn.id,
                run_id=first.run.id,
                event_type=EventType.RUN_COMPLETED,
                payload_json={"finished_at": datetime.now().isoformat()},
            ),
        ],
    )

    cleaned = service.cleanup_events(
        now=datetime.now() + timedelta(hours=2),
        completed_retention=timedelta(minutes=30),
        failed_retention=timedelta(days=7),
    )

    snapshot = service.get_snapshot("session-1")

    assert cleaned > 0
    assert snapshot.messages[-1].content_text == "done"
    assert service.list_events_after("session-1", after_seq=0) == []


def test_cleanup_events_keeps_seq_monotonic_and_marks_old_after_seq_for_resync(tmp_path):
    db = Database(str(tmp_path / "conversation-service-cleanup-monotonic.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    first = service.start_turn(
        session_id="session-1",
        content="first",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    service.cancel_run(first.run.id)
    first_last_seq = service.get_snapshot("session-1").session.last_event_seq

    cleaned = service.cleanup_events(
        now=datetime.now() + timedelta(days=8),
        completed_retention=timedelta(minutes=30),
        failed_retention=timedelta(days=7),
    )

    second = service.start_turn(
        session_id="session-1",
        content="second",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    events = service.list_events_after("session-1", after_seq=0)

    assert cleaned == first_last_seq
    assert service.requires_resync("session-1", after_seq=0) is True
    assert events[0].seq > first_last_seq
    assert second.user_message.content_text == "second"


def test_start_turn_concurrent_requests_only_allow_one_active_turn(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "conversation-service-concurrent-start-turn.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    original_append_events = service._append_events_locked
    barrier = Barrier(2)

    def barriered_append_events(session_id, events):
        try:
            barrier.wait(timeout=0.2)
        except BrokenBarrierError:
            pass
        return original_append_events(session_id, events)

    monkeypatch.setattr(service, "_append_events_locked", barriered_append_events)

    def run_start_turn(content: str):
        try:
            started = service.start_turn(
                session_id="session-1",
                content=content,
                provider_id="provider-a",
                model_id="model-a",
                workspace_ref=None,
            )
            return ("ok", started.turn.id)
        except ValueError as exc:
            return ("error", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_start_turn, "first")
        second = executor.submit(run_start_turn, "second")
        results = [first.result(), second.result()]

    success = [result for result in results if result[0] == "ok"]
    errors = [result for result in results if result[0] == "error"]
    snapshot = service.get_snapshot("session-1")

    assert len(success) == 1
    assert len(errors) == 1
    assert "已有活跃轮次" in errors[0][1]
    assert len(snapshot.turns) == 1
