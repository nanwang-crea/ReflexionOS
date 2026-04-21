import type { AxiosResponse } from 'axios'
import { apiClient } from '@/services/apiClient'
import type {
  SessionCreatePayload,
  SessionHistory,
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

interface SessionHistoryItemDto {
  id: string
  type: 'user-message' | 'assistant-message' | 'agent-update' | 'action-receipt'
  content: string
  receipt_status: SessionHistory['rounds'][number]['items'][number]['receiptStatus'] | null
  details: SessionHistory['rounds'][number]['items'][number]['details']
  created_at: string
}

interface SessionHistoryRoundDto {
  id: string
  created_at: string
  items: SessionHistoryItemDto[]
}

interface SessionHistoryDto {
  session_id: string
  project_id: string | null
  rounds: SessionHistoryRoundDto[]
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

function toSessionHistory(history: SessionHistoryDto): SessionHistory {
  return {
    sessionId: history.session_id,
    projectId: history.project_id,
    rounds: history.rounds.map((round) => ({
      id: round.id,
      createdAt: round.created_at,
      items: round.items.map((item) => ({
        id: item.id,
        type: item.type,
        content: item.content,
        receiptStatus: item.receipt_status ?? undefined,
        details: item.details,
        createdAt: item.created_at,
      })),
    })),
  }
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

async function mapSessionHistoryResponse(
  request: Promise<AxiosResponse<SessionHistoryDto>>
): Promise<AxiosResponse<SessionHistory>> {
  const response = await request
  return {
    ...response,
    data: toSessionHistory(response.data),
  }
}

export const sessionApi = {
  listProjectSessions: (projectId: string) =>
    mapSessionListResponse(apiClient.get<SessionSummaryDto[]>(`/api/projects/${projectId}/sessions`)),
  createSession: (projectId: string, data: SessionCreatePayload) =>
    mapSessionResponse(apiClient.post<SessionSummaryDto>(`/api/projects/${projectId}/sessions`, toSessionPayload(data))),
  getSessionHistory: (sessionId: string) =>
    mapSessionHistoryResponse(apiClient.get<SessionHistoryDto>(`/api/sessions/${sessionId}/history`)),
  updateSession: (sessionId: string, data: SessionUpdatePayload) =>
    mapSessionResponse(apiClient.patch<SessionSummaryDto>(`/api/sessions/${sessionId}`, toSessionPayload(data))),
  deleteSession: (sessionId: string) =>
    apiClient.delete(`/api/sessions/${sessionId}`),
}
