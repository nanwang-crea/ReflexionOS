import { describe, expect, it } from 'vitest'
import { createExecutionDraftRoundState } from './useExecutionDraftRound'

describe('createExecutionDraftRoundState', () => {
  it('exposes only clearDraftRound as the terminal draft API', () => {
    const state = createExecutionDraftRoundState()

    expect(state.clearDraftRound).toEqual(expect.any(Function))
    expect('completeDraftRound' in state).toBe(false)
    expect('cancelDraftRound' in state).toBe(false)
    expect('failDraftRound' in state).toBe(false)
  })

  it('clears draft state', () => {
    const state = createExecutionDraftRoundState()

    state.startDraftRound('session-1', 'hello')

    expect(state.items).toHaveLength(1)
    expect(state.items[0]?.type).toBe('user-message')

    state.clearDraftRound()

    expect(state.sessionId).toBeNull()
    expect(state.items).toEqual([])
  })

  it('clears appended draft items', () => {
    const state = createExecutionDraftRoundState()

    state.startDraftRound('session-1', 'hello')
    state.appendItems([
      {
        id: 'assistant-1',
        type: 'assistant-message',
        content: 'partial',
      },
    ])

    state.clearDraftRound()

    expect(state.sessionId).toBeNull()
    expect(state.items).toEqual([])
  })
})
