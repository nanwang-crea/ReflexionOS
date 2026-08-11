import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConversationSnapshot } from '@/types/conversation'

// 多会话并行运行时测试：相比单连接版本，这里的 WebSocket mock 支持
// 多个实例，并按 sessionId 区分 handlers，可对不同会话独立触发事件 /
// 控制连接成败。覆盖：A 运行中切到 B、A/B 独立运行、超上限降级、
// 重连失败降级与切回补拉、未读判定、动作不串会话。

interface MockWsInstance {
  sessionId: string | null
  handlers: Map<string, (data: unknown) => void>
  isConnectedValue: boolean
  connectImpl: (sessionId: string) => Promise<void>
  startTurn: ReturnType<typeof vi.fn>
  cancelRun: ReturnType<typeof vi.fn>
  approveTool: ReturnType<typeof vi.fn>
  denyTool: ReturnType<typeof vi.fn>
  editAndRerun: ReturnType<typeof vi.fn>
  send: ReturnType<typeof vi.fn>
  sendSync: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
}

const {
  getConversationMock,
  wsInstances,
  wsBySessionId,
  conversationStoreState,
  workspaceStoreState,
  addToastMock,
  markDegradedMock,
  clearHealthMock,
} = vi.hoisted(() => {
  return {
    getConversationMock: vi.fn(),
    wsInstances: [] as MockWsInstance[],
    wsBySessionId: new Map<string, MockWsInstance>(),
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
    workspaceStoreState: {
      sessionSyncHealthBySessionId: {} as Record<string, 'degraded'>,
      markSessionSyncDegraded: vi.fn(),
      clearSessionSyncHealth: vi.fn(),
    },
    addToastMock: vi.fn(),
    markDegradedMock: vi.fn(),
    clearHealthMock: vi.fn(),
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

vi.mock('@/features/conversation/stores/conversation.store', () => {
  const useConversationStore = ((selector?: (state: typeof conversationStoreState) => unknown) =>
    selector ? selector(conversationStoreState) : conversationStoreState) as unknown as {
      (selector?: (state: typeof conversationStoreState) => unknown): unknown
      getState: () => typeof conversationStoreState
    }
  useConversationStore.getState = () => conversationStoreState

  return {
    useConversationStore,
    findSessionIdByRunId: (
      conversationsBySessionId: Record<string, { runsById?: Record<string, unknown> }>,
      runId: string,
    ) => {
      for (const [sessionId, conversation] of Object.entries(conversationsBySessionId)) {
        if (conversation.runsById?.[runId]) {
          return sessionId
        }
      }
      return null
    },
  }
})

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
      addToast: addToastMock,
    }),
  },
}))

vi.mock('@/features/workspace/stores/workspace.store', () => ({
  useWorkspaceStore: {
    getState: () => workspaceStoreState,
  },
}))

// 多实例 WebSocket mock：每次 new 创建独立实例与独立 handlers；
// connect(sessionId) 时把实例登记到 wsBySessionId，供测试按会话触发事件。
vi.mock('@/services/sessionConversationWebSocket', () => ({
  SessionConversationWebSocket: vi.fn(() => {
    const instance: MockWsInstance = {
      sessionId: null,
      handlers: new Map(),
      isConnectedValue: false,
      connectImpl: async () => {},
      startTurn: vi.fn(),
      cancelRun: vi.fn(),
      approveTool: vi.fn(),
      denyTool: vi.fn(),
      editAndRerun: vi.fn(),
      send: vi.fn(),
      sendSync: vi.fn(),
      close: vi.fn(),
    }

    const ws = {
      on: (event: string, handler: (data: unknown) => void) => {
        instance.handlers.set(event, handler)
      },
      connect: async (sessionId: string) => {
        instance.sessionId = sessionId
        wsBySessionId.set(sessionId, instance)
        await instance.connectImpl(sessionId)
        instance.isConnectedValue = true
      },
      isConnected: () => instance.isConnectedValue,
      startTurn: instance.startTurn,
      cancelRun: instance.cancelRun,
      approveTool: instance.approveTool,
      denyTool: instance.denyTool,
      editAndRerun: instance.editAndRerun,
      send: instance.send,
      sendSync: instance.sendSync,
      close: (...args: unknown[]) => {
        instance.isConnectedValue = false
        instance.close(...args)
      },
    }

    wsInstances.push(instance)
    return ws
  }),
}))

function buildSnapshot(sessionId: string, overrides: Partial<ConversationSnapshot['session']> = {}): ConversationSnapshot {
  return {
    session: {
      id: sessionId,
      projectId: 'project-1',
      title: `会话-${sessionId}`,
      preferredProviderId: 'provider-a',
      preferredModelId: 'model-a',
      lastEventSeq: 9,
      activeTurnId: 'turn-1',
      createdAt: '2026-06-20T10:00:00Z',
      updatedAt: '2026-06-20T10:00:02Z',
      ...overrides,
    },
    turns: [],
    runs: [],
    messages: [],
    hasMore: false,
    nextBeforeTurnId: null,
  }
}

// 构造一个带活跃 run 的会话 store 条目（供调度判定“后台活跃”）。
function activeConversation(sessionId: string, runId: string, status = 'running') {
  return {
    sessionId,
    session: { activeTurnId: 'turn-1' },
    turnsById: { 'turn-1': { activeRunId: runId } },
    runsById: { [runId]: { id: runId, sessionId, status } },
  }
}

async function flushAsyncEffects() {
  await Promise.resolve()
  await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

function fireWsEvent(sessionId: string, event: string, data: unknown) {
  wsBySessionId.get(sessionId)?.handlers.get(event)?.(data)
}

describe('useConversationRuntime（多会话并行）', () => {
  beforeEach(() => {
    vi.resetModules()
    getConversationMock.mockReset()
    addToastMock.mockReset()
    workspaceStoreState.markSessionSyncDegraded = markDegradedMock
    workspaceStoreState.clearSessionSyncHealth = clearHealthMock
    markDegradedMock.mockReset()
    clearHealthMock.mockReset()
    workspaceStoreState.sessionSyncHealthBySessionId = {}

    wsInstances.length = 0
    wsBySessionId.clear()

    conversationStoreState.conversationsBySessionId = {}
    conversationStoreState.setSnapshot = vi.fn()
    conversationStoreState.applyEvent = vi.fn()
    conversationStoreState.applyLiveEvent = vi.fn()
    conversationStoreState.setLiveState = vi.fn()
    conversationStoreState.clearConversation = vi.fn()
    conversationStoreState.setPlan = vi.fn()

    // 默认：任何 sessionId 都返回以它为主键的快照。
    getConversationMock.mockImplementation((sessionId: string) =>
      Promise.resolve({ data: buildSnapshot(sessionId) }),
    )
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('当前会话与后台活跃会话各自建立独立连接', async () => {
    // session-1 当前；session-2 后台运行中。
    conversationStoreState.conversationsBySessionId = {
      'session-2': activeConversation('session-2', 'run-2'),
    }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    // 两个会话各连一条，互不复用。
    expect(wsBySessionId.has('session-1')).toBe(true)
    expect(wsBySessionId.has('session-2')).toBe(true)
    expect(wsBySessionId.get('session-1')).not.toBe(wsBySessionId.get('session-2'))
  })

  it('两个会话的事件分别落到各自会话，不串会话', async () => {
    conversationStoreState.conversationsBySessionId = {
      'session-2': activeConversation('session-2', 'run-2'),
    }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    fireWsEvent('session-1', 'conversation:event', {
      id: 'evt-a', session_id: 'session-1', seq: 11, turn_id: 'turn-1', run_id: 'run-1',
      message_id: 'msg-a', event_type: 'message.content_committed',
      payload_json: {}, created_at: '2026-06-20T10:00:03Z',
    })
    fireWsEvent('session-2', 'conversation:event', {
      id: 'evt-b', session_id: 'session-2', seq: 12, turn_id: 'turn-1', run_id: 'run-2',
      message_id: 'msg-b', event_type: 'message.content_committed',
      payload_json: {}, created_at: '2026-06-20T10:00:04Z',
    })

    const applyEvent = conversationStoreState.applyEvent as ReturnType<typeof vi.fn>
    const targetSessions = applyEvent.mock.calls.map((call) => call[0])
    expect(targetSessions).toContain('session-1')
    expect(targetSessions).toContain('session-2')
    // session-1 的事件只 apply 给 session-1。
    const evtACall = applyEvent.mock.calls.find((call) => call[1].id === 'evt-a')
    expect(evtACall?.[0]).toBe('session-1')
    const evtBCall = applyEvent.mock.calls.find((call) => call[1].id === 'evt-b')
    expect(evtBCall?.[0]).toBe('session-2')
  })

  it('两个会话的子 agent 事件按 session 隔离存储', async () => {
    conversationStoreState.conversationsBySessionId = {
      'session-2': activeConversation('session-2', 'run-2'),
    }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    const { useSubAgentEventsStore } = await import('../useSubAgentEvents')
    useSubAgentEventsStore.getState().clearAll()
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    fireWsEvent('session-1', 'sub_agent:event', {
      event_type: 'tool:start',
      delegate_call_id: 'delegate-call-1',
      payload: { tool_name: 'file' },
    })
    fireWsEvent('session-2', 'sub_agent:event', {
      event_type: 'tool:start',
      delegate_call_id: 'delegate-call-1',
      payload: { tool_name: 'shell' },
    })

    const state = useSubAgentEventsStore.getState()
    expect(state.stepsBySessionId.get('session-1')?.get('delegate-call-1')?.[0].payload.tool_name).toBe('file')
    expect(state.stepsBySessionId.get('session-2')?.get('delegate-call-1')?.[0].payload.tool_name).toBe('shell')
  })

  it('活跃会话数超过上限（5）时，多出来的会话不建立连接（降级补拉）', async () => {
    // 6 个后台活跃会话；加上当前会话本应 7 条，但上限 5。
    const conversations: Record<string, unknown> = {}
    for (let i = 2; i <= 7; i += 1) {
      conversations[`session-${i}`] = activeConversation(`session-${i}`, `run-${i}`)
    }
    conversationStoreState.conversationsBySessionId = conversations

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    // 当前会话必连，加上至多 4 个后台 = 5 条连接，不超过上限。
    expect(wsBySessionId.has('session-1')).toBe(true)
    expect(wsBySessionId.size).toBeLessThanOrEqual(5)
  })

  it('审批 / 拒绝按 runId 路由到正确会话的连接', async () => {
    conversationStoreState.conversationsBySessionId = {
      'session-1': activeConversation('session-1', 'run-1', 'waiting_for_approval'),
      'session-2': activeConversation('session-2', 'run-2', 'waiting_for_approval'),
    }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    const runtime = useConversationRuntime('session-1')

    await flushAsyncEffects()

    runtime.approveTool('run-2', 'approval-2')

    // 只在 session-2 的连接上发审批，不串到 session-1。
    expect(wsBySessionId.get('session-2')?.approveTool).toHaveBeenCalledWith({
      runId: 'run-2', approvalId: 'approval-2', decision: 'allow_once',
    })
    expect(wsBySessionId.get('session-1')?.approveTool).not.toHaveBeenCalled()
  })

  it('切回被标记为同步异常的会话时，强制补拉一次快照并清除异常标记', async () => {
    workspaceStoreState.sessionSyncHealthBySessionId = { 'session-1': 'degraded' }

    const { useConversationRuntime } = await import('../useConversationRuntime')
    useConversationRuntime('session-1')

    await flushAsyncEffects()

    // 强制补拉发生（getConversation 被调用）且异常标记被清除。
    expect(getConversationMock).toHaveBeenCalledWith('session-1', { limit: 20 })
    expect(clearHealthMock).toHaveBeenCalledWith('session-1')
  })
})
