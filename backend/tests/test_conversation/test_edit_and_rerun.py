from datetime import datetime

import pytest

from app.errors import NotFoundValueError
from app.ids import new_message_id
from app.models.conversation import ConversationEvent, EventType, MessageType, RunStatus
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def _setup_service(tmp_path, db_name="edit-rerun.db"):
    db = Database(str(tmp_path / db_name))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    return service


def _complete_turn(service, started):
    assistant_msg_id = new_message_id()
    service.append_events(
        "session-1",
        [
            ConversationEvent(
                id=f"evt-msg-{assistant_msg_id}",
                session_id="session-1",
                turn_id=started.turn.id,
                run_id=started.run.id,
                message_id=assistant_msg_id,
                event_type=EventType.MESSAGE_CREATED,
                payload_json={
                    "message_id": assistant_msg_id,
                    "turn_id": started.turn.id,
                    "run_id": started.run.id,
                    "role": "assistant",
                    "message_type": "assistant_message",
                    "turn_message_index": 2,
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {},
                },
            ),
            ConversationEvent(
                id=f"evt-commit-{assistant_msg_id}",
                session_id="session-1",
                turn_id=started.turn.id,
                run_id=started.run.id,
                message_id=assistant_msg_id,
                event_type=EventType.MESSAGE_CONTENT_COMMITTED,
                payload_json={"content_text": "assistant reply"},
            ),
            ConversationEvent(
                id=f"evt-complete-{assistant_msg_id}",
                session_id="session-1",
                turn_id=started.turn.id,
                run_id=started.run.id,
                message_id=assistant_msg_id,
                event_type=EventType.MESSAGE_COMPLETED,
                payload_json={"completed_at": datetime.now().isoformat()},
            ),
            ConversationEvent(
                id=f"evt-run-complete-{started.run.id}",
                session_id="session-1",
                turn_id=started.turn.id,
                run_id=started.run.id,
                event_type=EventType.RUN_COMPLETED,
                payload_json={"finished_at": datetime.now().isoformat()},
            ),
        ],
    )


def test_edit_user_message_truncates_subsequent_turns(tmp_path):
    service = _setup_service(tmp_path, "edit-user-msg.db")

    first = service.start_turn(
        session_id="session-1",
        content="first question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, first)

    second = service.start_turn(
        session_id="session-1",
        content="second question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, second)

    first_user_msg = service.message_repo.get(first.user_message.id)
    assert first_user_msg is not None

    result = service.edit_and_rerun(
        session_id="session-1",
        message_id=first_user_msg.id,
        new_content="edited question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    assert result.user_message.content_text == "edited question"
    assert service.turn_repo.get(first.turn.id) is None
    assert service.turn_repo.get(second.turn.id) is None
    assert service.turn_repo.get(result.turn.id) is not None
    next_idx = service.turn_repo.next_turn_index("session-1")
    assert next_idx == 2


def test_regenerate_assistant_message_truncates_subsequent_turns(tmp_path):
    service = _setup_service(tmp_path, "regenerate-assistant.db")

    first = service.start_turn(
        session_id="session-1",
        content="original question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, first)

    second = service.start_turn(
        session_id="session-1",
        content="follow-up question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, second)

    first_assistant_msg = service.message_repo.list_by_turn(first.turn.id)[1]
    assert first_assistant_msg.message_type == MessageType.ASSISTANT_MESSAGE

    result = service.edit_and_rerun(
        session_id="session-1",
        message_id=first_assistant_msg.id,
        new_content=None,
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    assert result.user_message.content_text == "original question"
    assert service.turn_repo.get(first.turn.id) is None
    assert service.turn_repo.get(second.turn.id) is None
    assert service.turn_repo.get(result.turn.id) is not None


def test_edit_last_user_message_works_when_no_subsequent_turns(tmp_path):
    service = _setup_service(tmp_path, "edit-last-msg.db")

    first = service.start_turn(
        session_id="session-1",
        content="only question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, first)

    user_msg = service.message_repo.get(first.user_message.id)
    assert user_msg is not None

    result = service.edit_and_rerun(
        session_id="session-1",
        message_id=user_msg.id,
        new_content="edited only question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    assert result.user_message.content_text == "edited only question"
    assert service.turn_repo.get(first.turn.id) is None
    assert service.turn_repo.get(result.turn.id) is not None


def test_edit_with_nonexistent_message_id_raises_not_found(tmp_path):
    service = _setup_service(tmp_path, "edit-nonexistent.db")

    with pytest.raises(NotFoundValueError, match="消息不存在"):
        service.edit_and_rerun(
            session_id="session-1",
            message_id="msg-nonexistent",
            new_content="new",
            provider_id="provider-a",
            model_id="model-a",
            workspace_ref=None,
        )


def test_edit_with_message_from_wrong_session_raises_value_error(tmp_path):
    service = _setup_service(tmp_path, "edit-wrong-session.db")
    service.session_repo.create(Session(id="session-2", project_id="project-1", title="会话2"))

    other = service.start_turn(
        session_id="session-2",
        content="other session question",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )
    _complete_turn(service, other)

    other_user_msg = service.message_repo.get(other.user_message.id)
    assert other_user_msg is not None

    with pytest.raises(ValueError, match="消息不属于当前会话"):
        service.edit_and_rerun(
            session_id="session-1",
            message_id=other_user_msg.id,
            new_content="new",
            provider_id="provider-a",
            model_id="model-a",
            workspace_ref=None,
        )
