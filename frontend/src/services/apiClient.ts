import axios from 'axios'
import type {
  DefaultLLMSelection,
  ProviderConnectionTestRequest,
  ProviderInstance,
} from '@/types/llm'
import { getApiBaseUrl } from './runtimeConfig'

export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.data) {
      const data = error.response.data as Record<string, unknown>
      if (typeof data.message === 'string' && typeof data.code === 'string') {
        error.response.data = {
          ...data,
          detail: data.message,
        }
      }
    }
    return Promise.reject(error)
  }
)

export const projectApi = {
  list: () => apiClient.get('/api/projects'),
  create: (data: { name: string; path: string; language?: string }) =>
    apiClient.post('/api/projects', data),
  delete: (id: string) => apiClient.delete(`/api/projects/${id}`),
}

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

export const skillApi = {
  list: () => apiClient.get('/api/skills'),
}
