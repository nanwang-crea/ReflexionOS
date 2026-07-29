from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明基类"""

    pass


class ProjectModel(Base):
    """项目数据模型"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    language: Mapped[str | None] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class SessionModel(Base):
    """会话数据模型"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="新建聊天")
    preferred_provider_id: Mapped[str | None] = mapped_column(String)
    preferred_model_id: Mapped[str | None] = mapped_column(String)
    agent_mode: Mapped[str] = mapped_column(String, nullable=False, default="build")
    permission_mode: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    last_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_turn_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), index=True
    )


class TurnModel(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    root_message_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    active_run_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class RunModel(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_id: Mapped[str | None] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String)
    workspace_ref: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "turn_id", "turn_message_index", name="uq_messages_turn_turn_message_index"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    turn_message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    message_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    stream_state: Mapped[str] = mapped_column(String, nullable=False)
    display_mode: Mapped[str] = mapped_column(String, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    attachments_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class MessageSearchDocumentModel(Base):
    __tablename__ = "message_search_documents"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    turn_message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )


class ConversationEventModel(Base):
    __tablename__ = "conversation_events"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_conversation_events_session_seq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_id: Mapped[str | None] = mapped_column(String, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    message_id: Mapped[str | None] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)


LLM_CALL_STATUSES = "'running','completed','failed','cancelled','interrupted'"
TOOL_CALL_STATUSES = (
    "'running','waiting_for_approval','completed','failed','cancelled','interrupted'"
)
APPROVAL_EVENT_TYPES = "'requested','approved','denied','expired','stale'"


class LLMLogicalCallModel(Base):
    __tablename__ = "llm_logical_calls"
    __table_args__ = (
        CheckConstraint(f"status IN ({LLM_CALL_STATUSES})", name="ck_llm_logical_calls_status"),
        Index("ix_llm_logical_calls_project_started", "project_id", "started_at"),
        Index("ix_llm_logical_calls_run_started", "run_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True)
    session_id: Mapped[str | None] = mapped_column(String, index=True)
    turn_id: Mapped[str | None] = mapped_column(String)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    provider_id: Mapped[str | None] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String)
    call_kind: Mapped[str] = mapped_column(String, nullable=False)
    loop_iteration: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    first_token_ms: Mapped[int | None] = mapped_column(BigInteger)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost_nano_usd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_entity_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    project_name_snapshot: Mapped[str | None] = mapped_column(String)
    session_title_snapshot: Mapped[str | None] = mapped_column(String)
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LLMProviderRequestModel(Base):
    __tablename__ = "llm_provider_requests"
    __table_args__ = (
        UniqueConstraint(
            "logical_call_id",
            "request_attempt_index",
            name="uq_llm_provider_requests_call_attempt",
        ),
        CheckConstraint(f"status IN ({LLM_CALL_STATUSES})", name="ck_llm_provider_requests_status"),
        CheckConstraint(
            "cost_status IN ('exact','estimated','incomplete','unpriced')",
            name="ck_llm_provider_requests_cost_status",
        ),
        Index(
            "ix_llm_provider_requests_provider_model_started",
            "provider_id",
            "model_id",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    logical_call_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    request_attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String)
    provider_id: Mapped[str | None] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cached_input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    estimated_input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    estimated_output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    input_usage_source: Mapped[str] = mapped_column(String, nullable=False, default="unavailable")
    output_usage_source: Mapped[str] = mapped_column(String, nullable=False, default="unavailable")
    cached_usage_source: Mapped[str] = mapped_column(String, nullable=False, default="unavailable")
    pricing_id: Mapped[str | None] = mapped_column(String)
    pricing_match_rule: Mapped[str | None] = mapped_column(String)
    pricing_version: Mapped[str | None] = mapped_column(String)
    input_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    output_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    cached_input_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    input_cost_nano_usd: Mapped[int | None] = mapped_column(BigInteger)
    output_cost_nano_usd: Mapped[int | None] = mapped_column(BigInteger)
    cached_input_cost_nano_usd: Mapped[int | None] = mapped_column(BigInteger)
    total_cost_nano_usd: Mapped[int | None] = mapped_column(BigInteger)
    cost_status: Mapped[str] = mapped_column(String, nullable=False, default="unpriced")
    status: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    finish_reason: Mapped[str | None] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    last_entity_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolCallMetricModel(Base):
    __tablename__ = "tool_call_metrics"
    __table_args__ = (
        UniqueConstraint("invocation_id", name="uq_tool_call_metrics_invocation_id"),
        UniqueConstraint(
            "source_run_id_hash", "tool_call_id", name="uq_tool_call_metrics_source_call"
        ),
        CheckConstraint(f"status IN ({TOOL_CALL_STATUSES})", name="ck_tool_call_metrics_status"),
        Index("ix_tool_call_metrics_project_started", "project_id", "started_at"),
        Index("ix_tool_call_metrics_tool_started", "tool_name", "started_at"),
        Index("ix_tool_call_metrics_run_started", "run_id", "started_at"),
        Index("ix_tool_call_metrics_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    invocation_id: Mapped[str] = mapped_column(String, nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String, nullable=False)
    source_run_id_hash: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str | None] = mapped_column(String)
    session_id: Mapped[str | None] = mapped_column(String)
    turn_id: Mapped[str | None] = mapped_column(String)
    run_id: Mapped[str | None] = mapped_column(String)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    execution_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    approval_wait_ms: Mapped[int | None] = mapped_column(BigInteger)
    total_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    error_category: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
    terminal_reason: Mapped[str | None] = mapped_column(String)
    last_entity_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    project_name_snapshot: Mapped[str | None] = mapped_column(String)
    session_title_snapshot: Mapped[str | None] = mapped_column(String)
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolApprovalEventModel(Base):
    __tablename__ = "tool_approval_events"
    __table_args__ = (
        UniqueConstraint(
            "tool_call_metric_id",
            "approval_id",
            "event_type",
            name="uq_tool_approval_events_type",
        ),
        CheckConstraint(
            f"event_type IN ({APPROVAL_EVENT_TYPES})", name="ck_tool_approval_events_type"
        ),
        Index(
            "uq_tool_approval_events_terminal",
            "tool_call_metric_id",
            "approval_id",
            unique=True,
            sqlite_where=text("event_type IN ('approved','denied','expired','stale')"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tool_call_metric_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    approval_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_type: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelPricingModel(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (
        CheckConstraint("match_type IN ('exact','pattern')", name="ck_model_pricing_match_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model_pattern: Mapped[str] = mapped_column(String, nullable=False)
    match_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    output_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    cached_input_price_nano_usd_per_million: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObservabilityEventModel(Base):
    __tablename__ = "observability_events"
    __table_args__ = (
        UniqueConstraint("id", name="uq_observability_events_id"),
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            name="uq_observability_events_entity_version",
        ),
        Index("ix_observability_events_subject_session_seq", "subject_session_id", "sequence"),
        Index("ix_observability_events_subject_project_seq", "subject_project_id", "sequence"),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    subject_project_id: Mapped[str | None] = mapped_column(String)
    subject_session_id: Mapped[str | None] = mapped_column(String)
    subject_run_id: Mapped[str | None] = mapped_column(String)
    subject_type: Mapped[str | None] = mapped_column(String)
    subject_key_hash: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    privacy_redacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObservabilityProjectionCheckpointModel(Base):
    __tablename__ = "observability_projection_checkpoints"

    projector_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_projected_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String)
