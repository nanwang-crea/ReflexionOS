/**
 * 文件功能：运行时状态描述工具
 * 文件描述：根据当前会话的运行状态（是否运行中、模型重试信息、消息列表）推断出用于 UI 展示的状态描述（如“正在思考”“正在执行工具”）
 * 核心逻辑：按优先级依次判断重试中 > 模型思考中（有 reasoning_text）> 工具执行中 > 正在整理回答 > 等待模型响应，
 *          未运行则返回 idle 状态
 */
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

/**
 * 函数名：getReasoningText
 * 入参：
 *   - message (ConversationMessage | undefined): 待提取推理文本的消息，可能为空
 * 功能：从消息的 payloadJson 中安全提取 reasoning_text（模型思维链文本）
 * 运行逻辑：读取 message.payloadJson.reasoning_text，非字符串类型则返回空字符串
 * 出参：string - 提取到的推理文本，缺失时为空字符串
 */
function getReasoningText(message: ConversationMessage | undefined): string {
  const value = message?.payloadJson?.reasoning_text
  return typeof value === 'string' ? value : ''
}

/**
 * 函数名：getLatestAssistantMessage
 * 入参：
 *   - messages (ConversationMessage[]): 会话消息列表
 * 功能：从消息列表中查找最后一条助手消息
 * 运行逻辑：从数组末尾向前遍历，找到第一条 messageType 为 'assistant_message' 的消息即返回
 * 出参：ConversationMessage | null - 找到的最新助手消息，未找到则为 null
 */
export function getLatestAssistantMessage(messages: ConversationMessage[]): ConversationMessage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.messageType === 'assistant_message') {
      return message
    }
  }
  return null
}

/**
 * 函数名：getRuntimeStatusDescriptor
 * 入参：
 *   - args.isRunning (boolean): 当前会话是否处于运行状态
 *   - args.retryInfo (LlmRetryDto | null | undefined，可选): 模型重试信息，存在则表示正在重试
 *   - args.messages (ConversationMessage[]): 当前会话的消息列表
 * 功能：综合运行状态、重试信息与消息列表，推断出用于 UI 展示的运行状态描述（类型 + 文案）
 * 运行逻辑：
 *   1. 未运行时返回 idle 状态（空文案）
 *   2. 存在重试信息时返回 retrying（等待模型重试）
 *   3. 最新助手消息携带推理文本时返回 thinking（模型正在思考）
 *   4. 存在处于 streaming/idle 状态的 tool_trace 消息时返回 executing_tool（正在执行工具）
 *   5. 最新助手消息处于 streaming 且已有内容文本时返回 composing（正在整理回答）
 *   6. 以上均不满足时返回 waiting（等待模型响应）
 * 出参：RuntimeStatusDescriptor - 包含状态类型 kind 与展示文案 label
 */
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

/**
 * 函数名：getAssistantReasoningText
 * 入参：
 *   - message (ConversationMessage): 助手消息
 * 功能：对外暴露的辅助函数，提取助手消息的推理文本（思维链）
 * 运行逻辑：直接委托给内部的 getReasoningText 实现
 * 出参：string - 提取到的推理文本，缺失时为空字符串
 */
export function getAssistantReasoningText(message: ConversationMessage): string {
  return getReasoningText(message)
}
