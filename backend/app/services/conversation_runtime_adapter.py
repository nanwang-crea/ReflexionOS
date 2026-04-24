from datetime import datetime
from uuid import uuid4

from app.models.conversation import (
    ConversationEvent,
    EventType,
    MessageType,
    RunStatus,
    StreamState,
)

from .conversation_service import ConversationService


class ConversationRuntimeAdapter:
    """将 runtime raw 事件翻译为 conversation 事件并写入 ConversationService。"""

    def __init__(
        self,
        *,
        conversation_service: ConversationService,
        session_id: str,
        turn_id: str,
        run_id: str,
    ):
        self.conversation_service = conversation_service
        self.session_id = session_id
        self.turn_id = turn_id
        self.run_id = run_id
        self.assistant_message_id: str | None = None
        self.tool_message_ids: dict[str, str] = {}
        self._latest_tool_key: str | None = None
        self._run_terminal = False

    def handle_event(self, event_type: str, data: dict) -> list[ConversationEvent]:
        """消费一条 runtime 事件并追加 conversation 事件。"""
        if event_type == "execution:start":
            return self._append_events([
                self._new_event(
                    event_type=EventType.RUN_STARTED,
                    run_id=self.run_id,
                    payload_json={"started_at": datetime.now().isoformat()},
                )
            ])

        if event_type in {"llm:content", "summary:token"}:
            delta = data.get("content") if event_type == "llm:content" else data.get("token")
            if not delta:
                return []
            return self._append_events(self._assistant_delta_events(str(delta)))

        if event_type == "tool:start":
            return self._append_events(self._tool_start_events(data))

        if event_type == "tool:result":
            return self._append_events(self._tool_result_events(data))

        if event_type == "tool:error":
            failed_data = {
                "tool_name": data.get("tool_name"),
                "step_number": data.get("step_number"),
                "success": False,
                "output": None,
                "error": data.get("error"),
                "duration": data.get("duration"),
            }
            return self._append_events(self._tool_result_events(failed_data))

        if event_type == "execution:error":
            return self._append_events(self._execution_error_events(data))

        if event_type == "execution:complete":
            return self._append_events(self._execution_complete_events())

        if event_type == "execution:cancelled":
            return self._append_events(self._execution_cancelled_events())

        return []

    def _assistant_delta_events(self, delta: str) -> list[ConversationEvent]:
        events: list[ConversationEvent] = []
        if self.assistant_message_id is None:
            self.assistant_message_id = f"msg-{uuid4().hex[:8]}"
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_CREATED,
                    message_id=self.assistant_message_id,
                    run_id=self.run_id,
                    payload_json={
                        "message_id": self.assistant_message_id,
                        "turn_id": self.turn_id,
                        "run_id": self.run_id,
                        "role": "assistant",
                        "message_type": "assistant_message",
                        "message_index": self._next_message_index(),
                        "display_mode": "default",
                        "content_text": "",
                        "payload_json": {},
                    },
                )
            )

        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_DELTA_APPENDED,
                message_id=self.assistant_message_id,
                run_id=self.run_id,
                payload_json={"delta": delta},
            )
        )
        return events

    def _tool_start_events(self, data: dict) -> list[ConversationEvent]:
        tool_key = self._tool_key(data)
        message_id = f"msg-{uuid4().hex[:8]}"
        self.tool_message_ids[tool_key] = message_id
        self._latest_tool_key = tool_key
        return [
            self._new_event(
                event_type=EventType.MESSAGE_CREATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={
                    "message_id": message_id,
                    "turn_id": self.turn_id,
                    "run_id": self.run_id,
                    "role": "assistant",
                    "message_type": "tool_trace",
                    "message_index": self._next_message_index(),
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {
                        "tool_name": data.get("tool_name"),
                        "arguments": data.get("arguments"),
                        "step_number": data.get("step_number"),
                        "status": "running",
                    },
                },
            )
        ]

    def _tool_result_events(self, data: dict) -> list[ConversationEvent]:
        tool_key = self._tool_key(data)
        message_id = self.tool_message_ids.get(tool_key)
        events: list[ConversationEvent] = []
        if message_id is None:
            start_events = self._tool_start_events(data)
            events.extend(start_events)
            message_id = start_events[0].message_id

        payload_update = {
            "tool_name": data.get("tool_name"),
            "step_number": data.get("step_number"),
            "success": data.get("success"),
            "output": data.get("output"),
            "error": data.get("error"),
            "duration": data.get("duration"),
            "status": "completed",
        }
        if data.get("arguments") is not None:
            payload_update["arguments"] = data.get("arguments")

        success = bool(data.get("success"))
        payload_update["status"] = "completed" if success else "failed"

        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={
                    "payload_json": payload_update
                },
            )
        )
        if success:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_COMPLETED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"completed_at": datetime.now().isoformat()},
                )
            )
        else:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_FAILED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={
                        "error_code": "tool_error",
                        "error_message": str(data.get("error") or "tool execution failed"),
                    },
                )
            )
        return events

    def _execution_error_events(self, data: dict) -> list[ConversationEvent]:
        error_message = str(data.get("error") or "execution failed")
        events: list[ConversationEvent] = []
        if self.assistant_message_id:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_FAILED,
                    message_id=self.assistant_message_id,
                    run_id=self.run_id,
                    payload_json={
                        "error_code": "execution_error",
                        "error_message": error_message,
                    },
                )
            )

        terminal_event = self._run_terminal_event(
            EventType.RUN_FAILED,
            payload_json={
                "finished_at": datetime.now().isoformat(),
                "error_code": "execution_error",
                "error_message": error_message,
            },
        )
        if terminal_event is not None:
            events.append(terminal_event)
        return events

    def _execution_complete_events(self) -> list[ConversationEvent]:
        events: list[ConversationEvent] = []
        if self.assistant_message_id and not self._message_is_terminal(self.assistant_message_id):
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_COMPLETED,
                    message_id=self.assistant_message_id,
                    run_id=self.run_id,
                    payload_json={"completed_at": datetime.now().isoformat()},
                )
            )

        terminal_event = self._run_terminal_event(
            EventType.RUN_COMPLETED,
            payload_json={"finished_at": datetime.now().isoformat()},
        )
        if terminal_event is not None:
            events.append(terminal_event)
        return events

    def _execution_cancelled_events(self) -> list[ConversationEvent]:
        events = self._close_open_messages_for_cancel()

        terminal_event = self._run_terminal_event(
            EventType.RUN_CANCELLED,
            payload_json={"finished_at": datetime.now().isoformat()},
        )
        if terminal_event is not None:
            events.append(terminal_event)
            events.append(self._cancel_notice_event())
        return events

    def _close_open_messages_for_cancel(self) -> list[ConversationEvent]:
        events: list[ConversationEvent] = []
        open_ids: set[str] = {
            message.id
            for message in self.conversation_service.message_repo.list_by_turn(self.turn_id)
            if message.run_id == self.run_id
            and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
            and message.stream_state in {StreamState.IDLE, StreamState.STREAMING}
        }

        if self.assistant_message_id:
            open_ids.add(self.assistant_message_id)
        open_ids.update(self.tool_message_ids.values())

        for message_id in sorted(open_ids):
            if self._message_is_terminal(message_id):
                continue
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"status": "cancelled"}},
                )
            )
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_FAILED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={
                        "error_code": "run_cancelled",
                        "error_message": "本次执行已取消",
                    },
                )
            )

        return events

    def _cancel_notice_event(self) -> ConversationEvent:
        message_id = f"msg-{uuid4().hex[:8]}"
        return self._new_event(
            event_type=EventType.SYSTEM_NOTICE_EMITTED,
            run_id=self.run_id,
            message_id=message_id,
            payload_json={
                "message_id": message_id,
                "turn_id": self.turn_id,
                "message_index": self._next_message_index(),
                "notice_code": "run_cancelled",
                "content_text": "本次执行已取消",
                "related_run_id": self.run_id,
                "retryable": True,
            },
        )

    def _run_terminal_event(self, event_type: EventType, payload_json: dict) -> ConversationEvent | None:
        if self._run_terminal or self._run_is_terminal():
            self._run_terminal = True
            return None

        self._run_terminal = True
        return self._new_event(
            event_type=event_type,
            run_id=self.run_id,
            payload_json=payload_json,
        )

    def _run_is_terminal(self) -> bool:
        run = self.conversation_service.run_repo.get(self.run_id)
        if run is None:
            return False
        return run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    def _message_is_terminal(self, message_id: str) -> bool:
        message = self.conversation_service.message_repo.get(message_id)
        if message is None:
            return False
        return message.stream_state in {StreamState.COMPLETED, StreamState.FAILED, StreamState.CANCELLED}

    def _tool_key(self, data: dict) -> str:
        step_number = data.get("step_number")
        if step_number is not None:
            return str(step_number)
        tool_name = data.get("tool_name") or "tool"
        return self._latest_tool_key or f"{tool_name}-{len(self.tool_message_ids) + 1}"

    def _next_message_index(self) -> int:
        return self.conversation_service.message_repo.next_message_index(self.turn_id)

    def _append_events(self, events: list[ConversationEvent]) -> list[ConversationEvent]:
        if not events:
            return []
        return self.conversation_service.append_events(self.session_id, events)

    def _new_event(
        self,
        *,
        event_type: EventType,
        payload_json: dict,
        message_id: str | None = None,
        run_id: str | None = None,
    ) -> ConversationEvent:
        return ConversationEvent(
            id=f"evt-{uuid4().hex[:8]}",
            session_id=self.session_id,
            turn_id=self.turn_id,
            run_id=run_id or self.run_id,
            message_id=message_id,
            event_type=event_type,
            payload_json=payload_json,
        )
