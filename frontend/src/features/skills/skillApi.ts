import { apiClient } from '@/services/apiClient'

export const skillApi = {
  list: () => apiClient.get('/api/skills'),
}
