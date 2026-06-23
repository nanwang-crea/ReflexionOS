import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

// 会话级同步健康状态：
// - 'degraded'：后台连接重连耗尽 / 被降级，已不再实时同步，需要切回时强制补拉。
//   注意这只表示“连接层异常”，不代表 run 业务失败——run 状态仍以快照为准。
// 健康（正常实时同步）用“缺省/不存在”表示，避免无谓写入。
export type SessionSyncHealth = 'degraded'

export interface WorkspaceUiState {
  currentSessionId: string | null
  expandedProjectIds: string[]
  expandedSessionProjectIds: string[]
  searchQuery: string
  searchOpen: boolean
  // 每个会话“最后看到的事件序号”，用于派生未读活动；与 UI 状态一起持久化，刷新后可恢复未读基线。
  lastSeenEventSeqBySessionId: Record<string, number>
  // 每个会话的连接同步健康状态。仅记录异常（degraded）；正常不写入。
  sessionSyncHealthBySessionId: Record<string, SessionSyncHealth>
}

interface WorkspaceState extends WorkspaceUiState {

  setCurrentSessionId: (sessionId: string | null) => void
  toggleProjectExpanded: (projectId: string) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  toggleProjectShowAll: (projectId: string) => void
  setSearchQuery: (query: string) => void
  setSearchOpen: (open: boolean) => void
  // 记录某会话已读到的事件序号（用户进入会话并完成最新快照同步后调用）。
  markSessionSeen: (sessionId: string, lastEventSeq: number) => void
  // 标记某会话连接同步异常（后台重连耗尽 / 被降级），切回时据此强制补拉。
  markSessionSyncDegraded: (sessionId: string) => void
  // 清除某会话的同步异常标记（重连成功 / 切回补拉成功后调用）。
  clearSessionSyncHealth: (sessionId: string) => void
}

function partializeWorkspaceUiState(state: WorkspaceState): WorkspaceUiState {
  return {
    currentSessionId: state.currentSessionId,
    expandedProjectIds: state.expandedProjectIds,
    expandedSessionProjectIds: state.expandedSessionProjectIds,
    searchQuery: state.searchQuery,
    searchOpen: state.searchOpen,
    lastSeenEventSeqBySessionId: state.lastSeenEventSeqBySessionId,
    sessionSyncHealthBySessionId: state.sessionSyncHealthBySessionId,
  }
}

const defaultWorkspaceUiState: WorkspaceUiState = {
  currentSessionId: null,
  expandedProjectIds: [],
  expandedSessionProjectIds: [],
  searchQuery: '',
  searchOpen: false,
  lastSeenEventSeqBySessionId: {},
  sessionSyncHealthBySessionId: {},
}

function upsertExpanded(list: string[], value: string, expanded: boolean) {
  if (expanded) {
    return list.includes(value) ? list : [...list, value]
  }

  return list.filter(item => item !== value)
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      ...defaultWorkspaceUiState,

      setCurrentSessionId: (sessionId) => set({ currentSessionId: sessionId }),

      toggleProjectExpanded: (projectId) => set((state) => ({
        expandedProjectIds: state.expandedProjectIds.includes(projectId)
          ? state.expandedProjectIds.filter(id => id !== projectId)
          : [...state.expandedProjectIds, projectId]
      })),

      setProjectExpanded: (projectId, expanded) => set((state) => ({
        expandedProjectIds: upsertExpanded(state.expandedProjectIds, projectId, expanded)
      })),

      toggleProjectShowAll: (projectId) => set((state) => ({
        expandedSessionProjectIds: state.expandedSessionProjectIds.includes(projectId)
          ? state.expandedSessionProjectIds.filter(id => id !== projectId)
          : [...state.expandedSessionProjectIds, projectId]
      })),

      setSearchQuery: (query) => set({ searchQuery: query }),
      setSearchOpen: (open) => set({ searchOpen: open }),

      markSessionSeen: (sessionId, lastEventSeq) => set((state) => {
        const current = state.lastSeenEventSeqBySessionId[sessionId] ?? 0
        if (lastEventSeq <= current) {
          return state
        }
        return {
          lastSeenEventSeqBySessionId: {
            ...state.lastSeenEventSeqBySessionId,
            [sessionId]: lastEventSeq,
          },
        }
      }),

      markSessionSyncDegraded: (sessionId) => set((state) => {
        if (state.sessionSyncHealthBySessionId[sessionId] === 'degraded') {
          return state
        }
        return {
          sessionSyncHealthBySessionId: {
            ...state.sessionSyncHealthBySessionId,
            [sessionId]: 'degraded',
          },
        }
      }),

      clearSessionSyncHealth: (sessionId) => set((state) => {
        if (!(sessionId in state.sessionSyncHealthBySessionId)) {
          return state
        }
        const next = { ...state.sessionSyncHealthBySessionId }
        delete next[sessionId]
        return { sessionSyncHealthBySessionId: next }
      })
    }),
    {
      name: 'reflexion-workspace',
      storage: createJSONStorage(() => localStorage),
      partialize: partializeWorkspaceUiState
    }
  )
)
