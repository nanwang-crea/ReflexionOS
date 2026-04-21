import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createOverlayRuntimeState,
  shouldResetOverlayForSessionChange,
} from './executionOverlayState'
import {
  createAssistantMessageItem,
  createExecutionRunState,
  createOverlayItemId,
  createReceiptOverlayItem,
  createStatusOverlayItem,
} from './executionOverlayHelpers'

afterEach(() => {
  vi.restoreAllMocks()
})

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

describe('createOverlayItemId', () => {
  it('builds a prefixed id from timestamp and random suffix', () => {
    vi.spyOn(Date, 'now').mockReturnValue(123456789)

    expect(createOverlayItemId('receipt')).toMatch(/^receipt-123456789-[a-z0-9]+$/)
  })
})

describe('createStatusOverlayItem', () => {
  it('creates a transient assistant status item with generated id', () => {
    vi.spyOn(Date, 'now').mockReturnValue(100)

    expect(createStatusOverlayItem('正在思考中')).toEqual({
      id: expect.stringMatching(/^status-100-[a-z0-9]+$/),
      type: 'assistant-status',
      statusLabel: '正在思考中',
      transient: true,
    })
  })
})

describe('createReceiptOverlayItem', () => {
  it('creates a transient running receipt item with empty details', () => {
    vi.spyOn(Date, 'now').mockReturnValue(200)

    expect(createReceiptOverlayItem()).toEqual({
      id: expect.stringMatching(/^receipt-200-[a-z0-9]+$/),
      type: 'action-receipt',
      receiptStatus: 'running',
      details: [],
      transient: true,
    })
  })
})

describe('createAssistantMessageItem', () => {
  it('creates an assistant message item with provided content', () => {
    vi.spyOn(Date, 'now').mockReturnValue(300)

    expect(createAssistantMessageItem('hello')).toEqual({
      id: expect.stringMatching(/^assistant-300-[a-z0-9]+$/),
      type: 'assistant-message',
      content: 'hello',
    })
  })
})

describe('createExecutionRunState', () => {
  it('returns a status item and matching runtime reset for a new session', () => {
    vi.spyOn(Date, 'now').mockReturnValue(400)

    const state = createExecutionRunState('session-1')

    expect(state.statusItem).toEqual({
      id: expect.stringMatching(/^status-400-[a-z0-9]+$/),
      type: 'assistant-status',
      statusLabel: '正在思考中',
      transient: true,
    })
    expect(state.runtimeState).toMatchObject({
      llmStreaming: '',
      summaryStarted: false,
      finalMessageHandled: false,
      currentExecutionId: null,
      activeSessionId: 'session-1',
      activeReceiptId: null,
      executionHasReceipts: false,
      thoughtFlushed: false,
      currentLlmMessageId: null,
      currentAssistantMessageId: null,
    })
    expect(state.runtimeState.currentStatusItemId).toBe(state.statusItem.id)
  })
})
