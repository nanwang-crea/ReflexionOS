import { useState, useRef, useEffect } from 'react'
import { agentApi, llmApi } from '@/services/apiClient'
import { useProjectStore } from '@/stores/projectStore'
import { useAgentStore } from '@/stores/agentStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { Execution } from '@/types/execution'

export default function AgentWorkspace() {
  const { currentProject } = useProjectStore()
  const { messages, addMessage, setExecutionStatus, reset } = useAgentStore()
  const { configured } = useSettingsStore()
  const [inputValue, setInputValue] = useState('')
  const [execution, setExecution] = useState<Execution | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set())
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    llmApi.getConfig().then((res) => {
      useSettingsStore.getState().setConfigured(res.data.configured || false)
    })
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, execution?.steps])

  const handleSend = async () => {
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
    
    addMessage({
      id: `msg-${Date.now()}`,
      role: 'user',
      content: userMessage,
      timestamp: Date.now()
    })

    setLoading(true)
    setExecutionStatus('running')

    try {
      const response = await agentApi.execute({
        project_id: currentProject.path,
        task: userMessage,
      })
      setExecution(response.data)
      setExecutionStatus(response.data.status)
      
      addMessage({
        id: `msg-${Date.now()}-agent`,
        role: 'assistant',
        content: response.data.result || '任务执行完成',
        timestamp: Date.now()
      })
    } catch (err: any) {
      console.error('Agent execution error:', err)
      const errorMsg = err.response?.data?.detail || err.message || '执行失败'
      addMessage({
        id: `msg-${Date.now()}-error`,
        role: 'assistant',
        content: `错误: ${errorMsg}`,
        timestamp: Date.now()
      })
      setExecutionStatus('failed')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    reset()
    setExecution(null)
    setExpandedSteps(new Set())
  }

  const toggleStep = (stepId: string) => {
    setExpandedSteps(prev => {
      const next = new Set(prev)
      if (next.has(stepId)) {
        next.delete(stepId)
      } else {
        next.add(stepId)
      }
      return next
    })
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return '✅'
      case 'running': return '🔄'
      case 'failed': return '❌'
      default: return '⏸️'
    }
  }

  const getToolIcon = (tool: string) => {
    switch (tool) {
      case 'file': return '📄'
      case 'shell': return '💻'
      case 'patch': return '📝'
      default: return '🔧'
    }
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
        <button
          onClick={handleReset}
          className="px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
        >
          重置对话
        </button>
      </div>

      {/* Main Content - Timeline & Chat */}
      <div className="flex-1 overflow-y-auto p-6 bg-gray-50">
        {/* Warning if not configured */}
        {!configured && (
          <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-yellow-800">
              请先在设置页面配置 LLM API Key
            </p>
          </div>
        )}

        {/* Messages */}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`mb-4 ${msg.role === 'user' ? 'text-right' : ''}`}
          >
            <div
              className={`inline-block max-w-[80%] px-4 py-3 rounded-lg ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-gray-200 text-gray-800'
              }`}
            >
              <div className="text-sm font-medium mb-1 opacity-70">
                {msg.role === 'user' ? '你' : '🤖 Agent'}
              </div>
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
          </div>
        ))}

        {/* Execution Steps Timeline */}
        {execution && execution.steps.length > 0 && (
          <div className="mt-6 bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">执行时间线</h3>
              <div className="text-sm text-gray-500">
                {execution.steps.length} 步骤 | 状态: {execution.status}
              </div>
            </div>
            
            <div className="space-y-3">
              {execution.steps.map((step, index) => (
                <div key={step.id} className="border border-gray-100 rounded-lg">
                  {/* Step Header */}
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50"
                    onClick={() => toggleStep(step.id)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-lg">{getStatusIcon(step.status)}</span>
                      <span className="font-medium">Step {index + 1}</span>
                      <span className="text-gray-500">
                        {getToolIcon(step.tool)} {step.tool}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      {step.duration && <span>{step.duration.toFixed(2)}s</span>}
                      <span>{expandedSteps.has(step.id) ? '▼' : '▶'}</span>
                    </div>
                  </div>

                  {/* Step Details */}
                  {expandedSteps.has(step.id) && (
                    <div className="px-3 pb-3 border-t border-gray-100">
                      {/* Args */}
                      {Object.keys(step.args).length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs font-medium text-gray-500 mb-1">参数:</div>
                          <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                            {JSON.stringify(step.args, null, 2)}
                          </pre>
                        </div>
                      )}
                      
                      {/* Output */}
                      {step.output && (
                        <div className="mt-2">
                          <div className="text-xs font-medium text-gray-500 mb-1">输出:</div>
                          <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-h-40 whitespace-pre-wrap">
                            {step.output}
                          </pre>
                        </div>
                      )}

                      {/* Error */}
                      {step.error && (
                        <div className="mt-2">
                          <div className="text-xs font-medium text-red-500 mb-1">错误:</div>
                          <pre className="text-xs bg-red-50 p-2 rounded text-red-700">
                            {step.error}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {loading && (
          <div className="mt-4 flex items-center gap-2 text-gray-500">
            <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full"></div>
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
            disabled={loading || !configured || !currentProject}
          />
          <button
            onClick={handleSend}
            disabled={loading || !inputValue.trim() || !configured || !currentProject}
            className={`px-6 py-2 rounded-lg font-medium ${
              loading || !inputValue.trim() || !configured || !currentProject
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            发送
          </button>
        </div>
        {!currentProject && (
          <p className="mt-2 text-sm text-gray-500">
            请先在项目页面选择一个项目
          </p>
        )}
      </div>
    </div>
  )
}
