import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'

const {
  getConversationMock,
  setSnapshotMock,
  applyEventMock,
  applyLiveEventMock,
  setLiveStateMock,
  prependMessagesMock,
  setPaginationMock,
  clearConversationMock,
  wsConnectMock,
  wsCloseMock,
  wsSendSyncMock,
  wsStartTurnMock,
  wsCancelRunMock,
  wsApproveToolMock,
  wsDenyToolMock,
  wsOnMock,
  wsHandlers,
  conversationStoreState,
} = vi.hoisted(() => {
  const handlers = new Map<string, (data: unknown) => void>()

  return {
    getConversationMock: vi.fn(),
    setSnapshotMock: vi.fn(),
    applyEventMock: vi.fn(),
    applyLiveEventMock: vi.fn(),
    setLiveStateMock: vi.fn(),
    prependMessagesMock: vi.fn(),
    setPaginationMock: vi.fn(),
    clearConversationMock: vi.fn(),
    wsConnectMock: vi.fn(),
    wsCloseMock: vi.fn(),
    wsSendSyncMock: vi.fn(),
    wsStartTurnMock: vi.fn(),
    wsCancelRunMock: vi.fn(),
    wsApproveToolMock: vi.fn(),
    wsDenyToolMock: vi.fn(),
    wsOnMock: vi.fn((event: string, handler: (data: unknown) => void) => {
      handlers.set(event, handler)
    }),
    wsHandlers: handlers,
    conversationStoreState: {
      conversationsBySessionId: {} as Record<string, unknown>,
      setSnapshot: vi.fn(),
      applyEvent: vi.fn(),
      applyLiveEvent: vi.fn(),
      setLiveState: vi.fn(),
      prependMessages: vi.fn(),
      setPagination: vi.fn(),
      clearConversation: vi.fn(),
      setPlan: vi.fn(),
      setAgentMode: vi.fn(),
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

vi.mock('@/features/conversation/api/conversation.api', () => ({
  conversationApi: {
    getConversation: getConversationMock,
    getConversationPaginated: getConversationMock,
  },
}))

vi.mock('@/features/conversation/stores/conversation.store', () => ({
  useConversationStore: {
    getState: () => conversationStoreState,
  },
}))

vi.mock('@/features/sessions/stores/session.store', () => ({
  useSessionStore: {
    getState: () => ({
      sessionsByProjectId: {},
      upsertSession: vi.fn(),
    }),
  },
}))

vi.mock('@/shared/stores/toast.store', () => ({
  useToastStore: {
    getState: () => ({
      addToast: vi.fn(),
    }),
  },
}))

vi.mock('@/services/sessionConversationWebSocket', () => ({
  SessionConversationWebSocket: vi.fn(() => ({
    connect: wsConnectMock,
    close: wsCloseMock,
    sendSync: wsSendSyncMock,
    startTurn: wsStartTurnMock,
    cancelRun: wsCancelRunMock,
    approveTool: wsApproveToolMock,
    denyTool: wsDenyToolMock,
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
    hasMore: false,
    nextBeforeTurnId: null,
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
    applyLiveEventMock.mockReset()
    setLiveStateMock.mockReset()
    prependMessagesMock.mockReset()
    setPaginationMock.mockReset()
    clearConversationMock.mockReset()
    wsConnectMock.mockReset()
    wsCloseMock.mockReset()
    wsSendSyncMock.mockReset()
    wsStartTurnMock.mockReset()
    wsCancelRunMock.mockReset()
    wsApproveToolMock.mockReset()
    wsDenyToolMock.mockReset()
    wsOnMock.mockClear()
    wsHandlers.clear()

    conversationStoreState.conversationsBySessionId = {}
    conversationStoreState.setSnapshot = setSnapshotMock
    conversationStoreState.applyEvent = applyEventMock
    conversationStoreState.applyLiveEvent = applyLiveEventMock
    conversationStoreState.setLiveState = setLiveStateMock
    conversationStoreState.prependMessages = prependMessagesMock
    conversationStoreState.setPagination = setPaginationMock
    conversationStoreState.clearConversation = clearConversationMock

    wsConnectMock.mockResolvedValue(undefined)
    wsSendSyncMock.mockImplementation(() => {})
    wsStartTurnMock.mockImplementation(() => {})
    wsCancelRunMock.mockImplementation(() => {})
    wsApproveToolMock.mockImplementation(() => {})
    wsDenyToolMock.mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads snapshot, connects websocket, sends sync, and routes durable/live conversation updates into the store', async () => {
    const snapshot = buildSnapshot()
    getConversationMock.mockResolvedValue({ data: snapshot })

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    expect(getConversationMock).toHaveBeenCalledWith('session-1', { limit: 20 })
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
      event_type: 'message.content_committed',
      payload_json: { content_text: '最终回答' },
      created_at: '2026-04-24T10:00:03Z',
    })

    expect(applyEventMock).toHaveBeenCalledWith('session-1', {
      id: 'evt-10',
      sessionId: 'session-1',
      seq: 10,
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      eventType: 'message.content_committed',
      payloadJson: { content_text: '最终回答' },
      createdAt: '2026-04-24T10:00:03Z',
    })

    wsHandlers.get('conversation:live_event')?.({
      session_id: 'session-1',
      turn_id: 'turn-1',
      run_id: 'run-1',
      message_id: 'msg-2',
      message_type: 'assistant_message',
      delta: '继',
      content_text: '继续',
      stream_state: 'streaming',
    })

    await new Promise((resolve) => setTimeout(resolve, 60))

    expect(applyLiveEventMock).toHaveBeenCalledWith('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      delta: '继',
      contentText: '继续',
      streamState: 'streaming',
    })

    wsHandlers.get('conversation:live_state')?.({
      session_id: 'session-1',
      turn_id: 'turn-1',
      run_id: 'run-1',
      message_id: 'msg-2',
      message_type: 'assistant_message',
      content_text: '继续输出中',
      stream_state: 'streaming',
    })

    expect(setLiveStateMock).toHaveBeenCalledWith('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      contentText: '继续输出中',
      streamState: 'streaming',
    })
  })

  it('applies the first live update immediately, then throttles rapid follow-up updates', async () => {
    vi.useFakeTimers()
    getConversationMock.mockResolvedValue({ data: buildSnapshot() })

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await vi.waitFor(() => {
      expect(wsHandlers.has('conversation:live_event')).toBe(true)
    })
    applyLiveEventMock.mockClear()

    wsHandlers.get('conversation:live_event')?.({
      session_id: 'session-1',
      turn_id: 'turn-1',
      run_id: 'run-1',
      message_id: 'msg-2',
      message_type: 'assistant_message',
      delta: 'A',
      content_text: 'A',
      stream_state: 'streaming',
    })

    expect(applyLiveEventMock).toHaveBeenCalledTimes(1)
    expect(applyLiveEventMock).toHaveBeenCalledWith('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      delta: 'A',
      contentText: 'A',
      streamState: 'streaming',
    })

    wsHandlers.get('conversation:live_event')?.({
      session_id: 'session-1',
      turn_id: 'turn-1',
      run_id: 'run-1',
      message_id: 'msg-2',
      message_type: 'assistant_message',
      delta: 'B',
      content_text: 'AB',
      stream_state: 'streaming',
    })

    expect(applyLiveEventMock).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(50)

    expect(applyLiveEventMock).toHaveBeenCalledTimes(2)
    expect(applyLiveEventMock).toHaveBeenCalledWith('session-1', {
      sessionId: 'session-1',
      turnId: 'turn-1',
      runId: 'run-1',
      messageId: 'msg-2',
      messageType: 'assistant_message',
      delta: 'B',
      contentText: 'AB',
      streamState: 'streaming',
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

    const { useConversationRuntime } = await import('../useConversationRuntime')
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

  it('can cancel runs that are waiting for approval', async () => {
    getConversationMock.mockResolvedValue({ data: buildSnapshot() })
    conversationStoreState.conversationsBySessionId = {
      'session-1': {
        session: { activeTurnId: 'turn-1' },
        turnsById: {
          'turn-1': { activeRunId: 'run-1' },
        },
        runsById: {
          'run-1': { status: 'waiting_for_approval' },
        },
      },
    }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    const runtime = useConversationRuntime('session-1')

    await flushAsyncEffects()

    runtime.cancelRun()

    expect(wsCancelRunMock).toHaveBeenCalledWith('run-1')
  })

  it('routes approve and deny tool decisions through the session websocket channel', async () => {
    getConversationMock.mockResolvedValue({ data: buildSnapshot() })

    const { useConversationRuntime } = await import('../useConversationRuntime')
    const runtime = useConversationRuntime('session-1')

    await flushAsyncEffects()

    runtime.approveTool('run-1', 'approval-1')
    runtime.denyTool('run-1', 'approval-1')

    expect(wsApproveToolMock).toHaveBeenCalledWith({
      runId: 'run-1',
      approvalId: 'approval-1',
      decision: 'allow_once',
    })
    expect(wsDenyToolMock).toHaveBeenCalledWith({
      runId: 'run-1',
      approvalId: 'approval-1',
    })
  })

  it('loads more history using the oldest loaded turn id', async () => {
    getConversationMock.mockResolvedValue({ data: buildSnapshot() })

    const { useConversationRuntime } = await import('../useConversationRuntime')
    const runtime = useConversationRuntime('session-1')

    await flushAsyncEffects()

    const olderPage: ConversationSnapshot = {
      ...buildSnapshot(),
      turns: [
        {
          id: 'turn-0',
          sessionId: 'session-1',
          turnIndex: 0,
          rootMessageId: 'msg-0',
          status: 'completed',
          activeRunId: null,
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:01Z',
          completedAt: '2026-04-24T09:59:02Z',
        },
      ],
      runs: [],
      messages: [
        {
          id: 'msg-0',
          sessionId: 'session-1',
          turnId: 'turn-0',
          runId: null,
          turnMessageIndex: 1,
          role: 'user',
          messageType: 'user_message',
          streamState: 'completed',
          displayMode: 'default',
          contentText: 'older turn',
          payloadJson: {},
          createdAt: '2026-04-24T09:59:00Z',
          updatedAt: '2026-04-24T09:59:00Z',
          completedAt: '2026-04-24T09:59:00Z',
        },
      ],
      hasMore: true,
      nextBeforeTurnId: 'turn-0',
    }
    getConversationMock.mockResolvedValueOnce({ data: olderPage })

    await runtime.loadMore('session-1', 'turn-1')

    expect(getConversationMock).toHaveBeenLastCalledWith('session-1', { limit: 20, beforeTurn: 'turn-1' })
    expect(prependMessagesMock).toHaveBeenCalledWith('session-1', olderPage.messages, olderPage.turns, olderPage.runs)
    expect(setPaginationMock).toHaveBeenCalledWith('session-1', {
      hasMore: true,
      nextBeforeTurnId: 'turn-0',
    })
  })

  it('queues snapshot refresh per session without dropping cross-session refreshes', async () => {
    const { createSnapshotRefreshQueue } = await import('../useConversationRuntime')
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

  it('refreshes the snapshot when the backend requests a resync', async () => {
    const snapshot = buildSnapshot()
    getConversationMock.mockResolvedValue({ data: snapshot })

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    wsHandlers.get('conversation:resync_required')?.({
      session_id: 'session-1',
      reason: 'stale_after_seq',
      after_seq: 0,
    })

    await flushAsyncEffects()

    expect(getConversationMock).toHaveBeenCalledTimes(2)
    expect(setSnapshotMock).toHaveBeenLastCalledWith('session-1', snapshot)
  })
})
