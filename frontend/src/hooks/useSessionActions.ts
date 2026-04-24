import { useCallback } from 'react'
import {
  createSession as createSessionAction,
  deleteSession as deleteSessionAction,
  ensureProjectSessionsLoaded,
  renameSession as renameSessionAction,
} from '@/features/sessions/sessionActions'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionCreatePayload, SessionSummary } from '@/types/workspace'

export function useSessionActions() {
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)

  const createSession = useCallback(async (
    projectId: string,
    payload: SessionCreatePayload = {}
  ): Promise<SessionSummary> => {
    const session = await createSessionAction(projectId, payload)
    setCurrentSessionId(session.id)
    return session
  }, [setCurrentSessionId])

  const renameSession = useCallback(async (sessionId: string, title: string): Promise<SessionSummary> => {
    return renameSessionAction(sessionId, title)
  }, [])

  const deleteSession = useCallback(async (projectId: string, sessionId: string) => {
    await deleteSessionAction(projectId, sessionId)
  }, [])

  const refreshProjectSessions = useCallback(async (projectId: string) => {
    await ensureProjectSessionsLoaded(projectId)
  }, [])

  return {
    createSession,
    renameSession,
    deleteSession,
    refreshProjectSessions,
  }
}
