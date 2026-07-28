"""add observability schema

Revision ID: e5f6a7b8c9d0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-26
"""

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


LLM_STATUSES = "'running','completed','failed','cancelled','interrupted'"
TOOL_STATUSES = "'running','waiting_for_approval','completed','failed','cancelled','interrupted'"


def upgrade() -> None:
    op.create_table(
        "llm_logical_calls",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String()),
        sa.Column("session_id", sa.String()),
        sa.Column("turn_id", sa.String()),
        sa.Column("run_id", sa.String()),
        sa.Column("provider_id", sa.String()),
        sa.Column("model_id", sa.String()),
        sa.Column("call_kind", sa.String(), nullable=False),
        sa.Column("loop_iteration", sa.Integer()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("first_token_ms", sa.BigInteger()),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_nano_usd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_entity_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_name_snapshot", sa.String()),
        sa.Column("session_title_snapshot", sa.String()),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN ({LLM_STATUSES})", name="ck_llm_logical_calls_status"),
    )
    op.create_index(
        "ix_llm_logical_calls_project_started", "llm_logical_calls", ["project_id", "started_at"]
    )
    op.create_index(
        "ix_llm_logical_calls_run_started", "llm_logical_calls", ["run_id", "started_at"]
    )
    op.create_index("ix_llm_logical_calls_session_id", "llm_logical_calls", ["session_id"])

    op.create_table(
        "llm_provider_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("logical_call_id", sa.String(), nullable=False),
        sa.Column("request_attempt_index", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String()),
        sa.Column("provider_id", sa.String()),
        sa.Column("model_id", sa.String()),
        sa.Column("input_tokens", sa.BigInteger()),
        sa.Column("output_tokens", sa.BigInteger()),
        sa.Column("cached_input_tokens", sa.BigInteger()),
        sa.Column("estimated_input_tokens", sa.BigInteger()),
        sa.Column("estimated_output_tokens", sa.BigInteger()),
        sa.Column("input_usage_source", sa.String(), nullable=False, server_default="unavailable"),
        sa.Column("output_usage_source", sa.String(), nullable=False, server_default="unavailable"),
        sa.Column("cached_usage_source", sa.String(), nullable=False, server_default="unavailable"),
        sa.Column("pricing_id", sa.String()),
        sa.Column("pricing_match_rule", sa.String()),
        sa.Column("pricing_version", sa.String()),
        sa.Column("input_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("output_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("cached_input_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("input_cost_nano_usd", sa.BigInteger()),
        sa.Column("output_cost_nano_usd", sa.BigInteger()),
        sa.Column("cached_input_cost_nano_usd", sa.BigInteger()),
        sa.Column("total_cost_nano_usd", sa.BigInteger()),
        sa.Column("cost_status", sa.String(), nullable=False, server_default="unpriced"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("finish_reason", sa.String()),
        sa.Column("error_code", sa.String()),
        sa.Column("error_message", sa.Text()),
        sa.Column("last_entity_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "logical_call_id", "request_attempt_index", name="uq_llm_provider_requests_call_attempt"
        ),
        sa.CheckConstraint(f"status IN ({LLM_STATUSES})", name="ck_llm_provider_requests_status"),
        sa.CheckConstraint(
            "cost_status IN ('exact','estimated','incomplete','unpriced')",
            name="ck_llm_provider_requests_cost_status",
        ),
    )
    op.create_index(
        "ix_llm_provider_requests_logical_call_id", "llm_provider_requests", ["logical_call_id"]
    )
    op.create_index(
        "ix_llm_provider_requests_provider_model_started",
        "llm_provider_requests",
        ["provider_id", "model_id", "started_at"],
    )

    op.create_table(
        "tool_call_metrics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("invocation_id", sa.String(), nullable=False),
        sa.Column("tool_call_id", sa.String(), nullable=False),
        sa.Column("source_run_id_hash", sa.String(), nullable=False),
        sa.Column("project_id", sa.String()),
        sa.Column("session_id", sa.String()),
        sa.Column("turn_id", sa.String()),
        sa.Column("run_id", sa.String()),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("execution_duration_ms", sa.BigInteger()),
        sa.Column("approval_wait_ms", sa.BigInteger()),
        sa.Column("total_duration_ms", sa.BigInteger()),
        sa.Column("error_category", sa.String()),
        sa.Column("error_message", sa.Text()),
        sa.Column("terminal_reason", sa.String()),
        sa.Column("last_entity_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_name_snapshot", sa.String()),
        sa.Column("session_title_snapshot", sa.String()),
        sa.Column("source_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("invocation_id", name="uq_tool_call_metrics_invocation_id"),
        sa.UniqueConstraint(
            "source_run_id_hash", "tool_call_id", name="uq_tool_call_metrics_source_call"
        ),
        sa.CheckConstraint(f"status IN ({TOOL_STATUSES})", name="ck_tool_call_metrics_status"),
    )
    op.create_index(
        "ix_tool_call_metrics_project_started", "tool_call_metrics", ["project_id", "started_at"]
    )
    op.create_index(
        "ix_tool_call_metrics_tool_started", "tool_call_metrics", ["tool_name", "started_at"]
    )
    op.create_index(
        "ix_tool_call_metrics_run_started", "tool_call_metrics", ["run_id", "started_at"]
    )
    op.create_index(
        "ix_tool_call_metrics_status_updated", "tool_call_metrics", ["status", "updated_at"]
    )

    op.create_table(
        "tool_approval_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tool_call_metric_id", sa.String(), nullable=False),
        sa.Column("approval_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor_type", sa.String()),
        sa.Column("reason", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("approval_id", "event_type", name="uq_tool_approval_events_type"),
        sa.CheckConstraint(
            "event_type IN ('requested','approved','denied','expired','stale')",
            name="ck_tool_approval_events_type",
        ),
    )
    op.create_index(
        "ix_tool_approval_events_tool_call_metric_id",
        "tool_approval_events",
        ["tool_call_metric_id"],
    )
    op.create_index("ix_tool_approval_events_approval_id", "tool_approval_events", ["approval_id"])
    op.create_index(
        "uq_tool_approval_events_terminal",
        "tool_approval_events",
        ["approval_id"],
        unique=True,
        sqlite_where=sa.text("event_type IN ('approved','denied','expired','stale')"),
    )

    op.create_table(
        "model_pricing",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("model_pattern", sa.String(), nullable=False),
        sa.Column("match_type", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("output_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("cached_input_price_nano_usd_per_million", sa.BigInteger()),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint("match_type IN ('exact','pattern')", name="ck_model_pricing_match_type"),
    )
    op.create_index("ix_model_pricing_provider_id", "model_pricing", ["provider_id"])

    op.create_table(
        "observability_events",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("subject_project_id", sa.String()),
        sa.Column("subject_session_id", sa.String()),
        sa.Column("subject_run_id", sa.String()),
        sa.Column("subject_type", sa.String()),
        sa.Column("subject_key_hash", sa.String()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("privacy_redacted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("id", name="uq_observability_events_id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            name="uq_observability_events_entity_version",
        ),
    )
    op.create_index(
        "ix_observability_events_subject_session_seq",
        "observability_events",
        ["subject_session_id", "sequence"],
    )
    op.create_index(
        "ix_observability_events_subject_project_seq",
        "observability_events",
        ["subject_project_id", "sequence"],
    )

    op.create_table(
        "observability_projection_checkpoints",
        sa.Column("projector_name", sa.String(), primary_key=True),
        sa.Column("last_projected_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("observability_projection_checkpoints")
    op.drop_index("ix_observability_events_subject_project_seq", table_name="observability_events")
    op.drop_index("ix_observability_events_subject_session_seq", table_name="observability_events")
    op.drop_table("observability_events")
    op.drop_index("ix_model_pricing_provider_id", table_name="model_pricing")
    op.drop_table("model_pricing")
    op.drop_index("uq_tool_approval_events_terminal", table_name="tool_approval_events")
    op.drop_index("ix_tool_approval_events_approval_id", table_name="tool_approval_events")
    op.drop_index("ix_tool_approval_events_tool_call_metric_id", table_name="tool_approval_events")
    op.drop_table("tool_approval_events")
    op.drop_index("ix_tool_call_metrics_status_updated", table_name="tool_call_metrics")
    op.drop_index("ix_tool_call_metrics_run_started", table_name="tool_call_metrics")
    op.drop_index("ix_tool_call_metrics_tool_started", table_name="tool_call_metrics")
    op.drop_index("ix_tool_call_metrics_project_started", table_name="tool_call_metrics")
    op.drop_table("tool_call_metrics")
    op.drop_index(
        "ix_llm_provider_requests_provider_model_started", table_name="llm_provider_requests"
    )
    op.drop_index("ix_llm_provider_requests_logical_call_id", table_name="llm_provider_requests")
    op.drop_table("llm_provider_requests")
    op.drop_index("ix_llm_logical_calls_session_id", table_name="llm_logical_calls")
    op.drop_index("ix_llm_logical_calls_run_started", table_name="llm_logical_calls")
    op.drop_index("ix_llm_logical_calls_project_started", table_name="llm_logical_calls")
    op.drop_table("llm_logical_calls")
