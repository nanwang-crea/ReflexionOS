import { useCallback, useEffect, useRef, useState } from 'react'
import { agentApi } from '@/services/apiClient'
import { ExecutionWebSocket } from '@/services/websocketClient'
import {
  buildReceiptDetail,
  type ActionReceiptDetail,
  type ActionReceiptStatus,
} from '@/components/execution/receiptUtils'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import {
  deriveSessionTitle,
  finalizeReceiptItem,
  updateFirstMatchingDetail,
} from '@/features/workspace/messageFlow'
import type { ConnectionStatus } from '@/features/workspace/types'
import type { WorkspaceChatItem } from '@/types/workspace'

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

export function useExecutionRuntime(
  currentSessionId: string | null,
  initialConnectionStatus: ConnectionStatus = 'disconnected'
) {
  const {
    phase,
    startExecution,
    setStatus,
    setPhase,
    setCanCancel,
    setThinkingPhase,
    setExecutingPhase,
    setSummarizingPhase,
    startCancelling,
    completeExecution,
    failExecution,
    cancelExecution,
    resetExecution,
  } = useExecutionStore()

  const [overlayItems, setOverlayItems] = useState<WorkspaceChatItem[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(initialConnectionStatus)

  const overlayItemsRef = useRef<WorkspaceChatItem[]>([])
  const wsRef = useRef<ExecutionWebSocket | null>(null)
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
    llmStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    currentStatusItemIdRef.current = null
    currentExecutionIdRef.current = null
    activeSessionIdRef.current = null
    activeReceiptIdRef.current = null
    executionHasReceiptsRef.current = false
    thoughtFlushedRef.current = false
    currentLlmMessageIdRef.current = null
    currentAssistantMessageIdRef.current = null
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

  const appendPersistedItems = useCallback((sessionId: string, items: WorkspaceChatItem[]) => {
    if (items.length === 0) {
      return
    }

    const state = useWorkspaceStore.getState()
    const session = state.sessions.find((item) => item.id === sessionId) || null
    if (!session) {
      return
    }

    const normalizedItems = items.map(normalizePersistedItem)
    const nextItems = [...session.items, ...normalizedItems]

    state.saveSessionItems(sessionId, nextItems)

    const nextTitle = deriveSessionTitle(nextItems)
    if (nextTitle && nextTitle !== session.title) {
      state.updateSessionTitle(sessionId, nextTitle)
    }
  }, [])

  const finalizeActiveReceipt = useCallback((forcedStatus?: ActionReceiptStatus) => {
    const sessionId = activeSessionIdRef.current
    const receiptId = activeReceiptIdRef.current

    if (!sessionId || !receiptId) {
      return
    }

    const receiptItem = getOverlayItem(receiptId)
    if (!receiptItem) {
      activeReceiptIdRef.current = null
      return
    }

    appendPersistedItems(sessionId, [
      finalizeReceiptItem(receiptItem, forcedStatus),
    ])
    removeOverlayItem(receiptId)
    activeReceiptIdRef.current = null
  }, [appendPersistedItems, getOverlayItem, removeOverlayItem])

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

  const flushStreamingAgentUpdate = useCallback((fallbackContent = '') => {
    const sessionId = activeSessionIdRef.current
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
      appendPersistedItems(sessionId, [{
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
  }, [appendPersistedItems, removeOverlayItem])

  const finalizeStreamingLlmAsAssistant = useCallback((finalContent?: string) => {
    const sessionId = activeSessionIdRef.current
    const messageId = currentLlmMessageIdRef.current || currentStatusItemIdRef.current
    const sourceItem = messageId ? getOverlayItem(messageId) : null
    const content = (finalContent || sourceItem?.content || '').trim()

    if (messageId) {
      removeOverlayItem(messageId)
    }

    if (sessionId && content) {
      appendPersistedItems(sessionId, [{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
      }])
    }

    currentLlmMessageIdRef.current = null
    currentStatusItemIdRef.current = null
  }, [appendPersistedItems, getOverlayItem, removeOverlayItem])

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
    const messageId = currentAssistantMessageIdRef.current
    const sourceItem = messageId ? getOverlayItem(messageId) : null
    const content = (finalContent || sourceItem?.content || '').trim()

    if (messageId) {
      removeOverlayItem(messageId)
    }

    if (sessionId && content) {
      appendPersistedItems(sessionId, [{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content,
      }])
    }

    currentAssistantMessageIdRef.current = null
  }, [appendPersistedItems, getOverlayItem, removeOverlayItem])

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
    setOverlayState([])
    resetRuntimeRefs()
  }, [resetRuntimeRefs, setOverlayState])

  const handleConnectionFailure = useCallback((message: string) => {
    const sessionId = activeSessionIdRef.current

    flushStreamingAgentUpdate()
    finalizeActiveReceipt('failed')
    finalizeStreamingAssistantMessage()
    removeStatusBubble()

    if (sessionId && message) {
      appendPersistedItems(sessionId, [{
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: message,
      }])
    }

    clearTransientState()
    setConnectionStatus('disconnected')
    failExecution()
  }, [
    appendPersistedItems,
    clearTransientState,
    failExecution,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    flushStreamingAgentUpdate,
    removeStatusBubble,
  ])

  const connectWebSocket = useCallback(async (executionKey: string) => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const ws = new ExecutionWebSocket()

    ws.on('connection:open', () => {
      setConnectionStatus('connected')
    })

    ws.on('connection:closed', (data) => {
      if (data.manuallyClosed) {
        setConnectionStatus('disconnected')
        return
      }

      setConnectionStatus(currentExecutionIdRef.current ? 'connecting' : 'disconnected')
    })

    ws.on('connection:reconnecting', () => {
      setConnectionStatus('connecting')
    })

    ws.on('connection:failed', () => {
      handleConnectionFailure('执行连接已断开，请重试。')
    })

    ws.on('execution:created', (data) => {
      currentExecutionIdRef.current = data.execution_id
      startExecution(data.execution_id, activeSessionIdRef.current)
    })

    ws.on('execution:start', (data) => {
      currentExecutionIdRef.current = data.execution_id
      startExecution(data.execution_id, activeSessionIdRef.current)
    })

    ws.on('llm:start', () => {
      finalizeActiveReceipt()
      thoughtFlushedRef.current = false
      llmStreamingRef.current = ''
      updateStatusBubble('正在思考中')
      setThinkingPhase()
    })

    ws.on('llm:content', (data) => {
      llmStreamingRef.current += data.content
      appendStreamingLlmToken(data.content)
      setThinkingPhase()
    })

    ws.on('llm:thought', (data) => {
      flushStreamingAgentUpdate(data.content)
      setThinkingPhase()
    })

    ws.on('llm:tool_call', (data) => {
      if (!thoughtFlushedRef.current) {
        flushStreamingAgentUpdate(data.thought)
      }

      executionHasReceiptsRef.current = true
      removeStatusBubble()
      appendReceiptDetail(data.tool_name, data.arguments as Record<string, unknown>)
      setExecutingPhase()
    })

    ws.on('tool:start', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'running',
      }))
      setExecutingPhase()
    })

    ws.on('tool:result', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: data.success ? 'success' : 'failed',
        output: data.output,
        error: data.error,
        duration: data.duration,
      }))
      setExecutingPhase()
    })

    ws.on('tool:error', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'failed',
        error: data.error,
      }))
      setExecutingPhase()
    })

    ws.on('summary:start', () => {
      finalizeActiveReceipt()
      summaryStartedRef.current = true
      if (executionHasReceiptsRef.current) {
        removeStatusBubble()
      }
      setSummarizingPhase()
      ensureStreamingAssistantMessage('')
    })

    ws.on('summary:token', (data) => {
      appendStreamingAssistantToken(data.token)
      setSummarizingPhase()
    })

    ws.on('summary:complete', (data) => {
      finalizeActiveReceipt()
      finalizeStreamingAssistantMessage(data.summary)
      finalMessageHandledRef.current = true
      summaryStartedRef.current = false
    })

    ws.on('execution:cancelled', () => {
      flushStreamingAgentUpdate()
      finalizeActiveReceipt('cancelled')
      finalizeStreamingAssistantMessage()
      removeStatusBubble()
      clearTransientState()
      cancelExecution()
    })

    ws.on('execution:complete', (data) => {
      finalizeActiveReceipt()
      finalizeStreamingAssistantMessage()

      if (data.status === 'failed') {
        removeStatusBubble()
        flushStreamingAgentUpdate()
        clearTransientState()
        failExecution()
        return
      }

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        finalizeStreamingLlmAsAssistant(data.result)
        finalMessageHandledRef.current = true
      } else {
        removeStatusBubble()
        flushStreamingAgentUpdate()
      }

      clearTransientState()
      completeExecution()
    })

    ws.on('execution:error', (data) => {
      const sessionId = activeSessionIdRef.current

      flushStreamingAgentUpdate()
      finalizeActiveReceipt('failed')
      finalizeStreamingAssistantMessage()
      removeStatusBubble()

      if (sessionId) {
        appendPersistedItems(sessionId, [{
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: `错误: ${data.error}`,
        }])
      }

      clearTransientState()
      failExecution()
    })

    try {
      setConnectionStatus('connecting')
      await ws.connect(executionKey)
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      handleConnectionFailure('连接执行通道失败，请重试。')
      throw error
    }
  }, [
    appendPersistedItems,
    appendReceiptDetail,
    appendStreamingAssistantToken,
    appendStreamingLlmToken,
    cancelExecution,
    clearTransientState,
    completeExecution,
    ensureStreamingAssistantMessage,
    failExecution,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    finalizeStreamingLlmAsAssistant,
    flushStreamingAgentUpdate,
    handleConnectionFailure,
    removeStatusBubble,
    setExecutingPhase,
    setSummarizingPhase,
    setThinkingPhase,
    startExecution,
    updateActiveReceiptDetail,
    updateStatusBubble,
  ])

  const startExecutionRun = useCallback(async (payload: {
    sessionId: string
    message: string
    projectPath: string
    providerId: string
    modelId: string
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

    appendPersistedItems(payload.sessionId, [userItem])
    setOverlayState([statusItem])

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

    const executionKey = `exec-${Date.now()}`

    try {
      await connectWebSocket(executionKey)
      wsRef.current?.startExecution(
        payload.message,
        payload.projectPath,
        payload.providerId,
        payload.modelId
      )
    } catch (error) {
      console.error('Failed to start execution:', error)
    }
  }, [appendPersistedItems, connectWebSocket, setOverlayState])

  const handleCancel = useCallback(async () => {
    if (!currentExecutionIdRef.current) {
      return
    }

    startCancelling()

    try {
      await agentApi.cancel(currentExecutionIdRef.current)
    } catch (error) {
      console.error('Failed to cancel execution:', error)
      setStatus('running')
      setCanCancel(true)
      setPhase(phase || 'thinking')
    }
  }, [phase, setCanCancel, setPhase, setStatus, startCancelling])

  const resetExecutionRuntime = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setConnectionStatus('disconnected')
    clearTransientState()
    resetExecution()
  }, [clearTransientState, resetExecution])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  useEffect(() => {
    if (!currentSessionId || currentSessionId === activeSessionIdRef.current) {
      return
    }

    setOverlayState([])
  }, [currentSessionId, setOverlayState])

  return {
    overlayItems,
    connectionStatus,
    startExecutionRun,
    handleCancel,
    resetExecutionRuntime,
  }
}
