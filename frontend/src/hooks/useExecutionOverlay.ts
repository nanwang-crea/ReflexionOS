import { useCallback, useRef, useState } from 'react'
import {
  buildReceiptDetail,
  type ActionReceiptDetail,
  type ActionReceiptStatus,
} from '@/components/execution/receiptUtils'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import {
  deriveSessionTitle,
  flattenRoundsToItems,
  finalizeReceiptItem,
  formatExecutionFailureMessage,
  trimRecentRounds,
  updateFirstMatchingDetail,
} from '@/features/workspace/messageFlow'
import { getReceiptFinalizeDelay } from '@/features/workspace/receiptTiming'
import { createStreamingBuffer } from '@/features/workspace/streamingBuffer'
import { createOverlayRuntimeState } from './executionOverlayState'
import type { WorkspaceChatItem, WorkspaceSessionRound } from '@/types/workspace'

const LONG_STREAM_FLUSH_INTERVAL_MS = 80

function createItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function normalizePersistedItem(item: WorkspaceChatItem): WorkspaceChatItem {
  return {
    ...item,
    isStreaming: false,
    transient: false,
  }
}

function createNow() {
  return new Date().toISOString()
}

export function useExecutionOverlay() {
  const [overlayItems, setOverlayItems] = useState<WorkspaceChatItem[]>([])
  const [activeRoundItems, setActiveRoundItems] = useState<WorkspaceChatItem[]>([])

  const overlayItemsRef = useRef<WorkspaceChatItem[]>([])
  const llmStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentStatusItemIdRef = useRef<string | null>(null)
  const currentExecutionIdRef = useRef<string | null>(null)
  const activeSessionIdRef = useRef<string | null>(null)
  const activeReceiptIdRef = useRef<string | null>(null)
  const activeReceiptVisibleAtRef = useRef<number | null>(null)
  const executionHasReceiptsRef = useRef(false)
  const thoughtFlushedRef = useRef(false)
  const currentLlmMessageIdRef = useRef<string | null>(null)
  const currentAssistantMessageIdRef = useRef<string | null>(null)
  const activeRoundRef = useRef<WorkspaceSessionRound | null>(null)
  const llmFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const summaryFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const setOverlayState = useCallback((
    updater: WorkspaceChatItem[] | ((items: WorkspaceChatItem[]) => WorkspaceChatItem[])
  ) => {
    setOverlayItems((current) => {
      const nextItems = typeof updater === 'function'
        ? updater(current)
        : updater
      overlayItemsRef.current = nextItems
      return nextItems
    })
  }, [])

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

  const getOverlayItem = useCallback((itemId: string) => (
    overlayItemsRef.current.find((item) => item.id === itemId) || null
  ), [])

  const addOverlayItem = useCallback((item: WorkspaceChatItem) => {
    setOverlayState((items) => [...items, item])
  }, [setOverlayState])

  const updateOverlayItem = useCallback((
    itemId: string,
    updater: (item: WorkspaceChatItem) => WorkspaceChatItem
  ) => {
    setOverlayState((items) => items.map((item) => (
      item.id === itemId
        ? updater(item)
        : item
    )))
  }, [setOverlayState])

  const removeOverlayItem = useCallback((itemId: string) => {
    setOverlayState((items) => items.filter((item) => item.id !== itemId))
  }, [setOverlayState])

  const clearFlushTimer = useCallback((timerRef: { current: ReturnType<typeof setTimeout> | null }) => {
    if (!timerRef.current) {
      return
    }

    clearTimeout(timerRef.current)
    timerRef.current = null
  }, [])

  const appendRoundItems = useCallback((items: WorkspaceChatItem[]) => {
    if (items.length === 0 || !activeRoundRef.current) {
      return
    }

    const nextRound = {
      ...activeRoundRef.current,
      items: [...activeRoundRef.current.items, ...items.map(normalizePersistedItem)],
    }
    activeRoundRef.current = nextRound
    setActiveRoundItems(nextRound.items)
  }, [])

  const persistActiveRound = useCallback((sessionId: string) => {
    const round = activeRoundRef.current
    if (!round || round.items.length === 0) {
      return
    }

    const state = useWorkspaceStore.getState()
    const session = state.sessions.find((item) => item.id === sessionId) || null
    if (!session) {
      return
    }

    const nextRounds = trimRecentRounds([...session.recentRounds, round])
    state.saveSessionRounds(sessionId, nextRounds)

    const nextTitle = deriveSessionTitle(flattenRoundsToItems(nextRounds))
    if (nextTitle && nextTitle !== session.title) {
      state.updateSessionTitle(sessionId, nextTitle)
    }
  }, [])

  const appendRoundItemsToActiveSession = useCallback((items: WorkspaceChatItem[]) => {
    if (items.length === 0) {
      return
    }

    appendRoundItems(items)
  }, [appendRoundItems])

  const finalizeActiveRound = useCallback((sessionId: string) => {
    persistActiveRound(sessionId)
    activeRoundRef.current = null
    setActiveRoundItems([])
  }, [persistActiveRound])

  const finalizeActiveReceipt = useCallback((forcedStatus?: ActionReceiptStatus) => {
    const sessionId = activeSessionIdRef.current
    const receiptId = activeReceiptIdRef.current

    if (!sessionId || !receiptId) {
      return
    }

    const receiptItem = getOverlayItem(receiptId)
    if (!receiptItem) {
      activeReceiptIdRef.current = null
      activeReceiptVisibleAtRef.current = null
      return
    }

    const completedReceipt = finalizeReceiptItem(receiptItem, forcedStatus)
    const finalizeNow = () => {
      appendRoundItemsToActiveSession([completedReceipt])
      removeOverlayItem(receiptId)
      activeReceiptIdRef.current = null
      activeReceiptVisibleAtRef.current = null
    }

    const delay = getReceiptFinalizeDelay(activeReceiptVisibleAtRef.current, Date.now())
    if (delay > 0) {
      setTimeout(finalizeNow, delay)
      return
    }

    finalizeNow()
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
    activeReceiptVisibleAtRef.current = Date.now()
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
      appendRoundItemsToActiveSession([
        {
        id: createItemId('update'),
        type: 'agent-update',
        content,
        },
      ])
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
      appendRoundItemsToActiveSession([
        {
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
        },
      ])
      finalizeActiveRound(sessionId)
    }

    currentLlmMessageIdRef.current = null
    currentStatusItemIdRef.current = null
  }, [appendRoundItemsToActiveSession, finalizeActiveRound, flushAllStreamingBuffers, getOverlayItem, removeOverlayItem])

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
      appendRoundItemsToActiveSession([
        {
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
        },
      ])
      finalizeActiveRound(sessionId)
    }

    currentAssistantMessageIdRef.current = null
  }, [appendRoundItemsToActiveSession, finalizeActiveRound, flushAllStreamingBuffers, getOverlayItem, removeOverlayItem])

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
    activeRoundRef.current = null
    activeReceiptVisibleAtRef.current = null
    setActiveRoundItems([])
    setOverlayState([])
    resetRuntimeRefs()
  }, [flushAllStreamingBuffers, resetRuntimeRefs, setOverlayState])

  const setCurrentExecutionId = useCallback((executionId: string | null) => {
    currentExecutionIdRef.current = executionId
  }, [])

  const prepareExecutionRun = useCallback((payload: {
    sessionId: string
    message: string
  }) => {
    const userItem: WorkspaceChatItem = {
      id: createItemId('user'),
      type: 'user-message',
      content: payload.message,
    }
    const statusItem: WorkspaceChatItem = {
      id: createItemId('status'),
      type: 'assistant-status',
      statusLabel: '正在思考中',
      transient: true,
    }

    setOverlayState([statusItem])
    activeRoundRef.current = {
      id: createItemId('round'),
      createdAt: createNow(),
      items: [normalizePersistedItem(userItem)],
    }
    setActiveRoundItems([normalizePersistedItem(userItem)])

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
  }, [setOverlayState])

  const handleConnectionFailure = useCallback((message: string) => {
    const sessionId = activeSessionIdRef.current

    flushStreamingAgentUpdate()
    finalizeActiveReceipt('failed')
    finalizeStreamingAssistantMessage()
    removeStatusBubble()

    if (sessionId && message) {
      appendRoundItemsToActiveSession([
        {
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: message,
        },
      ])
      finalizeActiveRound(sessionId)
    }

    clearTransientState()
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    finalizeActiveRound,
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
    finalizeActiveReceipt()
    finalizeStreamingAssistantMessage()

    if (data.status === 'failed') {
      removeStatusBubble()
      flushStreamingAgentUpdate()
      const failureMessage = formatExecutionFailureMessage(data.result)
      if (failureMessage && activeSessionIdRef.current) {
        appendRoundItemsToActiveSession([
          {
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: failureMessage,
          },
        ])
        finalizeActiveRound(activeSessionIdRef.current)
      }
      clearTransientState()
      return { failed: true }
    }

    if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
      finalizeStreamingLlmAsAssistant(data.result)
      finalMessageHandledRef.current = true
    } else {
      removeStatusBubble()
      flushStreamingAgentUpdate()
    }

    clearTransientState()
    return { failed: false }
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    finalizeActiveRound,
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
      appendRoundItemsToActiveSession([
        {
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: `错误: ${error}`,
        },
      ])
      finalizeActiveRound(sessionId)
    }

    clearTransientState()
  }, [
    appendRoundItemsToActiveSession,
    clearTransientState,
    finalizeActiveRound,
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
    activeRoundItems,
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
