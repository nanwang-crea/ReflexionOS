import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'

export interface ActiveFile {
  path: string
  language: string
}

const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 480
const DEFAULT_SIDEBAR_WIDTH = 240

interface CodeTabState {
  workspaceTab: WorkspaceTab
  activeFile: ActiveFile | null
  isDirty: boolean
  sidebarOpen: boolean
  sidebarWidth: number
  expandedDirs: Record<string, boolean>
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  setActiveFile: (path: string, language: string) => void
  setDirty: (dirty: boolean) => void
  clearActiveFile: () => void
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
  setSidebarWidth: (width: number) => void
  toggleDir: (path: string) => void
  setDirExpanded: (path: string, expanded: boolean) => void
}

export { MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH }

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  activeFile: null,
  isDirty: false,
  sidebarOpen: false,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
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
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarWidth: (width) => set({ sidebarWidth: Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, width)) }),
  toggleDir: (path) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: !state.expandedDirs[path] },
    })),
  setDirExpanded: (path, expanded) =>
    set((state) => ({
      expandedDirs: { ...state.expandedDirs, [path]: expanded },
    })),
}))
