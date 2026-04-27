import type { ConversationRunStatus } from '@/types/conversation'

type BusyConversationState = {
  session: { activeTurnId: string | null } | null
  turnsById: Record<string, { activeRunId: string | null }>
  runsById: Record<string, { status: ConversationRunStatus }>
}

function resolveActiveRunStatus(conversation: BusyConversationState | undefined): ConversationRunStatus | null {
  if (!conversation) {
    return null
  }

  const activeTurnId = conversation.session?.activeTurnId
  if (activeTurnId) {
    const activeRunId = conversation.turnsById[activeTurnId]?.activeRunId
    if (activeRunId) {
      return conversation.runsById[activeRunId]?.status ?? null
    }
  }

  const activeRun = Object.values(conversation.runsById).find((run) => run.status === 'running' || run.status === 'created')
  return activeRun?.status ?? null
}

export function isConversationBusy(conversation: BusyConversationState | undefined): boolean {
  const status = resolveActiveRunStatus(conversation)
  return status === 'running' || status === 'created'
}
