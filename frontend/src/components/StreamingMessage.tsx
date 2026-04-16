import { useEffect, useMemo, useState } from 'react'

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

interface ThoughtDisclosureProps {
  label: string
  content: string
  isStreaming?: boolean
  defaultOpen?: boolean
}

export function ThoughtDisclosure({
  label,
  content,
  isStreaming = false,
  defaultOpen = false
}: ThoughtDisclosureProps) {
  const [expanded, setExpanded] = useState(defaultOpen)

  useEffect(() => {
    if (defaultOpen) {
      setExpanded(true)
    }
  }, [defaultOpen])

  const preview = useMemo(() => {
    const normalized = content.replace(/\s+/g, ' ').trim()
    if (!normalized) {
      return isStreaming ? '正在分析当前任务...' : '查看本轮思考过程'
    }
    return normalized.length > 72 ? `${normalized.slice(0, 72)}...` : normalized
  }, [content, isStreaming])

  return (
    <div className="mb-3 max-w-[80%] rounded-xl border border-gray-200 bg-white text-gray-800 shadow-sm">
      <button
        type="button"
        onClick={() => setExpanded(prev => !prev)}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-gray-50"
      >
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
              {label}
            </span>
            {isStreaming && (
              <span className="text-xs text-blue-600">实时更新中</span>
            )}
          </div>
          <div className="truncate text-sm text-gray-500">{preview}</div>
        </div>
        <span className="shrink-0 text-sm text-gray-400">
          {expanded ? '收起' : '展开'}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3">
          <div className="whitespace-pre-wrap text-sm leading-6 text-gray-700">
            {content}
            {isStreaming && (
              <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-blue-500 align-middle" />
            )}
          </div>
        </div>
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
