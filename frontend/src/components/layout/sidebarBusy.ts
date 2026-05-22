import { ACTIVE_RUN_STATUSES, resolveActiveRunStatus } from '@/utils/activeRun'
import type { ConversationRunStatus } from '@/types/conversation'

type BusyConversationState = {
  session: { activeTurnId: string | null } | null
  turnsById: Record<string, { activeRunId: string | null }>
  runsById: Record<string, { status: ConversationRunStatus }>
}

export function isConversationBusy(conversation: BusyConversationState | undefined): boolean {
  const status = resolveActiveRunStatus(conversation)
  return status ? ACTIVE_RUN_STATUSES.has(status) : false
}
