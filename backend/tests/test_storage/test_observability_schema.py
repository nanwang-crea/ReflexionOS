from datetime import UTC, datetime

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.storage.database import Database
from app.storage.models import ObservabilityEventModel, ToolApprovalEventModel

EXPECTED_TABLES = {
    "llm_logical_calls",
    "llm_provider_requests",
    "tool_call_metrics",
    "tool_approval_events",
    "model_pricing",
    "observability_events",
    "observability_projection_checkpoints",
}
EXPECTED_MIGRATION_HEAD = "a7b8c9d0e1f2"


def test_observability_migration_reaches_head(tmp_path):
    db = Database(str(tmp_path / "observability-schema.db"))

    assert EXPECTED_TABLES.issubset(set(inspect(db.engine).get_table_names()))
    with db.engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == EXPECTED_MIGRATION_HEAD


def test_permission_migration_recovers_when_column_exists_before_version(tmp_path):
    database_path = tmp_path / "permission-migration-recovery.db"
    db = Database(str(database_path))
    with db.engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = 'e5f6a7b8c9d0'")
        )
    db.engine.dispose()

    recovered_db = Database(str(database_path))

    with recovered_db.engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    permission_columns = [
        column
        for column in inspect(recovered_db.engine).get_columns("sessions")
        if column["name"] == "permission_mode"
    ]
    assert version == EXPECTED_MIGRATION_HEAD
    assert len(permission_columns) == 1


def test_observability_event_entity_versions_are_unique(tmp_path):
    db = Database(str(tmp_path / "observability-events.db"))
    event = {
        "entity_type": "provider_request",
        "entity_id": "request-1",
        "entity_version": 1,
        "event_type": "request.started",
        "payload_json": {},
        "occurred_at": datetime(2026, 7, 26, 1, tzinfo=UTC),
        "recorded_at": datetime(2026, 7, 26, 1, tzinfo=UTC),
    }

    with db.get_session() as session:
        session.add(ObservabilityEventModel(id="event-1", **event))

    try:
        with db.get_session() as session:
            session.add(ObservabilityEventModel(id="event-2", **event))
    except IntegrityError:
        pass
    else:
        raise AssertionError("duplicate entity version must be rejected")


def test_approval_has_only_one_terminal_decision(tmp_path):
    db = Database(str(tmp_path / "observability-approval.db"))
    common = {
        "tool_call_metric_id": "tool-metric-1",
        "approval_id": "approval-1",
        "occurred_at": datetime(2026, 7, 26, 1, tzinfo=UTC),
    }

    with db.get_session() as session:
        session.add(ToolApprovalEventModel(id="approval-event-1", event_type="approved", **common))

    try:
        with db.get_session() as session:
            session.add(
                ToolApprovalEventModel(id="approval-event-2", event_type="denied", **common)
            )
    except IntegrityError:
        pass
    else:
        raise AssertionError("approval must have at most one terminal decision")


def test_approval_id_can_be_reused_by_another_tool_call(tmp_path):
    db = Database(str(tmp_path / "observability-approval-scope.db"))
    common = {
        "approval_id": "approval-1",
        "event_type": "approved",
        "occurred_at": datetime(2026, 7, 26, 1, tzinfo=UTC),
    }

    with db.get_session() as session:
        session.add(
            ToolApprovalEventModel(
                id="approval-event-1",
                tool_call_metric_id="tool-metric-1",
                **common,
            )
        )
        session.add(
            ToolApprovalEventModel(
                id="approval-event-2",
                tool_call_metric_id="tool-metric-2",
                **common,
            )
        )

    with db.get_session() as session:
        assert session.query(ToolApprovalEventModel).count() == 2
