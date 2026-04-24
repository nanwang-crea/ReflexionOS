import { sessionApi } from './sessionApi'
import { useSessionStore } from './sessionStore'
import type { SessionCreatePayload, SessionSummary, SessionUpdatePayload } from '@/types/workspace'

export async function ensureProjectSessionsLoaded(projectId: string): Promise<void> {
  const response = await sessionApi.listProjectSessions(projectId)
  useSessionStore.getState().setProjectSessions(projectId, response.data)
}

export async function createSession(
  projectId: string,
  payload: SessionCreatePayload = {}
): Promise<SessionSummary> {
  const response = await sessionApi.createSession(projectId, payload)
  useSessionStore.getState().upsertSession(projectId, response.data)
  await ensureProjectSessionsLoaded(projectId)
  return response.data
}

export async function updateSession(
  sessionId: string,
  payload: SessionUpdatePayload
): Promise<SessionSummary> {
  const response = await sessionApi.updateSession(sessionId, payload)
  useSessionStore.getState().upsertSession(response.data.projectId, response.data)
  await ensureProjectSessionsLoaded(response.data.projectId)
  return response.data
}

export async function writeSessionPreferences(
  sessionId: string,
  payload: Pick<SessionUpdatePayload, 'preferredProviderId' | 'preferredModelId'>
): Promise<SessionSummary> {
  const response = await sessionApi.updateSession(sessionId, payload)
  useSessionStore.getState().upsertSession(response.data.projectId, response.data)
  await ensureProjectSessionsLoaded(response.data.projectId)
  return response.data
}

export async function renameSession(sessionId: string, title: string): Promise<SessionSummary> {
  return updateSession(sessionId, { title })
}

export async function deleteSession(projectId: string, sessionId: string): Promise<void> {
  await sessionApi.deleteSession(sessionId)
  useSessionStore.getState().removeSession(projectId, sessionId)
  await ensureProjectSessionsLoaded(projectId)
}
