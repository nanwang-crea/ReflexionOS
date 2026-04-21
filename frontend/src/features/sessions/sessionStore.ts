import { create } from 'zustand'
import type { SessionSummary, WorkspaceSessionRound } from '@/types/workspace'

interface SessionState {
  sessionsByProjectId: Record<string, SessionSummary[]>
  historyBySessionId: Record<string, WorkspaceSessionRound[]>
  setProjectSessions: (projectId: string, sessions: SessionSummary[]) => void
  setSessionHistory: (sessionId: string, rounds: WorkspaceSessionRound[]) => void
  upsertSession: (projectId: string, session: SessionSummary) => void
  removeSession: (projectId: string, sessionId: string) => void
}

export const createSessionStore = () => create<SessionState>((set) => ({
  sessionsByProjectId: {},
  historyBySessionId: {},
  setProjectSessions: (projectId, sessions) => set((state) => {
    const nextSessionIds = new Set(sessions.map((session) => session.id))
    const previousSessionIds = new Set(
      (state.sessionsByProjectId[projectId] || []).map((session) => session.id)
    )

    return {
      sessionsByProjectId: {
        ...state.sessionsByProjectId,
        [projectId]: sessions,
      },
      historyBySessionId: Object.fromEntries(
        Object.entries(state.historyBySessionId).filter(([sessionId]) => (
          !previousSessionIds.has(sessionId) || nextSessionIds.has(sessionId)
        ))
      ),
    }
  }),
  setSessionHistory: (sessionId, rounds) => set((state) => ({
    historyBySessionId: {
      ...state.historyBySessionId,
      [sessionId]: rounds,
    },
  })),
  upsertSession: (projectId, session) => set((state) => {
    const sessions = state.sessionsByProjectId[projectId] || []
    const existingIndex = sessions.findIndex((entry) => entry.id === session.id)

    if (existingIndex === -1) {
      return {
        sessionsByProjectId: {
          ...state.sessionsByProjectId,
          [projectId]: [session, ...sessions],
        },
      }
    }

    return {
      sessionsByProjectId: {
        ...state.sessionsByProjectId,
        [projectId]: sessions.map((entry) => (entry.id === session.id ? session : entry)),
      },
    }
  }),
  removeSession: (projectId, sessionId) => set((state) => ({
    sessionsByProjectId: {
      ...state.sessionsByProjectId,
      [projectId]: (state.sessionsByProjectId[projectId] || []).filter((session) => session.id !== sessionId),
    },
    historyBySessionId: Object.fromEntries(
      Object.entries(state.historyBySessionId).filter(([id]) => id !== sessionId)
    ),
  })),
}))

export const useSessionStore = createSessionStore()

export type { SessionState }
