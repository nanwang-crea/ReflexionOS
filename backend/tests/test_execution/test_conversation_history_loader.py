from app.execution.conversation_history_loader import ConversationHistoryLoader, _filter_seed_messages
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


def test_filter_seed_messages_basic():
    """测试 _filter_seed_messages 的基本过滤功能"""
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "收到"},
        {"role": "", "content": "空角色应被过滤"},
        {"role": "system", "content": ""},  # 空内容应被过滤
        {"role": "tool", "content": "结果", "tool_call_id": "call_1"},
    ]
    result = _filter_seed_messages(messages)
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"
    assert result[2]["role"] == "tool"
    assert result[2]["tool_call_id"] == "call_1"


def test_filter_seed_messages_preserves_tool_calls():
    """测试 _filter_seed_messages 保留 tool_calls 字段"""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "name": "shell", "arguments": {"cmd": "ls"}}],
        },
    ]
    result = _filter_seed_messages(messages)
    assert len(result) == 1
    assert result[0]["tool_calls"] is not None
    assert result[0]["tool_calls"][0]["name"] == "shell"


def test_filter_seed_messages_multimodal_content():
    """测试 _filter_seed_messages 保留多模态内容格式"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看这个图片"},
                {"type": "image_url", "url": "data:image/png;base64,abc"},
            ],
        },
    ]
    result = _filter_seed_messages(messages)
    assert len(result) == 1
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 2


def test_conversation_history_loader_includes_completed_tool_traces(
    tmp_path,
):
    db = Database(str(tmp_path / "history-loader-tool-trace.db"))
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
            content_text="帮我修 bug",
            payload_json={},
        )
    )
    message_repo.create(
        Message(
            id="msg-tool-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=2,
            role="tool",
            message_type=MessageType.TOOL_TRACE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="",
            payload_json={
                "tool_name": "shell",
                "arguments": {"cmd": "pytest"},
                "tool_call_id": "call_abc12345",
                "success": True,
                "output": "2 passed",
            },
        )
    )
    message_repo.create(
        Message(
            id="msg-assistant-1",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=3,
            role="assistant",
            message_type=MessageType.ASSISTANT_MESSAGE,
            stream_state=StreamState.COMPLETED,
            display_mode="default",
            content_text="测试通过了",
            payload_json={},
        )
    )

    loader = ConversationHistoryLoader(conversation_service=conversation_service)
    seeded = loader.load_for_session(
        session_id="session-1",
        project_id="project-1",
        current_turn_id="turn-2",
    )

    user_msg = next(m for m in seeded if m["role"] == "user")
    assert "帮我修 bug" in user_msg["content"]

    assistant_tool_msg = next(m for m in seeded if m["role"] == "assistant" and m.get("tool_calls"))
    assert assistant_tool_msg["tool_calls"][0]["name"] == "shell"
    assert assistant_tool_msg["tool_calls"][0]["arguments"] == {"cmd": "pytest"}
    assert assistant_tool_msg["tool_calls"][0]["id"] == "call_abc12345"

    tool_result_msg = next(m for m in seeded if m["role"] == "tool")
    assert tool_result_msg["tool_call_id"] == "call_abc12345"
    assert "2 passed" in tool_result_msg["content"]

    assistant_text_msg = next(m for m in seeded if m["role"] == "assistant" and not m.get("tool_calls"))
    assert "测试通过了" in assistant_text_msg["content"]


def test_conversation_history_loader_excludes_non_completed_tool_traces(tmp_path):
    db = Database(str(tmp_path / "history-loader-tool-trace-exclude.db"))
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
            id="msg-tool-running",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=1,
            role="tool",
            message_type=MessageType.TOOL_TRACE,
            stream_state=StreamState.STREAMING,
            display_mode="default",
            content_text="",
            payload_json={
                "tool_name": "shell",
                "arguments": {"cmd": "ls"},
                "status": "running",
            },
        )
    )
    message_repo.create(
        Message(
            id="msg-tool-failed",
            session_id="session-1",
            turn_id="turn-1",
            run_id="run-1",
            turn_message_index=2,
            role="tool",
            message_type=MessageType.TOOL_TRACE,
            stream_state=StreamState.FAILED,
            display_mode="default",
            content_text="",
            payload_json={
                "tool_name": "shell",
                "arguments": {"cmd": "bad_cmd"},
                "success": False,
                "error": "command not found",
            },
        )
    )

    loader = ConversationHistoryLoader(conversation_service=conversation_service)
    seeded = loader.load_for_session(
        session_id="session-1",
        project_id="project-1",
        current_turn_id="turn-2",
    )

    # 非完成状态的 tool trace 不应出现在 seed messages 中
    seeded_contents = [msg["content"] for msg in seeded]
    assert not any("tool_name=shell" in c for c in seeded_contents)
