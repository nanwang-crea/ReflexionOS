import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { SlideIn } from '@/components/animations'
import { ExecutionTrace, type ExecutionTraceStatus, type ExecutionTraceStep } from '@/components/execution/ExecutionTrace'
import { ExecutionControls } from '@/components/execution/ExecutionControls'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ChatInput } from '@/components/chat/ChatInput'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useExecutionStore } from '@/stores/executionStore'
import { agentApi } from '@/services/apiClient'

type ChatItemType = 'user-message' | 'assistant-message' | 'execution-trace'

interface ChatItem {
  id: string
  type: ChatItemType
  content?: string
  executionKey?: string
  traceStatus?: ExecutionTraceStatus
  thought?: string
  thoughtStreaming?: boolean
  steps?: ExecutionTraceStep[]
}

function updateFirstMatchingStep(
  steps: ExecutionTraceStep[],
  matcher: (step: ExecutionTraceStep) => boolean,
  updater: (step: ExecutionTraceStep) => ExecutionTraceStep
) {
  const index = steps.findIndex(matcher)

  if (index === -1) {
    return steps
  }

  const nextSteps = [...steps]
  nextSteps[index] = updater(nextSteps[index])
  return nextSteps
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
  const [summaryStreamingContent, setSummaryStreamingContent] = useState('')
  const [connectionStatus, setConnectionStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected')

  const wsRef = useRef<ExecutionWebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const stepCounterRef = useRef(0)
  const llmStreamingRef = useRef('')
  const summaryStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentExecutionIdRef = useRef<string | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems, summaryStreamingContent])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  const addChatItem = useCallback((item: Omit<ChatItem, 'id'>) => {
    setChatItems(prev => [...prev, {
      ...item,
      id: `item-${Date.now()}-${Math.random()}`
    }])
  }, [])

  const updateTraceItem = useCallback((
    executionKey: string,
    updater: (item: ChatItem) => ChatItem
  ) => {
    setChatItems(prev => prev.map(item => (
      item.type === 'execution-trace' && item.executionKey === executionKey
        ? updater(item)
        : item
    )))
  }, [])

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

    ws.on('*', (message: any) => {
      console.log('[WS Event]', message.type, message.data)
    })

    ws.on('llm:start', () => {
      llmStreamingRef.current = ''
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'thinking',
        thought: '',
        thoughtStreaming: true
      }))
    })

    ws.on('llm:content', (data) => {
      llmStreamingRef.current += data.content
      updateTraceItem(executionKey, item => ({
        ...item,
        thought: llmStreamingRef.current,
        thoughtStreaming: true
      }))
    })

    ws.on('llm:tool_call', (data) => {
      const thought = data.thought || llmStreamingRef.current

      stepCounterRef.current++

      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'running',
        thought,
        thoughtStreaming: false,
        steps: [
          ...(item.steps || []),
          {
            id: `trace-step-${executionKey}-${stepCounterRef.current}`,
            stepNumber: stepCounterRef.current,
            toolName: data.tool_name,
            status: 'pending',
            arguments: data.arguments
          }
        ]
      }))
    })

    ws.on('tool:start', (data) => {
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'running',
        steps: updateFirstMatchingStep(
          item.steps || [],
          step => step.toolName === data.tool_name && step.status === 'pending',
          step => ({ ...step, status: 'running' })
        )
      }))
    })

    ws.on('tool:result', (data) => {
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'running',
        thoughtStreaming: false,
        steps: updateFirstMatchingStep(
          item.steps || [],
          step => step.toolName === data.tool_name && (
            step.status === 'running' || step.status === 'pending'
          ),
          step => ({
            ...step,
            status: data.success ? 'success' : 'failed',
            output: data.output,
            duration: data.duration
          })
        )
      }))
    })

    ws.on('tool:error', (data) => {
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'running',
        thoughtStreaming: false,
        steps: updateFirstMatchingStep(
          item.steps || [],
          step => step.toolName === data.tool_name && (
            step.status === 'running' || step.status === 'pending'
          ),
          step => ({
            ...step,
            status: 'failed',
            error: data.error
          })
        )
      }))
    })

    ws.on('summary:start', () => {
      summaryStartedRef.current = true
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'running',
        thoughtStreaming: false
      }))
    })

    ws.on('summary:token', (data) => {
      summaryStreamingRef.current += data.token
      setSummaryStreamingContent(prev => prev + data.token)
    })

    ws.on('summary:complete', (data) => {
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'completed',
        thoughtStreaming: false
      }))
      addChatItem({ type: 'assistant-message', content: data.summary })
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
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'completed',
        thoughtStreaming: false
      }))

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        addChatItem({ type: 'assistant-message', content: data.result })
        finalMessageHandledRef.current = true
      }
    })

    ws.on('execution:error', (data) => {
      resetExecution()
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      llmStreamingRef.current = ''
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'failed',
        thoughtStreaming: false
      }))
      addChatItem({ type: 'assistant-message', content: `错误: ${data.error}` })
    })

    try {
      setConnectionStatus('connecting')
      await ws.connect(executionKey)
      setConnectionStatus('connected')
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      setConnectionStatus('disconnected')
      updateTraceItem(executionKey, item => ({
        ...item,
        traceStatus: 'failed',
        thoughtStreaming: false,
        thought: '连接执行通道失败，请重试。'
      }))
      throw error
    }
  }, [addChatItem, resetExecution, startExecution, updateTraceItem])

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

    addChatItem({ type: 'user-message', content: message })

    stepCounterRef.current = 0
    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    setSummaryStreamingContent('')

    const executionKey = `exec-${Date.now()}`
    addChatItem({
      type: 'execution-trace',
      executionKey,
      traceStatus: 'thinking',
      thought: '',
      thoughtStreaming: true,
      steps: []
    })

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
    setSummaryStreamingContent('')
    stepCounterRef.current = 0
    currentExecutionIdRef.current = null
    resetExecution()
  }

  return (
    <div className="flex h-full flex-col">
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

      <div className="flex-1 overflow-y-auto bg-gray-50 p-6">
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
                  <div className="mb-4 text-right">
                    <motion.div
                      className="inline-block max-w-[80%] rounded-2xl bg-blue-600 px-4 py-3 text-white shadow-lg"
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 300 }}
                    >
                      <div className="mb-1 text-sm font-medium opacity-70">你</div>
                      <div className="whitespace-pre-wrap">{item.content}</div>
                    </motion.div>
                  </div>
                </SlideIn>
              )
            }

            if (item.type === 'assistant-message') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-4">
                    <motion.div
                      className="inline-block max-w-[80%] rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 shadow-sm"
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 300 }}
                    >
                      <div className="mb-1 text-sm font-medium opacity-70">Agent</div>
                      <MarkdownRenderer content={item.content || ''} />
                    </motion.div>
                  </div>
                </SlideIn>
              )
            }

            if (item.type === 'execution-trace') {
              return (
                <SlideIn key={item.id} direction="up">
                  <ExecutionTrace
                    status={item.traceStatus || 'thinking'}
                    thought={item.thought}
                    thoughtStreaming={item.thoughtStreaming}
                    steps={item.steps || []}
                  />
                </SlideIn>
              )
            }

            return null
          })}
        </AnimatePresence>

        {summaryStreamingContent && (
          <SlideIn direction="up">
            <div className="mb-4">
              <div className="inline-block max-w-[80%] rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 shadow-sm">
                <div className="mb-1 text-sm font-medium opacity-70">Agent 正在整理回答</div>
                <div className="whitespace-pre-wrap">
                  {summaryStreamingContent}
                  <motion.span
                    className="ml-1 inline-block h-5 w-2 bg-blue-500"
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                  />
                </div>
              </div>
            </div>
          </SlideIn>
        )}

        <div ref={messagesEndRef} />
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
