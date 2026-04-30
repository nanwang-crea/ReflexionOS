import { useMemo } from 'react'
import { useConversationStore } from '@/features/conversation/conversationStore'
import type { ConversationState } from '@/types/conversation'
import type { ConversationMessage } from '@/types/conversation'

function resolveActiveRunId(conversation: ConversationState | undefined) {
  const activeTurnId = conversation?.session?.activeTurnId
  if (activeTurnId) {
    const activeRunId = conversation.turnsById[activeTurnId]?.activeRunId
    if (activeRunId) {
      return activeRunId
    }
  }

  const activeRun = Object.values(conversation?.runsById ?? {}).find((run) => run.status === 'running' || run.status === 'created')
  return activeRun?.id ?? null
}

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

  const activeRun = useMemo(() => {
    if (!conversation) {
      return null
    }

    const activeRunId = resolveActiveRunId(conversation)
    return activeRunId ? conversation.runsById[activeRunId] ?? null : null
  }, [conversation])

  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'created'

  const plan = useConversationStore((state) => {
    if (!currentSessionId) {
      return null
    }
    return state.planBySessionId[currentSessionId] ?? null
  })

  return {
    conversation,
    messages,
    activeRun,
    isRunning,
    plan,
  }
}
