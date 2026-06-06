import { apiClient } from '@/services/apiClient'

interface UISettingsResponse {
  show_continuation_notices: boolean
  show_process_expanded: boolean
  auto_collapse_process: boolean
}

export const uiSettingsApi = {
  get: () => apiClient.get<UISettingsResponse>('/api/ui-settings'),
  update: (data: UISettingsResponse) => apiClient.put<UISettingsResponse>('/api/ui-settings', data),
}
