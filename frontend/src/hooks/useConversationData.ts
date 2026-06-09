import { useMemo } from 'react'
import { useConversationStore } from '@/features/conversation/conversationStore'
import type { ConversationMessage } from '@/types/conversation'
import { ACTIVE_RUN_STATUSES, resolveActiveRunId } from '@/utils/activeRun'

export function useConversationData(currentSessionId: string | null) {
  const conversation = useConversationStore((state) => {
    if (!currentSessionId) {
      return undefined
    }

    return state.conversationsBySessionId[currentSessionId]
  })

  const messages = useMemo(() => {
    if (!conversation) {
      return [] as ConversationMessage[]
    }

    return conversation.messageOrder
      .map((messageId) => conversation.messagesById[messageId])
      .filter((message): message is ConversationMessage => Boolean(message))
  }, [conversation])

  const isRunning = useMemo(() => {
    if (!conversation) {
      return false
    }
    const activeRunId = resolveActiveRunId(conversation)
    if (!activeRunId) {
      return false
    }
    const run = conversation.runsById[activeRunId]
    return run ? ACTIVE_RUN_STATUSES.has(run.status) : false
  }, [conversation])

  const plan = useConversationStore((state) => {
    if (!currentSessionId) {
      return null
    }
    return state.planBySessionId[currentSessionId] ?? null
  })

  const hasMore = conversation?.hasMore ?? true
  const oldestLoadedTurnId = conversation?.nextBeforeTurnId ?? null

  return { messages, isRunning, plan, hasMore, oldestLoadedTurnId }
}
