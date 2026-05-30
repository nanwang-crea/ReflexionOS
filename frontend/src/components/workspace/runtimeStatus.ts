import type { ConversationMessage } from '@/types/conversation'
import type { LlmRetryDto } from '@/services/sessionConversationWebSocket'

export type RuntimeStatusKind =
  | 'retrying'
  | 'thinking'
  | 'waiting'
  | 'executing_tool'
  | 'composing'
  | 'idle'

export interface RuntimeStatusDescriptor {
  kind: RuntimeStatusKind
  label: string
}

function getReasoningText(message: ConversationMessage | undefined): string {
  const value = message?.payloadJson?.reasoning_text
  return typeof value === 'string' ? value : ''
}

export function getLatestAssistantMessage(messages: ConversationMessage[]): ConversationMessage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.messageType === 'assistant_message') {
      return message
    }
  }
  return null
}

export function getRuntimeStatusDescriptor(args: {
  isRunning: boolean
  retryInfo?: LlmRetryDto | null
  messages: ConversationMessage[]
}): RuntimeStatusDescriptor {
  const { isRunning, retryInfo = null, messages } = args

  if (!isRunning) {
    return { kind: 'idle', label: '' }
  }

  if (retryInfo) {
    return { kind: 'retrying', label: '等待模型重试' }
  }

  const latestAssistant = getLatestAssistantMessage(messages)
  if (latestAssistant && getReasoningText(latestAssistant)) {
    return { kind: 'thinking', label: '模型正在思考' }
  }

  if (messages.some((message) => (
    message.messageType === 'tool_trace' &&
    (message.streamState === 'streaming' || message.streamState === 'idle')
  ))) {
    return { kind: 'executing_tool', label: '正在执行工具' }
  }

  if (latestAssistant?.streamState === 'streaming' && latestAssistant.contentText.trim()) {
    return { kind: 'composing', label: '正在整理回答' }
  }

  return { kind: 'waiting', label: '等待模型响应' }
}

export function getAssistantReasoningText(message: ConversationMessage): string {
  return getReasoningText(message)
}
