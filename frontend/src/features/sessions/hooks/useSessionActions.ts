import { useCallback } from 'react'
import {
  createSession as createSessionAction,
  deleteSession as deleteSessionAction,
  ensureProjectSessionsLoaded,
  renameSession as renameSessionAction,
} from '@/features/sessions/session.actions'
import { useWorkspaceStore } from '@/features/workspace/stores/workspace.store'
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
