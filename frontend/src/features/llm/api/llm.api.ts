import type { DefaultLLMSelection, ProviderConnectionTestRequest, ProviderInstance } from '@/types/llm'
import { apiClient } from '@/services/apiClient'

export const llmApi = {
  getProviders: () => apiClient.get<ProviderInstance[]>('/api/llm/providers'),
  createProvider: (data: ProviderInstance) => apiClient.post<ProviderInstance>('/api/llm/providers', data),
  updateProvider: (providerId: string, data: ProviderInstance) =>
    apiClient.put<ProviderInstance>(`/api/llm/providers/${providerId}`, data),
  deleteProvider: (providerId: string) => apiClient.delete(`/api/llm/providers/${providerId}`),
  testProvider: (data: ProviderConnectionTestRequest) =>
    apiClient.post('/api/llm/providers/test', data),
  getDefaultSelection: () => apiClient.get<DefaultLLMSelection>('/api/llm/default'),
  setDefaultSelection: (data: { provider_id: string; model_id: string }) =>
    apiClient.put<DefaultLLMSelection>('/api/llm/default', data),
}
