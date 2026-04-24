import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionSummary } from '@/types/workspace'
import {
  findCurrentSessionSummary,
  shouldClearStaleCurrentSessionId,
} from './useSessionData'

const {
  ensureLLMSettingsLoadedMock,
  projectStoreState,
  workspaceStoreState,
  sessionStoreState,
} = vi.hoisted(() => ({
  ensureLLMSettingsLoadedMock: vi.fn(),
  projectStoreState: {
    currentProject: null as { id: string } | null,
  },
  workspaceStoreState: {
    currentSessionId: null as string | null,
    setCurrentSessionId: vi.fn(),
  },
  sessionStoreState: {
    sessionsByProjectId: {} as Record<string, SessionSummary[]>,
  },
}))

vi.mock('react', () => ({
  useEffect: (effect: () => void | (() => void)) => {
    effect()
  },
  useMemo: <T>(factory: () => T) => factory(),
}))

vi.mock('@/demo/demoData', () => ({
  isDemoMode: () => false,
}))

vi.mock('@/features/llm/llmSettingsLoader', () => ({
  ensureLLMSettingsLoaded: ensureLLMSettingsLoadedMock,
}))

vi.mock('@/stores/projectStore', () => ({
  useProjectStore: Object.assign(
    (selector?: (state: typeof projectStoreState) => unknown) =>
      selector ? selector(projectStoreState) : projectStoreState,
    {
      getState: () => projectStoreState,
    }
  ),
}))

vi.mock('@/stores/workspaceStore', () => ({
  useWorkspaceStore: (selector: (state: typeof workspaceStoreState) => unknown) =>
    selector(workspaceStoreState),
}))

vi.mock('@/features/sessions/sessionStore', () => ({
  useSessionStore: (selector: (state: typeof sessionStoreState) => unknown) =>
    selector(sessionStoreState),
}))

function createSession(id: string): SessionSummary {
  return {
    id,
    projectId: 'project-1',
    title: id,
    preferredProviderId: 'provider-a',
    preferredModelId: 'model-a',
    createdAt: '2026-04-21T00:00:00Z',
    updatedAt: '2026-04-21T00:00:00Z',
  }
}

describe('useSessionData helpers', () => {
  beforeEach(() => {
    vi.resetModules()
    ensureLLMSettingsLoadedMock.mockReset()
    ensureLLMSettingsLoadedMock.mockResolvedValue(undefined)
    projectStoreState.currentProject = null
    workspaceStoreState.currentSessionId = null
    workspaceStoreState.setCurrentSessionId.mockReset()
    sessionStoreState.sessionsByProjectId = {}
  })

  it('does not clear the currentSessionId before project sessions finish loading', () => {
    const projectSessions = [createSession('session-1')]

    expect(
      shouldClearStaleCurrentSessionId({
        currentSessionId: 'missing-session',
        currentSessionSummary: findCurrentSessionSummary(projectSessions, 'missing-session'),
        hasLoadedProjectSessions: false,
      })
    ).toBe(false)
  })

  it('clears stale currentSessionId when it does not exist after project sessions load', () => {
    const projectSessions = [createSession('session-1')]

    expect(
      shouldClearStaleCurrentSessionId({
        currentSessionId: 'missing-session',
        currentSessionSummary: findCurrentSessionSummary(projectSessions, 'missing-session'),
        hasLoadedProjectSessions: true,
      })
    ).toBe(true)
  })

  it('keeps the currentSessionId when the selected summary still exists', () => {
    const projectSessions = [createSession('session-1')]
    const currentSessionSummary = findCurrentSessionSummary(projectSessions, 'session-1')

    expect(
      shouldClearStaleCurrentSessionId({
        currentSessionId: 'session-1',
        currentSessionSummary,
        hasLoadedProjectSessions: true,
      })
    ).toBe(false)
  })

  it('does not reload current project session summaries inside useSessionData', async () => {
    projectStoreState.currentProject = { id: 'project-1' }
    workspaceStoreState.currentSessionId = 'session-1'
    sessionStoreState.sessionsByProjectId = {
      'project-1': [createSession('session-1')],
    }

    const { useSessionData } = await import('./useSessionData')
    const result = useSessionData()

    expect(result.currentSessionSummary?.id).toBe('session-1')
    expect(ensureLLMSettingsLoadedMock).toHaveBeenCalledTimes(1)
    expect(workspaceStoreState.setCurrentSessionId).not.toHaveBeenCalled()
  })
})
