import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type {
  ConversationSession,
  ConversationSessionDto,
} from '@/types/conversation'
import type {
  SessionCreatePayload,
  SessionUpdatePayload,
} from '@/types/workspace'

function toSessionSummary(dto: ConversationSessionDto): ConversationSession {
  return {
    id: dto.id,
    projectId: dto.project_id,
    title: dto.title,
    preferredProviderId: dto.preferred_provider_id ?? undefined,
    preferredModelId: dto.preferred_model_id ?? undefined,
    lastEventSeq: dto.last_event_seq ?? 0,
    activeTurnId: dto.active_turn_id ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
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
  request: Promise<AxiosResponse<ConversationSessionDto>>
): Promise<AxiosResponse<ConversationSession>> {
  const response = await request
  return {
    ...response,
    data: toSessionSummary(response.data),
  }
}

async function mapSessionListResponse(
  request: Promise<AxiosResponse<ConversationSessionDto[]>>
): Promise<AxiosResponse<ConversationSession[]>> {
  const response = await request
  return {
    ...response,
    data: response.data.map(toSessionSummary),
  }
}

export const sessionApi = {
  listProjectSessions: (projectId: string) =>
    mapSessionListResponse(apiClient.get<ConversationSessionDto[]>(`/api/projects/${projectId}/sessions`)),
  createSession: (projectId: string, data: SessionCreatePayload) =>
    mapSessionResponse(
      apiClient.post<ConversationSessionDto>(
        `/api/projects/${projectId}/sessions`,
        toSessionPayload(data)
      )
    ),
  updateSession: (sessionId: string, data: SessionUpdatePayload) =>
    mapSessionResponse(apiClient.patch<ConversationSessionDto>(`/api/sessions/${sessionId}`, toSessionPayload(data))),
  deleteSession: (sessionId: string) =>
    apiClient.delete(`/api/sessions/${sessionId}`),
}
