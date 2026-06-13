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
} from '@/features/conversation/conversationReducer'

interface ConversationStoreState {
  conversationsBySessionId: Record<string, ConversationState>
  planBySessionId: Record<string, Plan>
  agentModeBySessionId: Record<string, import('@/types/conversation').AgentMode>
  setSnapshot: (sessionId: string, snapshot: ConversationSnapshot) => void
  applyEvent: (sessionId: string, event: ConversationEvent) => void
  applyLiveEvent: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  setLiveState: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  setPlan: (sessionId: string, plan: Plan | null) => void
  setAgentMode: (sessionId: string, mode: import('@/types/conversation').AgentMode) => void
  prependMessages: (sessionId: string, messages: ConversationMessage[], turns: ConversationTurn[], runs: ConversationRun[]) => void
  setPagination: (sessionId: string, pagination: Pick<ConversationSnapshot, 'hasMore' | 'nextBeforeTurnId'>) => void
  clearConversation: (sessionId: string) => void
}

export const createConversationStore = () => create<ConversationStoreState>((set) => ({
  conversationsBySessionId: {},
  planBySessionId: {},
  agentModeBySessionId: {},
  setSnapshot: (sessionId, snapshot) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationSnapshot(state.conversationsBySessionId[sessionId], snapshot),
    },
    agentModeBySessionId: {
      ...state.agentModeBySessionId,
      [sessionId]: snapshot.session.agentMode ?? 'build',
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
  })),
}))

export const useConversationStore = createConversationStore()
