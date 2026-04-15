import axios from 'axios'

const API_BASE_URL = 'http://127.0.0.1:8000'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
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
  execute: (data: { project_id: string; task: string }) =>
    apiClient.post('/api/agent/execute', data),
  getStatus: (executionId: string) =>
    apiClient.get(`/api/agent/status/${executionId}`),
  getHistory: (projectId: string) =>
    apiClient.get(`/api/agent/history/${projectId}`),
}

export const llmApi = {
  getConfig: () => apiClient.get('/api/llm/config'),
  setConfig: (data: { provider: string; model: string; api_key?: string; base_url?: string }) =>
    apiClient.post('/api/llm/config', data),
  getProviders: () => apiClient.get('/api/llm/providers'),
}
