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

export const projectApi = {
  list: () => apiClient.get('/api/projects'),
  get: (id: string) => apiClient.get(`/api/projects/${id}`),
  create: (data: { name: string; path: string; language?: string }) =>
    apiClient.post('/api/projects', data),
  delete: (id: string) => apiClient.delete(`/api/projects/${id}`),
  getStructure: (id: string) => apiClient.get(`/api/projects/${id}/structure`),
}

export const agentApi = {
  execute: (data: { project_id: string; task: string; provider_id?: string; model_id?: string }) =>
    apiClient.post('/api/agent/execute', data),
  getStatus: (executionId: string) =>
    apiClient.get(`/api/agent/status/${executionId}`),
  getHistory: (projectId: string) =>
    apiClient.get(`/api/agent/history/${projectId}`),
  cancel: (executionId: string) =>
    apiClient.post(`/api/agent/cancel/${executionId}`),
  stop: (executionId: string) =>
    apiClient.post(`/api/agent/stop/${executionId}`),
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
