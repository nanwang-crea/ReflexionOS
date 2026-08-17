/**
 * 文件功能：会话列表状态管理（zustand store）
 * 文件描述：按项目 ID 缓存各项目下的会话摘要列表，提供整表写入、单条 upsert、删除等操作。
 * 核心逻辑：以 sessionsByProjectId（projectId -> SessionSummary[]）为唯一数据源，
 *           upsertSession 存在则原地替换、不存在则插到列表头部（最新会话在前）。
 */
import { create } from 'zustand'
import type { SessionSummary } from '@/types/workspace'

interface SessionState {
  sessionsByProjectId: Record<string, SessionSummary[]>
  setProjectSessions: (projectId: string, sessions: SessionSummary[]) => void
  upsertSession: (projectId: string, session: SessionSummary) => void
  removeSession: (projectId: string, sessionId: string) => void
}

/**
 * 函数名：createSessionStore
 * 入参：无
 * 功能：创建一个独立的会话列表 zustand store 实例（便于测试隔离，避免共享单例状态）
 * 运行逻辑：
 *   1. setProjectSessions：整体替换某项目下的会话列表
 *   2. upsertSession：按会话 id 查找，命中则原地替换，未命中则插入列表头部
 *   3. removeSession：按会话 id 从列表中过滤掉指定会话
 * 出参：zustand store 实例，暴露 sessionsByProjectId 状态及上述三个操作方法
 */
export const createSessionStore = () => create<SessionState>((set) => ({
  sessionsByProjectId: {},
  setProjectSessions: (projectId, sessions) => set((state) => ({
    sessionsByProjectId: {
      ...state.sessionsByProjectId,
      [projectId]: sessions,
    },
  })),
  upsertSession: (projectId, session) => set((state) => {
    const sessions = state.sessionsByProjectId[projectId] || []
    const existingIndex = sessions.findIndex((entry) => entry.id === session.id)

    if (existingIndex === -1) {
      return {
        sessionsByProjectId: {
          ...state.sessionsByProjectId,
          [projectId]: [session, ...sessions],
        },
      }
    }

    return {
      sessionsByProjectId: {
        ...state.sessionsByProjectId,
        [projectId]: sessions.map((entry) => (entry.id === session.id ? session : entry)),
      },
    }
  }),
  removeSession: (projectId, sessionId) => set((state) => ({
    sessionsByProjectId: {
      ...state.sessionsByProjectId,
      [projectId]: (state.sessionsByProjectId[projectId] || []).filter((session) => session.id !== sessionId),
    },
  })),
}))

// 全局共享的会话列表 store 单例，供应用内组件统一使用
export const useSessionStore = createSessionStore()

export type { SessionState }
