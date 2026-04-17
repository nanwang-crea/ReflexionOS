export function buildThoughtPreview(content: string, isStreaming = false) {
  const normalized = content.replace(/\s+/g, ' ').trim()

  if (!normalized) {
    return isStreaming ? '正在分析当前任务...' : '等待执行轨迹...'
  }

  return normalized.length > 72 ? `${normalized.slice(0, 72)}...` : normalized
}

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
