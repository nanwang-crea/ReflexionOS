import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  ensureSessionHistoryLoadedMock,
  refreshSessionHistoryMock,
  useExecutionWebSocketMock,
  executionStoreState,
  draftRoundState,
  overlayState,
} = vi.hoisted(() => ({
  ensureSessionHistoryLoadedMock: vi.fn(),
  refreshSessionHistoryMock: vi.fn(),
  useExecutionWebSocketMock: vi.fn(),
  executionStoreState: {
    phase: null as string | null,
    startExecution: vi.fn(),
    setStatus: vi.fn(),
    setPhase: vi.fn(),
    setCanCancel: vi.fn(),
    setThinkingPhase: vi.fn(),
    setExecutingPhase: vi.fn(),
    setSummarizingPhase: vi.fn(),
    startCancelling: vi.fn(),
    completeExecution: vi.fn(),
    failExecution: vi.fn(),
    cancelExecution: vi.fn(),
    resetExecution: vi.fn(),
  },
  draftRoundState: {
    items: [],
    sessionIdRef: { current: null as string | null },
    startDraftRound: vi.fn(),
    appendItems: vi.fn(),
    clearDraftRound: vi.fn(),
  },
  overlayState: {
    overlayItems: [],
    currentExecutionIdRef: { current: null as string | null },
    activeSessionIdRef: { current: null as string | null },
    prepareExecutionRun: vi.fn(),
    resetExecutionOverlay: vi.fn(),
  },
}))

vi.mock('react', () => ({
  useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => {
    effect()
  },
}))

vi.mock('@/features/sessions/sessionLoader', () => ({
  ensureSessionHistoryLoaded: ensureSessionHistoryLoadedMock,
  refreshSessionHistory: refreshSessionHistoryMock,
}))

vi.mock('@/services/apiClient', () => ({
  agentApi: {
    cancel: vi.fn(),
  },
}))

vi.mock('@/stores/executionStore', () => ({
  useExecutionStore: () => executionStoreState,
}))

vi.mock('./useExecutionDraftRound', () => ({
  useExecutionDraftRound: () => draftRoundState,
}))

vi.mock('./useExecutionOverlay', () => ({
  useExecutionOverlay: () => overlayState,
}))

vi.mock('./useExecutionWebSocket', () => ({
  useExecutionWebSocket: useExecutionWebSocketMock,
}))

describe('useExecutionRuntime', () => {
  beforeEach(() => {
    ensureSessionHistoryLoadedMock.mockReset()
    refreshSessionHistoryMock.mockReset()
    useExecutionWebSocketMock.mockReset()
    useExecutionWebSocketMock.mockReturnValue({
      connectionStatus: 'disconnected',
      connectWebSocket: vi.fn(),
      startSocketExecution: vi.fn(),
      closeWebSocket: vi.fn(),
    })
  })

  it('wires refreshSessionHistory into the websocket draftRound bindings', async () => {
    const { useExecutionRuntime } = await import('./useExecutionRuntime')

    useExecutionRuntime('session-1')

    expect(useExecutionWebSocketMock).toHaveBeenCalledWith(
      expect.objectContaining({
        draftRound: expect.objectContaining({
          clearDraftRound: draftRoundState.clearDraftRound,
          refreshSessionHistory: refreshSessionHistoryMock,
        }),
      })
    )
  })

  it('exposes loadSessionHistory with ensure semantics', async () => {
    const { useExecutionRuntime } = await import('./useExecutionRuntime')

    const runtime = useExecutionRuntime('session-1')

    await runtime.loadSessionHistory('session-2')

    expect(ensureSessionHistoryLoadedMock).toHaveBeenCalledWith('session-2')
  })
})
