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
      completeDraftRound: vi.fn(async () => {
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
      failDraftRound: vi.fn(() => {
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
})
