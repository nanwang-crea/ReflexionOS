import { useState } from 'react'

interface StreamingMessageProps {
  content: string
  isStreaming: boolean
}

export function StreamingMessage({ content, isStreaming }: StreamingMessageProps) {
  return (
    <div className="streaming-message">
      <div className="whitespace-pre-wrap">{content}</div>
      {isStreaming && (
        <span className="inline-block w-2 h-5 bg-blue-500 animate-pulse ml-1" />
      )}
    </div>
  )
}

interface ToolExecutionProps {
  toolName: string
  arguments: Record<string, any>
  status: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
}

export function ToolExecution({ toolName, arguments: args, status, output, error, duration }: ToolExecutionProps) {
  const [expanded, setExpanded] = useState(false)
  
  const statusIcon = {
    running: '🔄',
    success: '✅',
    failed: '❌'
  }[status]
  
  const toolIcon = {
    file: '📄',
    shell: '💻',
    patch: '📝'
  }[toolName] || '🔧'

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span>{statusIcon}</span>
          <span className="font-medium">{toolIcon} {toolName}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          {duration && <span>{duration.toFixed(2)}s</span>}
          <span>{expanded ? '▼' : '▶'}</span>
        </div>
      </div>
      
      {expanded && (
        <div className="px-3 pb-3 border-t border-gray-100">
          {Object.keys(args).length > 0 && (
            <div className="mt-2">
              <div className="text-xs font-medium text-gray-500 mb-1">参数:</div>
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}
          
          {output && (
            <div className="mt-2">
              <div className="text-xs font-medium text-gray-500 mb-1">输出:</div>
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-h-40 whitespace-pre-wrap">
                {output}
              </pre>
            </div>
          )}
          
          {error && (
            <div className="mt-2">
              <div className="text-xs font-medium text-red-500 mb-1">错误:</div>
              <pre className="text-xs bg-red-50 p-2 rounded text-red-700">
                {error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface ExecutionTimelineProps {
  steps: Array<{
    id: string
    tool_name: string
    arguments: Record<string, any>
    status: 'running' | 'success' | 'failed'
    output?: string
    error?: string
    duration?: number
  }>
}

export function ExecutionTimeline({ steps }: ExecutionTimelineProps) {
  if (steps.length === 0) return null

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">执行时间线</h3>
        <span className="text-sm text-gray-500">{steps.length} 步骤</span>
      </div>
      
      <div className="space-y-3">
        {steps.map((step) => (
          <ToolExecution
            key={step.id}
            toolName={step.tool_name}
            arguments={step.arguments}
            status={step.status}
            output={step.output}
            error={step.error}
            duration={step.duration}
          />
        ))}
      </div>
    </div>
  )
}
