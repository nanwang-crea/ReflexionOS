import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'

export interface ActiveFile {
  path: string
  language: string
}

interface CodeTabState {
  workspaceTab: WorkspaceTab
  activeFile: ActiveFile | null
  isDirty: boolean
  sidebarOpen: boolean
  expandedDirs: Record<string, boolean>
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  setActiveFile: (path: string, language: string) => void
  setDirty: (dirty: boolean) => void
  clearActiveFile: () => void
  setSidebarOpen: (open: boolean) => void
  toggleDir: (path: string) => void
  setDirExpanded: (path: string, expanded: boolean) => void
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  activeFile: null,
  isDirty: false,
  sidebarOpen: true,
  expandedDirs: {},

  setWorkspaceTab: (tab) => set({ workspaceTab: tab }),
  setActiveFile: (path, language) =>
    set({
      activeFile: { path, language },
      isDirty: false,
      workspaceTab: 'code',
    }),
  setDirty: (dirty) => set({ isDirty: dirty }),
  clearActiveFile: () => set({ activeFile: null, isDirty: false }),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleDir: (path) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: !state.expandedDirs[path] },
    })),
  setDirExpanded: (path, expanded) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: expanded },
    })),
}))
