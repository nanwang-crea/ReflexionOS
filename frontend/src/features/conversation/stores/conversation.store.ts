/**
 * 文件功能：会话状态的 zustand store 定义
 * 文件描述：以 sessionId 为 key，集中存储所有会话的对话状态（消息/轮次/运行记录）、
 *          计划（Plan）、agent 模式、权限模式；对外暴露一组 action 方法，内部调用
 *          conversation.reducer.ts 中的纯函数完成状态转换。
 * 核心逻辑：store 本身不包含业务逻辑，只负责"取出某会话当前状态 -> 调用 reducer 纯函数
 *          计算新状态 -> 写回 map"这一固定流程，保证多会话之间状态互不影响。
 */
import { create } from 'zustand'
import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationMessage,
  ConversationRun,
  ConversationSnapshot,
  ConversationState,
  ConversationTurn,
  Plan,
} from '@/types/conversation'
import {
  applyConversationEvent,
  applyConversationLiveEvent,
  applyConversationLiveState,
  applyConversationSnapshot,
  createEmptyConversationState,
  prependMessages,
} from '@/features/conversation/conversation.reducer'

// store 状态与 action 方法的类型定义：以 sessionId 为 key 分别存储对话状态/计划/模式
interface ConversationStoreState {
  conversationsBySessionId: Record<string, ConversationState>
  planBySessionId: Record<string, Plan>
  agentModeBySessionId: Record<string, import('@/types/conversation').AgentMode>
  permissionModeBySessionId: Record<string, import('@/types/conversation').PermissionMode>
  setSnapshot: (sessionId: string, snapshot: ConversationSnapshot) => void
  applyEvent: (sessionId: string, event: ConversationEvent) => void
  applyLiveEvent: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  setLiveState: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  setPlan: (sessionId: string, plan: Plan | null) => void
  setAgentMode: (sessionId: string, mode: import('@/types/conversation').AgentMode) => void
  setPermissionMode: (sessionId: string, mode: import('@/types/conversation').PermissionMode) => void
  prependMessages: (sessionId: string, messages: ConversationMessage[], turns: ConversationTurn[], runs: ConversationRun[]) => void
  setPagination: (sessionId: string, pagination: Pick<ConversationSnapshot, 'hasMore' | 'nextBeforeTurnId'>) => void
  clearConversation: (sessionId: string) => void
}

/**
 * 函数名：createConversationStore
 * 入参：无
 * 功能：创建一个独立的会话状态 store 实例（zustand create）
 * 运行逻辑：定义初始状态（各 map 均为空对象）以及全部 action 方法：
 *   - setSnapshot：应用后端快照，同时同步 agentMode/permissionMode 到 store；
 *   - applyEvent/applyLiveEvent/setLiveState：分别对接持久化事件、实时增量事件、实时状态更新；
 *   - setPlan：设置或清除某会话的计划（传 null 表示清除）；
 *   - setAgentMode/setPermissionMode：切换指定会话的 agent 模式/权限模式；
 *   - prependMessages：向前分页加载历史消息后合并进现有状态；
 *   - setPagination：直接更新分页游标（hasMore/nextBeforeTurnId），null 游标视为终态；
 *   - clearConversation：从所有 map 中移除指定会话的全部数据（如关闭/删除会话时调用）。
 *   之所以封装成工厂函数而非直接创建单例，是为了方便单测中创建互相隔离的 store 实例。
 * 出参：ReturnType<typeof create<ConversationStoreState>> - zustand store 实例
 */
export const createConversationStore = () => create<ConversationStoreState>((set) => ({
  conversationsBySessionId: {},
  planBySessionId: {},
  agentModeBySessionId: {},
  permissionModeBySessionId: {},
  setSnapshot: (sessionId, snapshot) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationSnapshot(state.conversationsBySessionId[sessionId], snapshot),
    },
    agentModeBySessionId: {
      ...state.agentModeBySessionId,
      [sessionId]: snapshot.session.agentMode ?? 'build',
    },
    permissionModeBySessionId: {
      ...state.permissionModeBySessionId,
      [sessionId]: snapshot.session.permissionMode ?? 'auto',
    },
  })),
  applyEvent: (sessionId, event) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationEvent(
        state.conversationsBySessionId[sessionId] ?? createEmptyConversationState(sessionId),
        event
      ),
    },
  })),
  applyLiveEvent: (sessionId, liveMessage) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationLiveEvent(
        state.conversationsBySessionId[sessionId] ?? createEmptyConversationState(sessionId),
        liveMessage
      ),
    },
  })),
  setLiveState: (sessionId, liveMessage) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationLiveState(
        state.conversationsBySessionId[sessionId] ?? createEmptyConversationState(sessionId),
        liveMessage
      ),
    },
  })),
  setPlan: (sessionId, plan) => set((state) => {
    if (plan === null) {
      const { [sessionId]: _, ...rest } = state.planBySessionId
      return { planBySessionId: rest }
    }
    return {
      planBySessionId: {
        ...state.planBySessionId,
        [sessionId]: plan,
      },
    }
  }),
  setAgentMode: (sessionId, mode) => set((state) => ({
    agentModeBySessionId: {
      ...state.agentModeBySessionId,
      [sessionId]: mode,
    },
  })),
  setPermissionMode: (sessionId, mode) => set((state) => ({
    permissionModeBySessionId: {
      ...state.permissionModeBySessionId,
      [sessionId]: mode,
    },
  })),
  prependMessages: (sessionId, messages, turns, runs) => set((state) => {
    const conversation = state.conversationsBySessionId[sessionId]
    if (!conversation) return state
    const nextConversation = prependMessages(conversation, messages, turns, runs)
    return {
      conversationsBySessionId: {
        ...state.conversationsBySessionId,
        [sessionId]: nextConversation,
      },
    }
  }),
  setPagination: (sessionId, pagination) => set((state) => {
    const conversation = state.conversationsBySessionId[sessionId]
    if (!conversation) return state
    return {
      conversationsBySessionId: {
        ...state.conversationsBySessionId,
        [sessionId]: {
          ...conversation,
          hasMore: pagination.nextBeforeTurnId !== null && pagination.hasMore,
          nextBeforeTurnId: pagination.nextBeforeTurnId,
        },
      },
    }
  }),
  clearConversation: (sessionId) => set((state) => ({
    conversationsBySessionId: Object.fromEntries(
      Object.entries(state.conversationsBySessionId).filter(([id]) => id !== sessionId)
    ),
    planBySessionId: Object.fromEntries(
      Object.entries(state.planBySessionId).filter(([id]) => id !== sessionId)
    ),
    agentModeBySessionId: Object.fromEntries(
      Object.entries(state.agentModeBySessionId).filter(([id]) => id !== sessionId)
    ),
    permissionModeBySessionId: Object.fromEntries(
      Object.entries(state.permissionModeBySessionId).filter(([id]) => id !== sessionId)
    ),
  })),
}))

// 全局单例 store：应用内绝大多数场景使用这个共享实例
export const useConversationStore = createConversationStore()

/**
 * 函数名：findSessionIdByRunId
 * 入参：
 *   - conversationsBySessionId (Record<string, ConversationState>): 所有会话的对话状态 map
 *   - runId (string): 需要查找所属会话的运行记录 id
 * 功能：根据 runId 反查其所属的 sessionId
 * 运行逻辑：遍历所有会话，在每个会话的 runsById 中查找该 runId 是否存在；
 *          之所以现查而不额外维护 runId -> sessionId 的对照表，是为了保证与会话真值
 *          （runsById）始终一致，避免对照表和真实状态不同步的问题
 * 出参：string | null - 找到则返回 sessionId，否则返回 null
 */
export function findSessionIdByRunId(
  conversationsBySessionId: Record<string, ConversationState>,
  runId: string,
): string | null {
  for (const [sessionId, conversation] of Object.entries(conversationsBySessionId)) {
    if (conversation.runsById[runId]) {
      return sessionId
    }
  }
  return null
}
