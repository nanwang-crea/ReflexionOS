import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type {
  SessionCreatePayload,
  SessionSummary,
  SessionUpdatePayload,
} from '@/types/workspace'

interface SessionSummaryDto {
  id: string
  project_id: string
  title: string
  preferred_provider_id?: string | null
  preferred_model_id?: string | null
  created_at: string
  updated_at: string
}

function toSessionSummary(session: SessionSummaryDto): SessionSummary {
  return {
    id: session.id,
    projectId: session.project_id,
    title: session.title,
    preferredProviderId: session.preferred_provider_id ?? undefined,
    preferredModelId: session.preferred_model_id ?? undefined,
    createdAt: session.created_at,
    updatedAt: session.updated_at,
  }
}

function toSessionPayload(data: SessionCreatePayload | SessionUpdatePayload) {
  return Object.fromEntries(
    Object.entries({
      title: data.title,
      preferred_provider_id: data.preferredProviderId,
      preferred_model_id: data.preferredModelId,
    }).filter(([, value]) => value !== undefined)
  )
}

async function mapSessionResponse(
  request: Promise<AxiosResponse<SessionSummaryDto>>
): Promise<AxiosResponse<SessionSummary>> {
  const response = await request
  return {
    ...response,
    data: toSessionSummary(response.data),
  }
}

async function mapSessionListResponse(
  request: Promise<AxiosResponse<SessionSummaryDto[]>>
): Promise<AxiosResponse<SessionSummary[]>> {
  const response = await request
  return {
    ...response,
    data: response.data.map(toSessionSummary),
  }
}

export const sessionApi = {
  listProjectSessions: (projectId: string) =>
    mapSessionListResponse(apiClient.get<SessionSummaryDto[]>(`/api/projects/${projectId}/sessions`)),
  createSession: (projectId: string, data: SessionCreatePayload) =>
    mapSessionResponse(
      apiClient.post<SessionSummaryDto>(
        `/api/projects/${projectId}/sessions`,
        toSessionPayload(data)
      )
    ),
  updateSession: (sessionId: string, data: SessionUpdatePayload) =>
    mapSessionResponse(apiClient.patch<SessionSummaryDto>(`/api/sessions/${sessionId}`, toSessionPayload(data))),
  deleteSession: (sessionId: string) =>
    apiClient.delete(`/api/sessions/${sessionId}`),
}
