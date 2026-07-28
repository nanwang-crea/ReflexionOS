import hashlib
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal[
    "logical_call",
    "provider_request",
    "tool_call",
    "approval",
    "privacy_tombstone",
]
ObservabilityHealthStatus = Literal["healthy", "degraded", "critical"]
ObservabilityWriteTarget = Literal["database", "journal", "memory"]

SENSITIVE_PAYLOAD_KEYS = {
    "project_id",
    "session_id",
    "turn_id",
    "run_id",
    "provider_request_id",
    "project_name_snapshot",
    "session_title_snapshot",
    "error",
    "error_message",
    "message",
    "detail",
    "reason",
    "arguments",
    "output",
    "content",
    "path",
    "command",
    "url",
    "headers",
    "authorization",
    "api_key",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def subject_hash(subject_type: str, subject_id: str) -> str:
    value = f"reflexion-observability:{subject_type}:{subject_id}".encode()
    return hashlib.sha256(value).hexdigest()


def redact_observability_payload(value: Any, *, sensitive_values: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_observability_payload(item, sensitive_values=sensitive_values)
            for key, item in value.items()
            if key.casefold() not in SENSITIVE_PAYLOAD_KEYS
        }
    if isinstance(value, list):
        return [
            redact_observability_payload(item, sensitive_values=sensitive_values) for item in value
        ]
    if isinstance(value, str):
        redacted = value
        for sensitive in sensitive_values:
            if sensitive:
                redacted = redacted.replace(sensitive, "[redacted]")
        return redacted
    return value


class ObservabilityEventCreate(BaseModel):
    id: str = Field(default_factory=lambda: f"obs-{uuid4().hex}")
    entity_type: EntityType
    entity_id: str
    event_type: str
    payload_json: dict = Field(default_factory=dict)
    entity_version: int | None = Field(default=None, ge=1)
    subject_project_id: str | None = None
    subject_session_id: str | None = None
    subject_run_id: str | None = None
    subject_type: Literal["project", "session", "run"] | None = None
    subject_key_hash: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)


class ObservabilityEvent(ObservabilityEventCreate):
    model_config = ConfigDict(from_attributes=True)

    sequence: int
    entity_version: int
    recorded_at: datetime
    privacy_redacted_at: datetime | None = None


class ProjectionResult(BaseModel):
    projector_name: str
    processed_count: int
    last_projected_sequence: int


class ObservabilityCollectionResult(BaseModel):
    event_id: str
    target: ObservabilityWriteTarget
    event_sequence: int | None = None
    journal_sequence: int | None = None


class ObservabilityHealth(BaseModel):
    status: ObservabilityHealthStatus
    last_event_recorded_at: datetime | None = None
    last_projection_at: datetime | None = None
    projection_lag_count: int = 0
    fallback_backlog_count: int = 0
    memory_queue_depth: int = 0
    dropped_metrics_count: int = 0
    last_error_code: str | None = None
    last_error_at: datetime | None = None
