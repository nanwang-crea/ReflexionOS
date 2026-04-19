import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { demoWorkspaceState, isDemoMode } from '@/demo/demoData'
import type { ChatSession, WorkspaceChatItem } from '@/types/workspace'

interface WorkspaceState {
  sessions: ChatSession[]
  currentSessionId: string | null
  expandedProjectIds: string[]
  expandedSessionProjectIds: string[]
  searchQuery: string
  searchOpen: boolean

  createSession: (
    projectId: string,
    title?: string,
    preferredProviderId?: string | null,
    preferredModelId?: string | null
  ) => ChatSession
  setCurrentSessionId: (sessionId: string | null) => void
  saveSessionItems: (sessionId: string, items: WorkspaceChatItem[]) => void
  updateSessionTitle: (sessionId: string, title: string) => void
  updateSessionPreferences: (
    sessionId: string,
    preferences: { preferredProviderId?: string | null; preferredModelId?: string | null }
  ) => void
  removeSession: (sessionId: string) => void
  touchSession: (sessionId: string) => void
  toggleProjectExpanded: (projectId: string) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  toggleProjectShowAll: (projectId: string) => void
  setSearchQuery: (query: string) => void
  setSearchOpen: (open: boolean) => void
  removeProjectSessions: (projectId: string) => void
}

function createSessionId() {
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createNow() {
  return new Date().toISOString()
}

function upsertExpanded(list: string[], value: string, expanded: boolean) {
  if (expanded) {
    return list.includes(value) ? list : [...list, value]
  }

  return list.filter(item => item !== value)
}

function stripTransientItems(sessions: ChatSession[]) {
  return sessions.map((session) => ({
    ...session,
    items: session.items.filter((item) => !item.transient)
  }))
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      sessions: isDemoMode() ? demoWorkspaceState.sessions : [],
      currentSessionId: isDemoMode() ? demoWorkspaceState.currentSessionId : null,
      expandedProjectIds: isDemoMode() ? demoWorkspaceState.expandedProjectIds : [],
      expandedSessionProjectIds: isDemoMode() ? demoWorkspaceState.expandedSessionProjectIds : [],
      searchQuery: isDemoMode() ? demoWorkspaceState.searchQuery : '',
      searchOpen: isDemoMode() ? demoWorkspaceState.searchOpen : false,

      createSession: (
        projectId,
        title = '新建聊天',
        preferredProviderId = null,
        preferredModelId = null
      ) => {
        const now = createNow()
        const session: ChatSession = {
          id: createSessionId(),
          projectId,
          title,
          preferredProviderId: preferredProviderId || undefined,
          preferredModelId: preferredModelId || undefined,
          items: [],
          createdAt: now,
          updatedAt: now
        }

        set((state) => ({
          sessions: [session, ...state.sessions],
          currentSessionId: session.id,
          expandedProjectIds: state.expandedProjectIds.includes(projectId)
            ? state.expandedProjectIds
            : [...state.expandedProjectIds, projectId]
        }))

        return session
      },

      setCurrentSessionId: (sessionId) => set({ currentSessionId: sessionId }),

      saveSessionItems: (sessionId, items) => set((state) => ({
        sessions: state.sessions.map((session) => (
          session.id === sessionId
            ? {
                ...session,
                items,
                updatedAt: createNow()
              }
            : session
        ))
      })),

      updateSessionTitle: (sessionId, title) => set((state) => ({
        sessions: state.sessions.map((session) => (
          session.id === sessionId
            ? {
                ...session,
                title,
                updatedAt: createNow()
              }
            : session
        ))
      })),

      updateSessionPreferences: (sessionId, preferences) => set((state) => ({
        sessions: state.sessions.map((session) => (
          session.id === sessionId
            ? {
                ...session,
                preferredProviderId: preferences.preferredProviderId || undefined,
                preferredModelId: preferences.preferredModelId || undefined,
                updatedAt: createNow()
              }
            : session
        ))
      })),

      removeSession: (sessionId) => set((state) => {
        const targetSession = state.sessions.find((session) => session.id === sessionId) || null
        const nextSessions = state.sessions.filter((session) => session.id !== sessionId)
        const siblingSessionId = targetSession
          ? nextSessions.find((session) => session.projectId === targetSession.projectId)?.id || null
          : null
        const nextCurrentSessionId = state.currentSessionId === sessionId
          ? siblingSessionId || nextSessions[0]?.id || null
          : state.currentSessionId

        return {
          sessions: nextSessions,
          currentSessionId: nextCurrentSessionId
        }
      }),

      touchSession: (sessionId) => set((state) => ({
        sessions: state.sessions.map((session) => (
          session.id === sessionId
            ? {
                ...session,
                updatedAt: createNow()
              }
            : session
        ))
      })),

      toggleProjectExpanded: (projectId) => set((state) => ({
        expandedProjectIds: state.expandedProjectIds.includes(projectId)
          ? state.expandedProjectIds.filter(id => id !== projectId)
          : [...state.expandedProjectIds, projectId]
      })),

      setProjectExpanded: (projectId, expanded) => set((state) => ({
        expandedProjectIds: upsertExpanded(state.expandedProjectIds, projectId, expanded)
      })),

      toggleProjectShowAll: (projectId) => set((state) => ({
        expandedSessionProjectIds: state.expandedSessionProjectIds.includes(projectId)
          ? state.expandedSessionProjectIds.filter(id => id !== projectId)
          : [...state.expandedSessionProjectIds, projectId]
      })),

      setSearchQuery: (query) => set({ searchQuery: query }),
      setSearchOpen: (open) => set({ searchOpen: open }),

      removeProjectSessions: (projectId) => set((state) => {
        const remainingSessions = state.sessions.filter(session => session.projectId !== projectId)
        const activeSessionStillExists = remainingSessions.some(session => session.id === state.currentSessionId)

        return {
          sessions: remainingSessions,
          currentSessionId: activeSessionStillExists ? state.currentSessionId : null,
          expandedProjectIds: state.expandedProjectIds.filter(id => id !== projectId),
          expandedSessionProjectIds: state.expandedSessionProjectIds.filter(id => id !== projectId)
        }
      })
    }),
    {
      name: isDemoMode() ? 'reflexion-workspace-demo' : 'reflexion-workspace',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sessions: stripTransientItems(state.sessions),
        currentSessionId: state.currentSessionId,
        expandedProjectIds: state.expandedProjectIds,
        expandedSessionProjectIds: state.expandedSessionProjectIds,
        searchQuery: state.searchQuery,
        searchOpen: state.searchOpen
      })
    }
  )
)
