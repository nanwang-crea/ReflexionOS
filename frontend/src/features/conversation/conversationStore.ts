import { create } from 'zustand'
import type {
  ConversationEvent,
  ConversationLiveMessage,
  ConversationSnapshot,
  ConversationState,
} from '@/types/conversation'
import {
  applyConversationEvent,
  applyConversationLiveEvent,
  applyConversationLiveState,
  applyConversationSnapshot,
  createEmptyConversationState,
} from './conversationReducer'

interface ConversationStoreState {
  conversationsBySessionId: Record<string, ConversationState>
  setSnapshot: (sessionId: string, snapshot: ConversationSnapshot) => void
  applyEvent: (sessionId: string, event: ConversationEvent) => void
  applyLiveEvent: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  setLiveState: (sessionId: string, liveMessage: ConversationLiveMessage) => void
  clearConversation: (sessionId: string) => void
}

export const createConversationStore = () => create<ConversationStoreState>((set) => ({
  conversationsBySessionId: {},
  setSnapshot: (sessionId, snapshot) => set((state) => ({
    conversationsBySessionId: {
      ...state.conversationsBySessionId,
      [sessionId]: applyConversationSnapshot(state.conversationsBySessionId[sessionId], snapshot),
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
  clearConversation: (sessionId) => set((state) => ({
    conversationsBySessionId: Object.fromEntries(
      Object.entries(state.conversationsBySessionId).filter(([id]) => id !== sessionId)
    ),
  })),
}))

export const useConversationStore = createConversationStore()

export type { ConversationStoreState }
