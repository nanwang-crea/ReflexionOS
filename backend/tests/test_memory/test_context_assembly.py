from app.memory.context_assembly import ContextAssembler, build_context_assembly
from app.memory.continuation import build_continuation_artifact
from app.models.conversation import (
    Message,
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


def test_context_assembly_builds_static_recent_and_supplemental_layers():
    result = build_context_assembly(
        static_blocks=["AGENTS", "USER", "MEMORY"],
        recent_messages=[{"role": "user", "content": "最近消息"}],
        supplemental_block="当前目标: 继续实现 recall",
    )

    assert "AGENTS" in result.system_sections[0]
    assert result.recent_messages[0]["content"] == "最近消息"
    assert result.supplemental_block == "当前目标: 继续实现 recall"


def test_context_assembler_picks_latest_persisted_continuation_artifact_as_supplemental_block(
    tmp_path,
):
    db = Database(str(tmp_path / "context-assembly.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    turn_repo.create(
        Turn(
            id="turn-1",
            session_id="session-1",
            turn_index=1,
            root_message_id="msg-root-1",
            status=TurnStatus.COMPLETED,
        )
    )
    turn_repo.create(
        Turn(
            id="turn-2",
            session_id="session-1",
            turn_index=2,
            root_message_id="msg-root-2",
            status=TurnStatus.CREATED,
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
            content_text="上一轮需求",
            payload_json={},
        )
    )
    message_repo.create(
        Message(
            id="msg-assistant-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=2,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="上一轮结论",
            payload_json={},
        )
    )

    artifact = build_continuation_artifact(
        session_id="session-1",
        turn_id="turn-1",
        content_text="当前目标: 修 memory",
        message_id="msg-cont-1",
        turn_message_index=3,
    )
    message_repo.create(artifact)

    # Current turn root user message should NOT be included as seeded history.
    message_repo.create(
        Message(
            id="msg-user-2",
            session_id="session-1",
            turn_id="turn-2",
            run_id=None,
            turn_message_index=1,
            role="user",
            message_type=MessageType.USER_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="本轮需求",
            payload_json={},
        )
    )

    assembler = ContextAssembler(conversation_service=conversation_service)
    result = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(tmp_path),
        current_turn_id="turn-2",
    )

    assert result.supplemental_block == "当前目标: 修 memory"
    seeded_contents = [message["content"] for message in result.recent_messages]
    assert "上一轮需求" in seeded_contents
    assert "本轮需求" not in seeded_contents


def test_context_assembler_reads_agents_md_as_system_section(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Project rules here", encoding="utf-8")
    db = Database(str(tmp_path / "context-assembly-agents.db"))
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    message_repo = MessageRepository(db)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        message_repo=message_repo,
    )

    session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))

    assembler = ContextAssembler(conversation_service=conversation_service)
    result = assembler.build_for_session(
        session_id="session-1",
        project_id="project-1",
        project_path=str(tmp_path),
        current_turn_id=None,
    )

    assert any("Project rules here" in section for section in result.system_sections)
