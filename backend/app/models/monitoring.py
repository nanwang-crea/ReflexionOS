from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import MonitoringAlertSettings
from app.models.observability import ObservabilityHealth


class MonitoringLLMOverview(BaseModel):
    logical_call_count: int = 0
    provider_request_count: int = 0
    retry_request_count: int = 0
    failed_request_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_input_tokens: int = 0
    total_cost_nano_usd: int = 0
    p95_duration_ms: int | None = None
    cost_status_counts: dict[str, int] = Field(default_factory=dict)


class MonitoringToolOverview(BaseModel):
    tool_call_count: int = 0
    failed_call_count: int = 0
    denied_call_count: int = 0
    waiting_for_approval_count: int = 0
    approval_requested_count: int = 0
    approval_denied_count: int = 0
    p95_total_duration_ms: int | None = None
    p95_approval_wait_ms: int | None = None


class MonitoringModelSummary(BaseModel):
    provider_id: str
    model_id: str
    request_count: int
    retry_request_count: int
    total_cost_nano_usd: int


class MonitoringToolSummary(BaseModel):
    tool_name: str
    call_count: int
    failed_call_count: int
    denied_call_count: int
    average_total_duration_ms: int | None = None


class MonitoringOverviewResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    window_hours: int
    health: ObservabilityHealth
    llm: MonitoringLLMOverview
    tools: MonitoringToolOverview
    top_models: list[MonitoringModelSummary] = Field(default_factory=list)
    top_tools: list[MonitoringToolSummary] = Field(default_factory=list)


class MonitoringProviderRequestItem(BaseModel):
    id: str
    logical_call_id: str
    project_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    request_attempt_index: int
    status: str
    duration_ms: int | None = None
    total_cost_nano_usd: int | None = None
    cost_status: str
    finish_reason: str | None = None
    started_at: datetime
    error_message: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None


class MonitoringProviderRequestListResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    window_hours: int
    total: int
    items: list[MonitoringProviderRequestItem]


class MonitoringToolCallItem(BaseModel):
    id: str
    invocation_id: str
    tool_call_id: str
    project_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    tool_name: str
    status: str
    execution_duration_ms: int | None = None
    approval_wait_ms: int | None = None
    total_duration_ms: int | None = None
    terminal_reason: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    latest_approval_event_type: str | None = None
    latest_approval_reason: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class MonitoringToolCallListResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    window_hours: int
    total: int
    items: list[MonitoringToolCallItem]


class MonitoringTrendPoint(BaseModel):
    bucket_start: datetime
    llm_request_count: int = 0
    llm_failed_count: int = 0
    llm_retry_count: int = 0
    llm_total_cost_nano_usd: int = 0
    tool_call_count: int = 0
    tool_failed_count: int = 0
    tool_denied_count: int = 0


class MonitoringTrendResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    window_hours: int
    bucket_hours: int
    points: list[MonitoringTrendPoint]


class MonitoringApprovalEventItem(BaseModel):
    id: str
    approval_id: str
    event_type: str
    actor_type: str | None = None
    reason: str | None = None
    occurred_at: datetime


class MonitoringProviderRequestDetail(MonitoringProviderRequestItem):
    pricing_id: str | None = None
    pricing_match_rule: str | None = None
    pricing_version: str | None = None
    input_price_nano_usd_per_million: int | None = None
    output_price_nano_usd_per_million: int | None = None
    cached_input_price_nano_usd_per_million: int | None = None
    input_cost_nano_usd: int | None = None
    output_cost_nano_usd: int | None = None
    cached_input_cost_nano_usd: int | None = None


class MonitoringToolCallDetail(MonitoringToolCallItem):
    approval_events: list[MonitoringApprovalEventItem] = Field(default_factory=list)


class MonitoringModelAnomaly(BaseModel):
    provider_id: str
    model_id: str
    request_count: int
    retry_request_count: int
    failed_request_count: int
    incomplete_cost_count: int
    total_cost_nano_usd: int


class MonitoringToolAnomaly(BaseModel):
    tool_name: str
    call_count: int
    failed_call_count: int
    denied_call_count: int
    waiting_for_approval_count: int
    average_approval_wait_ms: int | None = None


class MonitoringAnomalyResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    window_hours: int
    incomplete_cost_request_count: int = 0
    interrupted_request_count: int = 0
    waiting_approval_call_count: int = 0
    hottest_retry_models: list[MonitoringModelAnomaly] = Field(default_factory=list)
    noisiest_tools: list[MonitoringToolAnomaly] = Field(default_factory=list)


class MonitoringAlertState(BaseModel):
    key: str
    severity: str
    title: str
    current_value: int
    threshold_value: int
    description: str


class MonitoringAlertStatusResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    settings: MonitoringAlertSettings
    active_alerts: list[MonitoringAlertState] = Field(default_factory=list)
