import { useCallback } from 'react'
import {
  createSession as createSessionAction,
  updateSession as updateSessionAction,
} from '@/features/sessions/sessionActions'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionCreatePayload, SessionSummary, SessionUpdatePayload } from '@/types/workspace'

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

  const updateSession = useCallback(async (
    sessionId: string,
    payload: SessionUpdatePayload
  ): Promise<SessionSummary> => {
    return updateSessionAction(sessionId, payload)
  }, [])

  const updateSessionPreferences = useCallback(async (
    sessionId: string,
    payload: Pick<SessionUpdatePayload, 'preferredProviderId' | 'preferredModelId'>
  ) => {
    return updateSession(sessionId, payload)
  }, [updateSession])

  return {
    createSession,
    updateSession,
    updateSessionPreferences,
  }
}
