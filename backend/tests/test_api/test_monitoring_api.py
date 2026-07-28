from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config.settings import MonitoringAlertSettings
from app.main import app
from app.models.monitoring import MonitoringOverviewResponse
from app.models.observability import ObservabilityEventCreate
from app.observability.collector import ObservabilityCollector
from app.services.monitoring_service import MonitoringService
from app.storage.database import Database
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)


def test_monitoring_health_endpoint_returns_collector_state(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "monitoring-api.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    collector.record(
        ObservabilityEventCreate(
            id="event-1",
            entity_type="logical_call",
            entity_id="logical-1",
            event_type="logical.started",
            payload_json={"status": "running", "call_kind": "main"},
            subject_project_id="project-1",
            subject_session_id="session-1",
            subject_run_id="run-1",
        )
    )

    import app.api.routes.monitoring as monitoring_route_module
    import app.app_services as app_services_module

    monkeypatch.setattr(monitoring_route_module, "observability_collector", collector)
    monkeypatch.setattr(app_services_module, "_observability_collector", collector)

    with TestClient(app) as client:
        response = client.get("/api/monitoring/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["projection_lag_count"] == 0
    assert response.json()["fallback_backlog_count"] == 0


def test_monitoring_alert_settings_can_be_read_and_updated(monkeypatch):
    class DummyConfigManager:
        def __init__(self):
            self.settings = type(
                "Settings",
                (),
                {
                    "monitoring_alerts": MonitoringAlertSettings(),
                },
            )()

        def update_monitoring_alerts(self, value):
            self.settings.monitoring_alerts = value

    dummy = DummyConfigManager()

    import app.services.monitoring_service as monitoring_service_module

    monkeypatch.setattr(monitoring_service_module, "config_manager", dummy)

    with TestClient(app) as client:
        get_response = client.get("/api/monitoring/alerts")
        put_response = client.put(
            "/api/monitoring/alerts",
            json={
                "enable_in_app_notifications": True,
                "poll_interval_seconds": 60,
                "enable_webhook_notifications": False,
                "webhook_url": None,
                "webhook_min_severity": "critical",
                "webhook_cooldown_seconds": 300,
                "retry_request_count_warn": 5,
                "failed_request_count_warn": 4,
                "incomplete_cost_request_count_warn": 2,
                "tool_failed_call_count_warn": 3,
                "approval_denied_count_warn": 2,
                "approval_wait_p95_ms_warn": 45000,
                "projection_lag_count_warn": 2,
                "fallback_backlog_count_warn": 2,
                "memory_queue_depth_critical": 1,
            },
        )

    assert get_response.status_code == 200
    assert get_response.json()["settings"]["retry_request_count_warn"] == 3
    assert put_response.status_code == 200
    assert put_response.json()["retry_request_count_warn"] == 5


def test_monitoring_overview_and_lists_return_project_filtered_data(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "monitoring-query-api.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    base_time = datetime.now(UTC) - timedelta(hours=1)

    with db.get_session() as session:
        session.add(
            LLMLogicalCallModel(
                id="logical-1",
                project_id="project-1",
                session_id="session-1",
                turn_id="turn-1",
                run_id="run-1",
                provider_id="provider-a",
                model_id="model-a",
                call_kind="main",
                status="completed",
                request_count=2,
                total_cost_nano_usd=13,
                last_entity_version=2,
                started_at=base_time,
                finished_at=base_time + timedelta(minutes=1),
                updated_at=base_time + timedelta(minutes=1),
            )
        )
        session.add(
            LLMProviderRequestModel(
                id="request-1",
                logical_call_id="logical-1",
                request_attempt_index=0,
                provider_id="provider-a",
                model_id="model-a",
                input_tokens=6,
                output_tokens=4,
                cached_input_tokens=2,
                input_usage_source="provider",
                output_usage_source="provider",
                cached_usage_source="provider",
                pricing_id="price-1",
                pricing_match_rule="exact:model-a",
                pricing_version="v1",
                input_cost_nano_usd=4,
                output_cost_nano_usd=8,
                cached_input_cost_nano_usd=1,
                total_cost_nano_usd=13,
                cost_status="exact",
                status="completed",
                duration_ms=1200,
                finish_reason="stop",
                last_entity_version=2,
                started_at=base_time,
                finished_at=base_time + timedelta(seconds=1),
                updated_at=base_time + timedelta(seconds=1),
            )
        )
        session.add(
            LLMProviderRequestModel(
                id="request-2",
                logical_call_id="logical-1",
                request_attempt_index=1,
                provider_id="provider-a",
                model_id="model-a",
                cost_status="unpriced",
                status="failed",
                duration_ms=300,
                error_message="rate limited",
                last_entity_version=1,
                started_at=base_time + timedelta(seconds=2),
                finished_at=base_time + timedelta(seconds=2),
                updated_at=base_time + timedelta(seconds=2),
            )
        )
        session.add(
            ToolCallMetricModel(
                id="tool-1",
                invocation_id="tool-invocation-1",
                tool_call_id="call-1",
                source_run_id_hash="hash-1",
                project_id="project-1",
                session_id="session-1",
                turn_id="turn-1",
                run_id="run-1",
                tool_name="shell",
                status="failed",
                approval_wait_ms=900,
                total_duration_ms=900,
                error_category="approval_denied",
                error_message="审批被拒绝",
                terminal_reason="denied",
                last_entity_version=3,
                started_at=base_time,
                updated_at=base_time + timedelta(seconds=3),
            )
        )
        session.add(
            ToolApprovalEventModel(
                id="approval-event-1",
                tool_call_metric_id="tool-1",
                approval_id="approval-1",
                event_type="denied",
                actor_type="user",
                reason="deny",
                occurred_at=base_time + timedelta(seconds=2),
            )
        )

    monitoring_service = MonitoringService(db=db, collector=collector)

    import app.api.routes.monitoring as monitoring_route_module
    import app.app_services as app_services_module

    monkeypatch.setattr(monitoring_route_module, "observability_collector", collector)
    monkeypatch.setattr(monitoring_route_module, "monitoring_service", monitoring_service)
    monkeypatch.setattr(app_services_module, "_observability_collector", collector)

    with TestClient(app) as client:
        overview = client.get("/api/monitoring/overview", params={"project_id": "project-1", "window_hours": 24})
        requests = client.get("/api/monitoring/llm/requests", params={"project_id": "project-1", "limit": 10})
        request_detail = client.get("/api/monitoring/llm/requests/request-1")
        filtered_requests = client.get(
            "/api/monitoring/llm/requests",
            params={"project_id": "project-1", "status": "failed", "cost_status": "unpriced"},
        )
        tools = client.get("/api/monitoring/tools/calls", params={"project_id": "project-1", "limit": 10})
        tool_detail = client.get("/api/monitoring/tools/calls/tool-1")
        filtered_tools = client.get(
            "/api/monitoring/tools/calls",
            params={"project_id": "project-1", "terminal_reason": "denied", "approval_event_type": "denied"},
        )
        trends = client.get("/api/monitoring/trends", params={"project_id": "project-1", "window_hours": 24, "bucket_hours": 1})
        anomalies = client.get("/api/monitoring/anomalies", params={"project_id": "project-1", "window_hours": 24})

    assert overview.status_code == 200
    overview_body = MonitoringOverviewResponse.model_validate(overview.json())
    assert overview_body.llm.logical_call_count == 1
    assert overview_body.llm.provider_request_count == 2
    assert overview_body.llm.retry_request_count == 1
    assert overview_body.llm.total_cost_nano_usd == 13
    assert overview_body.tools.tool_call_count == 1
    assert overview_body.tools.denied_call_count == 1
    assert overview_body.tools.approval_denied_count == 1

    assert requests.status_code == 200
    assert requests.json()["total"] == 2
    assert requests.json()["items"][0]["project_id"] == "project-1"
    assert filtered_requests.status_code == 200
    assert filtered_requests.json()["total"] == 1
    assert filtered_requests.json()["items"][0]["id"] == "request-2"
    assert request_detail.status_code == 200
    assert request_detail.json()["pricing_id"] == "price-1"
    assert request_detail.json()["input_cost_nano_usd"] == 4

    assert tools.status_code == 200
    assert tools.json()["total"] == 1
    assert tools.json()["items"][0]["latest_approval_event_type"] == "denied"
    assert tools.json()["items"][0]["terminal_reason"] == "denied"
    assert filtered_tools.status_code == 200
    assert filtered_tools.json()["total"] == 1
    assert filtered_tools.json()["items"][0]["id"] == "tool-1"
    assert tool_detail.status_code == 200
    assert tool_detail.json()["approval_events"][0]["event_type"] == "denied"
    assert trends.status_code == 200
    assert len(trends.json()["points"]) == 1
    assert trends.json()["points"][0]["llm_request_count"] == 2
    assert trends.json()["points"][0]["tool_denied_count"] == 1
    assert anomalies.status_code == 200
    assert anomalies.json()["incomplete_cost_request_count"] == 1
    assert anomalies.json()["hottest_retry_models"][0]["model_id"] == "model-a"
    assert anomalies.json()["noisiest_tools"][0]["tool_name"] == "shell"
