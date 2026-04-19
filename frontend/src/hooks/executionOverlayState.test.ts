import { describe, expect, it } from 'vitest'
import {
  createOverlayRuntimeState,
  resetOverlayRuntimeState,
  shouldResetOverlayForSessionChange,
} from './executionOverlayState'

describe('resetOverlayRuntimeState', () => {
  it('clears all transient refs when the active session is abandoned', () => {
    const state = createOverlayRuntimeState()

    state.llmStreaming = 'partial'
    state.summaryStarted = true
    state.finalMessageHandled = true
    state.currentStatusItemId = 'status-1'
    state.currentExecutionId = 'exec-1'
    state.activeSessionId = 'session-1'
    state.activeReceiptId = 'receipt-1'
    state.executionHasReceipts = true
    state.thoughtFlushed = true
    state.currentLlmMessageId = 'llm-1'
    state.currentAssistantMessageId = 'assistant-1'

    resetOverlayRuntimeState(state)

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
