from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.observability import ObservabilityEvent, ProjectionResult
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ObservabilityEventModel,
    ObservabilityProjectionCheckpointModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)
from app.storage.repositories.observability_event_repo import ObservabilityEventRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectionContractError(RuntimeError):
    pass


class UnsupportedObservabilityEventError(ProjectionContractError):
    pass


PROVIDER_MUTABLE_FIELDS = {
    "provider_request_id",
    "provider_id",
    "model_id",
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "estimated_input_tokens",
    "estimated_output_tokens",
    "input_usage_source",
    "output_usage_source",
    "cached_usage_source",
    "pricing_id",
    "pricing_match_rule",
    "pricing_version",
    "input_price_nano_usd_per_million",
    "output_price_nano_usd_per_million",
    "cached_input_price_nano_usd_per_million",
    "input_cost_nano_usd",
    "output_cost_nano_usd",
    "cached_input_cost_nano_usd",
    "total_cost_nano_usd",
    "cost_status",
    "status",
    "duration_ms",
    "finish_reason",
    "error_code",
    "error_message",
    "finished_at",
}

TOOL_MUTABLE_FIELDS = {
    "status",
    "execution_duration_ms",
    "approval_wait_ms",
    "total_duration_ms",
    "error_category",
    "error_message",
    "terminal_reason",
    "execution_started_at",
    "finished_at",
}


class ObservabilityProjector:
    def __init__(self, db, *, projector_name: str = "core"):
        self.db = db
        self.projector_name = projector_name
        self.event_repo = ObservabilityEventRepository(db)

    def project_next_batch(self, *, limit: int = 100) -> ProjectionResult:
        with self.db.get_session() as db_session:
            checkpoint = (
                db_session.query(ObservabilityProjectionCheckpointModel)
                .filter_by(projector_name=self.projector_name)
                .first()
            )
            if checkpoint is None:
                checkpoint = ObservabilityProjectionCheckpointModel(
                    projector_name=self.projector_name,
                    last_projected_sequence=0,
                    updated_at=_utc_now(),
                )
                db_session.add(checkpoint)
                db_session.flush()

            events = self.event_repo.list_after(
                checkpoint.last_projected_sequence,
                limit=limit,
                db_session=db_session,
            )
            for event in events:
                self._apply_event(event, db_session)
                checkpoint.last_projected_sequence = event.sequence

            checkpoint.updated_at = _utc_now()
            checkpoint.last_error_code = None
            db_session.flush()

            return ProjectionResult(
                projector_name=self.projector_name,
                processed_count=len(events),
                last_projected_sequence=checkpoint.last_projected_sequence,
            )

    def _apply_event(self, event: ObservabilityEvent, db_session) -> None:
        if event.entity_type == "logical_call":
            self._project_logical_call(event, db_session)
        elif event.entity_type == "provider_request":
            self._project_provider_request(event, db_session)
        elif event.entity_type == "tool_call":
            self._project_tool_call(event, db_session)
        elif event.entity_type == "approval":
            self._project_approval(event, db_session)
        elif event.entity_type == "privacy_tombstone":
            self._project_privacy_tombstone(event, db_session)
        else:
            raise UnsupportedObservabilityEventError(
                f"unsupported observability entity type: {event.entity_type}"
            )

    def _project_logical_call(self, event: ObservabilityEvent, db_session) -> None:
        model = db_session.query(LLMLogicalCallModel).filter_by(id=event.entity_id).first()
        if model is not None and event.entity_version <= model.last_entity_version:
            return

        payload = event.payload_json
        terminal_statuses = {"completed", "failed", "cancelled", "interrupted"}
        if model is None:
            model = LLMLogicalCallModel(
                id=event.entity_id,
                project_id=event.subject_project_id,
                session_id=event.subject_session_id,
                run_id=event.subject_run_id,
                turn_id=payload.get("turn_id"),
                provider_id=payload.get("provider_id"),
                model_id=payload.get("model_id"),
                call_kind=payload.get("call_kind", "main"),
                loop_iteration=payload.get("loop_iteration"),
                status=payload.get("status", "running"),
                request_count=0,
                total_cost_nano_usd=0,
                started_at=payload.get("started_at", event.occurred_at),
                updated_at=event.occurred_at,
                project_name_snapshot=payload.get("project_name_snapshot"),
                session_title_snapshot=payload.get("session_title_snapshot"),
                last_entity_version=event.entity_version,
            )
            db_session.add(model)
            return

        for key in ("status", "duration_ms", "first_token_ms", "finished_at"):
            if key in payload:
                setattr(model, key, payload[key])
        if payload.get("status") in terminal_statuses and "finished_at" not in payload:
            model.finished_at = event.occurred_at
        model.updated_at = event.occurred_at
        model.last_entity_version = event.entity_version

    def _project_provider_request(self, event: ObservabilityEvent, db_session) -> None:
        model = db_session.query(LLMProviderRequestModel).filter_by(id=event.entity_id).first()
        if model is not None and event.entity_version <= model.last_entity_version:
            return

        payload = event.payload_json
        logical_call_id = payload.get("logical_call_id")
        terminal_statuses = {"completed", "failed", "cancelled", "interrupted"}
        if model is None:
            missing = {
                "logical_call_id",
                "request_attempt_index",
                "status",
            } - payload.keys()
            if missing:
                raise ProjectionContractError(
                    f"provider request snapshot missing fields: {sorted(missing)}"
                )
            model = LLMProviderRequestModel(
                id=event.entity_id,
                logical_call_id=payload["logical_call_id"],
                request_attempt_index=payload["request_attempt_index"],
                status=payload["status"],
                cost_status=payload.get("cost_status", "unpriced"),
                started_at=payload.get("started_at", event.occurred_at),
                updated_at=event.occurred_at,
                last_entity_version=event.entity_version,
            )
            self._copy_provider_snapshot(model, payload)
            db_session.add(model)
            db_session.flush()
        else:
            self._copy_provider_snapshot(model, payload)
            if payload.get("status") in terminal_statuses and "finished_at" not in payload:
                model.finished_at = event.occurred_at
            model.updated_at = event.occurred_at
            model.last_entity_version = event.entity_version
            logical_call_id = model.logical_call_id
            db_session.flush()

        if model is not None and payload.get("status") in terminal_statuses and model.finished_at is None:
            model.finished_at = event.occurred_at

        self._recompute_logical_call(logical_call_id, db_session)

    @staticmethod
    def _copy_provider_snapshot(model: LLMProviderRequestModel, payload: dict) -> None:
        for key in PROVIDER_MUTABLE_FIELDS:
            if key in payload:
                setattr(model, key, payload[key])

    def _project_tool_call(self, event: ObservabilityEvent, db_session) -> None:
        model = db_session.query(ToolCallMetricModel).filter_by(id=event.entity_id).first()
        if model is not None and event.entity_version <= model.last_entity_version:
            return

        payload = event.payload_json
        terminal_statuses = {"completed", "failed", "cancelled", "interrupted"}
        if model is None:
            missing = {
                "invocation_id",
                "tool_call_id",
                "source_run_id_hash",
                "tool_name",
                "status",
            } - payload.keys()
            if missing:
                raise ProjectionContractError(
                    f"tool call snapshot missing fields: {sorted(missing)}"
                )
            model = ToolCallMetricModel(
                id=event.entity_id,
                invocation_id=payload["invocation_id"],
                tool_call_id=payload["tool_call_id"],
                source_run_id_hash=payload["source_run_id_hash"],
                project_id=event.subject_project_id,
                session_id=event.subject_session_id,
                turn_id=payload.get("turn_id"),
                run_id=event.subject_run_id,
                tool_name=payload["tool_name"],
                status=payload["status"],
                started_at=payload.get("started_at", event.occurred_at),
                updated_at=event.occurred_at,
                project_name_snapshot=payload.get("project_name_snapshot"),
                session_title_snapshot=payload.get("session_title_snapshot"),
                last_entity_version=event.entity_version,
            )
            self._copy_tool_snapshot(model, payload)
            if payload.get("status") in terminal_statuses and model.finished_at is None:
                model.finished_at = event.occurred_at
            db_session.add(model)
            db_session.flush()
            return

        self._copy_tool_snapshot(model, payload)
        if payload.get("status") in terminal_statuses and "finished_at" not in payload:
            model.finished_at = event.occurred_at
        model.updated_at = event.occurred_at
        model.last_entity_version = event.entity_version

    @staticmethod
    def _copy_tool_snapshot(model: ToolCallMetricModel, payload: dict) -> None:
        for key in TOOL_MUTABLE_FIELDS:
            if key in payload:
                value = payload[key]
                if key in {"execution_started_at", "finished_at"} and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                setattr(model, key, value)

    def _project_approval(self, event: ObservabilityEvent, db_session) -> None:
        payload = event.payload_json
        missing = {"tool_call_metric_id", "approval_id", "event_type"} - payload.keys()
        if missing:
            raise ProjectionContractError(
                f"approval snapshot missing fields: {sorted(missing)}"
            )

        if db_session.get(ToolApprovalEventModel, event.id) is not None:
            return

        db_session.add(
            ToolApprovalEventModel(
                id=event.id,
                tool_call_metric_id=payload["tool_call_metric_id"],
                approval_id=payload["approval_id"],
                event_type=payload["event_type"],
                actor_type=payload.get("actor_type"),
                reason=payload.get("reason"),
                occurred_at=event.occurred_at,
            )
        )

    @staticmethod
    def _project_privacy_tombstone(event: ObservabilityEvent, db_session) -> None:
        if not event.subject_type or not event.subject_key_hash:
            raise ProjectionContractError(
                "privacy tombstone requires subject_type and subject_key_hash"
            )

        entity_rows = db_session.execute(
            select(ObservabilityEventModel.entity_type, ObservabilityEventModel.entity_id).where(
                ObservabilityEventModel.subject_key_hash == event.subject_key_hash,
                ObservabilityEventModel.sequence < event.sequence,
            )
        ).all()
        logical_ids = {
            entity_id for entity_type, entity_id in entity_rows if entity_type == "logical_call"
        }
        request_ids = {
            entity_id for entity_type, entity_id in entity_rows if entity_type == "provider_request"
        }
        tool_ids = {
            entity_id for entity_type, entity_id in entity_rows if entity_type == "tool_call"
        }

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
                    LLMLogicalCallModel.source_deleted_at: event.occurred_at,
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
                    ToolCallMetricModel.source_deleted_at: event.occurred_at,
                },
                synchronize_session=False,
            )
            db_session.query(ToolApprovalEventModel).filter(
                ToolApprovalEventModel.tool_call_metric_id.in_(tool_ids)
            ).update(
                {ToolApprovalEventModel.reason: None},
                synchronize_session=False,
            )

    @staticmethod
    def _recompute_logical_call(logical_call_id: str, db_session) -> None:
        logical_call = db_session.query(LLMLogicalCallModel).filter_by(id=logical_call_id).first()
        if logical_call is None:
            return
        count, total = (
            db_session.query(
                func.count(LLMProviderRequestModel.id),
                func.coalesce(func.sum(LLMProviderRequestModel.total_cost_nano_usd), 0),
            )
            .filter(LLMProviderRequestModel.logical_call_id == logical_call_id)
            .one()
        )
        logical_call.request_count = int(count or 0)
        logical_call.total_cost_nano_usd = int(total or 0)
