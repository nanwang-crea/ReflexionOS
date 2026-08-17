/**
 * 文件功能：会话相关的后端 API 封装
 * 文件描述：提供会话的增删改查（创建、更新、重置、删除、按项目列表查询）接口，
 *           并负责前端 camelCase 载荷与后端 snake_case 载荷之间的双向转换。
 * 核心逻辑：请求前用 toSessionPayload 把前端字段名转换为后端字段名（并过滤掉 undefined 字段）；
 *           响应后用 toConversationSession 把后端 DTO 转换为前端使用的会话对象。
 */
import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type {
  ConversationSession,
  ConversationSessionDto,
} from '@/types/conversation'
import { toConversationSession } from '@/types/conversation'
import type {
  SessionCreatePayload,
  SessionUpdatePayload,
} from '@/types/workspace'

/**
 * 函数名：toSessionPayload
 * 入参：
 *   - data (SessionCreatePayload | SessionUpdatePayload): 前端形式的会话创建/更新载荷（camelCase 字段）
 * 功能：将前端字段名转换为后端接口期望的字段名（snake_case），并剔除值为 undefined 的字段
 * 运行逻辑：手动映射 title/preferredProviderId/preferredModelId 三个字段，再用 Object.fromEntries + filter 过滤掉未提供的字段
 * 出参：Record<string, unknown> - 可直接作为请求体发送给后端的对象
 */
function toSessionPayload(data: SessionCreatePayload | SessionUpdatePayload) {
  return Object.fromEntries(
    Object.entries({
      title: data.title,
      preferred_provider_id: data.preferredProviderId,
      preferred_model_id: data.preferredModelId,
    }).filter(([, value]) => value !== undefined)
  )
}

/**
 * 函数名：mapSessionResponse
 * 入参：
 *   - request (Promise<AxiosResponse<ConversationSessionDto>>): 返回单个会话 DTO 的请求 Promise
 * 功能：等待请求完成后，将响应体中的会话 DTO 转换为前端使用的 ConversationSession 对象
 * 运行逻辑：await 请求结果，保留原始 response 的其他字段，仅替换 data 字段
 * 出参：Promise<AxiosResponse<ConversationSession>> - data 字段已转换为前端类型的响应对象
 */
async function mapSessionResponse(
  request: Promise<AxiosResponse<ConversationSessionDto>>
): Promise<AxiosResponse<ConversationSession>> {
  const response = await request
  return {
    ...response,
    data: toConversationSession(response.data),
  }
}

/**
 * 函数名：mapSessionListResponse
 * 入参：
 *   - request (Promise<AxiosResponse<ConversationSessionDto[]>>): 返回会话 DTO 列表的请求 Promise
 * 功能：等待请求完成后，将响应体中的会话 DTO 数组逐一转换为前端使用的 ConversationSession 数组
 * 运行逻辑：await 请求结果，对 data 数组中每一项调用 toConversationSession 做转换
 * 出参：Promise<AxiosResponse<ConversationSession[]>> - data 字段已转换为前端类型数组的响应对象
 */
async function mapSessionListResponse(
  request: Promise<AxiosResponse<ConversationSessionDto[]>>
): Promise<AxiosResponse<ConversationSession[]>> {
  const response = await request
  return {
    ...response,
    data: response.data.map(toConversationSession),
  }
}

// 会话相关接口集合：列表查询、创建、更新、重置、删除
export const sessionApi = {
  listProjectSessions: (projectId: string) =>
    mapSessionListResponse(apiClient.get<ConversationSessionDto[]>(`/api/projects/${projectId}/sessions`)),
  createSession: (projectId: string, data: SessionCreatePayload) =>
    mapSessionResponse(
      apiClient.post<ConversationSessionDto>(
        `/api/projects/${projectId}/sessions`,
        toSessionPayload(data)
      )
    ),
  updateSession: (sessionId: string, data: SessionUpdatePayload) =>
    mapSessionResponse(apiClient.patch<ConversationSessionDto>(`/api/sessions/${sessionId}`, toSessionPayload(data))),
  resetSession: (sessionId: string) =>
    mapSessionResponse(apiClient.post<ConversationSessionDto>(`/api/sessions/${sessionId}/reset`)),
  deleteSession: (sessionId: string) =>
    apiClient.delete(`/api/sessions/${sessionId}`),
}
