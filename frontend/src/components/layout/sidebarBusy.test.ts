import { describe, expect, it } from 'vitest'
import { isConversationBusy } from './sidebarBusy'

describe('isConversationBusy', () => {
  it('returns false when there is no conversation state', () => {
    expect(isConversationBusy(undefined)).toBe(false)
  })

  it('returns true when the active run is still running', () => {
    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'running' } },
    })).toBe(true)
  })

  it('returns false when there is no active running or created run', () => {
    expect(isConversationBusy({
      session: { activeTurnId: 'turn-1' },
      turnsById: { 'turn-1': { activeRunId: 'run-1' } },
      runsById: { 'run-1': { status: 'completed' } },
    })).toBe(false)
  })
})
