from datetime import UTC, datetime
from uuid import uuid4

from app.models.observability import (
    ObservabilityEventCreate,
    redact_observability_payload,
    subject_hash,
)
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ObservabilityEventModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)
from app.storage.repositories.observability_event_repo import ObservabilityEventRepository


class ObservabilityPrivacyService:
    def __init__(self, db):
        self.db = db
        self.event_repo = ObservabilityEventRepository(db)

    def redact_session(self, session_id: str, *, db_session) -> str:
        now = datetime.now(UTC)
        key_hash = subject_hash("session", session_id)
        events = (
            db_session.query(ObservabilityEventModel)
            .filter(ObservabilityEventModel.subject_session_id == session_id)
            .all()
        )
        logical_ids = {event.entity_id for event in events if event.entity_type == "logical_call"}
        request_ids = {
            event.entity_id for event in events if event.entity_type == "provider_request"
        }
        tool_ids = {event.entity_id for event in events if event.entity_type == "tool_call"}

        if logical_ids:
            db_session.query(LLMLogicalCallModel).filter(
                LLMLogicalCallModel.id.in_(logical_ids)
            ).update(
                {
                    LLMLogicalCallModel.project_id: None,
                    LLMLogicalCallModel.session_id: None,
                    LLMLogicalCallModel.turn_id: None,
                    LLMLogicalCallModel.run_id: None,
                    LLMLogicalCallModel.project_name_snapshot: None,
                    LLMLogicalCallModel.session_title_snapshot: None,
                    LLMLogicalCallModel.source_deleted_at: now,
                },
                synchronize_session=False,
            )
        if request_ids:
            db_session.query(LLMProviderRequestModel).filter(
                LLMProviderRequestModel.id.in_(request_ids)
            ).update(
                {
                    LLMProviderRequestModel.provider_request_id: None,
                    LLMProviderRequestModel.error_message: None,
                },
                synchronize_session=False,
            )
        if tool_ids:
            db_session.query(ToolCallMetricModel).filter(
                ToolCallMetricModel.id.in_(tool_ids)
            ).update(
                {
                    ToolCallMetricModel.project_id: None,
                    ToolCallMetricModel.session_id: None,
                    ToolCallMetricModel.turn_id: None,
                    ToolCallMetricModel.run_id: None,
                    ToolCallMetricModel.project_name_snapshot: None,
                    ToolCallMetricModel.session_title_snapshot: None,
                    ToolCallMetricModel.error_message: None,
                    ToolCallMetricModel.source_deleted_at: now,
                },
                synchronize_session=False,
            )
            db_session.query(ToolApprovalEventModel).filter(
                ToolApprovalEventModel.tool_call_metric_id.in_(tool_ids)
            ).update({ToolApprovalEventModel.reason: None}, synchronize_session=False)

        for event in events:
            event.payload_json = redact_observability_payload(
                event.payload_json,
                sensitive_values={
                    session_id,
                    event.subject_project_id or "",
                    event.subject_run_id or "",
                },
            )
            event.subject_project_id = None
            event.subject_session_id = None
            event.subject_run_id = None
            event.subject_type = "session"
            event.subject_key_hash = key_hash
            event.privacy_redacted_at = now

        tombstone_id = f"tombstone-{uuid4().hex}"
        self.event_repo.append(
            ObservabilityEventCreate(
                id=tombstone_id,
                entity_type="privacy_tombstone",
                entity_id=tombstone_id,
                event_type="privacy.deleted",
                payload_json={"subject_type": "session"},
                subject_type="session",
                subject_key_hash=key_hash,
                occurred_at=now,
            ),
            db_session=db_session,
        )
        return tombstone_id
