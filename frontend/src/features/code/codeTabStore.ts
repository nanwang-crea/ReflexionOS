import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'
export type ViewMode = 'edit' | 'diff'

export interface OpenFile {
  id: string
  path: string
  language: string
  isDirty: boolean
  viewMode: ViewMode
  modifiedContent?: string
  originalContent?: string
}

const MIN_SIDEBAR_WIDTH = 180
const MAX_SIDEBAR_WIDTH = 480
const DEFAULT_SIDEBAR_WIDTH = 240

let _nextFileId = 0

interface CodeTabState {
  workspaceTab: WorkspaceTab
  openFiles: OpenFile[]
  activeFileId: string | null
  sidebarOpen: boolean
  sidebarWidth: number
  expandedDirs: Record<string, boolean>
  sidebarTab: 'files' | 'changes'
  activeFile: OpenFile | null
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  openFile: (path: string, viewMode: ViewMode) => void
  closeFile: (id: string) => void
  setViewMode: (id: string, mode: ViewMode) => void
  setDirty: (id: string, isDirty: boolean, modifiedContent?: string) => void
  clearDirty: (id: string) => void
  setFileLanguage: (id: string, language: string) => void
  setActiveFile: (path: string, language: string) => void
  setSidebarOpen: (open: boolean) => void
  toggleSidebar: () => void
  setSidebarWidth: (width: number) => void
  toggleDir: (path: string) => void
  setDirExpanded: (path: string, expanded: boolean) => void
  setSidebarTab: (tab: 'files' | 'changes') => void
}

export { MIN_SIDEBAR_WIDTH, MAX_SIDEBAR_WIDTH }

function _computeActiveFile(state: CodeTabState): OpenFile | null {
  if (!state.activeFileId) return null
  return state.openFiles.find((f) => f.id === state.activeFileId) ?? null
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  openFiles: [],
  activeFileId: null,
  sidebarOpen: false,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
  expandedDirs: {},
  sidebarTab: 'files' as const,
  activeFile: null,

  setWorkspaceTab: (tab) => set({ workspaceTab: tab }),

  openFile: (path, viewMode) =>
    set((state) => {
      const existing = state.openFiles.find((f) => f.path === path)
      if (existing) {
        return {
          activeFileId: existing.id,
          workspaceTab: 'code',
          activeFile: existing,
        }
      }
      const newFile: OpenFile = {
        id: `file-${++_nextFileId}`,
        path,
        language: '',
        isDirty: false,
        viewMode,
      }
      const nextFiles = [...state.openFiles, newFile]
      return {
        openFiles: nextFiles,
        activeFileId: newFile.id,
        workspaceTab: 'code',
        activeFile: newFile,
      }
    }),

  closeFile: (id) =>
    set((state) => {
      const idx = state.openFiles.findIndex((f) => f.id === id)
      if (idx === -1) return state
      const nextFiles = state.openFiles.filter((f) => f.id !== id)
      let nextActiveId: string | null = null
      if (state.activeFileId === id) {
        if (nextFiles.length === 0) {
          nextActiveId = null
        } else if (idx < nextFiles.length) {
          nextActiveId = nextFiles[idx].id
        } else {
          nextActiveId = nextFiles[nextFiles.length - 1].id
        }
      } else {
        nextActiveId = state.activeFileId
      }
      const nextActive = nextActiveId
        ? nextFiles.find((f) => f.id === nextActiveId) ?? null
        : null
      return {
        openFiles: nextFiles,
        activeFileId: nextActiveId,
        activeFile: nextActive,
      }
    }),

  setViewMode: (id, mode) =>
    set((state) => {
      const nextFiles = state.openFiles.map((f) =>
        f.id === id ? { ...f, viewMode: mode } : f,
      )
      const nextActive = state.activeFileId === id
        ? { ...state.activeFile!, viewMode: mode }
        : state.activeFile
      return { openFiles: nextFiles, activeFile: nextActive }
    }),

  setDirty: (id, isDirty, modifiedContent) =>
    set((state) => {
      const nextFiles = state.openFiles.map((f) =>
        f.id === id ? { ...f, isDirty, modifiedContent } : f,
      )
      const nextActive = state.activeFileId === id
        ? { ...state.activeFile!, isDirty, modifiedContent }
        : state.activeFile
      return { openFiles: nextFiles, activeFile: nextActive }
    }),

  clearDirty: (id) =>
    set((state) => {
      const nextFiles = state.openFiles.map((f) =>
        f.id === id ? { ...f, isDirty: false, modifiedContent: undefined } : f,
      )
      const nextActive = state.activeFileId === id
        ? { ...state.activeFile!, isDirty: false, modifiedContent: undefined }
        : state.activeFile
      return { openFiles: nextFiles, activeFile: nextActive }
    }),

  setFileLanguage: (id, language) =>
    set((state) => {
      const nextFiles = state.openFiles.map((f) =>
        f.id === id ? { ...f, language } : f,
      )
      const nextActive = state.activeFileId === id
        ? { ...state.activeFile!, language }
        : state.activeFile
      return { openFiles: nextFiles, activeFile: nextActive }
    }),

  setActiveFile: (path, language) => {
    const state = useCodeTabStore.getState()
    const existing = state.openFiles.find((f) => f.path === path)
    if (existing) {
      set({
        activeFileId: existing.id,
        workspaceTab: 'code',
        activeFile: existing,
      })
    } else {
      const newFile: OpenFile = {
        id: `file-${++_nextFileId}`,
        path,
        language,
        isDirty: false,
        viewMode: 'edit',
      }
      set({
        openFiles: [...state.openFiles, newFile],
        activeFileId: newFile.id,
        workspaceTab: 'code',
        activeFile: newFile,
      })
    }
  },

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
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
}))
