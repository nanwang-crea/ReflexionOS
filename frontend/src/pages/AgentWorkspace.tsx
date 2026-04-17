import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2 } from 'lucide-react'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { SlideIn } from '@/components/animations'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import {
  buildReceiptDetail,
  type ActionReceiptDetail,
  type ActionReceiptStatus,
  type ReceiptDetailStatus,
} from '@/components/execution/receiptUtils'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ChatInput } from '@/components/chat/ChatInput'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useExecutionStore } from '@/stores/executionStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { agentApi } from '@/services/apiClient'
import type { WorkspaceChatItem } from '@/types/workspace'

const transcriptClassName = [
  'max-w-[920px]',
  'text-[17px]',
  'leading-[1.8]',
  'text-slate-900',
  '[&_p]:m-0',
  '[&_p+p]:mt-6',
  '[&_ul]:my-4',
  '[&_ol]:my-4',
  '[&_li]:mt-1.5',
  '[&_h1]:mt-0',
  '[&_h2]:mt-8',
  '[&_h3]:mt-6',
  '[&_pre]:my-4',
  '[&_blockquote]:my-5',
].join(' ')

function createItemId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function updateFirstMatchingDetail(
  details: ActionReceiptDetail[],
  matcher: (detail: ActionReceiptDetail) => boolean,
  updater: (detail: ActionReceiptDetail) => ActionReceiptDetail
) {
  const index = details.findIndex(matcher)

  if (index === -1) {
    return details
  }

  const nextDetails = [...details]
  nextDetails[index] = updater(nextDetails[index])
  return nextDetails
}

function deriveSessionTitle(items: WorkspaceChatItem[]) {
  const firstUserMessage = items.find((item) => item.type === 'user-message' && item.content)?.content?.trim()
  if (!firstUserMessage) {
    return null
  }

  return firstUserMessage.length > 28 ? `${firstUserMessage.slice(0, 28)}...` : firstUserMessage
}

export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const { configured } = useSettingsStore()
  const {
    sessions,
    currentSessionId,
    createSession,
    saveSessionItems,
    updateSessionTitle,
  } = useWorkspaceStore()
  const {
    status,
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
    resetExecution
  } = useExecutionStore()

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) || null,
    [currentSessionId, sessions]
  )

  const [chatItems, setChatItems] = useState<WorkspaceChatItem[]>(currentSession?.items || [])
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  const wsRef = useRef<ExecutionWebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const llmStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentExecutionIdRef = useRef<string | null>(null)
  const activeReceiptIdRef = useRef<string | null>(null)
  const thoughtFlushedRef = useRef(false)
  const currentLlmMessageIdRef = useRef<string | null>(null)
  const currentAssistantMessageIdRef = useRef<string | null>(null)
  const lastSyncedItemsRef = useRef('')

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems])

  useEffect(() => {
    const nextItems = currentSession?.items || []
    setChatItems(nextItems)
    lastSyncedItemsRef.current = JSON.stringify(nextItems)
    llmStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    thoughtFlushedRef.current = false
    currentLlmMessageIdRef.current = null
    currentAssistantMessageIdRef.current = null
    currentExecutionIdRef.current = null
  }, [currentSessionId])

  useEffect(() => {
    if (!currentSessionId) {
      return
    }

    const serialized = JSON.stringify(chatItems)
    if (serialized === lastSyncedItemsRef.current) {
      return
    }

    saveSessionItems(currentSessionId, chatItems)
    lastSyncedItemsRef.current = serialized

    const nextTitle = deriveSessionTitle(chatItems)
    if (nextTitle && currentSession?.title !== nextTitle) {
      updateSessionTitle(currentSessionId, nextTitle)
    }
  }, [chatItems, currentSession?.title, currentSessionId, saveSessionItems, updateSessionTitle])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  const statusLine = useMemo(() => {
    if (status === 'cancelling') {
      return {
        label: '正在取消',
        className: 'text-amber-600'
      }
    }

    if (status !== 'running') {
      return null
    }

    const label = {
      thinking: '正在思考中',
      executing: '正在执行操作',
      summarizing: '正在整理回答',
      null: '正在思考中'
    }[String(phase) as 'thinking' | 'executing' | 'summarizing' | 'null']

    return {
      label,
      className: 'text-slate-500'
    }
  }, [phase, status])

  const addChatItem = useCallback((item: WorkspaceChatItem) => {
    setChatItems(prev => [...prev, item])
  }, [])

  const updateChatItem = useCallback((
    itemId: string,
    updater: (item: WorkspaceChatItem) => WorkspaceChatItem
  ) => {
    setChatItems(prev => prev.map(item => (
      item.id === itemId
        ? updater(item)
        : item
    )))
  }, [])

  const updateReceiptItem = useCallback((
    receiptId: string,
    updater: (item: WorkspaceChatItem) => WorkspaceChatItem
  ) => {
    setChatItems(prev => prev.map(item => (
      item.type === 'action-receipt' && item.id === receiptId
        ? updater(item)
        : item
    )))
  }, [])

  const ensureStreamingLlmMessage = useCallback((initialContent = '') => {
    if (currentLlmMessageIdRef.current) {
      return currentLlmMessageIdRef.current
    }

    const messageId = createItemId('llm')
    addChatItem({
      id: messageId,
      type: 'agent-update',
      content: initialContent,
      isStreaming: true
    })
    currentLlmMessageIdRef.current = messageId
    return messageId
  }, [addChatItem])

  const appendStreamingLlmToken = useCallback((token: string) => {
    const messageId = ensureStreamingLlmMessage()
    updateChatItem(messageId, (item) => ({
      ...item,
      content: `${item.content || ''}${token}`,
      isStreaming: true
    }))
  }, [ensureStreamingLlmMessage, updateChatItem])

  const flushStreamingAgentUpdate = useCallback((fallbackContent = '') => {
    const content = (llmStreamingRef.current || fallbackContent).trim()

    if (!content) {
      llmStreamingRef.current = ''
      if (currentLlmMessageIdRef.current) {
        updateChatItem(currentLlmMessageIdRef.current, (item) => ({
          ...item,
          isStreaming: false
        }))
        currentLlmMessageIdRef.current = null
      }
      return
    }

    if (currentLlmMessageIdRef.current) {
      updateChatItem(currentLlmMessageIdRef.current, (item) => ({
        ...item,
        type: 'agent-update',
        content,
        isStreaming: false
      }))
    } else {
      addChatItem({
        id: createItemId('update'),
        type: 'agent-update',
        content
      })
    }

    currentLlmMessageIdRef.current = null
    llmStreamingRef.current = ''
    thoughtFlushedRef.current = true
  }, [addChatItem, updateChatItem])

  const finalizeStreamingLlmAsAssistant = useCallback((finalContent?: string) => {
    if (!currentLlmMessageIdRef.current) {
      if (finalContent) {
        addChatItem({
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: finalContent,
          isStreaming: false
        })
      }
      return
    }

    const messageId = currentLlmMessageIdRef.current
    updateChatItem(messageId, (item) => ({
      ...item,
      type: 'assistant-message',
      content: finalContent ?? item.content,
      isStreaming: false
    }))
    currentLlmMessageIdRef.current = null
  }, [addChatItem, updateChatItem])

  const ensureStreamingAssistantMessage = useCallback((initialContent = '') => {
    if (currentAssistantMessageIdRef.current) {
      return currentAssistantMessageIdRef.current
    }

    const messageId = createItemId('assistant')
    addChatItem({
      id: messageId,
      type: 'assistant-message',
      content: initialContent,
      isStreaming: true
    })
    currentAssistantMessageIdRef.current = messageId
    return messageId
  }, [addChatItem])

  const appendStreamingAssistantToken = useCallback((token: string) => {
    const messageId = ensureStreamingAssistantMessage()
    updateChatItem(messageId, (item) => ({
      ...item,
      content: `${item.content || ''}${token}`,
      isStreaming: true
    }))
  }, [ensureStreamingAssistantMessage, updateChatItem])

  const finalizeStreamingAssistantMessage = useCallback((finalContent?: string) => {
    if (!currentAssistantMessageIdRef.current) {
      if (finalContent) {
        addChatItem({
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: finalContent,
          isStreaming: false
        })
      }
      return
    }

    const messageId = currentAssistantMessageIdRef.current
    updateChatItem(messageId, (item) => ({
      ...item,
      content: finalContent ?? item.content,
      isStreaming: false
    }))
    currentAssistantMessageIdRef.current = null
  }, [addChatItem, updateChatItem])

  const finalizeActiveReceipt = useCallback((forcedStatus?: ActionReceiptStatus) => {
    if (!activeReceiptIdRef.current) {
      return
    }

    const receiptId = activeReceiptIdRef.current
    updateReceiptItem(receiptId, (item) => {
      const resolvedStatus = forcedStatus || (
        item.details?.some(detail => detail.status === 'failed') ? 'failed' : 'completed'
      )

      return {
        ...item,
        receiptStatus: resolvedStatus,
        details: (item.details || []).map((detail) => {
          if (detail.status !== 'pending' && detail.status !== 'running') {
            return detail
          }

          const nextStatus: ReceiptDetailStatus = resolvedStatus === 'failed'
            ? 'failed'
            : resolvedStatus === 'cancelled'
              ? 'cancelled'
              : 'success'

          return { ...detail, status: nextStatus }
        })
      }
    })

    activeReceiptIdRef.current = null
  }, [updateReceiptItem])

  const ensureReceiptItem = useCallback(() => {
    if (activeReceiptIdRef.current) {
      return activeReceiptIdRef.current
    }

    const receiptId = createItemId('receipt')
    addChatItem({
      id: receiptId,
      type: 'action-receipt',
      receiptStatus: 'running',
      details: []
    })
    activeReceiptIdRef.current = receiptId
    return receiptId
  }, [addChatItem])

  const appendReceiptDetail = useCallback((toolName: string, args?: Record<string, unknown>) => {
    const receiptId = ensureReceiptItem()
    const detail = buildReceiptDetail(createItemId('detail'), toolName, args)

    updateReceiptItem(receiptId, (item) => ({
      ...item,
      receiptStatus: 'running',
      details: [...(item.details || []), detail]
    }))
  }, [ensureReceiptItem, updateReceiptItem])

  const updateActiveReceiptDetail = useCallback((
    toolName: string,
    updater: (detail: ActionReceiptDetail) => ActionReceiptDetail
  ) => {
    if (!activeReceiptIdRef.current) {
      return
    }

    updateReceiptItem(activeReceiptIdRef.current, (item) => ({
      ...item,
      details: updateFirstMatchingDetail(
        item.details || [],
        detail => detail.toolName === toolName && (
          detail.status === 'pending' || detail.status === 'running'
        ),
        updater
      )
    }))
  }, [updateReceiptItem])

  const handleCancel = async () => {
    if (!currentExecutionIdRef.current) return

    startCancelling()

    try {
      await agentApi.cancel(currentExecutionIdRef.current)
    } catch (error) {
      console.error('Failed to cancel execution:', error)
      setStatus('running')
      setCanCancel(true)
      setPhase(phase || 'thinking')
    }
  }

  const connectWebSocket = useCallback(async (executionKey: string) => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const ws = new ExecutionWebSocket()

    ws.on('*', (message: unknown) => {
      console.log('[WS Event]', message)
    })

    ws.on('execution:created', (data) => {
      currentExecutionIdRef.current = data.execution_id
      startExecution(data.execution_id)
    })

    ws.on('execution:start', (data) => {
      currentExecutionIdRef.current = data.execution_id
      startExecution(data.execution_id)
    })

    ws.on('llm:start', () => {
      finalizeActiveReceipt()
      thoughtFlushedRef.current = false
      llmStreamingRef.current = ''
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

      appendReceiptDetail(data.tool_name, data.arguments as Record<string, unknown>)
      setExecutingPhase()
    })

    ws.on('tool:start', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'running'
      }))
      setExecutingPhase()
    })

    ws.on('tool:result', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: data.success ? 'success' : 'failed',
        output: data.output,
        error: data.error,
        duration: data.duration
      }))
      setExecutingPhase()
    })

    ws.on('tool:error', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'failed',
        error: data.error
      }))
      setExecutingPhase()
    })

    ws.on('summary:start', () => {
      finalizeActiveReceipt()
      summaryStartedRef.current = true
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
      llmStreamingRef.current = ''
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      currentExecutionIdRef.current = null
      cancelExecution()
    })

    ws.on('execution:complete', (data) => {
      finalizeActiveReceipt()
      finalizeStreamingAssistantMessage()
      currentExecutionIdRef.current = null

      if (data.status === 'failed') {
        flushStreamingAgentUpdate()
        failExecution()
        return
      }

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        finalizeStreamingLlmAsAssistant(data.result)
        finalMessageHandledRef.current = true
      } else {
        flushStreamingAgentUpdate()
      }

      llmStreamingRef.current = ''
      completeExecution()
    })

    ws.on('execution:error', (data) => {
      flushStreamingAgentUpdate()
      finalizeActiveReceipt('failed')
      finalizeStreamingAssistantMessage()
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      llmStreamingRef.current = ''
      currentExecutionIdRef.current = null
      failExecution()
      addChatItem({
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: `错误: ${data.error}`
      })
    })

    try {
      setConnectionStatus('connecting')
      await ws.connect(executionKey)
      setConnectionStatus('connected')
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      setConnectionStatus('disconnected')
      flushStreamingAgentUpdate()
      finalizeStreamingAssistantMessage()
      failExecution()
      addChatItem({
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: '连接执行通道失败，请重试。'
      })
      throw error
    }
  }, [
    addChatItem,
    appendReceiptDetail,
    appendStreamingAssistantToken,
    cancelExecution,
    completeExecution,
    ensureStreamingAssistantMessage,
    finalizeStreamingLlmAsAssistant,
    failExecution,
    finalizeActiveReceipt,
    finalizeStreamingAssistantMessage,
    flushStreamingAgentUpdate,
    phase,
    setCanCancel,
    setExecutingPhase,
    setPhase,
    setStatus,
    setSummarizingPhase,
    setThinkingPhase,
    startCancelling,
    startExecution,
    updateActiveReceiptDetail,
  ])

  const handleSend = useCallback(async (message: string) => {
    if (!message.trim()) return

    if (!currentProject) {
      alert('请先选择一个项目')
      return
    }

    if (!configured) {
      alert('请先在设置页面配置 LLM')
      return
    }

    const userItem: WorkspaceChatItem = {
      id: createItemId('user'),
      type: 'user-message',
      content: message
    }

    const requiresFreshSession = !currentSession || currentSession.projectId !== currentProject.id

    if (requiresFreshSession) {
      const session = createSession(currentProject.id)
      saveSessionItems(session.id, [userItem])
      updateSessionTitle(session.id, deriveSessionTitle([userItem]) || session.title)
      setChatItems([userItem])
      lastSyncedItemsRef.current = JSON.stringify([userItem])
    } else {
      addChatItem(userItem)
    }

    llmStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    thoughtFlushedRef.current = false
    currentLlmMessageIdRef.current = null
    currentAssistantMessageIdRef.current = null
    currentExecutionIdRef.current = null

    const executionKey = `exec-${Date.now()}`

    try {
      await connectWebSocket(executionKey)
      wsRef.current?.startExecution(message, currentProject.path)
    } catch (error) {
      console.error('Failed to start execution:', error)
    }
  }, [
    addChatItem,
    configured,
    connectWebSocket,
    createSession,
    currentProject,
    currentSession,
    saveSessionItems,
    updateSessionTitle
  ])

  const handleReset = () => {
    wsRef.current?.close()
    wsRef.current = null
    setConnectionStatus('disconnected')
    setChatItems([])
    llmStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    thoughtFlushedRef.current = false
    currentLlmMessageIdRef.current = null
    currentAssistantMessageIdRef.current = null
    currentExecutionIdRef.current = null
    resetExecution()
  }

  const inputBusy = status === 'running' || status === 'cancelling'

  return (
      <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            {currentSession?.title || (currentProject ? currentProject.name : '选择项目开始')}
          </h2>
          {currentProject && (
            <p className="text-sm text-gray-500">{currentProject.path}</p>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`h-2 w-2 rounded-full ${
              connectionStatus === 'connected' ? 'bg-green-500' :
              connectionStatus === 'connecting' ? 'bg-yellow-500' : 'bg-gray-300'
            }`} />
            <span className="text-sm text-gray-500">
              {connectionStatus === 'connected' ? '已连接' :
               connectionStatus === 'connecting' ? '连接中...' : '未连接'}
            </span>
          </div>
          <button
            onClick={handleReset}
            className="rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
          >
            重置对话
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-white">
        <div className="mx-auto w-full max-w-[1280px] px-8 py-8">
          {!configured && (
            <div className="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 p-4">
              <p className="text-yellow-800">请先在设置页面配置 LLM API Key</p>
            </div>
          )}

          {statusLine && (
            <div className={`mb-6 flex items-center gap-2 text-sm ${statusLine.className}`}>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{statusLine.label}</span>
            </div>
          )}

          {!currentProject && (
            <div className="max-w-[720px] rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
              先在左侧选择一个项目，再开始新的聊天。
            </div>
          )}

          {currentProject && !currentSession && chatItems.length === 0 && (
            <div className="max-w-[720px] rounded-3xl border border-slate-200 bg-slate-50 px-6 py-8 text-slate-500">
              这个项目下还没有聊天。可以直接在下方输入，或者从左侧点击“新建聊天”。
            </div>
          )}

          <AnimatePresence mode="popLayout">
            {chatItems.map((item) => {
              if (item.type === 'user-message') {
                return (
                  <SlideIn key={item.id} direction="up">
                    <div className="mb-8 flex justify-end">
                      <motion.div
                        className="max-w-[720px] rounded-2xl bg-slate-100 px-5 py-4 text-[15px] leading-7 text-slate-700"
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        {item.content}
                      </motion.div>
                    </div>
                  </SlideIn>
                )
              }

              if (item.type === 'agent-update') {
                return (
                  <SlideIn key={item.id} direction="up">
                    <div className="mb-7">
                      <MarkdownRenderer
                        content={item.content || ''}
                        variant="plain"
                        isStreaming={item.isStreaming}
                        className={transcriptClassName}
                      />
                    </div>
                  </SlideIn>
                )
              }

              if (item.type === 'action-receipt') {
                return (
                  <SlideIn key={item.id} direction="up">
                    <ActionReceipt
                      status={item.receiptStatus || 'running'}
                      details={item.details || []}
                    />
                  </SlideIn>
                )
              }

              if (item.type === 'assistant-message') {
                return (
                  <SlideIn key={item.id} direction="up">
                    <div className="mb-10">
                      <MarkdownRenderer
                        content={item.content || ''}
                        variant="plain"
                        isStreaming={item.isStreaming}
                        className={transcriptClassName}
                      />
                    </div>
                  </SlideIn>
                )
              }

              return null
            })}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-gray-200 bg-white p-4">
        <ChatInput
          onSend={handleSend}
          onCancel={handleCancel}
          disabled={!configured || !currentProject || inputBusy}
          isLoading={inputBusy}
          canCancel={status === 'running'}
          isCancelling={status === 'cancelling'}
          placeholder={currentProject ? '给当前项目开一个新任务...' : '请先选择项目'}
        />
        {!currentProject && (
          <p className="mt-2 text-sm text-gray-500">请先从左侧选择一个项目</p>
        )}
      </div>
    </div>
  )
}
