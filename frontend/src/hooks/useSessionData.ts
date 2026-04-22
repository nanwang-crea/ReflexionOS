import { useEffect, useMemo } from 'react'
import { demoSessionHistoryById, isDemoMode } from '@/demo/demoData'
import { ensureLLMSettingsLoaded } from '@/features/llm/llmSettingsLoader'
import { useSessionStore } from '@/features/sessions/sessionStore'
import {
  ensureSessionHistoryLoaded,
} from '@/features/sessions/sessionLoader'
import { useProjectStore } from '@/stores/projectStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import type { SessionSummary, WorkspaceSessionRound } from '@/types/workspace'

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
  persistedRounds: WorkspaceSessionRound[]
}

export function useSessionData(): UseSessionDataResult {
  const { currentProject } = useProjectStore()
  const currentSessionId = useWorkspaceStore((state) => state.currentSessionId)
  const setCurrentSessionId = useWorkspaceStore((state) => state.setCurrentSessionId)
  const sessionsByProjectId = useSessionStore((state) => state.sessionsByProjectId)
  const historyBySessionId = useSessionStore((state) => state.historyBySessionId)
  const demoMode = isDemoMode()

  const projectSessions = currentProject ? sessionsByProjectId[currentProject.id] || EMPTY_SESSIONS : EMPTY_SESSIONS
  const hasLoadedProjectSessions = currentProject
    ? Object.prototype.hasOwnProperty.call(sessionsByProjectId, currentProject.id)
    : false
  const currentSessionSummary = useMemo(
    () => findCurrentSessionSummary(projectSessions, currentSessionId),
    [currentSessionId, projectSessions]
  )
  const persistedRounds = useMemo(() => {
    if (!currentSessionSummary) {
      return []
    }

    if (demoMode) {
      return demoSessionHistoryById[currentSessionSummary.id] || []
    }

    return historyBySessionId[currentSessionSummary.id] || []
  }, [currentSessionSummary, demoMode, historyBySessionId])

  useEffect(() => {
    ensureLLMSettingsLoaded().catch((error) => {
      console.error('Failed to load LLM settings:', error)
    })
  }, [])

  useEffect(() => {
    if (!currentSessionId || demoMode) {
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

    ensureSessionHistoryLoaded(currentSessionSummary.id).catch((error) => {
      console.error('Failed to load session history:', error)
    })
  }, [currentSessionId, currentSessionSummary, demoMode, hasLoadedProjectSessions, setCurrentSessionId])

  return {
    currentProject,
    currentSessionId,
    currentSessionSummary,
    persistedRounds,
  }
}
