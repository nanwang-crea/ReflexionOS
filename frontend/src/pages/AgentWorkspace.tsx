import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { ThoughtDisclosure } from '@/components/StreamingMessage'
import { SlideIn } from '@/components/animations'
import { StepCard } from '@/components/execution/StepCard'
import { ExecutionControls } from '@/components/execution/ExecutionControls'
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer'
import { ChatInput } from '@/components/chat/ChatInput'
import { LoadingSpinner } from '@/components/feedback/LoadingSpinner'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useExecutionStore } from '@/stores/executionStore'
import { agentApi } from '@/services/apiClient'

type ChatItemType = 'user-message' | 'assistant-message' | 'thought' | 'step'

interface ChatItem {
  id: string
  type: ChatItemType
  content?: string
  stepNumber?: number
  toolName?: string
  status?: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  arguments?: Record<string, any>
  isStreaming?: boolean
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
  const stepCounterRef = useRef(0)
  const llmStreamingRef = useRef('')
  const summaryStreamingRef = useRef('')
  const summaryStartedRef = useRef(false)
  const finalMessageHandledRef = useRef(false)
  const currentExecutionIdRef = useRef<string | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems, llmStreamingContent, summaryStreamingContent])

  const addChatItem = useCallback((item: Omit<ChatItem, 'id'>) => {
    setChatItems(prev => [...prev, {
      ...item,
      id: `item-${Date.now()}-${Math.random()}`
    }])
  }, [])

  const flushLlmStreamingMessage = useCallback((
    type: 'thought' | 'assistant-message',
    fallbackContent = ''
  ) => {
    const content = llmStreamingRef.current || fallbackContent
    if (!content) return

    addChatItem({ type, content })
    llmStreamingRef.current = ''
    setLlmStreamingContent('')
  }, [addChatItem])

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
    } catch (error) {
      console.error('Failed to stop execution:', error)
    }
  }

  const connectWebSocket = useCallback(async (execId: string) => {
    if (wsRef.current?.isConnected()) return
    
    const ws = new ExecutionWebSocket()
    
    ws.on('*', (message: any) => {
      console.log('[WS Event]', message.type, message.data)
    })

    ws.on('llm:start', () => {
      llmStreamingRef.current = ''
      setLlmStreamingContent('')
    })
    
    ws.on('llm:content', (data) => {
      llmStreamingRef.current += data.content
      setLlmStreamingContent(prev => prev + data.content)
    })
    
    ws.on('llm:tool_call', (data) => {
      flushLlmStreamingMessage('thought', data.thought)

      stepCounterRef.current++
      addChatItem({
        type: 'step',
        stepNumber: stepCounterRef.current,
        toolName: data.tool_name,
        status: 'running',
        arguments: data.arguments
      })
    })
    
    ws.on('tool:start', () => {
      // Tool start event - no action needed
    })
    
    ws.on('tool:result', (data) => {
      setChatItems(prev => prev.map(item => 
        item.type === 'step' && item.toolName === data.tool_name && item.status === 'running'
          ? { ...item, status: data.success ? 'success' : 'failed', output: data.output, duration: data.duration }
          : item
      ))
    })
    
    ws.on('tool:error', (data) => {
      setChatItems(prev => prev.map(item =>
        item.type === 'step' && item.toolName === data.tool_name && item.status === 'running'
          ? { ...item, status: 'failed', error: data.error }
          : item
      ))
    })
    
    ws.on('summary:start', () => {
      summaryStartedRef.current = true
      flushLlmStreamingMessage('thought')
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
    })
    
    ws.on('summary:token', (data) => {
      summaryStreamingRef.current += data.token
      setSummaryStreamingContent(prev => prev + data.token)
    })
    
    ws.on('summary:complete', (data) => {
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

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        flushLlmStreamingMessage('assistant-message', data.result)
        finalMessageHandledRef.current = true
      }
    })
    
    ws.on('execution:error', (data) => {
      resetExecution()
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      llmStreamingRef.current = ''
      summaryStreamingRef.current = ''
      setLlmStreamingContent('')
      setSummaryStreamingContent('')
      addChatItem({ type: 'assistant-message', content: `错误: ${data.error}` })
    })
    
    try {
      setConnectionStatus('connecting')
      await ws.connect(execId)
      setConnectionStatus('connected')
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      setConnectionStatus('disconnected')
    }
  }, [addChatItem, flushLlmStreamingMessage, startExecution, resetExecution])

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
    setLlmStreamingContent('')
    setSummaryStreamingContent('')
    
    const execId = `exec-${Date.now()}`
    await connectWebSocket(execId)
    
    wsRef.current?.startExecution(message, currentProject.path)
  }, [addChatItem, connectWebSocket, configured, currentProject])

  const handleReset = () => {
    setChatItems([])
    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    setLlmStreamingContent('')
    setSummaryStreamingContent('')
    stepCounterRef.current = 0
    resetExecution()
    currentExecutionIdRef.current = null
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
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
            <div className={`w-2 h-2 rounded-full ${
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
            className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            重置对话
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
        {!configured && (
          <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-yellow-800">请先在设置页面配置 LLM API Key</p>
          </div>
        )}

        {/* Chat Items */}
        <AnimatePresence mode="popLayout">
          {chatItems.map((item) => {
            if (item.type === 'user-message') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-4 text-right">
                    <motion.div 
                      className="inline-block max-w-[80%] px-4 py-3 rounded-2xl bg-blue-600 text-white shadow-lg"
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 300 }}
                    >
                      <div className="text-sm font-medium mb-1 opacity-70">你</div>
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
                      className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm"
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 300 }}
                    >
                      <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent</div>
                      <MarkdownRenderer content={item.content || ''} />
                    </motion.div>
                  </div>
                </SlideIn>
              )
            }
            
            if (item.type === 'thought') {
              return (
                <SlideIn key={item.id} direction="up">
                  <ThoughtDisclosure
                    label="已思考"
                    content={item.content || ''}
                  />
                </SlideIn>
              )
            }
            
            if (item.type === 'step') {
              return (
                <SlideIn key={item.id} direction="up">
                  <div className="mb-3">
                    <StepCard
                      stepNumber={item.stepNumber || 0}
                      toolName={item.toolName || ''}
                      status={item.status || 'running'}
                      output={item.output}
                      error={item.error}
                      duration={item.duration}
                      arguments={item.arguments}
                      defaultExpanded={item.status === 'running'}
                      autoCollapse={true}
                    />
                  </div>
                </SlideIn>
              )
            }
            
            return null
          })}
        </AnimatePresence>

        {/* LLM Streaming Content */}
        {llmStreamingContent && (
          <SlideIn direction="up">
            <ThoughtDisclosure
              label="思考中"
              content={llmStreamingContent}
              isStreaming
              defaultOpen
            />
          </SlideIn>
        )}

        {/* Summary Streaming Content */}
        {summaryStreamingContent && (
          <SlideIn direction="up">
            <div className="mb-4">
              <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm">
                <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent 正在整理回答</div>
                <div className="whitespace-pre-wrap">
                  {summaryStreamingContent}
                  <motion.span
                    className="inline-block w-2 h-5 bg-blue-500 ml-1"
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.5, repeat: Infinity }}
                  />
                </div>
              </div>
            </div>
          </SlideIn>
        )}

        {/* Loading indicator */}
        {status === 'running' && !llmStreamingContent && !summaryStreamingContent && chatItems.filter(i => i.type === 'step').length === 0 && (
          <div className="mt-4">
            <LoadingSpinner text="Agent 正在思考..." />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
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
