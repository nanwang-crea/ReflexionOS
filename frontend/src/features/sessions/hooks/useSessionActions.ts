/**
 * 文件功能：会话操作 Hook
 * 文件描述：封装创建/重命名/删除会话、刷新项目会话列表等操作，供组件层调用；
 *           创建会话成功后会自动将其设为当前会话（写入 workspace store）。
 * 核心逻辑：底层调用 session.actions.ts 中的纯函数动作，用 useCallback 包裹以保持引用稳定。
 */
import { useCallback } from 'react'
import {
  createSession as createSessionAction,
  deleteSession as deleteSessionAction,
  ensureProjectSessionsLoaded,
  renameSession as renameSessionAction,
} from '@/features/sessions/session.actions'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
import type { SessionCreatePayload, SessionSummary } from '@/types/workspace'

/**
 * 函数名：useSessionActions
 * 入参：无
 * 功能：提供一组与会话相关的操作方法（创建、重命名、删除、刷新列表）
 * 运行逻辑：从 workspace store 中取出 setCurrentSessionId，创建会话成功后调用它将新会话设为当前会话；
 *          其余操作直接转发给 session.actions.ts 中的对应动作函数
 * 出参：{ createSession, renameSession, deleteSession, refreshProjectSessions } - 会话操作方法集合
 */
export function useSessionActions() {
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)

  /**
   * 函数名：createSession（内部闭包）
   * 入参：
   *   - projectId (string): 所属项目 ID
   *   - payload (SessionCreatePayload): 创建会话的可选参数（如偏好的模型/供应商），默认为空对象
   * 功能：创建新会话并将其设为当前选中会话
   * 运行逻辑：调用 createSessionAction 创建会话，成功后通过 setCurrentSessionId 更新 workspace store
   * 出参：Promise<SessionSummary> - 新建的会话摘要
   */
  const createSession = useCallback(async (
    projectId: string,
    payload: SessionCreatePayload = {}
  ): Promise<SessionSummary> => {
    const session = await createSessionAction(projectId, payload)
    setCurrentSessionId(session.id)
    return session
  }, [setCurrentSessionId])

  /**
   * 函数名：renameSession（内部闭包）
   * 入参：
   *   - sessionId (string): 目标会话 ID
   *   - title (string): 新标题
   * 功能：重命名指定会话
   * 运行逻辑：直接转发给 renameSessionAction 执行
   * 出参：Promise<SessionSummary> - 更新后的会话摘要
   */
  const renameSession = useCallback(async (sessionId: string, title: string): Promise<SessionSummary> => {
    return renameSessionAction(sessionId, title)
  }, [])

  /**
   * 函数名：deleteSession（内部闭包）
   * 入参：
   *   - projectId (string): 所属项目 ID
   *   - sessionId (string): 待删除的会话 ID
   * 功能：删除指定会话
   * 运行逻辑：转发给 deleteSessionAction 执行删除
   * 出参：Promise<void>
   */
  const deleteSession = useCallback(async (projectId: string, sessionId: string) => {
    await deleteSessionAction(projectId, sessionId)
  }, [])

  /**
   * 函数名：refreshProjectSessions（内部闭包）
   * 入参：
   *   - projectId (string): 项目 ID
   * 功能：刷新（确保已加载）指定项目下的会话列表
   * 运行逻辑：转发给 ensureProjectSessionsLoaded 执行拉取与写入 store
   * 出参：Promise<void>
   */
  const refreshProjectSessions = useCallback(async (projectId: string) => {
    await ensureProjectSessionsLoaded(projectId)
  }, [])

  return {
    createSession,
    renameSession,
    deleteSession,
    refreshProjectSessions,
  }
}
