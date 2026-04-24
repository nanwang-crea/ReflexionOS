import { useEffect, useMemo } from 'react'
import { ensureLLMSettingsLoaded } from '@/features/llm/llmSettingsLoader'
import { useSessionStore } from '@/features/sessions/sessionStore'
import { useProjectStore } from '@/stores/projectStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionSummary } from '@/types/workspace'

const EMPTY_SESSIONS: SessionSummary[] = []

export function findCurrentSessionSummary(
  projectSessions: SessionSummary[],
  currentSessionId: string | null
) {
  if (!currentSessionId) {
    return null
  }

  return projectSessions.find((session) => session.id === currentSessionId) || null
}

export function shouldClearStaleCurrentSessionId(options: {
  currentSessionId: string | null
  currentSessionSummary: SessionSummary | null
  hasLoadedProjectSessions: boolean
}) {
  return Boolean(
    options.currentSessionId &&
    options.hasLoadedProjectSessions &&
    !options.currentSessionSummary
  )
}

interface UseSessionDataResult {
  currentProject: ReturnType<typeof useProjectStore.getState>['currentProject']
  currentSessionId: string | null
  currentSessionSummary: SessionSummary | null
}

export function useSessionData(): UseSessionDataResult {
  const { currentProject } = useProjectStore()
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)
  const sessionsByProjectId = useSessionStore((state) => state.sessionsByProjectId)

  const projectSessions = currentProject ? sessionsByProjectId[currentProject.id] || EMPTY_SESSIONS : EMPTY_SESSIONS
  const hasLoadedProjectSessions = currentProject
    ? Object.prototype.hasOwnProperty.call(sessionsByProjectId, currentProject.id)
    : false
  const currentSessionSummary = useMemo(
    () => findCurrentSessionSummary(projectSessions, currentSessionId),
    [currentSessionId, projectSessions]
  )

  useEffect(() => {
    ensureLLMSettingsLoaded().catch((error) => {
      console.error('Failed to load LLM settings:', error)
    })
  }, [])

  useEffect(() => {
    if (!currentSessionId) {
      return
    }

    if (shouldClearStaleCurrentSessionId({
      currentSessionId,
      currentSessionSummary,
      hasLoadedProjectSessions,
    })) {
      setCurrentSessionId(null)
      return
    }

    if (!currentSessionSummary) {
      return
    }
  }, [currentSessionId, currentSessionSummary, hasLoadedProjectSessions, setCurrentSessionId])

  return {
    currentProject,
    currentSessionId,
    currentSessionSummary,
  }
}
