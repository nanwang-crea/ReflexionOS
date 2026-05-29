import type { ConversationRunStatus } from '@/types/conversation'

export const ACTIVE_RUN_STATUSES = new Set<ConversationRunStatus>(['created', 'running', 'waiting_for_approval', 'resuming'])

interface ActiveRunState {
  session: { activeTurnId: string | null } | null
  turnsById: Record<string, { activeRunId: string | null }>
  runsById: Record<string, { status: ConversationRunStatus }>
}

export function resolveActiveRunId(conversation: ActiveRunState | undefined): string | null {
  if (!conversation) {
    return null
  }

  const activeTurnId = conversation.session?.activeTurnId
  if (activeTurnId) {
    const activeRunId = conversation.turnsById[activeTurnId]?.activeRunId
    if (activeRunId) {
      return activeRunId
    }
  }

  // Fallback: when WebSocket events arrive out of order, session.activeTurnId
  // may not yet reflect the server state. Scan all runs for an active one.
  // The backend (resolve_active_run_id_from_conversation) does NOT need this
  // fallback because it reads from the authoritative snapshot directly.
  const activeRunEntry = Object.entries(conversation.runsById).find(([, run]) => ACTIVE_RUN_STATUSES.has(run.status))
  return activeRunEntry?.[0] ?? null
}

export function resolveActiveRunStatus(conversation: ActiveRunState | undefined): ConversationRunStatus | null {
  if (!conversation) {
    return null
  }

  const activeRunId = resolveActiveRunId(conversation)
  if (activeRunId) {
    return conversation.runsById[activeRunId]?.status ?? null
  }

  return null
}
