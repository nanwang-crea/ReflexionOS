import { create } from 'zustand'
import type { SessionSummary } from '@/types/workspace'

interface SessionState {
  sessionsByProjectId: Record<string, SessionSummary[]>
  setProjectSessions: (projectId: string, sessions: SessionSummary[]) => void
  upsertSession: (projectId: string, session: SessionSummary) => void
  removeSession: (projectId: string, sessionId: string) => void
}

export const createSessionStore = () => create<SessionState>((set) => ({
  sessionsByProjectId: {},
  setProjectSessions: (projectId, sessions) => set((state) => ({
    sessionsByProjectId: {
      ...state.sessionsByProjectId,
      [projectId]: sessions,
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
  })),
}))

export const useSessionStore = createSessionStore()

export type { SessionState }
