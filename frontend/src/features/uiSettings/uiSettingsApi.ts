import { apiClient } from '@/services/apiClient'

interface UISettingsResponse {
  show_continuation_notices: boolean
}

export const uiSettingsApi = {
  get: () => apiClient.get<UISettingsResponse>('/api/ui-settings'),
  update: (data: UISettingsResponse) => apiClient.put<UISettingsResponse>('/api/ui-settings', data),
}
