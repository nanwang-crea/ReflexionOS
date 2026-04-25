from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TurnStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_TRACE = "tool_trace"
    SYSTEM_NOTICE = "system_notice"


class StreamState(str, Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    TURN_CREATED = "turn.created"
    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    MESSAGE_CREATED = "message.created"
    MESSAGE_DELTA_APPENDED = "message.delta_appended"
    MESSAGE_CONTENT_COMMITTED = "message.content_committed"
    MESSAGE_PAYLOAD_UPDATED = "message.payload_updated"
    MESSAGE_COMPLETED = "message.completed"
    MESSAGE_FAILED = "message.failed"
    SYSTEM_NOTICE_EMITTED = "system.notice_emitted"


class Turn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_index: int
    root_message_id: str
    status: TurnStatus
    active_run_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    session_id: str
    turn_id: str
    attempt_index: int
    status: RunStatus
    provider_id: str | None = None
    model_id: str | None = None
    workspace_ref: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    message_index: int
    role: str
    message_type: MessageType
    stream_state: StreamState
    display_mode: str
    content_text: str = ""
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None


class ConversationEvent(BaseModel):
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
