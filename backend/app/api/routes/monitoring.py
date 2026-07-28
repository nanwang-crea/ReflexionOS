from fastapi import APIRouter, Query

from app.errors import NotFoundError
from app.config.settings import MonitoringAlertSettings
from app.app_services import observability_collector
from app.models.monitoring import (
    MonitoringAnomalyResponse,
    MonitoringAlertStatusResponse,
    MonitoringOverviewResponse,
    MonitoringProviderRequestDetail,
    MonitoringProviderRequestListResponse,
    MonitoringToolCallDetail,
    MonitoringToolCallListResponse,
    MonitoringTrendResponse,
)
from app.models.observability import ObservabilityHealth
from app.services.monitoring_service import monitoring_service

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/health", response_model=ObservabilityHealth)
async def get_monitoring_health():
    return observability_collector.get_health()


@router.get("/overview", response_model=MonitoringOverviewResponse)
async def get_monitoring_overview(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
):
    return monitoring_service.get_overview(
        project_id=project_id,
        window_hours=window_hours,
    )


@router.get("/llm/requests", response_model=MonitoringProviderRequestListResponse)
async def get_monitoring_provider_requests(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=50, ge=1, le=200),
    provider_id: str | None = None,
    model_id: str | None = None,
    status: str | None = None,
    cost_status: str | None = None,
):
    return monitoring_service.list_provider_requests(
        project_id=project_id,
        window_hours=window_hours,
        limit=limit,
        provider_id=provider_id,
        model_id=model_id,
        status=status,
        cost_status=cost_status,
    )


@router.get("/tools/calls", response_model=MonitoringToolCallListResponse)
async def get_monitoring_tool_calls(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=50, ge=1, le=200),
    tool_name: str | None = None,
    status: str | None = None,
    terminal_reason: str | None = None,
    approval_event_type: str | None = None,
):
    return monitoring_service.list_tool_calls(
        project_id=project_id,
        window_hours=window_hours,
        limit=limit,
        tool_name=tool_name,
        status=status,
        terminal_reason=terminal_reason,
        approval_event_type=approval_event_type,
    )


@router.get("/trends", response_model=MonitoringTrendResponse)
async def get_monitoring_trends(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    bucket_hours: int = Query(default=1, ge=1, le=24),
):
    return monitoring_service.get_trends(
        project_id=project_id,
        window_hours=window_hours,
        bucket_hours=bucket_hours,
    )


@router.get("/anomalies", response_model=MonitoringAnomalyResponse)
async def get_monitoring_anomalies(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
):
    return monitoring_service.get_anomalies(
        project_id=project_id,
        window_hours=window_hours,
    )


@router.get("/alerts", response_model=MonitoringAlertStatusResponse)
async def get_monitoring_alerts(
    project_id: str | None = None,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
):
    return monitoring_service.get_alert_status(
        project_id=project_id,
        window_hours=window_hours,
    )


@router.put("/alerts", response_model=MonitoringAlertSettings)
async def update_monitoring_alerts(settings: MonitoringAlertSettings):
    return monitoring_service.update_alert_settings(settings)


@router.get("/llm/requests/{request_id}", response_model=MonitoringProviderRequestDetail)
async def get_monitoring_provider_request_detail(request_id: str):
    detail = monitoring_service.get_provider_request_detail(request_id)
    if detail is None:
        raise NotFoundError(resource="Provider 请求", resource_id=request_id)
    return detail


@router.get("/tools/calls/{tool_call_metric_id}", response_model=MonitoringToolCallDetail)
async def get_monitoring_tool_call_detail(tool_call_metric_id: str):
    detail = monitoring_service.get_tool_call_detail(tool_call_metric_id)
    if detail is None:
        raise NotFoundError(resource="工具调用", resource_id=tool_call_metric_id)
    return detail
