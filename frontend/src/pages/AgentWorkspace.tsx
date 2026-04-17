import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { SlideIn } from '@/components/animations'
import { ActionReceipt } from '@/components/execution/ActionReceipt'
import { ExecutionControls } from '@/components/execution/ExecutionControls'
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
import { agentApi } from '@/services/apiClient'

type ChatItemType = 'user-message' | 'assistant-message' | 'agent-update' | 'action-receipt'

interface ChatItem {
  id: string
  type: ChatItemType
  content?: string
  receiptStatus?: ActionReceiptStatus
  details?: ActionReceiptDetail[]
}

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

export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const { configured } = useSettingsStore()
  const {
    status,
    startExecution,
    pauseExecution,
    resumeExecution,
    stopExecution,
    resetExecution
  } = useExecutionStore()

  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [llmStreamingContent, setLlmStreamingContent] = useState('')
  const [summaryStreamingContent, setSummaryStreamingContent] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  const wsRef = useRef<ExecutionWebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const llmStreamingRef = useRef('')
  const summaryStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentExecutionIdRef = useRef<string | null>(null)
  const activeReceiptIdRef = useRef<string | null>(null)
  const thoughtFlushedRef = useRef(false)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems, llmStreamingContent, summaryStreamingContent])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  const addChatItem = useCallback((item: ChatItem) => {
    setChatItems(prev => [...prev, item])
  }, [])

  const updateReceiptItem = useCallback((
    receiptId: string,
    updater: (item: ChatItem) => ChatItem
  ) => {
    setChatItems(prev => prev.map(item => (
      item.type === 'action-receipt' && item.id === receiptId
        ? updater(item)
        : item
    )))
  }, [])

  const flushStreamingAgentUpdate = useCallback((fallbackContent = '') => {
    const content = (llmStreamingRef.current || fallbackContent).trim()

    if (!content) {
      llmStreamingRef.current = ''
      setLlmStreamingContent('')
      return
    }

    addChatItem({
      id: createItemId('update'),
      type: 'agent-update',
      content
    })
    llmStreamingRef.current = ''
    setLlmStreamingContent('')
    thoughtFlushedRef.current = true
  }, [addChatItem])

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

          const nextStatus: ReceiptDetailStatus = resolvedStatus === 'failed' ? 'failed' : 'success'
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

  const handlePause = async () => {
    if (!currentExecutionIdRef.current) return

    try {
      await agentApi.pause(currentExecutionIdRef.current)
      pauseExecution()
    } catch (error) {
      console.error('Failed to pause execution:', error)
    }
  }

  const handleResume = async () => {
    if (!currentExecutionIdRef.current) return

    try {
      await agentApi.resume(currentExecutionIdRef.current)
      resumeExecution()
    } catch (error) {
      console.error('Failed to resume execution:', error)
    }
  }

  const handleStop = async () => {
    if (!currentExecutionIdRef.current) return

    try {
      await agentApi.stop(currentExecutionIdRef.current)
      stopExecution()
      wsRef.current?.close()
      wsRef.current = null
      setConnectionStatus('disconnected')
      finalizeActiveReceipt('failed')
    } catch (error) {
      console.error('Failed to stop execution:', error)
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

    ws.on('llm:start', () => {
      finalizeActiveReceipt()
      thoughtFlushedRef.current = false
      llmStreamingRef.current = ''
      setLlmStreamingContent('')
    })

    ws.on('llm:content', (data) => {
      llmStreamingRef.current += data.content
      setLlmStreamingContent(llmStreamingRef.current)
    })

    ws.on('llm:tool_call', (data) => {
      if (!thoughtFlushedRef.current) {
        flushStreamingAgentUpdate(data.thought)
      }

      appendReceiptDetail(data.tool_name, data.arguments as Record<string, unknown>)
    })

    ws.on('tool:start', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'running'
      }))
    })

    ws.on('tool:result', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: data.success ? 'success' : 'failed',
        output: data.output,
        error: data.error,
        duration: data.duration
      }))
    })

    ws.on('tool:error', (data) => {
      updateActiveReceiptDetail(data.tool_name, (detail) => ({
        ...detail,
        status: 'failed',
        error: data.error
      }))
    })

    ws.on('summary:start', () => {
      finalizeActiveReceipt()
      summaryStartedRef.current = true
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
    })

    ws.on('summary:token', (data) => {
      summaryStreamingRef.current += data.token
      setSummaryStreamingContent(summaryStreamingRef.current)
    })

    ws.on('summary:complete', (data) => {
      finalizeActiveReceipt()
      addChatItem({
        id: createItemId('assistant'),
        type: 'assistant-message',
        content: data.summary
      })
      finalMessageHandledRef.current = true
      summaryStartedRef.current = false
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
    })

    ws.on('execution:start', (data) => {
      currentExecutionIdRef.current = data.execution_id
      startExecution(data.execution_id)
    })

    ws.on('execution:complete', (data) => {
      resetExecution()
      finalizeActiveReceipt()
      llmStreamingRef.current = ''
      setLlmStreamingContent('')

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        addChatItem({
          id: createItemId('assistant'),
          type: 'assistant-message',
          content: data.result
        })
        finalMessageHandledRef.current = true
      }
    })

    ws.on('execution:error', (data) => {
      resetExecution()
      finalizeActiveReceipt('failed')
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      llmStreamingRef.current = ''
      summaryStreamingRef.current = ''
      setLlmStreamingContent('')
      setSummaryStreamingContent('')
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
    finalizeActiveReceipt,
    flushStreamingAgentUpdate,
    resetExecution,
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

    addChatItem({
      id: createItemId('user'),
      type: 'user-message',
      content: message
    })

    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    thoughtFlushedRef.current = false
    setLlmStreamingContent('')
    setSummaryStreamingContent('')

    const executionKey = `exec-${Date.now()}`

    try {
      await connectWebSocket(executionKey)
      wsRef.current?.startExecution(message, currentProject.path)
    } catch (error) {
      console.error('Failed to start execution:', error)
    }
  }, [addChatItem, configured, connectWebSocket, currentProject])

  const handleReset = () => {
    wsRef.current?.close()
    wsRef.current = null
    setConnectionStatus('disconnected')
    setChatItems([])
    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    activeReceiptIdRef.current = null
    thoughtFlushedRef.current = false
    setLlmStreamingContent('')
    setSummaryStreamingContent('')
    currentExecutionIdRef.current = null
    resetExecution()
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            {currentProject ? currentProject.name : '选择项目开始'}
          </h2>
          {currentProject && (
            <p className="text-sm text-gray-500">{currentProject.path}</p>
          )}
        </div>
        <div className="flex items-center gap-4">
          <ExecutionControls
            onPause={handlePause}
            onResume={handleResume}
            onStop={handleStop}
          />
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
                        className={transcriptClassName}
                      />
                    </div>
                  </SlideIn>
                )
              }

              return null
            })}
          </AnimatePresence>

          {llmStreamingContent && (
            <SlideIn direction="up">
              <div className="mb-7 max-w-[920px] text-[17px] leading-[1.8] text-slate-800">
                <div className="whitespace-pre-wrap">
                  {llmStreamingContent}
                  <motion.span
                    className="ml-1 inline-block h-5 w-2 bg-slate-300 align-middle"
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                  />
                </div>
              </div>
            </SlideIn>
          )}

          {summaryStreamingContent && (
            <SlideIn direction="up">
              <div className="mb-10 max-w-[920px] text-[17px] leading-[1.8] text-slate-900">
                <div className="whitespace-pre-wrap">
                  {summaryStreamingContent}
                  <motion.span
                    className="ml-1 inline-block h-5 w-2 bg-slate-300 align-middle"
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                  />
                </div>
              </div>
            </SlideIn>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-gray-200 bg-white p-4">
        <ChatInput
          onSend={handleSend}
          disabled={!configured || !currentProject || status === 'running'}
          isLoading={status === 'running'}
        />
        {!currentProject && (
          <p className="mt-2 text-sm text-gray-500">请先在项目页面选择一个项目</p>
        )}
      </div>
    </div>
  )
}
