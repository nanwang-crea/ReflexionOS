/**
 * 文件功能：会话业务动作（session actions）
 * 文件描述：会话相关的具体业务操作（创建、更新、重命名、写偏好、重置、删除、拉取列表），
 *           负责调用 session.api.ts 发起请求，并将结果同步写入 session.store.ts 中的缓存。
 * 核心逻辑：每个写操作在拿到后端返回的最新会话数据后，先 upsert 到本地缓存做乐观更新，
 *           再重新拉取整份项目会话列表（ensureProjectSessionsLoaded）以保证与后端最终一致。
 */
import { sessionApi } from './api/session.api'
import { useSessionStore } from './stores/session.store'
import type { SessionCreatePayload, SessionSummary, SessionUpdatePayload } from '@/types/workspace'

/**
 * 函数名：ensureProjectSessionsLoaded
 * 入参：
 *   - projectId (string): 项目 ID
 * 功能：拉取指定项目下的全部会话列表，并整体写入本地 store 缓存
 * 运行逻辑：调用 sessionApi.listProjectSessions 请求列表，再调用 setProjectSessions 覆盖写入缓存
 * 出参：Promise<void>
 */
export async function ensureProjectSessionsLoaded(projectId: string): Promise<void> {
  const response = await sessionApi.listProjectSessions(projectId)
  useSessionStore.getState().setProjectSessions(projectId, response.data)
}

/**
 * 函数名：createSession
 * 入参：
 *   - projectId (string): 所属项目 ID
 *   - payload (SessionCreatePayload): 创建会话的可选参数（标题、偏好供应商/模型等），默认为空对象
 * 功能：在指定项目下创建新会话
 * 运行逻辑：调用 sessionApi.createSession 创建会话 -> upsert 到本地缓存做乐观更新 -> 重新拉取项目会话列表保证一致
 * 出参：Promise<SessionSummary> - 新建的会话摘要
 */
export async function createSession(
  projectId: string,
  payload: SessionCreatePayload = {}
): Promise<SessionSummary> {
  const response = await sessionApi.createSession(projectId, payload)
  useSessionStore.getState().upsertSession(projectId, response.data)
  await ensureProjectSessionsLoaded(projectId)
  return response.data
}

/**
 * 函数名：updateSession
 * 入参：
 *   - sessionId (string): 目标会话 ID
 *   - payload (SessionUpdatePayload): 待更新的字段（标题、偏好供应商/模型等）
 * 功能：更新指定会话的字段
 * 运行逻辑：调用 sessionApi.updateSession 提交更新 -> upsert 到本地缓存 -> 重新拉取该会话所属项目的会话列表
 * 出参：Promise<SessionSummary> - 更新后的会话摘要
 */
export async function updateSession(
  sessionId: string,
  payload: SessionUpdatePayload
): Promise<SessionSummary> {
  const response = await sessionApi.updateSession(sessionId, payload)
  useSessionStore.getState().upsertSession(response.data.projectId, response.data)
  await ensureProjectSessionsLoaded(response.data.projectId)
  return response.data
}

/**
 * 函数名：writeSessionPreferences
 * 入参：
 *   - sessionId (string): 目标会话 ID
 *   - payload (Pick<SessionUpdatePayload, 'preferredProviderId' | 'preferredModelId'>): 仅包含偏好供应商/模型的窄载荷
 * 功能：只写入会话的偏好供应商与偏好模型，语义上比通用 updateSession 更收窄、更明确
 * 运行逻辑：直接转发给 updateSession 执行
 * 出参：Promise<SessionSummary> - 更新后的会话摘要
 */
export async function writeSessionPreferences(
  sessionId: string,
  payload: Pick<SessionUpdatePayload, 'preferredProviderId' | 'preferredModelId'>
): Promise<SessionSummary> {
  return updateSession(sessionId, payload)
}

/**
 * 函数名：renameSession
 * 入参：
 *   - sessionId (string): 目标会话 ID
 *   - title (string): 新标题
 * 功能：重命名指定会话
 * 运行逻辑：转发给 updateSession，仅传入 title 字段
 * 出参：Promise<SessionSummary> - 更新后的会话摘要
 */
export async function renameSession(sessionId: string, title: string): Promise<SessionSummary> {
  return updateSession(sessionId, { title })
}

/**
 * 函数名：resetSession
 * 入参：
 *   - sessionId (string): 目标会话 ID
 * 功能：重置指定会话（清空事件计数与活跃 turn 等运行态数据）
 * 运行逻辑：调用 sessionApi.resetSession 执行重置 -> 用返回的最新会话数据 upsert 到本地缓存
 *          （注意：这里不重新拉取整份列表，直接用重置接口的返回值刷新缓存即可）
 * 出参：Promise<SessionSummary> - 重置后的会话摘要
 */
export async function resetSession(sessionId: string): Promise<SessionSummary> {
  const response = await sessionApi.resetSession(sessionId)
  useSessionStore.getState().upsertSession(response.data.projectId, response.data)
  return response.data
}

/**
 * 函数名：deleteSession
 * 入参：
 *   - projectId (string): 所属项目 ID
 *   - sessionId (string): 待删除的会话 ID
 * 功能：删除指定会话
 * 运行逻辑：调用 sessionApi.deleteSession 执行删除 -> 从本地缓存移除该会话 -> 重新拉取项目会话列表保证一致
 * 出参：Promise<void>
 */
export async function deleteSession(projectId: string, sessionId: string): Promise<void> {
  await sessionApi.deleteSession(sessionId)
  useSessionStore.getState().removeSession(projectId, sessionId)
  await ensureProjectSessionsLoaded(projectId)
}
