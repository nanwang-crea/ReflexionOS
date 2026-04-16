import { useState, useRef, useEffect, useCallback } from 'react'
import { ExecutionWebSocket } from '@/services/websocketClient'
import { ThoughtDisclosure } from '@/components/StreamingMessage'
import { useProjectStore } from '@/stores/projectStore'
import { useSettingsStore } from '@/stores/settingsStore'

interface ToolStep {
  id: string
  tool_name: string
  arguments: Record<string, any>
  status: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
}

interface Message {
  id: string
  type: 'message'
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

interface ThoughtItem {
  id: string
  type: 'thought'
  content: string
}

type ChatItem = Message | ThoughtItem

export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const { configured } = useSettingsStore()
  
  const [inputValue, setInputValue] = useState('')
  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [steps, setSteps] = useState<ToolStep[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatItems, llmStreamingContent, summaryStreamingContent, steps])

  const appendChatMessage = useCallback((role: 'user' | 'assistant', content: string) => {
    if (!content) return

    setChatItems(prev => [...prev, {
      id: `msg-${Date.now()}`,
      type: 'message',
      role,
      content,
      isStreaming: false
    }])
  }, [])

  const appendAssistantMessage = useCallback((content: string) => {
    appendChatMessage('assistant', content)
  }, [appendChatMessage])

  const appendThoughtItem = useCallback((content: string) => {
    if (!content) return

    setChatItems(prev => [...prev, {
      id: `thought-${Date.now()}`,
      type: 'thought',
      content
    }])
  }, [])

  const flushLlmStreamingMessage = useCallback((
    target: 'thought' | 'assistant',
    fallbackContent = ''
  ) => {
    const content = llmStreamingRef.current || fallbackContent
    if (!content) return

    if (target === 'thought') {
      appendThoughtItem(content)
    } else {
      appendAssistantMessage(content)
    }

    llmStreamingRef.current = ''
    setLlmStreamingContent('')
  }, [appendAssistantMessage, appendThoughtItem])

  const connectWebSocket = useCallback(async () => {
    if (wsRef.current?.isConnected()) return
    
    const executionId = `exec-${Date.now()}`
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
      const newStep: ToolStep = {
        id: `step-${stepCounterRef.current}`,
        tool_name: data.tool_name,
        arguments: data.arguments,
        status: 'running'
      }
      setSteps(prev => [...prev, newStep])
    })
    
    ws.on('tool:start', (data) => {
      setSteps(prev => prev.map(s => 
        s.tool_name === data.tool_name && s.status === 'running'
          ? { ...s, status: 'running' }
          : s
      ))
    })
    
    ws.on('tool:result', (data) => {
      setSteps(prev => prev.map(s =>
        s.tool_name === data.tool_name && s.status === 'running'
          ? { ...s, status: data.success ? 'success' : 'failed', output: data.output, duration: data.duration }
          : s
      ))
    })
    
    ws.on('tool:error', (data) => {
      setSteps(prev => prev.map(s =>
        s.tool_name === data.tool_name && s.status === 'running'
          ? { ...s, status: 'failed', error: data.error }
          : s
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
      appendAssistantMessage(data.summary)
      finalMessageHandledRef.current = true
      summaryStartedRef.current = false
      summaryStreamingRef.current = ''
      setSummaryStreamingContent('')
    })
    
    ws.on('execution:complete', (data) => {
      setIsExecuting(false)

      if (!summaryStartedRef.current && !finalMessageHandledRef.current) {
        flushLlmStreamingMessage('assistant', data.result)
        finalMessageHandledRef.current = true
      }
    })
    
    ws.on('execution:error', (data) => {
      setIsExecuting(false)
      summaryStartedRef.current = false
      finalMessageHandledRef.current = false
      llmStreamingRef.current = ''
      summaryStreamingRef.current = ''
      setLlmStreamingContent('')
      setSummaryStreamingContent('')
      appendAssistantMessage(`错误: ${data.error}`)
    })
    
    try {
      setConnectionStatus('connecting')
      await ws.connect(executionId)
      setConnectionStatus('connected')
      wsRef.current = ws
    } catch (error) {
      console.error('WebSocket connection failed:', error)
      setConnectionStatus('disconnected')
    }
  }, [appendAssistantMessage, flushLlmStreamingMessage])

  const handleSend = useCallback(async () => {
    if (!inputValue.trim()) return
    if (!currentProject) {
      alert('请先选择一个项目')
      return
    }
    if (!configured) {
      alert('请先在设置页面配置 LLM')
      return
    }

    const userMessage = inputValue.trim()
    setInputValue('')
    
    appendChatMessage('user', userMessage)
    
    setSteps([])
    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    setLlmStreamingContent('')
    setSummaryStreamingContent('')
    setIsExecuting(true)
    
    if (!wsRef.current?.isConnected()) {
      await connectWebSocket()
    }
    
    wsRef.current?.startExecution(userMessage, currentProject.path)
  }, [appendChatMessage, connectWebSocket, configured, currentProject, inputValue])

  const handleReset = () => {
    setChatItems([])
    setSteps([])
    llmStreamingRef.current = ''
    summaryStreamingRef.current = ''
    summaryStartedRef.current = false
    finalMessageHandledRef.current = false
    setLlmStreamingContent('')
    setSummaryStreamingContent('')
    setIsExecuting(false)
    stepCounterRef.current = 0
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
        {chatItems.map((item) => {
          if (item.type === 'thought') {
            return (
              <ThoughtDisclosure
                key={item.id}
                label="已思考"
                content={item.content}
              />
            )
          }

          return (
            <div
              key={item.id}
              className={`mb-4 ${item.role === 'user' ? 'text-right' : ''}`}
            >
              <div
                className={`inline-block max-w-[80%] px-4 py-3 rounded-2xl ${
                  item.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border border-gray-200 text-gray-800 shadow-sm'
                }`}
              >
                <div className="text-sm font-medium mb-1 opacity-70">
                  {item.role === 'user' ? '你' : '🤖 Agent'}
                </div>
                <div className="whitespace-pre-wrap">{item.content}</div>
              </div>
            </div>
          )
        })}

        {/* LLM Streaming Content */}
        {llmStreamingContent && (
          <ThoughtDisclosure
            label="思考中"
            content={llmStreamingContent}
            isStreaming
            defaultOpen
          />
        )}

        {/* Summary Streaming Content */}
        {summaryStreamingContent && (
          <div className="mb-4">
            <div className="inline-block max-w-[80%] px-4 py-3 rounded-2xl border border-gray-200 bg-white text-gray-800 shadow-sm">
              <div className="mb-1 text-sm font-medium opacity-70">🤖 Agent 正在整理回答</div>
              <div className="whitespace-pre-wrap">
                {summaryStreamingContent}
                <span className="inline-block w-2 h-5 bg-blue-500 animate-pulse ml-1" />
              </div>
            </div>
          </div>
        )}

        {/* Execution Timeline */}
        {steps.length > 0 && (
          <div className="mt-6 bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">执行时间线</h3>
              <span className="text-sm text-gray-500">{steps.length} 步骤</span>
            </div>
            
            <div className="space-y-3">
              {steps.map((step, index) => (
                <div key={step.id} className="border border-gray-100 rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between p-3 hover:bg-gray-50">
                    <div className="flex items-center gap-3">
                      <span>
                        {step.status === 'running' ? '🔄' :
                         step.status === 'success' ? '✅' : '❌'}
                      </span>
                      <span className="font-medium">Step {index + 1}</span>
                      <span className="text-gray-500">{step.tool_name}</span>
                    </div>
                    <div className="text-sm text-gray-500">
                      {step.duration && `${step.duration.toFixed(2)}s`}
                    </div>
                  </div>
                  
                  {step.output && (
                    <div className="px-3 pb-3 border-t border-gray-100">
                      <pre className="text-xs bg-gray-50 p-2 rounded mt-2 overflow-auto max-h-32">
                        {step.output}
                      </pre>
                    </div>
                  )}
                  
                  {step.error && (
                    <div className="px-3 pb-3 border-t border-gray-100">
                      <pre className="text-xs bg-red-50 p-2 rounded mt-2 text-red-700">
                        {step.error}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isExecuting && !llmStreamingContent && !summaryStreamingContent && steps.length === 0 && (
          <div className="mt-4 flex items-center gap-2 text-gray-500">
            <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full" />
            <span>Agent 正在思考...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-gray-200 bg-white p-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="描述你想要 Agent 做什么..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isExecuting || !configured || !currentProject}
          />
          <button
            onClick={handleSend}
            disabled={isExecuting || !inputValue.trim() || !configured || !currentProject}
            className={`px-6 py-2 rounded-lg font-medium ${
              isExecuting || !inputValue.trim() || !configured || !currentProject
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {isExecuting ? '执行中...' : '发送'}
          </button>
        </div>
        {!currentProject && (
          <p className="mt-2 text-sm text-gray-500">请先在项目页面选择一个项目</p>
        )}
      </div>
    </div>
  )
}
