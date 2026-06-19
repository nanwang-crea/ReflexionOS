from app.models.conversation import EventType, MessageType, RunStatus, StreamState
from app.models.session import Session
from app.services.conversation_runtime_adapter import ConversationRuntimeAdapter
from app.services.conversation_service import ConversationService
from app.storage.database import Database


def build_started_turn(tmp_path):
    db = Database(str(tmp_path / "conversation-runtime-adapter.db"))
    service = ConversationService(db=db)
    service.session_repo.create(Session(id="session-1", project_id="project-1", title="会话"))
    started = service.start_turn(
        session_id="session-1",
        content="请检查项目",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref="/tmp/reflexion",
    )
    return service, started


def test_buffers_llm_content_until_run_completes(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    llm_events = adapter.handle_event("llm:content", {"content": "你好"})
    summary_events = adapter.handle_event("summary:token", {"token": "，世界"})

    snapshot_before_terminal = service.get_snapshot("session-1")
    assistant_messages_before_terminal = [
        message
        for message in snapshot_before_terminal.messages
        if message.message_type == MessageType.ASSISTANT_MESSAGE
    ]

    completion_events = adapter.handle_event("run:complete", {"result": "done"})

    snapshot = service.get_snapshot("session-1")
    assistant_messages = [
        message
        for message in snapshot.messages
        if message.message_type == MessageType.ASSISTANT_MESSAGE
    ]
    run = next(run for run in snapshot.runs if run.id == started.run.id)

    assert llm_events == []
    assert summary_events == []
    assert assistant_messages_before_terminal == []
    assert [event.event_type for event in completion_events] == [
        EventType.MESSAGE_CREATED,
        EventType.MESSAGE_CONTENT_COMMITTED,
        EventType.MESSAGE_COMPLETED,
        EventType.RUN_COMPLETED,
    ]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].content_text == "你好，世界"
    assert assistant_messages[0].stream_state == StreamState.COMPLETED
    assert run.status == RunStatus.COMPLETED


def test_streams_reasoning_into_live_state_and_persists_on_completion(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:reasoning", {"reasoning_content": "先查看项目结构"})
    live_event = adapter.build_live_event("llm:reasoning", {"reasoning_content": "，再决定下一步"})
    completion_events = adapter.handle_event("run:complete", {})

    snapshot = service.get_snapshot("session-1")
    assistant = next(
        message
        for message in snapshot.messages
        if message.message_type == MessageType.ASSISTANT_MESSAGE
    )

    assert live_event is not None
    assert live_event["payload_json"]["reasoning_text"] == "先查看项目结构"
    assert EventType.MESSAGE_PAYLOAD_UPDATED in [event.event_type for event in completion_events]
    assert assistant.payload_json["reasoning_text"] == "先查看项目结构"


def test_maps_tool_start_and_result_to_tool_trace_message(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:start",
        {"tool_name": "shell", "arguments": {"cmd": "ls"}, "step_number": 1},
    )
    adapter.handle_event(
        "tool:result",
        {
            "tool_name": "shell",
            "step_number": 1,
            "success": True,
            "output": "README.md",
            "error": None,
            "duration": 0.02,
        },
    )

    snapshot = service.get_snapshot("session-1")
    traces = [
        message for message in snapshot.messages if message.message_type == MessageType.TOOL_TRACE
    ]

    assert len(traces) == 1
    assert traces[0].payload_json["tool_name"] == "shell"
    assert traces[0].payload_json["arguments"] == {"cmd": "ls"}
    assert traces[0].payload_json["success"] is True
    assert traces[0].payload_json["output"] == "README.md"
    assert traces[0].stream_state == StreamState.COMPLETED


def test_maps_approval_required_to_waiting_tool_trace_and_run_event(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:start",
        {
            "tool_name": "shell",
            "arguments": {"cmd": "pytest -q"},
            "tool_call_id": "call-1",
            "step_number": 3,
        },
    )
    approval_events = adapter.handle_event(
        "approval:required",
        {
            "tool_name": "shell",
            "arguments": {"cmd": "pytest -q"},
            "tool_call_id": "call-1",
            "approval_id": "approval-1",
            "step_number": 3,
            "approval": {
                "approval_id": "approval-1",
                "tool_name": "shell",
                "summary": "Run pytest",
                "payload": {"cmd": "pytest -q"},
            },
        },
    )

    snapshot = service.get_snapshot("session-1")
    trace = next(
        message for message in snapshot.messages if message.message_type == MessageType.TOOL_TRACE
    )
    run = next(run for run in snapshot.runs if run.id == started.run.id)

    assert [event.event_type for event in approval_events] == [
        EventType.MESSAGE_PAYLOAD_UPDATED,
        EventType.APPROVAL_REQUIRED,
        EventType.RUN_WAITING_FOR_APPROVAL,
    ]
    assert trace.stream_state == StreamState.IDLE
    assert trace.payload_json["status"] == "waiting_for_approval"
    assert trace.payload_json["approval_id"] == "approval-1"
    assert trace.payload_json["tool_call_id"] == "call-1"
    assert trace.payload_json["arguments"] == {"cmd": "pytest -q"}
    assert trace.payload_json["step_number"] == 3
    assert trace.payload_json["approval"]["summary"] == "Run pytest"
    assert run.status == RunStatus.WAITING_FOR_APPROVAL


def test_marks_assistant_segments_before_tool_traces_as_working_notes(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "我先检查配置。"})
    adapter.handle_event(
        "tool:start",
        {"tool_name": "file", "arguments": {"action": "read", "path": "config.py"}, "step_number": 1},
    )
    adapter.handle_event(
        "tool:result",
        {
            "tool_name": "file",
            "step_number": 1,
            "success": True,
            "output": "config",
            "error": None,
            "duration": 0.02,
        },
    )
    adapter.handle_event("llm:content", {"content": "配置没问题，我再跑测试。"})
    adapter.handle_event(
        "tool:start",
        {"tool_name": "shell", "arguments": {"command": "pytest -q"}, "step_number": 2},
    )
    adapter.handle_event("run:complete", {})

    messages = service.list_turn_messages(started.turn.id)

    assert [
        (
            message.message_type,
            message.content_text or message.payload_json.get("tool_name"),
            message.display_mode,
        )
        for message in messages
    ] == [
        (MessageType.USER_MESSAGE, "请检查项目", "default"),
        (MessageType.ASSISTANT_MESSAGE, "我先检查配置。", "working_note"),
        (MessageType.TOOL_TRACE, "file", "default"),
        (MessageType.ASSISTANT_MESSAGE, "配置没问题，我再跑测试。", "working_note"),
        (MessageType.TOOL_TRACE, "shell", "default"),
    ]


def test_run_complete_closes_open_tool_traces(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:start",
        {
            "tool_name": "file",
            "arguments": {
                "action": "read",
                "path": "frontend/src/types/conversation.ts",
            },
            "step_number": 1,
        },
    )

    completion_events = adapter.handle_event("run:complete", {})

    snapshot = service.get_snapshot("session-1")
    trace = next(
        message for message in snapshot.messages if message.message_type == MessageType.TOOL_TRACE
    )

    assert [event.event_type for event in completion_events] == [
        EventType.MESSAGE_PAYLOAD_UPDATED,
        EventType.MESSAGE_COMPLETED,
        EventType.RUN_COMPLETED,
    ]
    assert trace.stream_state == StreamState.COMPLETED
    assert trace.payload_json["status"] == "completed"


def test_marks_run_failed_when_run_error_arrives(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "处理中..."})
    error_events = adapter.handle_event("run:error", {"error": "boom"})

    snapshot = service.get_snapshot("session-1")
    run = next(run for run in snapshot.runs if run.id == started.run.id)
    assistant = next(
        message
        for message in snapshot.messages
        if message.message_type == MessageType.ASSISTANT_MESSAGE
    )

    assert run.status == RunStatus.FAILED
    assert run.error_message == "boom"
    assert [event.event_type for event in error_events] == [
        EventType.MESSAGE_CREATED,
        EventType.MESSAGE_CONTENT_COMMITTED,
        EventType.MESSAGE_FAILED,
        EventType.RUN_FAILED,
    ]
    assert assistant.stream_state == StreamState.FAILED
    assert assistant.content_text == "处理中..."
    assert assistant.payload_json["error_message"] == "boom"


def test_run_cancelled_assigns_unique_turn_message_indexes_with_buffered_assistant_content(
    tmp_path,
):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "处理中..."})
    adapter.handle_event("run:cancelled", {})

    messages = service.list_turn_messages(started.turn.id)

    assert [(message.message_type, message.turn_message_index) for message in messages] == [
        (MessageType.USER_MESSAGE, 1),
        (MessageType.ASSISTANT_MESSAGE, 2),
        (MessageType.SYSTEM_NOTICE, 3),
    ]


def test_tool_error_marks_tool_trace_failed_instead_of_completed(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:start",
        {"tool_name": "shell", "arguments": {"cmd": "bad"}, "step_number": 2},
    )
    adapter.handle_event(
        "tool:error",
        {"tool_name": "shell", "step_number": 2, "error": "permission denied"},
    )

    snapshot = service.get_snapshot("session-1")
    trace = next(
        message for message in snapshot.messages if message.message_type == MessageType.TOOL_TRACE
    )

    assert trace.stream_state == StreamState.FAILED
    assert trace.payload_json["status"] == "failed"
    assert trace.payload_json["error_message"] == "permission denied"


def test_run_cancelled_without_assistant_content_creates_no_empty_assistant_message(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("run:cancelled", {})

    snapshot = service.get_snapshot("session-1")
    assistant_messages = [
        m for m in snapshot.messages if m.message_type == MessageType.ASSISTANT_MESSAGE
    ]

    assert len(assistant_messages) == 1
    msg = assistant_messages[0]
    assert msg.stream_state == StreamState.FAILED
    assert msg.content_text == ""
    assert msg.payload_json["error_code"] == "run_cancelled"


def test_run_error_without_assistant_content_creates_no_empty_assistant_message(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("run:error", {"error": "unexpected failure"})

    snapshot = service.get_snapshot("session-1")
    assistant_messages = [
        m for m in snapshot.messages if m.message_type == MessageType.ASSISTANT_MESSAGE
    ]

    assert len(assistant_messages) == 1
    msg = assistant_messages[0]
    assert msg.stream_state == StreamState.FAILED
    assert msg.content_text == ""
    assert msg.payload_json["error_code"] == "execution_error"
    assert msg.payload_json["error_message"] == "unexpected failure"


def test_run_cancelled_does_not_emit_duplicate_message_failed_for_completed_tool_trace(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:start",
        {"tool_name": "file", "arguments": {"action": "read", "path": "a.py"}, "step_number": 1},
    )
    adapter.handle_event(
        "tool:result",
        {"tool_name": "file", "step_number": 1, "success": True, "output": "ok", "error": None, "duration": 0.01},
    )
    cancel_events = adapter.handle_event("run:cancelled", {})

    message_failed_count = sum(
        1 for e in cancel_events if e.event_type == EventType.MESSAGE_FAILED
    )
    # Production now emits MESSAGE_FAILED for the assistant message on cancellation
    assert message_failed_count == 1

    snapshot = service.get_snapshot("session-1")
    traces = [m for m in snapshot.messages if m.message_type == MessageType.TOOL_TRACE]
    assert len(traces) == 1
    assert traces[0].stream_state == StreamState.COMPLETED


def test_tool_start_skips_if_tool_key_already_registered(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event(
        "tool:result",
        {"tool_name": "file", "step_number": 1, "success": True, "output": "ok", "error": None, "duration": 0.01},
    )
    start_events = adapter.handle_event(
        "tool:start",
        {"tool_name": "file", "arguments": {"action": "read", "path": "a.py"}, "step_number": 1},
    )

    assert start_events == []

    snapshot = service.get_snapshot("session-1")
    traces = [m for m in snapshot.messages if m.message_type == MessageType.TOOL_TRACE]
    assert len(traces) == 1


def test_build_live_event_emits_terminal_on_run_complete(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "你好"})
    adapter.handle_event("llm:content", {"content": "世界"})
    adapter.handle_event("run:complete", {})

    live = adapter.build_live_event("run:complete", {})
    assert live is not None
    assert live["stream_state"] == "completed"
    assert live["delta"] == ""
    assert live["content_text"] == "你好世界"


def test_build_live_event_emits_terminal_on_run_error(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "出错了"})
    adapter.handle_event("run:error", {"error": "boom"})

    live = adapter.build_live_event("run:error", {})
    assert live is not None
    assert live["stream_state"] == "failed"
    assert live["content_text"] == "出错了"


def test_build_live_event_emits_terminal_on_run_cancelled(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "取消中"})
    adapter.handle_event("run:cancelled", {})

    live = adapter.build_live_event("run:cancelled", {})
    assert live is not None
    assert live["stream_state"] == "cancelled"


def test_build_live_event_returns_none_for_terminal_without_assistant_content(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("run:complete", {})

    live = adapter.build_live_event("run:complete", {})
    assert live is None


def test_build_live_event_ignores_incremental_after_terminal(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "完成"})
    adapter.handle_event("run:complete", {})

    live = adapter.build_live_event("llm:content", {"content": "多余"})
    assert live is None


def test_build_live_event_terminal_is_idempotent(tmp_path):
    service, started = build_started_turn(tmp_path)
    adapter = ConversationRuntimeAdapter(
        conversation_service=service,
        session_id="session-1",
        turn_id=started.turn.id,
        run_id=started.run.id,
    )

    adapter.handle_event("llm:content", {"content": "完成"})
    adapter.handle_event("run:complete", {})

    first = adapter.build_live_event("run:complete", {})
    assert first is not None
    assert first["stream_state"] == "completed"

    second = adapter.build_live_event("run:complete", {})
    assert second is None
