import { useCallback, useRef } from 'react'
import {
  buildReceiptDetail,
  type ActionReceiptDetail,
  type ActionReceiptStatus,
} from '@/components/execution/receiptUtils'
import {
  finalizeReceiptItem,
  formatExecutionFailureMessage,
  updateFirstMatchingDetail,
} from '@/features/workspace/messageFlow'
import { createStreamingBuffer } from '@/features/workspace/streamingBuffer'
import { useExecutionOverlayUi } from './useExecutionOverlayUi'
import { createOverlayRuntimeState } from './executionOverlayState'
import type { WorkspaceChatItem } from '@/types/workspace'

const LONG_STREAM_FLUSH_INTERVAL_MS = 80

function createItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

interface ExecutionDraftRoundBindings {
  startDraftRound: (sessionId: string, message: string) => void
  appendItems: (items: WorkspaceChatItem[]) => void
  cancelDraftRound: () => void
  failDraftRound: () => void
}

export function useExecutionOverlay(draftRound: ExecutionDraftRoundBindings) {
  const {
    overlayItems,
    setOverlayState,
    addOverlayItem,
    updateOverlayItem,
    removeOverlayItem,
    getOverlayItem,
    clearOverlayItems,
  } = useExecutionOverlayUi()

  const llmStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentStatusItemIdRef = useRef<string | null>(null)
  const currentExecutionIdRef = useRef<string | null>(null)
  const activeSessionIdRef = useRef<string | null>(null)
  const activeReceiptIdRef = useRef<string | null>(null)
  const executionHasReceiptsRef = useRef(false)
  const thoughtFlushedRef = useRef(false)
  const currentLlmMessageIdRef = useRef<string | null>(null)
  const currentAssistantMessageIdRef = useRef<string | null>(null)
  const llmFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const summaryFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resetRuntimeRefs = useCallback(() => {
    const nextState = createOverlayRuntimeState()
    llmStreamingRef.current = nextState.llmStreaming
    summaryStartedRef.current = nextState.summaryStarted
    finalMessageHandledRef.current = nextState.finalMessageHandled
    currentStatusItemIdRef.current = nextState.currentStatusItemId
    currentExecutionIdRef.current = nextState.currentExecutionId
    activeSessionIdRef.current = nextState.activeSessionId
    activeReceiptIdRef.current = nextState.activeReceiptId
    executionHasReceiptsRef.current = nextState.executionHasReceipts
    thoughtFlushedRef.current = nextState.thoughtFlushed
    currentLlmMessageIdRef.current = nextState.currentLlmMessageId
    currentAssistantMessageIdRef.current = nextState.currentAssistantMessageId
  }, [])

  const clearFlushTimer = useCallback((timerRef: { current: ReturnType<typeof setTimeout> | null }) => {
    if (!timerRef.current) {
      return
    }

    clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const appendRoundItemsToActiveSession = useCallback((items: WorkspaceChatItem[]) => {
    if (items.length === 0) {
      return
    }

    draftRound.appendItems(items)
  }, [draftRound])

  const finalizeActiveReceipt = useCallback((forcedStatus?: ActionReceiptStatus) => {
    const receiptId = activeReceiptIdRef.current

    if (!receiptId) {
      return
    }

    const receiptItem = getOverlayItem(receiptId)
    if (!receiptItem) {
      activeReceiptIdRef.current = null
      return
    }

    const completedReceipt = finalizeReceiptItem(receiptItem, forcedStatus)
    appendRoundItemsToActiveSession([completedReceipt])
    removeOverlayItem(receiptId)
    activeReceiptIdRef.current = null
  }, [appendRoundItemsToActiveSession, getOverlayItem, removeOverlayItem])

  const ensureReceiptItem = useCallback(() => {
    if (activeReceiptIdRef.current) {
      return activeReceiptIdRef.current
    }

    const receiptId = createItemId('receipt')
    addOverlayItem({
      id: receiptId,
      type: 'action-receipt',
      receiptStatus: 'running',
      details: [],
      transient: true,
    })
    activeReceiptIdRef.current = receiptId
    return receiptId
  }, [addOverlayItem])

  const updateStatusBubble = useCallback((label: string) => {
    if (!currentStatusItemIdRef.current) {
      return
    }

    updateOverlayItem(currentStatusItemIdRef.current, (item) => (
      item.type === 'assistant-status'
        ? {
            ...item,
            statusLabel: label,
          }
        : item
    ))
  }, [updateOverlayItem])

  const removeStatusBubble = useCallback(() => {
    if (!currentStatusItemIdRef.current) {
      return
    }

    removeOverlayItem(currentStatusItemIdRef.current)
    currentStatusItemIdRef.current = null
  }, [removeOverlayItem])

  const ensureStreamingLlmMessage = useCallback((initialContent = '') => {
    if (currentLlmMessageIdRef.current) {
      return currentLlmMessageIdRef.current
    }

    if (currentStatusItemIdRef.current) {
      const messageId = currentStatusItemIdRef.current
      updateOverlayItem(messageId, (item) => ({
        ...item,
        type: 'agent-update',
        content: initialContent,
        isStreaming: true,
        transient: true,
      }))
      currentLlmMessageIdRef.current = messageId
      currentStatusItemIdRef.current = null
      return messageId
    }

    const messageId = createItemId('llm')
    addOverlayItem({
      id: messageId,
      type: 'agent-update',
      content: initialContent,
      isStreaming: true,
      transient: true,
    })
    currentLlmMessageIdRef.current = messageId
    return messageId
  }, [addOverlayItem, updateOverlayItem])

  const appendStreamingLlmToken = useCallback((token: string) => {
    const messageId = ensureStreamingLlmMessage()
    updateOverlayItem(messageId, (item) => ({
      ...item,
      content: `${item.content || ''}${token}`,
      isStreaming: true,
      transient: true,
    }))
  }, [ensureStreamingLlmMessage, updateOverlayItem])

  const flushAllStreamingBuffers = useCallback(() => {
    clearFlushTimer(llmFlushTimerRef)
    clearFlushTimer(summaryFlushTimerRef)
    llmBufferRef.current.flush()
    summaryBufferRef.current.flush()
  }, [clearFlushTimer])

  const flushStreamingAgentUpdate = useCallback((fallbackContent = '') => {
    const sessionId = activeSessionIdRef.current
    flushAllStreamingBuffers()
    const content = (llmStreamingRef.current || fallbackContent).trim()

    if (!content) {
      llmStreamingRef.current = ''
      if (currentLlmMessageIdRef.current) {
        removeOverlayItem(currentLlmMessageIdRef.current)
        currentLlmMessageIdRef.current = null
      }
      return
    }

    if (sessionId) {
      appendRoundItemsToActiveSession([{
        id: createItemId('update'),
        type: 'agent-update',
        content,
      }])
    }

    if (currentLlmMessageIdRef.current) {
      removeOverlayItem(currentLlmMessageIdRef.current)
    }

    currentLlmMessageIdRef.current = null
    llmStreamingRef.current = ''
    thoughtFlushedRef.current = true
  }, [appendRoundItemsToActiveSession, flushAllStreamingBuffers, removeOverlayItem])

  const finalizeStreamingLlmAsAssistant = useCallback((finalContent?: string) => {
    const sessionId = activeSessionIdRef.current
    flushAllStreamingBuffers()
    const messageId = currentLlmMessageIdRef.current || currentStatusItemIdRef.current
    const sourceItem = messageId ? getOverlayItem(messageId) : null
    const content = (finalContent || sourceItem?.content || '').trim()

    if (messageId) {
      removeOverlayItem(messageId)
    }

    if (sessionId && content) {
      appendRoundItemsToActiveSession([{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
      }])
    }

    currentLlmMessageIdRef.current = null
    currentStatusItemIdRef.current = null
  }, [appendRoundItemsToActiveSession, flushAllStreamingBuffers, getOverlayItem, removeOverlayItem])

  const ensureStreamingAssistantMessage = useCallback((initialContent = '') => {
    if (currentAssistantMessageIdRef.current) {
      return currentAssistantMessageIdRef.current
    }

    if (!executionHasReceiptsRef.current) {
      const messageId = currentLlmMessageIdRef.current || currentStatusItemIdRef.current

      if (messageId) {
        updateOverlayItem(messageId, (item) => ({
          ...item,
          type: 'assistant-message',
          content: initialContent || item.content || '',
          isStreaming: true,
          transient: true,
        }))
        currentAssistantMessageIdRef.current = messageId
        currentLlmMessageIdRef.current = null
        currentStatusItemIdRef.current = null
        return messageId
      }
    }

    const messageId = createItemId('assistant')
    addOverlayItem({
      id: messageId,
      type: 'assistant-message',
      content: initialContent,
      isStreaming: true,
      transient: true,
    })
    currentAssistantMessageIdRef.current = messageId
    return messageId
  }, [addOverlayItem, updateOverlayItem])

  const appendStreamingAssistantToken = useCallback((token: string) => {
    const messageId = ensureStreamingAssistantMessage()
    updateOverlayItem(messageId, (item) => ({
      ...item,
      content: `${item.content || ''}${token}`,
      isStreaming: true,
      transient: true,
    }))
  }, [ensureStreamingAssistantMessage, updateOverlayItem])

  const llmBufferRef = useRef(createStreamingBuffer({
    onFlush: (chunk) => {
      appendStreamingLlmToken(chunk)
    },
  }))

  const summaryBufferRef = useRef(createStreamingBuffer({
    onFlush: (chunk) => {
      appendStreamingAssistantToken(chunk)
    },
  }))

  const scheduleBufferedFlush = useCallback((
    timerRef: { current: ReturnType<typeof setTimeout> | null },
    flush: () => void
  ) => {
    if (timerRef.current) {
      return
    }

    timerRef.current = setTimeout(() => {
      timerRef.current = null
      flush()
    }, LONG_STREAM_FLUSH_INTERVAL_MS)
  }, [])

  const finalizeStreamingAssistantMessage = useCallback((finalContent?: string) => {
    const sessionId = activeSessionIdRef.current
    flushAllStreamingBuffers()
    const messageId = currentAssistantMessageIdRef.current
    const sourceItem = messageId ? getOverlayItem(messageId) : null
    const content = (finalContent || sourceItem?.content || '').trim()

    if (messageId) {
      removeOverlayItem(messageId)
    }

    if (sessionId && content) {
      appendRoundItemsToActiveSession([{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
      }])
    }

    currentAssistantMessageIdRef.current = null
  }, [appendRoundItemsToActiveSession, flushAllStreamingBuffers, getOverlayItem, removeOverlayItem])

  const appendReceiptDetail = useCallback((toolName: string, args?: Record<string, unknown>) => {
    const receiptId = ensureReceiptItem()
    const detail = buildReceiptDetail(createItemId('detail'), toolName, args)

    updateOverlayItem(receiptId, (item) => ({
      ...item,
      receiptStatus: 'running',
      details: [...(item.details || []), detail],
      transient: true,
    }))
  }, [ensureReceiptItem, updateOverlayItem])

  const updateActiveReceiptDetail = useCallback((
    toolName: string,
    updater: (detail: ActionReceiptDetail) => ActionReceiptDetail
  ) => {
    if (!activeReceiptIdRef.current) {
      return
    }

    updateOverlayItem(activeReceiptIdRef.current, (item) => ({
      ...item,
      details: updateFirstMatchingDetail(
        item.details || [],
        (detail) => detail.toolName === toolName && (
          detail.status === 'pending' || detail.status === 'running'
        ),
        updater
      ),
      transient: true,
    }))
  }, [updateOverlayItem])

  const clearTransientState = useCallback(() => {
    flushAllStreamingBuffers()
    llmBufferRef.current.reset()
    summaryBufferRef.current.reset()
    clearOverlayItems()
    resetRuntimeRefs()
  }, [clearOverlayItems, flushAllStreamingBuffers, resetRuntimeRefs])

  const setCurrentExecutionId = useCallback((executionId: string | null) => {
    currentExecutionIdRef.current = executionId
  }, [])

  const prepareExecutionRun = useCallback((payload: {
    sessionId: string
    message: string
  }) => {
    const statusItem: WorkspaceChatItem = {
      id: createItemId('status'),
      type: 'assistant-status',
      statusLabel: '正在思考中',
      transient: true,
    }

    setOverlayState([statusItem])
    draftRound.startDraftRound(payload.sessionId, payload.message)

    llmStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    executionHasReceiptsRef.current = false
    thoughtFlushedRef.current = false
    currentStatusItemIdRef.current = statusItem.id
    currentLlmMessageIdRef.current = null
    currentAssistantMessageIdRef.current = null
    currentExecutionIdRef.current = null
    activeSessionIdRef.current = payload.sessionId
  }, [draftRound, setOverlayState])

  const handleConnectionFailure = useCallback((message: string) => {
    const sessionId = activeSessionIdRef.current

    flushStreamingAgentUpdate()
    finalizeActiveReceipt('failed')
    finalizeStreamingAssistantMessage()
    removeStatusBubble()

    if (sessionId && message) {
      appendRoundItemsToActiveSession([{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: message,
      }])
    }

    draftRound.failDraftRound()
    clearTransientState()
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    draftRound,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    flushStreamingAgentUpdate,
    removeStatusBubble,
  ])

  const handleLlmStart = useCallback(() => {
    finalizeActiveReceipt()
    thoughtFlushedRef.current = false
    llmStreamingRef.current = ''
    llmBufferRef.current.reset()
    clearFlushTimer(llmFlushTimerRef)
    updateStatusBubble('正在思考中')
  }, [clearFlushTimer, finalizeActiveReceipt, updateStatusBubble])

  const handleLlmContent = useCallback((content: string) => {
    llmStreamingRef.current += content
    llmBufferRef.current.push(content)
    scheduleBufferedFlush(llmFlushTimerRef, () => {
      llmBufferRef.current.flush()
    })
  }, [scheduleBufferedFlush])

  const handleLlmThought = useCallback((content: string) => {
    flushStreamingAgentUpdate(content)
  }, [flushStreamingAgentUpdate])

  const handleToolCall = useCallback((data: {
    tool_name: string
    arguments: object
    thought: string
  }) => {
    if (!thoughtFlushedRef.current) {
      flushStreamingAgentUpdate(data.thought)
    }

    executionHasReceiptsRef.current = true
    removeStatusBubble()
    appendReceiptDetail(data.tool_name, data.arguments as Record<string, unknown>)
  }, [appendReceiptDetail, flushStreamingAgentUpdate, removeStatusBubble])

  const handleToolStart = useCallback((toolName: string) => {
    updateActiveReceiptDetail(toolName, (detail) => ({
      ...detail,
      status: 'running',
    }))
  }, [updateActiveReceiptDetail])

  const handleToolResult = useCallback((data: {
    tool_name: string
    success: boolean
    output?: string
    error?: string
    duration: number
  }) => {
    updateActiveReceiptDetail(data.tool_name, (detail) => ({
      ...detail,
      status: data.success ? 'success' : 'failed',
      output: data.output,
      error: data.error,
      duration: data.duration,
    }))
  }, [updateActiveReceiptDetail])

  const handleToolError = useCallback((toolName: string, error: string) => {
    updateActiveReceiptDetail(toolName, (detail) => ({
      ...detail,
      status: 'failed',
      error,
    }))
  }, [updateActiveReceiptDetail])

  const handleSummaryStart = useCallback(() => {
    finalizeActiveReceipt()
    summaryStartedRef.current = true
    summaryBufferRef.current.reset()
    clearFlushTimer(summaryFlushTimerRef)
    if (executionHasReceiptsRef.current) {
      removeStatusBubble()
    }
    ensureStreamingAssistantMessage('')
  }, [clearFlushTimer, ensureStreamingAssistantMessage, finalizeActiveReceipt, removeStatusBubble])

  const handleSummaryToken = useCallback((token: string) => {
    summaryBufferRef.current.push(token)
    scheduleBufferedFlush(summaryFlushTimerRef, () => {
      summaryBufferRef.current.flush()
    })
  }, [scheduleBufferedFlush])

  const handleSummaryComplete = useCallback((summary: string) => {
    finalizeActiveReceipt()
    finalizeStreamingAssistantMessage(summary)
    finalMessageHandledRef.current = true
    summaryStartedRef.current = false
  }, [finalizeActiveReceipt, finalizeStreamingAssistantMessage])

  const handleExecutionCancelled = useCallback(() => {
    flushStreamingAgentUpdate()
    finalizeActiveReceipt('cancelled')
    finalizeStreamingAssistantMessage()
    removeStatusBubble()
    clearTransientState()
  }, [
    clearTransientState,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    flushStreamingAgentUpdate,
    removeStatusBubble,
  ])

  const handleExecutionComplete = useCallback((data: {
    status: string
    result: string
  }) => {
    const sessionId = activeSessionIdRef.current

    finalizeActiveReceipt()
    finalizeStreamingAssistantMessage()

    if (data.status === 'failed') {
      removeStatusBubble()
      flushStreamingAgentUpdate()
      const failureMessage = formatExecutionFailureMessage(data.result)
      if (failureMessage && sessionId) {
        appendRoundItemsToActiveSession([{
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: failureMessage,
        }])
      }
      clearTransientState()
      return { failed: true, sessionId }
    }

    if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
      finalizeStreamingLlmAsAssistant(data.result)
      finalMessageHandledRef.current = true
    } else {
      removeStatusBubble()
      flushStreamingAgentUpdate()
    }

    clearTransientState()
    return { failed: false, sessionId }
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    finalizeStreamingLlmAsAssistant,
    flushStreamingAgentUpdate,
    removeStatusBubble,
  ])

  const handleExecutionError = useCallback((error: string) => {
    const sessionId = activeSessionIdRef.current

    flushStreamingAgentUpdate()
    finalizeActiveReceipt('failed')
    finalizeStreamingAssistantMessage()
    removeStatusBubble()

    if (sessionId) {
      appendRoundItemsToActiveSession([{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: `错误: ${error}`,
      }])
    }

    clearTransientState()
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    flushStreamingAgentUpdate,
    removeStatusBubble,
  ])

  const resetExecutionOverlay = useCallback(() => {
    clearTransientState()
  }, [clearTransientState])

  return {
    overlayItems,
    currentExecutionIdRef,
    activeSessionIdRef,
    setCurrentExecutionId,
    prepareExecutionRun,
    handleConnectionFailure,
    handleLlmStart,
    handleLlmContent,
    handleLlmThought,
    handleToolCall,
    handleToolStart,
    handleToolResult,
    handleToolError,
    handleSummaryStart,
    handleSummaryToken,
    handleSummaryComplete,
    handleExecutionCancelled,
    handleExecutionComplete,
    handleExecutionError,
    resetExecutionOverlay,
  }
}
