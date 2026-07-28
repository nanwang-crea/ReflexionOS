from concurrent.futures import ThreadPoolExecutor

import pytest

from app.models.observability import ObservabilityEventCreate
from app.observability.projector import (
    ObservabilityProjector,
    ProjectionContractError,
)
from app.storage.database import Database
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ObservabilityProjectionCheckpointModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)
from app.storage.repositories.observability_event_repo import ObservabilityEventRepository


def _event(entity_type, entity_id, event_type, payload, *, version=None):
    return ObservabilityEventCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload_json=payload,
        entity_version=version,
        subject_project_id="project-1",
        subject_session_id="session-1",
        subject_run_id="run-1",
    )


def test_append_is_idempotent_and_assigns_entity_versions(tmp_path):
    db = Database(str(tmp_path / "events.db"))
    repo = ObservabilityEventRepository(db)
    first_input = _event("logical_call", "logical-1", "logical.started", {"status": "running"})

    first = repo.append(first_input)
    duplicate = repo.append(first_input)
    second = repo.append(
        _event("logical_call", "logical-1", "logical.completed", {"status": "completed"})
    )

    assert duplicate.sequence == first.sequence
    assert first.entity_version == 1
    assert second.entity_version == 2
    assert second.sequence > first.sequence


def test_concurrent_append_assigns_distinct_entity_versions(tmp_path):
    db = Database(str(tmp_path / "events-concurrent.db"))

    def append(index):
        return ObservabilityEventRepository(db).append(
            _event(
                "logical_call",
                "logical-concurrent",
                f"logical.event-{index}",
                {"status": "running"},
            )
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        events = list(executor.map(append, range(2)))

    assert sorted(event.entity_version for event in events) == [1, 2]
    assert len({event.sequence for event in events}) == 2


def test_projector_recomputes_request_count_and_cost(tmp_path):
    db = Database(str(tmp_path / "projection.db"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        _event(
            "logical_call",
            "logical-1",
            "logical.started",
            {
                "status": "running",
                "call_kind": "main",
                "provider_id": "provider-1",
                "model_id": "model-1",
            },
        )
    )
    repo.append(
        _event(
            "provider_request",
            "request-1",
            "request.started",
            {
                "logical_call_id": "logical-1",
                "request_attempt_index": 0,
                "status": "running",
            },
        )
    )
    repo.append(
        _event(
            "provider_request",
            "request-1",
            "request.completed",
            {
                "logical_call_id": "logical-1",
                "status": "completed",
                "cost_status": "exact",
                "total_cost_nano_usd": 1250,
                "input_tokens": 100,
                "output_tokens": 20,
            },
        )
    )

    result = ObservabilityProjector(db).project_next_batch()

    assert result.processed_count == 3
    with db.get_session() as session:
        logical = session.get(LLMLogicalCallModel, "logical-1")
        request = session.get(LLMProviderRequestModel, "request-1")
        checkpoint = session.get(ObservabilityProjectionCheckpointModel, "core")
        assert logical.request_count == 1
        assert logical.total_cost_nano_usd == 1250
        assert request.status == "completed"
        assert request.last_entity_version == 2
        assert checkpoint.last_projected_sequence == result.last_projected_sequence

    replay = ObservabilityProjector(db).project_next_batch()
    assert replay.processed_count == 0
    with db.get_session() as session:
        logical = session.get(LLMLogicalCallModel, "logical-1")
        assert logical.total_cost_nano_usd == 1250


def test_projection_and_checkpoint_roll_back_together(tmp_path):
    db = Database(str(tmp_path / "projection-rollback.db"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        _event(
            "logical_call",
            "logical-1",
            "logical.started",
            {"status": "running", "call_kind": "main"},
        )
    )
    repo.append(
        _event(
            "provider_request",
            "request-bad",
            "request.started",
            {"logical_call_id": "logical-1", "status": "running"},
        )
    )

    with pytest.raises(ProjectionContractError):
        ObservabilityProjector(db).project_next_batch()

    with db.get_session() as session:
        assert session.get(LLMLogicalCallModel, "logical-1") is None
        assert session.get(ObservabilityProjectionCheckpointModel, "core") is None


def test_unsupported_event_blocks_checkpoint(tmp_path):
    db = Database(str(tmp_path / "unsupported-event.db"))
    event = ObservabilityEventRepository(db).append(
        _event("tool_call", "tool-bad", "tool.running", {"status": "running"})
    )

    with pytest.raises(ProjectionContractError):
        ObservabilityProjector(db).project_next_batch()

    with db.get_session() as session:
        checkpoint = session.get(ObservabilityProjectionCheckpointModel, "core")
        assert checkpoint is None or checkpoint.last_projected_sequence < event.sequence


def test_projector_projects_tool_call_and_approval_events(tmp_path):
    db = Database(str(tmp_path / "tool-approval.db"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        _event(
            "tool_call",
            "tool-metric-1",
            "tool.running",
            {
                "invocation_id": "tool-invocation-1",
                "tool_call_id": "call-1",
                "source_run_id_hash": "hash-1",
                "tool_name": "shell",
                "turn_id": "turn-1",
                "status": "running",
                "execution_started_at": "2026-07-26T01:00:00+00:00",
            },
        )
    )
    repo.append(
        _event(
            "tool_call",
            "tool-metric-1",
            "tool.waiting_for_approval",
            {
                "invocation_id": "tool-invocation-1",
                "tool_call_id": "call-1",
                "source_run_id_hash": "hash-1",
                "tool_name": "shell",
                "status": "waiting_for_approval",
            },
        )
    )
    repo.append(
        _event(
            "approval",
            "approval-1",
            "approval.requested",
            {
                "tool_call_metric_id": "tool-metric-1",
                "approval_id": "approval-1",
                "event_type": "requested",
                "actor_type": "system",
                "reason": "需要审批",
            },
        )
    )
    repo.append(
        _event(
            "approval",
            "approval-1",
            "approval.denied",
            {
                "tool_call_metric_id": "tool-metric-1",
                "approval_id": "approval-1",
                "event_type": "denied",
                "actor_type": "user",
                "reason": "deny",
            },
        )
    )
    repo.append(
        _event(
            "tool_call",
            "tool-metric-1",
            "tool.failed",
            {
                "invocation_id": "tool-invocation-1",
                "tool_call_id": "call-1",
                "source_run_id_hash": "hash-1",
                "tool_name": "shell",
                "status": "failed",
                "approval_wait_ms": 1200,
                "total_duration_ms": 1200,
                "error_category": "approval_denied",
                "error_message": "审批被拒绝",
                "terminal_reason": "denied",
            },
        )
    )

    ObservabilityProjector(db).project_next_batch()

    with db.get_session() as session:
        tool_metric = session.get(ToolCallMetricModel, "tool-metric-1")
        approval_rows = (
            session.query(ToolApprovalEventModel)
            .order_by(ToolApprovalEventModel.occurred_at.asc())
            .all()
        )

        assert tool_metric.status == "failed"
        assert tool_metric.invocation_id == "tool-invocation-1"
        assert tool_metric.approval_wait_ms == 1200
        assert tool_metric.total_duration_ms == 1200
        assert tool_metric.error_category == "approval_denied"
        assert tool_metric.terminal_reason == "denied"
        assert len(approval_rows) == 2
        assert [row.event_type for row in approval_rows] == ["requested", "denied"]


def test_terminal_provider_snapshot_can_arrive_first(tmp_path):
    db = Database(str(tmp_path / "terminal-first.db"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        _event(
            "logical_call",
            "logical-1",
            "logical.started",
            {"status": "running", "call_kind": "main"},
        )
    )
    repo.append(
        _event(
            "provider_request",
            "request-1",
            "request.completed",
            {
                "logical_call_id": "logical-1",
                "request_attempt_index": 0,
                "provider_request_id": "provider-request-1",
                "provider_id": "provider-1",
                "model_id": "model-1",
                "status": "completed",
                "input_tokens": 300,
                "output_tokens": 40,
                "input_usage_source": "provider",
                "output_usage_source": "provider",
                "cached_usage_source": "unavailable",
                "cost_status": "incomplete",
                "total_cost_nano_usd": 9000,
                "duration_ms": 1250,
                "finish_reason": "stop",
            },
            version=2,
        )
    )

    ObservabilityProjector(db).project_next_batch()

    with db.get_session() as session:
        request = session.get(LLMProviderRequestModel, "request-1")
        logical = session.get(LLMLogicalCallModel, "logical-1")
        assert request.provider_request_id == "provider-request-1"
        assert request.input_tokens == 300
        assert request.output_tokens == 40
        assert request.duration_ms == 1250
        assert request.last_entity_version == 2
        assert logical.total_cost_nano_usd == 9000
