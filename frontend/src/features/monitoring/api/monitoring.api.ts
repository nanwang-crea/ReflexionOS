import { apiClient } from '@/services/apiClient'
import type {
  MonitoringAnomalyResponse,
  MonitoringAlertSettings,
  MonitoringAlertStatusResponse,
  MonitoringHealth,
  MonitoringOverviewResponse,
  MonitoringProviderRequestDetail,
  MonitoringProviderRequestListResponse,
  MonitoringToolCallDetail,
  MonitoringToolCallListResponse,
  MonitoringTrendResponse,
} from '@/types/monitoring'

interface MonitoringQuery {
  project_id?: string
  window_hours?: number
  limit?: number
  provider_id?: string
  model_id?: string
  tool_name?: string
  status?: string
  cost_status?: string
  terminal_reason?: string
  approval_event_type?: string
}

export const monitoringApi = {
  health: () => apiClient.get<MonitoringHealth>('/api/monitoring/health'),
  alerts: (params?: MonitoringQuery) =>
    apiClient.get<MonitoringAlertStatusResponse>('/api/monitoring/alerts', { params }),
  updateAlerts: (data: MonitoringAlertSettings) =>
    apiClient.put<MonitoringAlertSettings>('/api/monitoring/alerts', data),
  overview: (params: MonitoringQuery) =>
    apiClient.get<MonitoringOverviewResponse>('/api/monitoring/overview', { params }),
  anomalies: (params: MonitoringQuery) =>
    apiClient.get<MonitoringAnomalyResponse>('/api/monitoring/anomalies', { params }),
  trends: (params: MonitoringQuery & { bucket_hours?: number }) =>
    apiClient.get<MonitoringTrendResponse>('/api/monitoring/trends', { params }),
  listProviderRequests: (params: MonitoringQuery) =>
    apiClient.get<MonitoringProviderRequestListResponse>('/api/monitoring/llm/requests', { params }),
  getProviderRequestDetail: (requestId: string) =>
    apiClient.get<MonitoringProviderRequestDetail>(`/api/monitoring/llm/requests/${requestId}`),
  listToolCalls: (params: MonitoringQuery) =>
    apiClient.get<MonitoringToolCallListResponse>('/api/monitoring/tools/calls', { params }),
  getToolCallDetail: (toolCallMetricId: string) =>
    apiClient.get<MonitoringToolCallDetail>(`/api/monitoring/tools/calls/${toolCallMetricId}`),
}
