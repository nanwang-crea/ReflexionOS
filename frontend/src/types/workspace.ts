export interface SessionSummary {
  id: string
  projectId: string
  title: string
  preferredProviderId?: string
  preferredModelId?: string
  createdAt: string
  updatedAt: string
}

export interface SessionCreatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}

export interface SessionUpdatePayload {
  title?: string
  preferredProviderId?: string | null
  preferredModelId?: string | null
}
