import { describe, expect, it } from 'vitest'
import { createExecutionDraftRoundState } from './useExecutionDraftRound'

describe('createExecutionDraftRoundState', () => {
  it('clears draft on complete', () => {
    const state = createExecutionDraftRoundState()

    state.startDraftRound('session-1', 'hello')

    expect(state.items).toHaveLength(1)
    expect(state.items[0]?.type).toBe('user-message')

    state.completeDraftRound()

    expect(state.items).toEqual([])
  })

  it('discards draft on cancellation', () => {
    const state = createExecutionDraftRoundState()

    state.startDraftRound('session-1', 'hello')
    state.appendItems([
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: 'partial',
      },
    ])

    state.cancelDraftRound()

    expect(state.items).toEqual([])
  })

  it('clears draft on failure', () => {
    const state = createExecutionDraftRoundState()

    state.startDraftRound('session-1', 'hello')
    state.appendItems([
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: '错误: failed',
      },
    ])

    state.failDraftRound()

    expect(state.sessionId).toBeNull()
    expect(state.items).toEqual([])
  })
})
