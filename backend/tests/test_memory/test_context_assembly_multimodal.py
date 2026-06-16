from app.memory.context_assembly import ContextAssembler, build_context_assembly
from app.models.conversation import (
    Message,
    MessageAttachment,
    MessageType,
    StreamState,
    Turn,
    TurnStatus,
)
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.storage.database import Database
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository


def test_build_context_assembly_preserves_multimodal_content_parts():
    result = build_context_assembly(
        static_blocks=[],
        recent_messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please inspect this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                ],
            }
        ],
        current_turn_message=None,
        supplemental_block=None,
    )

    assert isinstance(result.recent_messages[0]["content"], list)
    assert result.recent_messages[0]["content"][0]["type"] == "text"
    assert result.recent_messages[0]["content"][1]["type"] == "image_url"


def test_context_assembler_keeps_image_parts_for_recent_user_messages(tmp_path):
    db = Database(str(tmp_path / "context-assembly-images.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="Conversation"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-root-1",
            status=TurnStatus.COMPLETED,
        )
    )

    message_repo.create(
        Message(
            id="msg-user-image",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="Please inspect this image",
            payload_json={},
            attachments=[
                MessageAttachment(
                    id="att-1",
                    type="image",
                    mime_type="image/png",
                    file_path="https://example.com/image.png",
                    file_size=123,
                )
            ],
        )
    )

    assembler = ContextAssembler(conversation_service=conversation_service)
    result = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(tmp_path),
        supports_vision=True,
    )

    content = result.recent_messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_context_assembler_exposes_current_turn_multimodal_message(tmp_path):
    db = Database(str(tmp_path / "context-assembly-current-turn.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="Conversation"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-user-image",
            status=TurnStatus.RUNNING,
        )
    )

    message_repo.create(
        Message(
            id="msg-user-image",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="Please inspect this image",
            payload_json={},
            attachments=[
                MessageAttachment(
                    id="att-1",
                    type="image",
                    mime_type="image/png",
                    file_path="https://example.com/image.png",
                    file_size=123,
                )
            ],
        )
    )

    assembler = ContextAssembler(conversation_service=conversation_service)
    result = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(tmp_path),
        current_turn_id="turn-1",
        supports_vision=True,
    )

    assert result.current_turn_message is not None
    content = result.current_turn_message["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_context_assembler_skips_supplemental_block_for_multimodal_current_turn(tmp_path):
    db = Database(str(tmp_path / "context-assembly-skip-supplemental.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="Conversation"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-user-image",
            status=TurnStatus.RUNNING,
        )
    )

    message_repo.create(
        Message(
            id="msg-user-image",
            session_id="session-1",
            turn_id="turn-1",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="Please inspect this image",
            payload_json={},
            attachments=[
                MessageAttachment(
                    id="att-1",
                    type="image",
                    mime_type="image/png",
                    file_path="https://example.com/image.png",
                    file_size=123,
                )
            ],
        )
    )

    message_repo.create(
        Message(
            id="msg-cont-1",
            session_id="session-1",
            turn_id="turn-prev",
            run_id="run-prev",
            turn_message_index=99,
            role="system",
            message_type=MessageType.SYSTEM_NOTICE,
            stream_state=StreamState.COMPLETED,
            display_mode="collapsed",
            content_text="Current goal: I cannot view images",
            payload_json={"kind": "continuation_artifact", "exclude_from_recall": True},
        )
    )

    assembler = ContextAssembler(conversation_service=conversation_service)
    result = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(tmp_path),
        current_turn_id="turn-1",
        supports_vision=True,
    )

    assert result.current_turn_message is not None
    assert result.supplemental_block is None
