# 对话核心数据模型：定义会话中「回合（Turn）- 运行（Run）- 消息（Message）- 事件（ConversationEvent）」
# 的数据结构与各自的状态枚举，是整个对话系统的核心领域模型。
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TurnStatus(str, Enum):
    """回合（Turn）状态：已创建/运行中/已完成/失败/已取消。"""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    """运行（Run）状态：一个回合可能因中断/重试而产生多次运行，覆盖从创建、等待审批、
    恢复执行到最终完成/失败/取消的完整生命周期。"""

    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RESUMING = "resuming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    """消息类型：用户消息/AI 回复消息/工具调用轨迹/系统通知。"""

    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_TRACE = "tool_trace"
    SYSTEM_NOTICE = "system_notice"


class StreamState(str, Enum):
    """消息的流式生成状态：空闲/流式输出中/已完成/失败/已取消。"""

    IDLE = "idle"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """会话事件类型：用于事件流（SSE/WebSocket 等）向前端推送的各类状态变更事件，
    覆盖回合/运行/审批/消息生命周期及系统通知、历史截断等场景。"""

    TURN_CREATED = "turn.created"
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_WAITING_FOR_APPROVAL = "run.waiting_for_approval"
    RUN_RESUMING = "run.resuming"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_DENIED = "approval.denied"
    APPROVAL_STALE = "approval.stale"
    MESSAGE_CREATED = "message.created"
    MESSAGE_CONTENT_COMMITTED = "message.content_committed"
    MESSAGE_PAYLOAD_UPDATED = "message.payload_updated"
    MESSAGE_COMPLETED = "message.completed"
    MESSAGE_FAILED = "message.failed"
    SYSTEM_NOTICE_EMITTED = "system.notice_emitted"
    MESSAGES_TRUNCATED = "messages.truncated"


class Turn(BaseModel):
    """对话回合：代表一次用户发起的交互轮次，是消息与运行的组织单元。
    root_message_id 指向该回合的起始（用户）消息，active_run_id 指向当前生效的运行。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_index: int  # 回合在所属会话中的序号
    root_message_id: str
    status: TurnStatus
    active_run_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class Run(BaseModel):
    """运行：一个回合下的具体一次执行尝试（可能因失败重试或人工恢复而产生多次），
    记录所用的模型/服务商、工作区引用及执行结果（错误码/错误信息）。"""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    session_id: str
    turn_id: str
    attempt_index: int  # 在所属回合内的第几次尝试
    status: RunStatus
    provider_id: str | None = None
    model_id: str | None = None
    workspace_ref: str | None = None  # 关联的工作区/沙箱引用标识
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class MessageAttachment(BaseModel):
    """消息附件"""
    id: str
    type: str  # image, file
    mime_type: str
    file_path: str
    file_size: int
    created_at: datetime = Field(default_factory=datetime.now)


class Message(BaseModel):
    """会话消息：对话中的一条具体消息（用户输入、AI 回复、工具调用轨迹或系统通知），
    支持流式生成状态跟踪、附件、以及任意结构的载荷（payload_json，如工具调用详情）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    turn_message_index: int  # 消息在所属回合内的序号
    role: str
    message_type: MessageType
    stream_state: StreamState
    display_mode: str
    content_text: str = ""
    payload_json: dict = Field(default_factory=dict)
    attachments: list[MessageAttachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def _as_payload_dict(self) -> dict:
        """将 payload_json 归一化为 dict：若已是 dict 直接返回；若是字符串则尝试
        JSON 解析，解析失败或结果非 dict 时返回空字典，避免调用方处理多种类型。"""
        payload = self.payload_json
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except (TypeError, ValueError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def is_excluded_from_recall(self) -> bool:
        """判断该消息是否应在构造模型上下文（记忆召回）时被排除，
        依据 payload_json 中的 exclude_from_recall 标记，默认不排除。"""
        return bool(self._as_payload_dict().get("exclude_from_recall", False))


class ConversationEvent(BaseModel):
    """会话事件：记录会话生命周期中发生的各类事件（回合/运行/审批/消息状态变更等），
    seq 为会话内的单调递增序号，用于客户端增量拉取/断线重连后的事件对齐。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    seq: int = 0
    turn_id: str | None = None
    run_id: str | None = None
    message_id: str | None = None
    event_type: EventType
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
