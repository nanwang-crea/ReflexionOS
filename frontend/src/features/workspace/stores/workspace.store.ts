/**
 * 文件功能：工作区 UI 级状态管理（zustand store，带本地持久化）
 * 文件描述：管理当前选中会话、项目/会话列表展开状态、搜索框状态、
 *           会话已读基线（未读活动派生依据）、会话同步健康状态等跨组件共享的 UI 状态，
 *           并将其中的展示相关状态持久化到 localStorage，刷新页面后可恢复。
 * 核心逻辑：用 zustand 的 persist 中间件配合 partialize 只持久化 WorkspaceUiState 定义的字段（不持久化方法）；
 *           markSessionSeen 保证已读序号单调递增，resetSessionSeen 是唯一允许其回退的入口。
 */
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
  // 重置某会话的已读基线（清除其 seen，等价于回退到 0）。
  // 这是 markSessionSeen 单调递增之外唯一允许 seen 回退的入口，专供「重置对话」使用：
  // 后端 last_event_seq 清零后从 1 重新计数，若不回退 seen 会导致重置后长期“永不未读”。
  resetSessionSeen: (sessionId: string) => void
  // 标记某会话连接同步异常（后台重连耗尽 / 被降级），切回时据此强制补拉。
  markSessionSyncDegraded: (sessionId: string) => void
  // 清除某会话的同步异常标记（重连成功 / 切回补拉成功后调用）。
  clearSessionSyncHealth: (sessionId: string) => void
}

/**
 * 函数名：partializeWorkspaceUiState
 * 入参：
 *   - state (WorkspaceState): 完整的 store 状态（含数据字段与方法）
 * 功能：从完整 store 状态中提取出需要持久化到 localStorage 的子集（仅数据字段，不含方法）
 * 运行逻辑：逐字段挑选出 WorkspaceUiState 中声明的字段并返回
 * 出参：WorkspaceUiState - 用于持久化的状态子集
 */
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

/**
 * 函数名：upsertExpanded
 * 入参：
 *   - list (string[]): 当前展开项 ID 列表
 *   - value (string): 待增删的目标 ID
 *   - expanded (boolean): 目标最终应处于展开（true）还是收起（false）状态
 * 功能：根据期望的展开状态，将目标 ID 添加到列表或从列表移除
 * 运行逻辑：expanded 为 true 时，若列表中不存在该 ID 则追加；为 false 时，从列表中过滤掉该 ID
 * 出参：string[] - 更新后的展开项 ID 列表（新数组，不修改原数组）
 */
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

      // 设置当前选中的会话 ID（null 表示未选中任何会话）
      setCurrentSessionId: (sessionId) => set({ currentSessionId: sessionId }),

      // 切换指定项目在侧边栏的展开/收起状态
      toggleProjectExpanded: (projectId) => set((state) => ({
        expandedProjectIds: state.expandedProjectIds.includes(projectId)
          ? state.expandedProjectIds.filter(id => id !== projectId)
          : [...state.expandedProjectIds, projectId]
      })),

      // 显式设置指定项目的展开/收起状态（区别于 toggle，这里直接指定目标状态）
      setProjectExpanded: (projectId, expanded) => set((state) => ({
        expandedProjectIds: upsertExpanded(state.expandedProjectIds, projectId, expanded)
      })),

      // 切换指定项目下“会话列表是否展开显示全部”的状态
      toggleProjectShowAll: (projectId) => set((state) => ({
        expandedSessionProjectIds: state.expandedSessionProjectIds.includes(projectId)
          ? state.expandedSessionProjectIds.filter(id => id !== projectId)
          : [...state.expandedSessionProjectIds, projectId]
      })),

      // 设置搜索框的查询关键字
      setSearchQuery: (query) => set({ searchQuery: query }),
      // 设置搜索框的展开/收起状态
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

      resetSessionSeen: (sessionId) => set((state) => {
        if (!(sessionId in state.lastSeenEventSeqBySessionId)) {
          return state
        }
        const next = { ...state.lastSeenEventSeqBySessionId }
        delete next[sessionId]
        return { lastSeenEventSeqBySessionId: next }
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
