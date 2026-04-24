import type { ConversationMessage, ConversationState } from '@/types/conversation'
import type { ConversationStoreState } from './conversationStore'

export function selectConversationState(
  state: ConversationStoreState,
  sessionId: string
): ConversationState | undefined {
  return state.conversationsBySessionId[sessionId]
}

export function selectConversationMessages(
  state: ConversationStoreState,
  sessionId: string
): ConversationMessage[] {
  const conversation = state.conversationsBySessionId[sessionId]
  if (!conversation) {
    return []
  }

  return conversation.messageOrder
    .map((messageId) => conversation.messagesById[messageId])
    .filter((message): message is ConversationMessage => Boolean(message))
}
