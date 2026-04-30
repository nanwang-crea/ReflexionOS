import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export interface WorkspaceUiState {
  currentSessionId: string | null
  expandedProjectIds: string[]
  expandedSessionProjectIds: string[]
  searchQuery: string
  searchOpen: boolean
}

interface WorkspaceState extends WorkspaceUiState {

  setCurrentSessionId: (sessionId: string | null) => void
  toggleProjectExpanded: (projectId: string) => void
  setProjectExpanded: (projectId: string, expanded: boolean) => void
  toggleProjectShowAll: (projectId: string) => void
  setSearchQuery: (query: string) => void
  setSearchOpen: (open: boolean) => void
}

function partializeWorkspaceUiState(state: WorkspaceState): WorkspaceUiState {
  return {
    currentSessionId: state.currentSessionId,
    expandedProjectIds: state.expandedProjectIds,
    expandedSessionProjectIds: state.expandedSessionProjectIds,
    searchQuery: state.searchQuery,
    searchOpen: state.searchOpen,
  }
}

const defaultWorkspaceUiState: WorkspaceUiState = {
  currentSessionId: null,
  expandedProjectIds: [],
  expandedSessionProjectIds: [],
  searchQuery: '',
  searchOpen: false,
}

function upsertExpanded(list: string[], value: string, expanded: boolean) {
  if (expanded) {
    return list.includes(value) ? list : [...list, value]
  }

  return list.filter(item => item !== value)
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      ...defaultWorkspaceUiState,

      setCurrentSessionId: (sessionId) => set({ currentSessionId: sessionId }),

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
      setSearchOpen: (open) => set({ searchOpen: open })
    }),
    {
      name: 'reflexion-workspace',
      storage: createJSONStorage(() => localStorage),
      partialize: partializeWorkspaceUiState
    }
  )
)
