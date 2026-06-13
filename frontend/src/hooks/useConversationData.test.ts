import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationSession, ConversationState } from '@/types/conversation'

const { conversationStoreState } = vi.hoisted(() => ({
  conversationStoreState: {
    conversationsBySessionId: {} as Record<string, ConversationState>,
    planBySessionId: {} as Record<string, unknown>,
  },
}))

vi.mock('react', () => ({
  useMemo: <T>(factory: () => T) => factory(),
}))

vi.mock('@/features/conversation/stores/conversation.store', () => ({
  useConversationStore: (selector: (state: typeof conversationStoreState) => unknown) => selector(conversationStoreState),
}))

function createConversation(overrides: Partial<ConversationState> = {}): ConversationState {
  return {
    sessionId: 'session-1',
    lastEventSeq: 0,
    session: {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      lastEventSeq: 0,
      activeTurnId: null,
      createdAt: '2026-04-21T00:00:00Z',
      updatedAt: '2026-04-21T00:00:00Z',
    } as ConversationSession,
    turnOrder: [],
    turnsById: {},
    runsById: {},
    messageOrder: [],
    messagesById: {},
    hasMore: false,
    nextBeforeTurnId: null,
    ...overrides,
  }
}

describe('useConversationData', () => {
  beforeEach(() => {
    vi.resetModules()
    conversationStoreState.conversationsBySessionId = {}
    conversationStoreState.planBySessionId = {}
  })

  it('defaults hasMore to false when the current conversation has not loaded yet', async () => {
    const { useConversationData } = await import('./useConversationData')

    const result = useConversationData('session-1')

    expect(result.hasMore).toBe(false)
    expect(result.oldestLoadedTurnId).toBeNull()
    expect(result.messages).toEqual([])
  })

  it('returns the stored pagination flags once the conversation exists', async () => {
    conversationStoreState.conversationsBySessionId['session-1'] = createConversation({
      hasMore: true,
      nextBeforeTurnId: 'turn-3',
    })

    const { useConversationData } = await import('./useConversationData')

    const result = useConversationData('session-1')

    expect(result.hasMore).toBe(true)
    expect(result.oldestLoadedTurnId).toBe('turn-3')
  })
})
