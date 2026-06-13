import { useConversationStore } from '@/features/conversation/stores/conversation.store'
import type { ConversationMessage } from '@/types/conversation'

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
