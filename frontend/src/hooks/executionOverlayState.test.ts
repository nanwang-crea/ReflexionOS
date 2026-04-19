import { describe, expect, it } from 'vitest'
import {
  createOverlayRuntimeState,
  shouldResetOverlayForSessionChange,
} from './executionOverlayState'

describe('createOverlayRuntimeState', () => {
  it('creates a clean transient runtime state object', () => {
    const state = createOverlayRuntimeState()

    expect(state).toEqual({
      llmStreaming: '',
      summaryStarted: false,
      finalMessageHandled: false,
      currentStatusItemId: null,
      currentExecutionId: null,
      activeSessionId: null,
      activeReceiptId: null,
      executionHasReceipts: false,
      thoughtFlushed: false,
      currentLlmMessageId: null,
      currentAssistantMessageId: null,
    })
  })
})

describe('shouldResetOverlayForSessionChange', () => {
  it('resets when the current session changes away from the active execution session', () => {
    expect(shouldResetOverlayForSessionChange('session-b', 'session-a')).toBe(true)
  })

  it('does not reset when there is no active execution session or the session is unchanged', () => {
    expect(shouldResetOverlayForSessionChange('session-a', 'session-a')).toBe(false)
    expect(shouldResetOverlayForSessionChange(null, 'session-a')).toBe(true)
    expect(shouldResetOverlayForSessionChange('session-a', null)).toBe(false)
  })
})
