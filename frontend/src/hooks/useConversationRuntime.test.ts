import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'

const {
  getConversationMock,
  setSnapshotMock,
  applyEventMock,
  clearConversationMock,
  wsConnectMock,
  wsCloseMock,
  wsSendSyncMock,
  wsStartTurnMock,
  wsCancelRunMock,
  wsOnMock,
  wsHandlers,
  conversationStoreState,
} = vi.hoisted(() => {
  const handlers = new Map<string, (data: unknown) => void>()

  return {
    getConversationMock: vi.fn(),
    setSnapshotMock: vi.fn(),
    applyEventMock: vi.fn(),
    clearConversationMock: vi.fn(),
    wsConnectMock: vi.fn(),
    wsCloseMock: vi.fn(),
    wsSendSyncMock: vi.fn(),
    wsStartTurnMock: vi.fn(),
    wsCancelRunMock: vi.fn(),
    wsOnMock: vi.fn((event: string, handler: (data: unknown) => void) => {
      handlers.set(event, handler)
    }),
    wsHandlers: handlers,
    conversationStoreState: {
      conversationsBySessionId: {} as Record<string, unknown>,
      setSnapshot: vi.fn(),
      applyEvent: vi.fn(),
      clearConversation: vi.fn(),
    },
  }
})

vi.mock('react', () => ({
  useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => {
    effect()
  },
  useRef: <T,>(value: T) => ({ current: value }),
  useState: <T,>(value: T) => [value, vi.fn()] as const,
}))

vi.mock('@/features/conversation/conversationApi', () => ({
  conversationApi: {
    getConversation: getConversationMock,
  },
}))

vi.mock('@/features/conversation/conversationStore', () => ({
  useConversationStore: {
    getState: () => conversationStoreState,
  },
}))

vi.mock('@/services/sessionConversationWebSocket', () => ({
  SessionConversationWebSocket: vi.fn(() => ({
    connect: wsConnectMock,
    close: wsCloseMock,
    sendSync: wsSendSyncMock,
    startTurn: wsStartTurnMock,
    cancelRun: wsCancelRunMock,
    on: wsOnMock,
    isConnected: () => true,
  })),
}))

function buildSnapshot(): ConversationSnapshot {
  return {
    session: {
      id: 'session-1',
      projectId: 'project-1',
      title: '会话',
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      lastEventSeq: 9,
      activeTurnId: 'turn-1',
      createdAt: '2026-04-24T10:00:00Z',
      updatedAt: '2026-04-24T10:00:02Z',
    },
    turns: [
      {
        id: 'turn-1',
        sessionId: 'session-1',
        turnIndex: 1,
        rootMessageId: 'msg-1',
        status: 'running',
        activeRunId: 'run-1',
        createdAt: '2026-04-24T10:00:00Z',
        updatedAt: '2026-04-24T10:00:01Z',
        completedAt: null,
      },
    ],
    runs: [
      {
        id: 'run-1',
        sessionId: 'session-1',
        turnId: 'turn-1',
        attemptIndex: 1,
        status: 'running',
        providerId: 'provider-a',
        modelId: 'model-a',
        workspaceRef: '/tmp/reflexion',
        startedAt: null,
        finishedAt: null,
        errorCode: null,
        errorMessage: null,
      },
    ],
    messages: [],
  }
}

async function flushAsyncEffects() {
  await Promise.resolve()
  await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

describe('useConversationRuntime', () => {
  beforeEach(() => {
    vi.resetModules()
    getConversationMock.mockReset()
    setSnapshotMock.mockReset()
    applyEventMock.mockReset()
    clearConversationMock.mockReset()
    wsConnectMock.mockReset()
    wsCloseMock.mockReset()
    wsSendSyncMock.mockReset()
    wsStartTurnMock.mockReset()
    wsCancelRunMock.mockReset()
    wsOnMock.mockClear()
    wsHandlers.clear()

    conversationStoreState.conversationsBySessionId = {}
    conversationStoreState.setSnapshot = setSnapshotMock
    conversationStoreState.applyEvent = applyEventMock
    conversationStoreState.clearConversation = clearConversationMock

    wsConnectMock.mockResolvedValue(undefined)
    wsSendSyncMock.mockImplementation(() => {})
    wsStartTurnMock.mockImplementation(() => {})
    wsCancelRunMock.mockImplementation(() => {})
  })

  it('loads snapshot, connects websocket, sends sync, and maps conversation.event into store events', async () => {
    const snapshot = buildSnapshot()
    getConversationMock.mockResolvedValue({ data: snapshot })

    const { useConversationRuntime } = await import('./useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    expect(getConversationMock).toHaveBeenCalledWith('session-1')
    expect(setSnapshotMock).toHaveBeenCalledWith('session-1', snapshot)
    expect(wsConnectMock).toHaveBeenCalledWith('session-1')
    expect(wsSendSyncMock).toHaveBeenCalledWith(9)

    wsHandlers.get('conversation:event')?.({
      id: 'evt-10',
      session_id: 'session-1',
      seq: 10,
      turn_id: 'turn-1',
      run_id: 'run-1',
      message_id: 'msg-2',
      event_type: 'message.delta_appended',
      payload_json: { delta: '继续' },
      created_at: '2026-04-24T10:00:03Z',
    })

    expect(applyEventMock).toHaveBeenCalledWith('session-1', {
      id: 'evt-10',
      sessionId: 'session-1',
      seq: 10,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.delta_appended',
      payloadJson: { delta: '继续' },
      createdAt: '2026-04-24T10:00:03Z',
    })
  })

  it('routes startTurn and cancelRun through the session websocket channel', async () => {
    getConversationMock.mockResolvedValue({ data: buildSnapshot() })
    conversationStoreState.conversationsBySessionId = {
      'session-1': {
        session: { activeTurnId: 'turn-1' },
        turnsById: {
          'turn-1': { activeRunId: 'run-1' },
        },
        runsById: {
          'run-1': { status: 'running' },
        },
      },
    }

    const { useConversationRuntime } = await import('./useConversationRuntime')
    const runtime = useConversationRuntime('session-1')

    await flushAsyncEffects()

    await runtime.startTurn({
      sessionId: 'session-1',
      message: '请检查日志',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
    runtime.cancelRun()

    expect(wsStartTurnMock).toHaveBeenCalledWith({
      content: '请检查日志',
      providerId: 'provider-a',
      modelId: 'model-a',
    })
    expect(wsCancelRunMock).toHaveBeenCalledWith('run-1')
  })

  it('queues snapshot refresh per session without dropping cross-session refreshes', async () => {
    const { createSnapshotRefreshQueue } = await import('./useConversationRuntime')
    const pendingResolves = new Map<string, Array<() => void>>()
    const refreshCalls: string[] = []

    const queueResolve = (sessionId: string, resolve: () => void) => {
      const queue = pendingResolves.get(sessionId) ?? []
      queue.push(resolve)
      pendingResolves.set(sessionId, queue)
    }

    const resolveNext = (sessionId: string) => {
      const queue = pendingResolves.get(sessionId) ?? []
      const resolve = queue.shift()
      if (queue.length === 0) {
        pendingResolves.delete(sessionId)
      } else {
        pendingResolves.set(sessionId, queue)
      }
      resolve?.()
    }

    const refreshSnapshotMock = vi.fn((sessionId: string) => {
      refreshCalls.push(sessionId)
      return new Promise<void>((resolve) => queueResolve(sessionId, resolve))
    })

    const queueSnapshotRefresh = createSnapshotRefreshQueue(refreshSnapshotMock)
    queueSnapshotRefresh('session-1')
    queueSnapshotRefresh('session-2')

    expect(refreshCalls).toEqual(['session-1'])

    resolveNext('session-1')
    await flushAsyncEffects()

    expect(refreshCalls).toEqual(['session-1', 'session-2'])
  })
})
