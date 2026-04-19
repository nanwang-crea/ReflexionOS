interface OverlayRuntimeState {
  llmStreaming: string
  summaryStarted: boolean
  finalMessageHandled: boolean
  currentStatusItemId: string | null
  currentExecutionId: string | null
  activeSessionId: string | null
  activeReceiptId: string | null
  executionHasReceipts: boolean
  thoughtFlushed: boolean
  currentLlmMessageId: string | null
  currentAssistantMessageId: string | null
}

export function createOverlayRuntimeState(): OverlayRuntimeState {
  return {
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
  }
}

export function shouldResetOverlayForSessionChange(
  currentSessionId: string | null,
  activeSessionId: string | null
) {
  return Boolean(activeSessionId && currentSessionId !== activeSessionId)
}
