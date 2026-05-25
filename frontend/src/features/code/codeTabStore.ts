import { create } from 'zustand'

export type WorkspaceTab = 'chat' | 'code'
export type CodeSubTab = 'diff' | 'edit'

export interface ActiveFile {
  path: string
  language: string
}

interface CodeTabState {
  workspaceTab: WorkspaceTab
  codeSubTab: CodeSubTab
  activeFile: ActiveFile | null
  isDirty: boolean
}

interface CodeTabActions {
  setWorkspaceTab: (tab: WorkspaceTab) => void
  setCodeSubTab: (subTab: CodeSubTab) => void
  setActiveFile: (path: string, language: string, defaultSubTab?: CodeSubTab) => void
  setDirty: (dirty: boolean) => void
  clearActiveFile: () => void
}

export const useCodeTabStore = create<CodeTabState & CodeTabActions>()((set) => ({
  workspaceTab: 'chat',
  codeSubTab: 'diff',
  activeFile: null,
  isDirty: false,

  setWorkspaceTab: (tab) => set({ workspaceTab: tab }),
  setCodeSubTab: (subTab) => set({ codeSubTab: subTab }),
  setActiveFile: (path, language, defaultSubTab) =>
    set((state) => ({
      activeFile: { path, language },
      isDirty: false,
      workspaceTab: 'code',
      codeSubTab: defaultSubTab ?? state.codeSubTab,
    })),
  setDirty: (dirty) => set({ isDirty: dirty }),
  clearActiveFile: () => set({ activeFile: null, isDirty: false }),
}))
