export type MonitoringHealthStatus = 'healthy' | 'degraded' | 'critical'

export interface MonitoringHealth {
  status: MonitoringHealthStatus
  last_event_recorded_at?: string | null
  last_projection_at?: string | null
  projection_lag_count: number
  fallback_backlog_count: number
  memory_queue_depth: number
  dropped_metrics_count: number
  last_error_code?: string | null
  last_error_at?: string | null
}

export interface MonitoringLLMOverview {
  logical_call_count: number
  provider_request_count: number
  retry_request_count: number
  failed_request_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cached_input_tokens: number
  total_cost_nano_usd: number
  p95_duration_ms?: number | null
  cost_status_counts: Record<string, number>
}

export interface MonitoringToolOverview {
  tool_call_count: number
  failed_call_count: number
  denied_call_count: number
  waiting_for_approval_count: number
  approval_requested_count: number
  approval_denied_count: number
  p95_total_duration_ms?: number | null
  p95_approval_wait_ms?: number | null
}

export interface MonitoringModelSummary {
  provider_id: string
  model_id: string
  request_count: number
  retry_request_count: number
  total_cost_nano_usd: number
}

export interface MonitoringToolSummary {
  tool_name: string
  call_count: number
  failed_call_count: number
  denied_call_count: number
  average_total_duration_ms?: number | null
}

export interface MonitoringOverviewResponse {
  project_id?: string | null
  window_hours: number
  health: MonitoringHealth
  llm: MonitoringLLMOverview
  tools: MonitoringToolOverview
  top_models: MonitoringModelSummary[]
  top_tools: MonitoringToolSummary[]
}

export interface MonitoringProviderRequestItem {
  id: string
  logical_call_id: string
  project_id?: string | null
  session_id?: string | null
  run_id?: string | null
  provider_id?: string | null
  model_id?: string | null
  request_attempt_index: number
  status: string
  duration_ms?: number | null
  total_cost_nano_usd?: number | null
  cost_status: string
  finish_reason?: string | null
  started_at: string
  error_message?: string | null
  input_tokens?: number | null
  output_tokens?: number | null
  cached_input_tokens?: number | null
}

export interface MonitoringProviderRequestListResponse {
  project_id?: string | null
  window_hours: number
  total: number
  items: MonitoringProviderRequestItem[]
}

export interface MonitoringToolCallItem {
  id: string
  invocation_id: string
  tool_call_id: string
  project_id?: string | null
  session_id?: string | null
  run_id?: string | null
  tool_name: string
  status: string
  execution_duration_ms?: number | null
  approval_wait_ms?: number | null
  total_duration_ms?: number | null
  terminal_reason?: string | null
  error_category?: string | null
  error_message?: string | null
  latest_approval_event_type?: string | null
  latest_approval_reason?: string | null
  started_at: string
  finished_at?: string | null
}

export interface MonitoringToolCallListResponse {
  project_id?: string | null
  window_hours: number
  total: number
  items: MonitoringToolCallItem[]
}

export interface MonitoringTrendPoint {
  bucket_start: string
  llm_request_count: number
  llm_failed_count: number
  llm_retry_count: number
  llm_total_cost_nano_usd: number
  tool_call_count: number
  tool_failed_count: number
  tool_denied_count: number
}

export interface MonitoringTrendResponse {
  project_id?: string | null
  window_hours: number
  bucket_hours: number
  points: MonitoringTrendPoint[]
}

export interface MonitoringApprovalEventItem {
  id: string
  approval_id: string
  event_type: string
  actor_type?: string | null
  reason?: string | null
  occurred_at: string
}

export interface MonitoringProviderRequestDetail extends MonitoringProviderRequestItem {
  pricing_id?: string | null
  pricing_match_rule?: string | null
  pricing_version?: string | null
  input_price_nano_usd_per_million?: number | null
  output_price_nano_usd_per_million?: number | null
  cached_input_price_nano_usd_per_million?: number | null
  input_cost_nano_usd?: number | null
  output_cost_nano_usd?: number | null
  cached_input_cost_nano_usd?: number | null
}

export interface MonitoringToolCallDetail extends MonitoringToolCallItem {
  approval_events: MonitoringApprovalEventItem[]
}

export interface MonitoringModelAnomaly {
  provider_id: string
  model_id: string
  request_count: number
  retry_request_count: number
  failed_request_count: number
  incomplete_cost_count: number
  total_cost_nano_usd: number
}

export interface MonitoringToolAnomaly {
  tool_name: string
  call_count: number
  failed_call_count: number
  denied_call_count: number
  waiting_for_approval_count: number
  average_approval_wait_ms?: number | null
}

export interface MonitoringAnomalyResponse {
  project_id?: string | null
  window_hours: number
  incomplete_cost_request_count: number
  interrupted_request_count: number
  waiting_approval_call_count: number
  hottest_retry_models: MonitoringModelAnomaly[]
  noisiest_tools: MonitoringToolAnomaly[]
}

export interface MonitoringAlertSettings {
  enable_in_app_notifications: boolean
  poll_interval_seconds: number
  enable_webhook_notifications: boolean
  webhook_url?: string | null
  webhook_min_severity: string
  webhook_cooldown_seconds: number
  retry_request_count_warn: number
  failed_request_count_warn: number
  incomplete_cost_request_count_warn: number
  tool_failed_call_count_warn: number
  approval_denied_count_warn: number
  approval_wait_p95_ms_warn: number
  projection_lag_count_warn: number
  fallback_backlog_count_warn: number
  memory_queue_depth_critical: number
}

export interface MonitoringAlertState {
  key: string
  severity: string
  title: string
  current_value: number
  threshold_value: number
  description: string
}

export interface MonitoringAlertStatusResponse {
  settings: MonitoringAlertSettings
  active_alerts: MonitoringAlertState[]
}
