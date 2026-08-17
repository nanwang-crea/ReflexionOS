"""会话运行时适配器：Agent 执行循环（runtime）与事件溯源持久层之间的转换层。
将运行时抛出的原始生命周期事件（如 llm:content、tool:start、run:complete 等字符串事件）
翻译为可持久化、可通过 WebSocket 重放的 ConversationEvent，同时维护一份用于"实时增量推送"
（build_live_event/get_live_state）的内存态，避免每个 token 都落库。
执行循环本身不应了解任何 UI 消息结构，本适配器就是这层隔离的接缝（seam）。"""

from datetime import datetime

from app.ids import new_event_id, new_message_id
from app.llm.base import MessageRole
from app.models.conversation import (
    ConversationEvent,
    EventType,
    MessageType,
    RunStatus,
    StreamState,
)

from .conversation_service import ConversationService


class ConversationRuntimeAdapter:
    """Translate low-level runtime events into persisted conversation events.

    The execution loop should not know anything about UI message shapes. This
    adapter is the seam that turns raw runtime lifecycle events into durable
    conversation projections that can be replayed over WebSocket.
    """

    def __init__(
        self,
        *,
        conversation_service: ConversationService,
        session_id: str,
        turn_id: str,
        run_id: str,
    ):
        """初始化适配器，绑定到具体的 session/turn/run，并准备助手消息缓冲区和工具消息映射表。
        输入：conversation_service（持久层服务）、session_id/turn_id/run_id（本次运行归属）
        内部状态说明：
          - assistant_message_id / _assistant_content / _assistant_reasoning：
            当前正在缓冲、尚未落库的助手回复内容和推理内容；
          - tool_message_ids：{tool_key: message_id}，跟踪每个工具调用对应的消息；
          - _terminal_tool_message_ids：已进入终态（完成/失败）的工具消息集合，防止重复终结；
          - _reserved_turn_message_index：本批次事件内预分配的消息序号游标，批次结束后重置；
          - _run_terminal：Run 是否已经落终态，防止重复发出终态事件；
          - _incremental_live_blocked / _terminal_live_emitted：控制实时推送（live event）的幂等性。
        """
        self.conversation_service = conversation_service
        self.session_id = session_id
        self.turn_id = turn_id
        self.run_id = run_id
        self.assistant_message_id: str | None = None
        self._assistant_content = ""
        self._assistant_reasoning = ""
        self.tool_message_ids: dict[str, str] = {}
        self._terminal_tool_message_ids: set[str] = set()
        self._latest_tool_key: str | None = None
        self._reserved_turn_message_index: int | None = None
        self._run_terminal = False
        self._incremental_live_blocked = False
        self._terminal_live_emitted = False

    def handle_event(self, event_type: str, data: dict) -> list[ConversationEvent]:
        """消费一个运行时事件，翻译为对应的 ConversationEvent 并追加持久化（核心分派入口）。
        输入：event_type（运行时事件类型字符串，如 "run:start"、"llm:content"、"tool:start" 等）、
              data（该事件的原始数据负载，字段随事件类型不同而不同）
        逻辑（按事件类型分派）：
          - run:start：追加 RUN_STARTED 事件；
          - llm:content / summary:token：仅缓冲增量内容到 _assistant_content，不立即落库
            （避免每个 token 都写数据库，攒到消息/工具边界时才批量提交）；
          - llm:reasoning：仅缓冲推理增量内容到 _assistant_reasoning；
          - tool:start：先把已缓冲的助手内容作为一段"工作笔记"消息落库（_assistant_segment_events），
            再创建工具调用消息；
          - tool:result：更新工具消息为完成/失败终态；
          - tool:error：等价于失败的 tool:result，若消息已是终态则跳过（防重复）；
          - approval:required：追加工具审批请求相关事件；
          - run:waiting_for_approval / run:resuming：追加 Run 级别的暂停/恢复事件；
          - run:error / run:complete / run:cancelled：Run 终态收尾（落地未完成的助手消息和工具消息）。
        输出：本次调用实际持久化的 ConversationEvent 列表（可能为空，如纯 token 缓冲阶段）
        """
        if event_type == "run:start":
            return self._append_events(
                [
                    self._new_event(
                        event_type=EventType.RUN_STARTED,
                        run_id=self.run_id,
                        payload_json={"started_at": datetime.now().isoformat()},
                    )
                ]
            )

        # Assistant tokens are buffered first and only projected into
        # messages when a tool/run boundary requires a visible segment.
        if event_type in {"llm:content", "summary:token"}:
            delta = data.get("content") if event_type == "llm:content" else data.get("token")
            if not delta:
                return []
            self._buffer_assistant_delta(str(delta))
            return []

        if event_type == "llm:reasoning":
            delta = data.get("reasoning_content")
            if not delta:
                return []
            self._buffer_assistant_reasoning(str(delta))
            return []

        if event_type == "tool:start":
            return self._append_events(
                [
                    *self._assistant_segment_events(),
                    *self._tool_start_events(data),
                ]
            )

        if event_type == "tool:result":
            return self._append_events(self._tool_result_events(data))

        if event_type == "tool:error":
            tool_key = self._tool_key(data)
            message_id = self.tool_message_ids.get(tool_key)
            if message_id and self._message_is_terminal(message_id):
                return []
            failed_data = {
                "tool_name": data.get("tool_name"),
                "step_number": data.get("step_number"),
                "success": False,
                "output": data.get("output"),
                "error": data.get("error"),
                "duration": data.get("duration"),
            }
            if data.get("tool_call_id") is not None:
                failed_data["tool_call_id"] = data.get("tool_call_id")
            if data.get("arguments") is not None:
                failed_data["arguments"] = data.get("arguments")
            return self._append_events(self._tool_result_events(failed_data))

        if event_type == "approval:required":
            return self._append_events(self._approval_required_events(data))

        if event_type == "run:waiting_for_approval":
            return self._append_events(self._run_waiting_for_approval_events(data))

        if event_type == "run:resuming":
            return self._append_events(self._run_resuming_events(data))

        if event_type == "run:error":
            return self._append_events(self._execution_error_events(data))

        if event_type == "run:complete":
            return self._append_events(self._execution_complete_events())

        if event_type == "run:cancelled":
            return self._append_events(self._execution_cancelled_events(data))

        return []

    _TERMINAL_LIVE_EVENTS = {"run:complete", "run:error", "run:cancelled"}
    _INCREMENTAL_LIVE_EVENTS = {"llm:content", "summary:token", "llm:reasoning"}

    def build_live_event(self, event_type: str, data: dict) -> dict | None:
        """构建用于 WebSocket 实时推送的"轻量事件"（不落库，仅供前端即时展示流式内容）。
        输入：event_type（运行时事件类型）、data（原始数据）
        逻辑：终态类事件（run:complete/error/cancelled）走 _build_terminal_live_event；
              增量类事件（llm:content/summary:token/llm:reasoning）走 _build_incremental_live_event；
              其余事件类型不产生实时推送。
        输出：可 JSON 序列化的事件字典，或 None（无需推送）
        """
        if event_type in self._TERMINAL_LIVE_EVENTS:
            return self._build_terminal_live_event(event_type)
        if event_type in self._INCREMENTAL_LIVE_EVENTS:
            return self._build_incremental_live_event(event_type, data)
        return None

    def _build_terminal_live_event(self, event_type: str) -> dict | None:
        """构建助手消息流结束时的终态实时推送事件（携带完整累积内容，通知前端流式展示结束）。
        输入：event_type（run:complete/run:error/run:cancelled 之一）
        逻辑：没有正在缓冲的助手消息，或已经推送过终态事件（幂等保护），则不再推送
        输出：实时事件字典，或 None
        """
        if self.assistant_message_id is None or self._terminal_live_emitted:
            return None
        stream_state = {
            "run:complete": "completed",
            "run:error": "failed",
            "run:cancelled": "cancelled",
        }[event_type]
        self._terminal_live_emitted = True
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "message_id": self.assistant_message_id,
            "message_type": "assistant_message",
            "delta": "",
            "content_text": self._assistant_content,
            "payload_json": {"reasoning_text": self._assistant_reasoning},
            "stream_state": stream_state,
        }

    def _build_incremental_live_event(self, event_type: str, data: dict) -> dict | None:
        """构建流式增量内容的实时推送事件（每个 token/reasoning 片段触发一次）。
        输入：event_type（llm:content/summary:token/llm:reasoning）、data（含增量内容）
        逻辑：没有正在缓冲的助手消息，或已被阻断（_incremental_live_blocked，通常因为已进入终态处理），
              或本次增量为空，则不推送
        输出：实时事件字典（delta 为本次增量，content_text 为累积到目前的全文），或 None
        """
        if self.assistant_message_id is None or self._incremental_live_blocked:
            return None
        if event_type == "llm:reasoning":
            delta = data.get("reasoning_content")
        else:
            delta = data.get("content") if event_type == "llm:content" else data.get("token")
        if not delta:
            return None
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "message_id": self.assistant_message_id,
            "message_type": "assistant_message",
            "delta": str(delta),
            "content_text": self._assistant_content,
            "payload_json": {"reasoning_text": self._assistant_reasoning},
            "stream_state": "streaming",
        }

    def get_live_state(self) -> dict | None:
        """获取当前正在流式生成的助手消息完整状态（供新连接的 WebSocket 客户端补拉当前进度）。
        输出：与 _build_incremental_live_event 相同结构的状态字典（无 delta 字段），或 None（无进行中的流）
        """
        if self.assistant_message_id is None or self._incremental_live_blocked:
            return None
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "message_id": self.assistant_message_id,
            "message_type": "assistant_message",
            "content_text": self._assistant_content,
            "payload_json": {"reasoning_text": self._assistant_reasoning},
            "stream_state": "streaming",
        }

    def _buffer_assistant_delta(self, delta: str) -> None:
        """缓冲一段助手回复文本增量（不落库），首次调用时分配 assistant_message_id。
        输入：delta（增量文本片段）
        输出：无（更新 self._assistant_content）
        """
        if self.assistant_message_id is None:
            self.assistant_message_id = new_message_id()
        self._assistant_content = f"{self._assistant_content}{delta}"

    def _buffer_assistant_reasoning(self, delta: str) -> None:
        """缓冲一段助手推理（reasoning/思维链）文本增量（不落库）。
        输入：delta（增量文本片段）
        输出：无（更新 self._assistant_reasoning）
        """
        if self.assistant_message_id is None:
            self.assistant_message_id = new_message_id()
        self._assistant_reasoning = f"{self._assistant_reasoning}{delta}"

    def _tool_start_events(self, data: dict) -> list[ConversationEvent]:
        """构建工具调用开始时的 MESSAGE_CREATED 事件（消息类型为 tool_trace，状态 running）。
        输入：data（含 tool_name/arguments/tool_call_id/step_number 等）
        逻辑：按 _tool_key 去重，若该工具调用已创建过消息则直接返回空列表（幂等）
        输出：单元素事件列表，或空列表（重复调用时）
        """
        tool_key = self._tool_key(data)
        existing_id = self.tool_message_ids.get(tool_key)
        if existing_id is not None:
            return []
        message_id = new_message_id()
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
                    "role": MessageRole.TOOL,
                    "message_type": "tool_trace",
                    "turn_message_index": self._reserve_turn_message_index(),
                    "display_mode": "default",
                    "content_text": "",
                    "payload_json": {
                        "tool_name": data.get("tool_name"),
                        "arguments": data.get("arguments"),
                        "tool_call_id": data.get("tool_call_id"),
                        "step_number": data.get("step_number"),
                        "status": "running",
                    },
                },
            )
        ]

    def _tool_result_events(self, data: dict) -> list[ConversationEvent]:
        """构建工具调用结果的事件（更新 payload 为完成/失败终态，并追加 MESSAGE_COMPLETED/FAILED）。
        输入：data（含 success/output/error/duration 等结果字段）
        逻辑：若对应工具消息尚未创建（如未收到 tool:start 就直接收到结果），先补建消息；
              然后按 success 决定追加 MESSAGE_COMPLETED 还是 MESSAGE_FAILED，并记入终态集合防重复。
        输出：本次追加的事件列表
        """
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
        if data.get("tool_call_id") is not None:
            payload_update["tool_call_id"] = data.get("tool_call_id")
        if data.get("arguments") is not None:
            payload_update["arguments"] = data.get("arguments")

        success = bool(data.get("success"))
        payload_update["status"] = "completed" if success else "failed"

        events.append(
            self._new_event(
                event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                message_id=message_id,
                run_id=self.run_id,
                payload_json={"payload_json": payload_update},
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
        self._terminal_tool_message_ids.add(message_id)
        return events

    def _approval_required_events(self, data: dict) -> list[ConversationEvent]:
        """
        处理工具层审批请求事件 (approval:required)

        职责：
        - 生成工具消息的审批状态更新
        - 生成 APPROVAL_REQUIRED 事件（携带完整工具信息，用于前端展示审批对话框）
        - 同时生成 RUN_WAITING_FOR_APPROVAL 事件（标记整个运行进入等待审批状态）

        事件来源：tool_call_executor.py 在执行工具时检测到需要审批
        """
        tool_key = self._tool_key(data)
        message_id = self.tool_message_ids.get(tool_key)
        events: list[ConversationEvent] = []
        if message_id is None:
            start_events = self._tool_start_events(data)
            events.extend(start_events)
            message_id = start_events[0].message_id

        # approval:required carries tool-scoped context, while the loop also
        # emits run:waiting_for_approval for run-level status. We project both so
        # the UI can show an approval dialog and a paused-run badge at once.
        approval_id = data.get("approval_id")
        approval_payload = data.get("approval")
        # 提取 parent_session_id（SubAgent 审批场景下由 DelegateTool 注入）
        parent_session_id = data.get("parent_session_id")
        payload_update = {
            "tool_name": data.get("tool_name"),
            "arguments": data.get("arguments"),
            "tool_call_id": data.get("tool_call_id"),
            "step_number": data.get("step_number"),
            "approval_id": approval_id,
            "approval": approval_payload,
            "status": "waiting_for_approval",
        }
        # SubAgent 审批场景：携带 parent_session_id 让前端路由审批响应到正确的 WebSocket
        if parent_session_id:
            payload_update["parent_session_id"] = parent_session_id
        events.extend(
            [
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"payload_json": payload_update},
                ),
                # 工具层审批事件：携带完整的工具信息（名称、参数、风险提示等）
                # 前端用此展示审批对话框
                self._new_event(
                    event_type=EventType.APPROVAL_REQUIRED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={
                        "approval_id": approval_id,
                        "tool_call_id": data.get("tool_call_id"),
                        "tool_name": data.get("tool_name"),
                        "arguments": data.get("arguments"),
                        "step_number": data.get("step_number"),
                        "approval": approval_payload,
                        **({"parent_session_id": parent_session_id} if parent_session_id else {}),
                    },
                ),
                # 运行状态事件：标记整个运行暂停
                # 前端用此更新运行状态显示（如状态栏显示"运行暂停"）
                self._new_event(
                    event_type=EventType.RUN_WAITING_FOR_APPROVAL,
                    run_id=self.run_id,
                    payload_json={
                        "approval_id": approval_id,
                        "tool_call_id": data.get("tool_call_id"),
                        "step_number": data.get("step_number"),
                    },
                ),
            ]
        )
        return events

    def _run_waiting_for_approval_events(self, data: dict) -> list[ConversationEvent]:
        """构建 Run 级别的"等待审批"状态事件（与 approval:required 互补）。

        approval:required 是消息层面的事件，携带用户需要审查的工具参数；
        run:waiting_for_approval 是运行层面的事件，让 UI 其余部分（如状态栏）也能反映
        执行循环当前处于暂停状态。
        输入：data（含 approval_id/step_number/tool_name/tool_call_id/arguments）
        输出：单元素 RUN_WAITING_FOR_APPROVAL 事件列表
        """
        return [
            self._new_event(
                event_type=EventType.RUN_WAITING_FOR_APPROVAL,
                run_id=self.run_id,
                payload_json={
                    "run_id": data.get("run_id"),
                    "approval_id": data.get("approval_id"),
                    "step_number": data.get("step_number"),
                    "tool_name": data.get("tool_name"),
                    "tool_call_id": data.get("tool_call_id"),
                    "arguments": data.get("arguments"),
                },
            )
        ]

    def _run_resuming_events(self, data: dict) -> list[ConversationEvent]:
        """构建 Run 从"等待审批"恢复执行时的事件。
        输入：data（含 approval_id、execution_success——审批对应工具的执行结果）
        输出：单元素 RUN_RESUMING 事件列表
        """
        return [
            self._new_event(
                event_type=EventType.RUN_RESUMING,
                run_id=self.run_id,
                payload_json={
                    "approval_id": data.get("approval_id"),
                    "execution_success": data.get("execution_success"),
                },
            ),
        ]

    def _execution_error_events(self, data: dict) -> list[ConversationEvent]:
        """处理 run:error 事件：将缓冲中的助手消息和未完成的工具消息统一标记为失败，并追加 RUN_FAILED。
        输入：data（含 error 错误信息）
        输出：事件列表（助手消息失败事件 + 遗留工具消息失败事件 + RUN_FAILED 终态事件）
        """
        error_message = str(data.get("error") or "execution failed")
        if self.assistant_message_id is None:
            self.assistant_message_id = new_message_id()
        events = self._assistant_terminal_events(
            terminal_event_type=EventType.MESSAGE_FAILED,
            payload_json={
                "error_code": "execution_error",
                "error_message": error_message,
            },
        )
        events.extend(self._fail_open_tool_trace_events("execution_error", error_message))

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
        """处理 run:complete 事件：落地缓冲中的助手消息，补全未收尾的工具消息为完成态，追加 RUN_COMPLETED。
        输出：事件列表（助手消息完成事件 + 遗留工具消息完成事件 + RUN_COMPLETED 终态事件）
        """
        events = self._assistant_terminal_events(
            terminal_event_type=EventType.MESSAGE_COMPLETED,
            payload_json={"completed_at": datetime.now().isoformat()},
        )
        events.extend(self._complete_open_tool_trace_events())

        terminal_event = self._run_terminal_event(
            EventType.RUN_COMPLETED,
            payload_json={"finished_at": datetime.now().isoformat()},
        )
        if terminal_event is not None:
            events.append(terminal_event)
        return events

    def _complete_open_tool_trace_events(self) -> list[ConversationEvent]:
        """扫描本轮次中仍处于运行态（IDLE/STREAMING）的工具消息，全部补收尾为完成态。
        用于 Run 正常结束时兜底：可能存在已开始但未收到显式 tool:result 的工具调用。
        输出：事件列表（每个未收尾工具消息对应一组 MESSAGE_PAYLOAD_UPDATED + MESSAGE_COMPLETED）
        """
        events: list[ConversationEvent] = []
        for message in self.conversation_service.list_turn_messages(self.turn_id):
            if (
                message.run_id != self.run_id
                or message.message_type != MessageType.TOOL_TRACE
                or message.stream_state not in {StreamState.IDLE, StreamState.STREAMING}
            ):
                continue

            status = message.payload_json.get("status")
            if status not in {None, "running"}:
                continue

            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message.id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"status": "completed"}},
                )
            )
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_COMPLETED,
                    message_id=message.id,
                    run_id=self.run_id,
                    payload_json={"completed_at": datetime.now().isoformat()},
                )
            )

        return events

    def _fail_open_tool_trace_events(
        self,
        error_code: str = "execution_error",
        error_message: str = "execution failed",
    ) -> list[ConversationEvent]:
        """扫描本轮次中仍处于运行态的工具消息，全部标记为失败（用于 Run 异常终止时的兜底收尾）。
        输入：error_code/error_message（统一填充到每条工具消息的失败原因）
        输出：事件列表（每个未收尾工具消息对应一组 MESSAGE_PAYLOAD_UPDATED + MESSAGE_FAILED）
        """
        events: list[ConversationEvent] = []
        for message in self.conversation_service.list_turn_messages(self.turn_id):
            if (
                message.run_id != self.run_id
                or message.message_type != MessageType.TOOL_TRACE
                or message.stream_state not in {StreamState.IDLE, StreamState.STREAMING}
            ):
                continue

            status = message.payload_json.get("status")
            if status not in {None, "running"}:
                continue

            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message.id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"status": "failed"}},
                )
            )
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_FAILED,
                    message_id=message.id,
                    run_id=self.run_id,
                    payload_json={
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                )
            )

        return events

    def _execution_cancelled_events(self, data: dict) -> list[ConversationEvent]:
        """处理 run:cancelled 事件：根据取消原因归类错误码/文案，收尾未完成消息，追加 RUN_CANCELLED。
        输入：data（含 reason——取消原因标识，如 llm_retry_exhausted/user_cancelled；error/result 详情）
        逻辑：
          1. 按 reason 映射出 error_code 和用户可读的 error_message；
          2. 收尾所有未完成的助手消息/工具消息（_close_open_messages_for_cancel）；
          3. 若确实产生了终态事件（未被幂等拦截），追加一条"已取消"的系统提示消息。
        输出：事件列表
        """
        reason = data.get("reason")
        error_msg = data.get("error")

        if reason == "llm_retry_exhausted":
            error_code = "llm_retry_exhausted"
            error_message = (
                f"LLM 重试次数已达上限: {error_msg}" if error_msg else "LLM 重试次数已达上限"
            )
        elif reason == "user_cancelled":
            error_code = "run_cancelled"
            error_message = "本次执行已取消"
        else:
            error_code = "run_cancelled"
            error_message = data.get("result") or "本次执行已取消"

        if self.assistant_message_id is None:
            self.assistant_message_id = new_message_id()
        events = self._close_open_messages_for_cancel(error_code, error_message)

        terminal_event = self._run_terminal_event(
            EventType.RUN_CANCELLED,
            payload_json={
                "finished_at": datetime.now().isoformat(),
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        if terminal_event is not None:
            events.append(terminal_event)
            events.append(self._cancel_notice_event(error_message=error_message))
        return events

    def _close_open_messages_for_cancel(
        self,
        error_code: str = "run_cancelled",
        error_message: str = "本次执行已取消",
    ) -> list[ConversationEvent]:
        """取消场景下，统一收尾缓冲中的助手消息和所有未终结的工具消息为失败态。
        输入：error_code/error_message（填充到收尾事件的错误信息）
        逻辑：先处理助手消息，再收集本轮次中运行态的工具消息 id，排除掉已经终结的（终态或已记录在
              _terminal_tool_message_ids 中），对剩余的逐个追加失败事件
        输出：事件列表
        """
        events = self._assistant_terminal_events(
            terminal_event_type=EventType.MESSAGE_FAILED,
            payload_json={
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        candidate_ids: set[str] = set()
        for message in self.conversation_service.list_turn_messages(self.turn_id):
            if (
                message.run_id == self.run_id
                and message.message_type == MessageType.TOOL_TRACE
                and message.stream_state in {StreamState.IDLE, StreamState.STREAMING}
            ):
                candidate_ids.add(message.id)
        for message_id in self.tool_message_ids.values():
            if self._message_is_terminal(message_id) or message_id in self._terminal_tool_message_ids:
                candidate_ids.discard(message_id)

        for message_id in sorted(candidate_ids):
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
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                )
            )

        return events

    def _create_assistant_message_event(
        self, *, message_id: str, turn_message_index: int, display_mode: str = "default"
    ) -> ConversationEvent:
        """构建一条助手消息的 MESSAGE_CREATED 事件。
        输入：message_id、turn_message_index（消息在轮次内的顺序号）、
              display_mode（展示模式，"default" 为正式回复，"working_note" 为工具调用前的过程性笔记）
        输出：MESSAGE_CREATED 事件（初始 content_text 为空，若已有缓冲的推理内容一并带上）
        """
        return self._new_event(
            event_type=EventType.MESSAGE_CREATED,
            message_id=message_id,
            run_id=self.run_id,
            payload_json={
                "message_id": message_id,
                "turn_id": self.turn_id,
                "run_id": self.run_id,
                "role": MessageRole.ASSISTANT,
                "message_type": "assistant_message",
                "turn_message_index": turn_message_index,
                "display_mode": display_mode,
                "content_text": "",
                "payload_json": (
                    {"reasoning_text": self._assistant_reasoning}
                    if self._assistant_reasoning
                    else {}
                ),
            },
        )

    def _assistant_terminal_events(
        self,
        *,
        terminal_event_type: EventType,
        payload_json: dict,
    ) -> list[ConversationEvent]:
        """将当前缓冲中的助手消息（内容+推理）落库并收尾为终态（完成/失败/取消其一）。
        输入：terminal_event_type（终态事件类型）、payload_json（终态事件负载，如错误信息或完成时间）
        逻辑：
          1. 没有缓冲中的助手消息，或该消息已是终态，直接返回空（幂等）；
          2. 若该消息尚未创建过（纯缓冲、从未落库），先补一条 MESSAGE_CREATED；
          3. 若有累积内容，追加 MESSAGE_CONTENT_COMMITTED 提交全文；
          4. 若有累积推理内容，追加 MESSAGE_PAYLOAD_UPDATED 写入 reasoning_text；
          5. 最后追加终态事件。
        输出：事件列表
        """
        if self.assistant_message_id is None or self._message_is_terminal(
            self.assistant_message_id
        ):
            return []

        events: list[ConversationEvent] = []
        if self.conversation_service.get_message(self.assistant_message_id) is None:
            events.append(self._create_assistant_message_event(
                message_id=self.assistant_message_id,
                turn_message_index=self._reserve_turn_message_index(),
            ))

        if self._assistant_content:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_CONTENT_COMMITTED,
                    message_id=self.assistant_message_id,
                    run_id=self.run_id,
                    payload_json={"content_text": self._assistant_content},
                )
            )

        if self._assistant_reasoning:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=self.assistant_message_id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"reasoning_text": self._assistant_reasoning}},
                )
            )

        events.append(
            self._new_event(
                event_type=terminal_event_type,
                message_id=self.assistant_message_id,
                run_id=self.run_id,
                payload_json=payload_json,
            )
        )
        return events

    def _assistant_segment_events(self) -> list[ConversationEvent]:
        """在工具调用开始前，把已缓冲的助手文本作为一段"过程性笔记"（working_note）落库并立即收尾。
        用途：模型在调用工具之前往往会先输出一段说明性文字，这段文字需要单独成一条消息展示，
              且需要在工具消息之前完成，因此这里生成完整的"创建+提交内容+完成"事件组，
              并重置缓冲区状态（为下一段助手输出让路，assistant_message_id 置空）。
        输出：事件列表；若没有缓冲内容则返回空列表
        """
        if self.assistant_message_id is None or not self._assistant_content:
            return []

        message_id = self.assistant_message_id
        content_text = self._assistant_content
        events = [
            self._create_assistant_message_event(
                message_id=message_id,
                turn_message_index=self._reserve_turn_message_index(),
                display_mode="working_note",
            ),
        ]
        if self._assistant_reasoning:
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"reasoning_text": self._assistant_reasoning}},
                )
            )
        events.extend(
            [
                self._new_event(
                    event_type=EventType.MESSAGE_CONTENT_COMMITTED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"content_text": content_text},
                ),
                self._new_event(
                    event_type=EventType.MESSAGE_COMPLETED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"completed_at": datetime.now().isoformat()},
                ),
            ]
        )
        self.assistant_message_id = None
        self._assistant_content = ""
        self._assistant_reasoning = ""
        return events

    def _cancel_notice_event(self, error_message: str | None = None) -> ConversationEvent:
        """构建一条"运行已取消"的系统提示消息事件，标记为可重试（retryable）。
        输入：error_message（可选，展示给用户的取消原因文案）
        输出：SYSTEM_NOTICE_EMITTED 事件
        """
        message_id = new_message_id()
        return self._new_event(
            event_type=EventType.SYSTEM_NOTICE_EMITTED,
            run_id=self.run_id,
            message_id=message_id,
            payload_json={
                "message_id": message_id,
                "turn_id": self.turn_id,
                "turn_message_index": self._reserve_turn_message_index(),
                "notice_code": "run_cancelled",
                "content_text": error_message or "本次执行已取消",
                "related_run_id": self.run_id,
                "retryable": True,
            },
        )

    def _run_terminal_event(
        self, event_type: EventType, payload_json: dict
    ) -> ConversationEvent | None:
        """构建 Run 的终态事件（完成/失败/取消），并保证同一个 Run 只会产出一次终态事件（幂等）。
        输入：event_type（RUN_COMPLETED/RUN_FAILED/RUN_CANCELLED）、payload_json（终态负载）
        逻辑：本地标记 _run_terminal 或读模型查到 Run 已是终态，则直接跳过（返回 None），
              同时置位 _incremental_live_blocked 阻断后续的增量实时推送
        输出：终态事件，或 None（已处于终态，跳过重复触发）
        """
        if self._run_terminal or self._run_is_terminal():
            self._run_terminal = True
            self._incremental_live_blocked = True
            return None

        self._run_terminal = True
        self._incremental_live_blocked = True
        return self._new_event(
            event_type=event_type,
            run_id=self.run_id,
            payload_json=payload_json,
        )

    def _run_is_terminal(self) -> bool:
        """从读模型查询 Run 当前是否已处于终态。
        输出：bool；Run 不存在时视为非终态（False）
        """
        run = self.conversation_service.get_run(self.run_id)
        if run is None:
            return False
        return run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    def _message_is_terminal(self, message_id: str) -> bool:
        """从读模型查询指定消息是否已处于终态（完成/失败/取消）。
        输入：message_id
        输出：bool；消息不存在时视为非终态（False）
        """
        message = self.conversation_service.get_message(message_id)
        if message is None:
            return False
        return message.stream_state in {
            StreamState.COMPLETED,
            StreamState.FAILED,
            StreamState.CANCELLED,
        }

    def _tool_key(self, data: dict) -> str:
        """计算工具调用的去重键，用于在 tool_message_ids 中定位对应消息。
        输入：data（工具事件数据）
        逻辑：优先使用 step_number（同一步骤号视为同一次调用）；若缺失，退化为"最近一次使用的 key"
              （处理 tool:result 紧跟 tool:start、但未带 step_number 的情况），仍无则生成新 key
        输出：字符串 key
        """
        step_number = data.get("step_number")
        if step_number is not None:
            return str(step_number)
        tool_name = data.get("tool_name") or "tool"
        return self._latest_tool_key or f"{tool_name}-{len(self.tool_message_ids) + 1}"

    def _reserve_turn_message_index(self) -> int:
        """在当前批次事件内预分配递增的消息序号（turn_message_index）。
        逻辑：批次内首次调用向 conversation_service 查询下一个可用序号并缓存；
              后续调用在此基础上递增，避免同一批次内重复查询数据库
        输出：本次分配到的序号；批次结束后（_append_events）会被重置为 None
        """
        if self._reserved_turn_message_index is None:
            self._reserved_turn_message_index = (
                self.conversation_service.next_message_index(self.turn_id)
            )
            return self._reserved_turn_message_index

        self._reserved_turn_message_index += 1
        return self._reserved_turn_message_index

    def _append_events(self, events: list[ConversationEvent]) -> list[ConversationEvent]:
        """将事件批次实际提交给 conversation_service 持久化，并重置序号预分配游标。
        输入：events（待追加事件列表）
        输出：持久化后的事件列表；events 为空则不落库直接返回空列表
        """
        if not events:
            self._reserved_turn_message_index = None
            return []
        try:
            return self.conversation_service.append_events(self.session_id, events)
        finally:
            self._reserved_turn_message_index = None

    def _new_event(
        self,
        *,
        event_type: EventType,
        payload_json: dict,
        message_id: str | None = None,
        run_id: str | None = None,
    ) -> ConversationEvent:
        """构建一个 ConversationEvent 对象（生成新 id，自动填充 session_id/turn_id，run_id 缺省用当前 run）。
        输入：event_type、payload_json（事件负载）、message_id（可选）、run_id（可选，缺省用 self.run_id）
        输出：未持久化的 ConversationEvent 对象
        """
        return ConversationEvent(
            id=new_event_id(),
            session_id=self.session_id,
            turn_id=self.turn_id,
            run_id=run_id or self.run_id,
            message_id=message_id,
            event_type=event_type,
            payload_json=payload_json,
        )
