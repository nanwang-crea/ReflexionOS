export interface SessionSummary {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  createdAt: string
  updatedAt: string
}

export interface SessionPayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export type SessionCreatePayload = SessionPayload
export type SessionUpdatePayload = SessionPayload
