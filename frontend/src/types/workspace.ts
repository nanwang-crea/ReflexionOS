import type { ConversationSession } from '@/types/conversation'

export type SessionSummary = ConversationSession

export interface SessionPayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export type SessionCreatePayload = SessionPayload
export type SessionUpdatePayload = SessionPayload
