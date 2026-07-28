from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from app.app_services import observability_collector
from app.config.settings import MonitoringAlertSettings, config_manager
from app.models.monitoring import (
    MonitoringApprovalEventItem,
    MonitoringAnomalyResponse,
    MonitoringAlertState,
    MonitoringAlertStatusResponse,
    MonitoringProviderRequestDetail,
    MonitoringLLMOverview,
    MonitoringModelAnomaly,
    MonitoringModelSummary,
    MonitoringOverviewResponse,
    MonitoringProviderRequestItem,
    MonitoringProviderRequestListResponse,
    MonitoringToolCallDetail,
    MonitoringToolCallItem,
    MonitoringToolCallListResponse,
    MonitoringToolAnomaly,
    MonitoringTrendPoint,
    MonitoringTrendResponse,
    MonitoringToolOverview,
    MonitoringToolSummary,
)
from app.storage.database import db as default_db
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)


def _window_start(window_hours: int) -> datetime:
    return datetime.now(UTC) - timedelta(hours=window_hours)


def _bucket_start(value: datetime, *, bucket_hours: int) -> datetime:
    normalized = value.astimezone(UTC)
    bucket_hour = (normalized.hour // bucket_hours) * bucket_hours
    return normalized.replace(minute=0, second=0, microsecond=0, hour=bucket_hour)


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, int(round((len(sorted_values) - 1) * 0.95)))
    return sorted_values[index]


class MonitoringService:
    def __init__(self, db=None, *, collector=None):
        self.db = db or default_db
        self.collector = collector or observability_collector

    def get_alert_settings(self) -> MonitoringAlertSettings:
        settings = config_manager.settings.monitoring_alerts
        if isinstance(settings, MonitoringAlertSettings):
            return settings
        return MonitoringAlertSettings.model_validate(settings)

    def update_alert_settings(
        self,
        settings: MonitoringAlertSettings,
    ) -> MonitoringAlertSettings:
        config_manager.update_monitoring_alerts(settings)
        return config_manager.settings.monitoring_alerts

    def get_overview(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
    ) -> MonitoringOverviewResponse:
        started_after = _window_start(window_hours)
        health = self.collector.get_health()

        with self.db.get_session() as db_session:
            logical_query = db_session.query(LLMLogicalCallModel).filter(
                LLMLogicalCallModel.started_at >= started_after
            )
            if project_id:
                logical_query = logical_query.filter(LLMLogicalCallModel.project_id == project_id)
            logical_calls = logical_query.all()

            request_query = (
                db_session.query(LLMProviderRequestModel, LLMLogicalCallModel)
                .join(
                    LLMLogicalCallModel,
                    LLMLogicalCallModel.id == LLMProviderRequestModel.logical_call_id,
                )
                .filter(LLMProviderRequestModel.started_at >= started_after)
            )
            if project_id:
                request_query = request_query.filter(LLMLogicalCallModel.project_id == project_id)
            request_rows = request_query.all()

            tool_query = db_session.query(ToolCallMetricModel).filter(
                ToolCallMetricModel.started_at >= started_after
            )
            if project_id:
                tool_query = tool_query.filter(ToolCallMetricModel.project_id == project_id)
            tool_metrics = tool_query.all()

            approval_query = (
                db_session.query(ToolApprovalEventModel, ToolCallMetricModel)
                .join(
                    ToolCallMetricModel,
                    ToolCallMetricModel.id == ToolApprovalEventModel.tool_call_metric_id,
                )
                .filter(ToolApprovalEventModel.occurred_at >= started_after)
            )
            if project_id:
                approval_query = approval_query.filter(ToolCallMetricModel.project_id == project_id)
            approval_rows = approval_query.all()
            cost_status_counts = Counter(
                request.cost_status for request, _ in request_rows if request.cost_status
            )
            request_durations = [
                int(request.duration_ms)
                for request, _ in request_rows
                if request.duration_ms is not None
            ]
            llm_overview = MonitoringLLMOverview(
                logical_call_count=len(logical_calls),
                provider_request_count=len(request_rows),
                retry_request_count=sum(
                    1 for request, _ in request_rows if request.request_attempt_index > 0
                ),
                failed_request_count=sum(
                    1
                    for request, _ in request_rows
                    if request.status in {"failed", "cancelled", "interrupted"}
                ),
                total_input_tokens=sum(request.input_tokens or 0 for request, _ in request_rows),
                total_output_tokens=sum(request.output_tokens or 0 for request, _ in request_rows),
                total_cached_input_tokens=sum(
                    request.cached_input_tokens or 0 for request, _ in request_rows
                ),
                total_cost_nano_usd=sum(
                    request.total_cost_nano_usd or 0 for request, _ in request_rows
                ),
                p95_duration_ms=_p95(request_durations),
                cost_status_counts=dict(cost_status_counts),
            )

            approval_event_counts = Counter(
                approval.event_type for approval, _ in approval_rows if approval.event_type
            )
            tool_durations = [
                int(tool.total_duration_ms)
                for tool in tool_metrics
                if tool.total_duration_ms is not None
            ]
            approval_waits = [
                int(tool.approval_wait_ms)
                for tool in tool_metrics
                if tool.approval_wait_ms is not None
            ]
            tool_overview = MonitoringToolOverview(
                tool_call_count=len(tool_metrics),
                failed_call_count=sum(
                    1
                    for tool in tool_metrics
                    if tool.status in {"failed", "cancelled", "interrupted"}
                ),
                denied_call_count=sum(
                    1 for tool in tool_metrics if tool.terminal_reason == "denied"
                ),
                waiting_for_approval_count=sum(
                    1 for tool in tool_metrics if tool.status == "waiting_for_approval"
                ),
                approval_requested_count=approval_event_counts.get("requested", 0),
                approval_denied_count=approval_event_counts.get("denied", 0),
                p95_total_duration_ms=_p95(tool_durations),
                p95_approval_wait_ms=_p95(approval_waits),
            )

            model_groups: dict[tuple[str, str], dict[str, int]] = defaultdict(
                lambda: {"request_count": 0, "retry_request_count": 0, "total_cost_nano_usd": 0}
            )
            for request, _ in request_rows:
                key = (request.provider_id or "unknown", request.model_id or "unknown")
                model_groups[key]["request_count"] += 1
                model_groups[key]["retry_request_count"] += int(request.request_attempt_index > 0)
                model_groups[key]["total_cost_nano_usd"] += request.total_cost_nano_usd or 0
            top_models = [
                MonitoringModelSummary(
                    provider_id=provider_id,
                    model_id=model_id,
                    request_count=values["request_count"],
                    retry_request_count=values["retry_request_count"],
                    total_cost_nano_usd=values["total_cost_nano_usd"],
                )
                for (provider_id, model_id), values in sorted(
                    model_groups.items(),
                    key=lambda item: (
                        -item[1]["total_cost_nano_usd"],
                        -item[1]["request_count"],
                        item[0][0],
                        item[0][1],
                    ),
                )[:5]
            ]

            tool_groups: dict[str, dict[str, list[int] | int]] = defaultdict(
                lambda: {
                    "call_count": 0,
                    "failed_call_count": 0,
                    "denied_call_count": 0,
                    "durations": [],
                }
            )
            for tool in tool_metrics:
                group = tool_groups[tool.tool_name]
                group["call_count"] += 1
                group["failed_call_count"] += int(
                    tool.status in {"failed", "cancelled", "interrupted"}
                )
                group["denied_call_count"] += int(tool.terminal_reason == "denied")
                if tool.total_duration_ms is not None:
                    group["durations"].append(int(tool.total_duration_ms))

            top_tools = [
                MonitoringToolSummary(
                    tool_name=tool_name,
                    call_count=int(values["call_count"]),
                    failed_call_count=int(values["failed_call_count"]),
                    denied_call_count=int(values["denied_call_count"]),
                    average_total_duration_ms=(
                        int(sum(values["durations"]) / len(values["durations"]))
                        if values["durations"]
                        else None
                    ),
                )
                for tool_name, values in sorted(
                    tool_groups.items(),
                    key=lambda item: (
                        -int(item[1]["failed_call_count"]),
                        -int(item[1]["call_count"]),
                        item[0],
                    ),
                )[:5]
            ]

            return MonitoringOverviewResponse(
                project_id=project_id,
                window_hours=window_hours,
                health=health,
                llm=llm_overview,
                tools=tool_overview,
                top_models=top_models,
                top_tools=top_tools,
            )

    def list_provider_requests(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
        limit: int = 50,
        provider_id: str | None = None,
        model_id: str | None = None,
        status: str | None = None,
        cost_status: str | None = None,
    ) -> MonitoringProviderRequestListResponse:
        started_after = _window_start(window_hours)
        with self.db.get_session() as db_session:
            query = (
                db_session.query(LLMProviderRequestModel, LLMLogicalCallModel)
                .join(
                    LLMLogicalCallModel,
                    LLMLogicalCallModel.id == LLMProviderRequestModel.logical_call_id,
                )
                .filter(LLMProviderRequestModel.started_at >= started_after)
            )
            if project_id:
                query = query.filter(LLMLogicalCallModel.project_id == project_id)
            if provider_id:
                query = query.filter(LLMProviderRequestModel.provider_id == provider_id)
            if model_id:
                query = query.filter(LLMProviderRequestModel.model_id == model_id)
            if status:
                query = query.filter(LLMProviderRequestModel.status == status)
            if cost_status:
                query = query.filter(LLMProviderRequestModel.cost_status == cost_status)
            total = query.count()
            rows = (
                query.order_by(
                    LLMProviderRequestModel.started_at.desc(),
                    LLMProviderRequestModel.id.desc(),
                )
                .limit(limit)
                .all()
            )
            items = [
                MonitoringProviderRequestItem(
                    id=request.id,
                    logical_call_id=request.logical_call_id,
                    project_id=logical_call.project_id,
                    session_id=logical_call.session_id,
                    run_id=logical_call.run_id,
                    provider_id=request.provider_id,
                    model_id=request.model_id,
                    request_attempt_index=request.request_attempt_index,
                    status=request.status,
                    duration_ms=request.duration_ms,
                    total_cost_nano_usd=request.total_cost_nano_usd,
                    cost_status=request.cost_status,
                    finish_reason=request.finish_reason,
                    started_at=request.started_at,
                    error_message=request.error_message,
                    input_tokens=request.input_tokens,
                    output_tokens=request.output_tokens,
                    cached_input_tokens=request.cached_input_tokens,
                )
                for request, logical_call in rows
            ]

            return MonitoringProviderRequestListResponse(
                project_id=project_id,
                window_hours=window_hours,
                total=total,
                items=items,
            )

    def list_tool_calls(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
        limit: int = 50,
        tool_name: str | None = None,
        status: str | None = None,
        terminal_reason: str | None = None,
        approval_event_type: str | None = None,
    ) -> MonitoringToolCallListResponse:
        started_after = _window_start(window_hours)
        with self.db.get_session() as db_session:
            query = db_session.query(ToolCallMetricModel).filter(
                ToolCallMetricModel.started_at >= started_after
            )
            if project_id:
                query = query.filter(ToolCallMetricModel.project_id == project_id)
            if tool_name:
                query = query.filter(ToolCallMetricModel.tool_name == tool_name)
            if status:
                query = query.filter(ToolCallMetricModel.status == status)
            if terminal_reason:
                query = query.filter(ToolCallMetricModel.terminal_reason == terminal_reason)
            total = query.count()
            tool_metrics = (
                query.order_by(ToolCallMetricModel.started_at.desc(), ToolCallMetricModel.id.desc())
                .limit(limit)
                .all()
            )

            metric_ids = [tool.id for tool in tool_metrics]
            approvals = (
                db_session.query(ToolApprovalEventModel)
                .filter(ToolApprovalEventModel.tool_call_metric_id.in_(metric_ids))
                .order_by(
                    ToolApprovalEventModel.tool_call_metric_id.asc(),
                    ToolApprovalEventModel.occurred_at.desc(),
                )
                .all()
                if metric_ids
                else []
            )
            latest_approval_by_metric: dict[str, ToolApprovalEventModel] = {}
            for approval in approvals:
                latest_approval_by_metric.setdefault(approval.tool_call_metric_id, approval)

            items = [
                MonitoringToolCallItem(
                    id=tool.id,
                    invocation_id=tool.invocation_id,
                    tool_call_id=tool.tool_call_id,
                    project_id=tool.project_id,
                    session_id=tool.session_id,
                    run_id=tool.run_id,
                    tool_name=tool.tool_name,
                    status=tool.status,
                    execution_duration_ms=tool.execution_duration_ms,
                    approval_wait_ms=tool.approval_wait_ms,
                    total_duration_ms=tool.total_duration_ms,
                    terminal_reason=tool.terminal_reason,
                    error_category=tool.error_category,
                    error_message=tool.error_message,
                    latest_approval_event_type=latest_approval_by_metric.get(tool.id).event_type
                    if latest_approval_by_metric.get(tool.id)
                    else None,
                    latest_approval_reason=latest_approval_by_metric.get(tool.id).reason
                    if latest_approval_by_metric.get(tool.id)
                    else None,
                    started_at=tool.started_at,
                    finished_at=tool.finished_at,
                )
                for tool in tool_metrics
                if (
                    approval_event_type is None
                    or (
                        latest_approval_by_metric.get(tool.id) is not None
                        and latest_approval_by_metric[tool.id].event_type == approval_event_type
                    )
                )
            ]

            return MonitoringToolCallListResponse(
                project_id=project_id,
                window_hours=window_hours,
                total=len(items) if approval_event_type else total,
                items=items,
            )

    def get_trends(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
        bucket_hours: int = 1,
    ) -> MonitoringTrendResponse:
        started_after = _window_start(window_hours)
        with self.db.get_session() as db_session:
            request_query = (
                db_session.query(LLMProviderRequestModel, LLMLogicalCallModel)
                .join(
                    LLMLogicalCallModel,
                    LLMLogicalCallModel.id == LLMProviderRequestModel.logical_call_id,
                )
                .filter(LLMProviderRequestModel.started_at >= started_after)
            )
            if project_id:
                request_query = request_query.filter(LLMLogicalCallModel.project_id == project_id)
            request_rows = request_query.all()

            tool_query = db_session.query(ToolCallMetricModel).filter(
                ToolCallMetricModel.started_at >= started_after
            )
            if project_id:
                tool_query = tool_query.filter(ToolCallMetricModel.project_id == project_id)
            tool_metrics = tool_query.all()
            buckets: dict[datetime, MonitoringTrendPoint] = {}

            def ensure_bucket(value: datetime) -> MonitoringTrendPoint:
                bucket = _bucket_start(value, bucket_hours=bucket_hours)
                point = buckets.get(bucket)
                if point is None:
                    point = MonitoringTrendPoint(bucket_start=bucket)
                    buckets[bucket] = point
                return point

            for request, _ in request_rows:
                point = ensure_bucket(request.started_at)
                point.llm_request_count += 1
                point.llm_retry_count += int(request.request_attempt_index > 0)
                point.llm_failed_count += int(
                    request.status in {"failed", "cancelled", "interrupted"}
                )
                point.llm_total_cost_nano_usd += request.total_cost_nano_usd or 0

            for tool in tool_metrics:
                point = ensure_bucket(tool.started_at)
                point.tool_call_count += 1
                point.tool_failed_count += int(
                    tool.status in {"failed", "cancelled", "interrupted"}
                )
                point.tool_denied_count += int(tool.terminal_reason == "denied")

            points = [
                buckets[key]
                for key in sorted(buckets.keys())
            ]

            return MonitoringTrendResponse(
                project_id=project_id,
                window_hours=window_hours,
                bucket_hours=bucket_hours,
                points=points,
            )

    def get_provider_request_detail(self, request_id: str) -> MonitoringProviderRequestDetail | None:
        with self.db.get_session() as db_session:
            row = (
                db_session.query(LLMProviderRequestModel, LLMLogicalCallModel)
                .join(
                    LLMLogicalCallModel,
                    LLMLogicalCallModel.id == LLMProviderRequestModel.logical_call_id,
                )
                .filter(LLMProviderRequestModel.id == request_id)
                .first()
            )
            if row is None:
                return None
            request, logical_call = row
            return MonitoringProviderRequestDetail(
                id=request.id,
                logical_call_id=request.logical_call_id,
                project_id=logical_call.project_id,
                session_id=logical_call.session_id,
                run_id=logical_call.run_id,
                provider_id=request.provider_id,
                model_id=request.model_id,
                request_attempt_index=request.request_attempt_index,
                status=request.status,
                duration_ms=request.duration_ms,
                total_cost_nano_usd=request.total_cost_nano_usd,
                cost_status=request.cost_status,
                finish_reason=request.finish_reason,
                started_at=request.started_at,
                error_message=request.error_message,
                input_tokens=request.input_tokens,
                output_tokens=request.output_tokens,
                cached_input_tokens=request.cached_input_tokens,
                pricing_id=request.pricing_id,
                pricing_match_rule=request.pricing_match_rule,
                pricing_version=request.pricing_version,
                input_price_nano_usd_per_million=request.input_price_nano_usd_per_million,
                output_price_nano_usd_per_million=request.output_price_nano_usd_per_million,
                cached_input_price_nano_usd_per_million=request.cached_input_price_nano_usd_per_million,
                input_cost_nano_usd=request.input_cost_nano_usd,
                output_cost_nano_usd=request.output_cost_nano_usd,
                cached_input_cost_nano_usd=request.cached_input_cost_nano_usd,
            )

    def get_tool_call_detail(self, tool_call_metric_id: str) -> MonitoringToolCallDetail | None:
        with self.db.get_session() as db_session:
            tool = db_session.get(ToolCallMetricModel, tool_call_metric_id)
            if tool is None:
                return None
            approvals = (
                db_session.query(ToolApprovalEventModel)
                .filter(ToolApprovalEventModel.tool_call_metric_id == tool_call_metric_id)
                .order_by(ToolApprovalEventModel.occurred_at.asc())
                .all()
            )
            latest = approvals[-1] if approvals else None
            return MonitoringToolCallDetail(
                id=tool.id,
                invocation_id=tool.invocation_id,
                tool_call_id=tool.tool_call_id,
                project_id=tool.project_id,
                session_id=tool.session_id,
                run_id=tool.run_id,
                tool_name=tool.tool_name,
                status=tool.status,
                execution_duration_ms=tool.execution_duration_ms,
                approval_wait_ms=tool.approval_wait_ms,
                total_duration_ms=tool.total_duration_ms,
                terminal_reason=tool.terminal_reason,
                error_category=tool.error_category,
                error_message=tool.error_message,
                latest_approval_event_type=latest.event_type if latest else None,
                latest_approval_reason=latest.reason if latest else None,
                started_at=tool.started_at,
                finished_at=tool.finished_at,
                approval_events=[
                    MonitoringApprovalEventItem(
                        id=approval.id,
                        approval_id=approval.approval_id,
                        event_type=approval.event_type,
                        actor_type=approval.actor_type,
                        reason=approval.reason,
                        occurred_at=approval.occurred_at,
                    )
                    for approval in approvals
                ],
            )

    def get_anomalies(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
    ) -> MonitoringAnomalyResponse:
        started_after = _window_start(window_hours)
        with self.db.get_session() as db_session:
            request_query = (
                db_session.query(LLMProviderRequestModel, LLMLogicalCallModel)
                .join(
                    LLMLogicalCallModel,
                    LLMLogicalCallModel.id == LLMProviderRequestModel.logical_call_id,
                )
                .filter(LLMProviderRequestModel.started_at >= started_after)
            )
            if project_id:
                request_query = request_query.filter(LLMLogicalCallModel.project_id == project_id)
            request_rows = request_query.all()

            tool_query = db_session.query(ToolCallMetricModel).filter(
                ToolCallMetricModel.started_at >= started_after
            )
            if project_id:
                tool_query = tool_query.filter(ToolCallMetricModel.project_id == project_id)
            tool_metrics = tool_query.all()
            model_groups: dict[tuple[str, str], dict[str, int]] = defaultdict(
                lambda: {
                    "request_count": 0,
                    "retry_request_count": 0,
                    "failed_request_count": 0,
                    "incomplete_cost_count": 0,
                    "total_cost_nano_usd": 0,
                }
            )
            for request, _logical_call in request_rows:
                key = (request.provider_id or "unknown", request.model_id or "unknown")
                group = model_groups[key]
                group["request_count"] += 1
                group["retry_request_count"] += int(request.request_attempt_index > 0)
                group["failed_request_count"] += int(
                    request.status in {"failed", "cancelled", "interrupted"}
                )
                group["incomplete_cost_count"] += int(
                    request.cost_status in {"incomplete", "unpriced", "estimated"}
                )
                group["total_cost_nano_usd"] += request.total_cost_nano_usd or 0

            tool_groups: dict[str, dict[str, list[int] | int]] = defaultdict(
                lambda: {
                    "call_count": 0,
                    "failed_call_count": 0,
                    "denied_call_count": 0,
                    "waiting_for_approval_count": 0,
                    "approval_waits": [],
                }
            )
            for tool in tool_metrics:
                group = tool_groups[tool.tool_name]
                group["call_count"] += 1
                group["failed_call_count"] += int(
                    tool.status in {"failed", "cancelled", "interrupted"}
                )
                group["denied_call_count"] += int(tool.terminal_reason == "denied")
                group["waiting_for_approval_count"] += int(tool.status == "waiting_for_approval")
                if tool.approval_wait_ms is not None:
                    group["approval_waits"].append(int(tool.approval_wait_ms))

            hottest_retry_models = [
                MonitoringModelAnomaly(
                    provider_id=provider_id,
                    model_id=model_id,
                    request_count=values["request_count"],
                    retry_request_count=values["retry_request_count"],
                    failed_request_count=values["failed_request_count"],
                    incomplete_cost_count=values["incomplete_cost_count"],
                    total_cost_nano_usd=values["total_cost_nano_usd"],
                )
                for (provider_id, model_id), values in sorted(
                    model_groups.items(),
                    key=lambda item: (
                        -item[1]["retry_request_count"],
                        -item[1]["failed_request_count"],
                        -item[1]["incomplete_cost_count"],
                        item[0][0],
                        item[0][1],
                    ),
                )
                if values["retry_request_count"] > 0
                or values["failed_request_count"] > 0
                or values["incomplete_cost_count"] > 0
            ][:5]

            noisiest_tools = [
                MonitoringToolAnomaly(
                    tool_name=tool_name,
                    call_count=int(values["call_count"]),
                    failed_call_count=int(values["failed_call_count"]),
                    denied_call_count=int(values["denied_call_count"]),
                    waiting_for_approval_count=int(values["waiting_for_approval_count"]),
                    average_approval_wait_ms=(
                        int(sum(values["approval_waits"]) / len(values["approval_waits"]))
                        if values["approval_waits"]
                        else None
                    ),
                )
                for tool_name, values in sorted(
                    tool_groups.items(),
                    key=lambda item: (
                        -int(item[1]["failed_call_count"]),
                        -int(item[1]["denied_call_count"]),
                        -int(item[1]["waiting_for_approval_count"]),
                        item[0],
                    ),
                )
                if values["failed_call_count"] > 0
                or values["denied_call_count"] > 0
                or values["waiting_for_approval_count"] > 0
            ][:5]

            return MonitoringAnomalyResponse(
                project_id=project_id,
                window_hours=window_hours,
                incomplete_cost_request_count=sum(
                    1
                    for request, _ in request_rows
                    if request.cost_status in {"incomplete", "unpriced", "estimated"}
                ),
                interrupted_request_count=sum(
                    1 for request, _ in request_rows if request.status == "interrupted"
                ),
                waiting_approval_call_count=sum(
                    1 for tool in tool_metrics if tool.status == "waiting_for_approval"
                ),
                hottest_retry_models=hottest_retry_models,
                noisiest_tools=noisiest_tools,
            )

    def get_alert_status(
        self,
        *,
        project_id: str | None = None,
        window_hours: int = 24,
    ) -> MonitoringAlertStatusResponse:
        overview = self.get_overview(project_id=project_id, window_hours=window_hours)
        anomalies = self.get_anomalies(project_id=project_id, window_hours=window_hours)
        settings = self.get_alert_settings()

        checks = [
            (
                "retry_request_count_warn",
                overview.llm.retry_request_count,
                settings.retry_request_count_warn,
                "warning",
                "LLM 重试请求偏高",
                "当前窗口内真实 Provider 重试请求数已超过阈值。",
            ),
            (
                "failed_request_count_warn",
                overview.llm.failed_request_count,
                settings.failed_request_count_warn,
                "warning",
                "LLM 失败请求偏高",
                "当前窗口内失败或中断的 Provider 请求数已超过阈值。",
            ),
            (
                "incomplete_cost_request_count_warn",
                anomalies.incomplete_cost_request_count,
                settings.incomplete_cost_request_count_warn,
                "warning",
                "费用不完整请求偏高",
                "存在较多无法精确定价或 Usage 不完整的请求。",
            ),
            (
                "tool_failed_call_count_warn",
                overview.tools.failed_call_count,
                settings.tool_failed_call_count_warn,
                "warning",
                "工具失败偏高",
                "当前窗口内失败工具调用数已超过阈值。",
            ),
            (
                "approval_denied_count_warn",
                overview.tools.approval_denied_count,
                settings.approval_denied_count_warn,
                "warning",
                "审批拒绝偏高",
                "当前窗口内审批拒绝次数已超过阈值。",
            ),
            (
                "approval_wait_p95_ms_warn",
                overview.tools.p95_approval_wait_ms or 0,
                settings.approval_wait_p95_ms_warn,
                "warning",
                "审批等待过长",
                "工具审批等待的 P95 已超过配置阈值。",
            ),
            (
                "projection_lag_count_warn",
                overview.health.projection_lag_count,
                settings.projection_lag_count_warn,
                "warning",
                "投影滞后",
                "监控投影消费落后于事件写入。",
            ),
            (
                "fallback_backlog_count_warn",
                overview.health.fallback_backlog_count,
                settings.fallback_backlog_count_warn,
                "warning",
                "Fallback backlog 非空",
                "采集器仍有 journal backlog 尚未重放完成。",
            ),
            (
                "memory_queue_depth_critical",
                overview.health.memory_queue_depth,
                settings.memory_queue_depth_critical,
                "critical",
                "内存队列已启用",
                "持久化存储不可用，采集已降级到内存队列。",
            ),
        ]

        active_alerts = [
            MonitoringAlertState(
                key=key,
                severity=severity,
                title=title,
                current_value=current_value,
                threshold_value=threshold_value,
                description=description,
            )
            for key, current_value, threshold_value, severity, title, description in checks
            if current_value >= threshold_value and threshold_value > 0
        ]

        return MonitoringAlertStatusResponse(
            settings=settings,
            active_alerts=active_alerts,
        )


monitoring_service = MonitoringService()
