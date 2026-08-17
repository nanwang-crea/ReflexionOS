/**
 * 文件功能：LLM 供应商/模型配置相关的后端接口封装
 * 文件描述：提供供应商的增删改查、连接测试、以及默认模型选择的读取与设置接口。
 * 核心逻辑：纯粹的接口地址与方法封装，不做数据转换，直接透传 apiClient 的响应。
 */
import type { DefaultLLMSelection, ProviderConnectionTestRequest, ProviderInstance } from '@/types/llm'
import { apiClient } from '@/services/apiClient'

// LLM 接口集合：供应商 CRUD、连接测试、默认模型选择的获取与设置
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
