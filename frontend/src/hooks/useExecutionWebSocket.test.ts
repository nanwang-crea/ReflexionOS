import { describe, expect, it, vi } from 'vitest'
import { runExecutionCompleteSequence, runExecutionErrorSequence } from './useExecutionWebSocket'

describe('runExecutionCompleteSequence', () => {
  it('clears draft and refreshes history before failing execution', async () => {
    const calls: string[] = []
    const overlay = {
      handleExecutionComplete: vi.fn(() => {
        calls.push('overlay:complete')
        return { failed: true, sessionId: 'session-1' }
      }),
    }
    const draftRound = {
      clearDraftRound: vi.fn(async () => {
        calls.push('draft:clear')
      }),
      refreshSessionHistory: vi.fn(async () => {
        calls.push('history:refresh')
      }),
    }
    const execution = {
      completeExecution: vi.fn(() => {
        calls.push('execution:complete')
      }),
      failExecution: vi.fn(() => {
        calls.push('execution:fail')
      }),
    }

    await runExecutionCompleteSequence(
      { status: 'failed', result: 'boom' },
      overlay,
      draftRound,
      execution
    )

    expect(calls).toEqual([
      'overlay:complete',
      'draft:clear',
      'history:refresh',
      'execution:fail',
    ])
    expect(execution.completeExecution).not.toHaveBeenCalled()
  })

  it('uses the explicit refresh path for completed executions with a session id', async () => {
    const draftRound = {
      clearDraftRound: vi.fn(),
      refreshSessionHistory: vi.fn(async () => {}),
    }

    await runExecutionCompleteSequence(
      { status: 'completed', result: 'ok' },
      {
        handleExecutionComplete: vi.fn(() => ({ failed: false, sessionId: 'session-1' })),
      },
      draftRound,
      {
        completeExecution: vi.fn(),
        failExecution: vi.fn(),
      }
    )

    expect(draftRound.refreshSessionHistory).toHaveBeenCalledWith('session-1')
  })

  it('completes execution even when history refresh fails', async () => {
    const execution = {
      completeExecution: vi.fn(),
      failExecution: vi.fn(),
    }

    await runExecutionCompleteSequence(
      { status: 'completed', result: 'ok' },
      {
        handleExecutionComplete: vi.fn(() => ({ failed: false, sessionId: 'session-1' })),
      },
      {
        clearDraftRound: vi.fn(),
        refreshSessionHistory: vi.fn(async () => {
          throw new Error('refresh failed')
        }),
      },
      execution
    )

    expect(execution.completeExecution).toHaveBeenCalledTimes(1)
    expect(execution.failExecution).not.toHaveBeenCalled()
  })
})

describe('runExecutionErrorSequence', () => {
  it('clears failed draft and refreshes history before failing execution', async () => {
    const calls: string[] = []
    const overlay = {
      activeSessionIdRef: { current: 'session-1' },
      handleExecutionError: vi.fn(() => {
        calls.push('overlay:error')
      }),
    }
    const draftRound = {
      clearDraftRound: vi.fn(() => {
        calls.push('draft:clear-failed')
      }),
      refreshSessionHistory: vi.fn(async () => {
        calls.push('history:refresh')
      }),
    }
    const execution = {
      failExecution: vi.fn(() => {
        calls.push('execution:fail')
      }),
    }

    await runExecutionErrorSequence('boom', overlay, draftRound, execution)

    expect(calls).toEqual([
      'overlay:error',
      'draft:clear-failed',
      'history:refresh',
      'execution:fail',
    ])
  })

  it('fails execution even when history refresh fails', async () => {
    const execution = {
      failExecution: vi.fn(),
    }

    await runExecutionErrorSequence(
      'boom',
      {
        activeSessionIdRef: { current: 'session-1' },
        handleExecutionError: vi.fn(),
      },
      {
        clearDraftRound: vi.fn(),
        refreshSessionHistory: vi.fn(async () => {
          throw new Error('refresh failed')
        }),
      },
      execution
    )

    expect(execution.failExecution).toHaveBeenCalledTimes(1)
  })
})
