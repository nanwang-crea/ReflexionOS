// 文件功能：获取指定会话中当前正在流式输出（或空闲待续）的助手消息
// 文件描述：从会话 store 中按消息顺序倒序查找最近一条处于 streaming/idle 状态的 assistant_message
// 核心逻辑：订阅 conversation.store，在消息顺序数组中从后往前遍历，命中即返回，找不到则返回 null
import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import type { ConversationMessage } from '@/types/conversation'

// 函数名：useStreamingMessage
// 入参：
//   - sessionId (string | null): 目标会话 ID，为 null 时表示无当前会话
// 功能：返回当前会话里正在流式输出（或流式空闲）的那条助手消息，供 UI 展示打字机效果等
// 运行逻辑：
//   1. sessionId 为空直接返回 null
//   2. 从 store 中取出该会话的对话数据，若不存在也返回 null
//   3. 从 messageOrder 末尾开始倒序遍历，找到第一条 streamState 为 streaming 或 idle
//      且 messageType 为 assistant_message 的消息即返回
//   4. 遍历完未命中则返回 null
// 出参：ConversationMessage | null - 命中的流式助手消息，或 null
export function useStreamingMessage(sessionId: string | null): ConversationMessage | null {
  return useConversationStore((state) => {
    if (!sessionId) return null
    const conversation = state.conversationsBySessionId[sessionId]
    if (!conversation) return null
    for (let i = conversation.messageOrder.length - 1; i >= 0; i--) {
      const messageId = conversation.messageOrder[i]
      const message = conversation.messagesById[messageId]
      if (message && (message.streamState === 'streaming' || message.streamState === 'idle') && message.messageType === 'assistant_message') {
        return message
      }
    }
    return null
  })
}
