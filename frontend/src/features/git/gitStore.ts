import { create } from 'zustand'
import { gitApi } from '@/features/git/gitApi'
import { useProjectStore } from '@/stores/projectStore'
import type { GitFileChange, GitBranchInfo } from '@/types/git'

type SidebarTab = 'files' | 'changes'

interface GitState {
  branchInfo: GitBranchInfo | null
  stagedFiles: GitFileChange[]
  unstagedFiles: GitFileChange[]
  untrackedFiles: GitFileChange[]
  sidebarTab: SidebarTab
  stagedCollapsed: boolean
  unstagedCollapsed: boolean
  commitMessage: string
  isLoading: boolean
  isCommitting: boolean
  isPushing: boolean
  isPulling: boolean

  totalChanges: () => number

  fetchStatus: () => Promise<void>
  stageFiles: (paths: string[]) => Promise<void>
  unstageFiles: (paths: string[]) => Promise<void>
  commit: (message: string) => Promise<void>
  push: () => Promise<void>
  pull: () => Promise<void>
  stash: (action: 'push' | 'pop') => Promise<void>
  discardChanges: (paths: string[]) => Promise<void>
  setSidebarTab: (tab: SidebarTab) => void
  setCommitMessage: (msg: string) => void
  toggleStagedCollapsed: () => void
  toggleUnstagedCollapsed: () => void
}

function _getProjectId(): string | null {
  return useProjectStore.getState().currentProject?.id ?? null
}

export const useGitStore = create<GitState>()((set, get) => ({
  branchInfo: null,
  stagedFiles: [],
  unstagedFiles: [],
  untrackedFiles: [],
  sidebarTab: 'files',
  stagedCollapsed: false,
  unstagedCollapsed: false,
  commitMessage: '',
  isLoading: false,
  isCommitting: false,
  isPushing: false,
  isPulling: false,

  totalChanges: () => {
    const s = get()
    return s.stagedFiles.length + s.unstagedFiles.length + s.untrackedFiles.length
  },

  fetchStatus: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isLoading: true })
    try {
      const resp = await gitApi.getStatus(projectId)
      const data = resp.data
      set({
        branchInfo: { name: data.branch, ahead: data.ahead, behind: data.behind },
        stagedFiles: data.staged,
        unstagedFiles: data.unstaged,
        untrackedFiles: data.untracked,
        isLoading: false,
      })
    } catch {
      set({ isLoading: false })
    }
  },

  stageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.stageFiles(projectId, paths)
    await get().fetchStatus()
  },

  unstageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.unstageFiles(projectId, paths)
    await get().fetchStatus()
  },

  commit: async (message) => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isCommitting: true })
    try {
      await gitApi.commit(projectId, message)
      set({ commitMessage: '', isCommitting: false })
      await get().fetchStatus()
    } catch {
      set({ isCommitting: false })
    }
  },

  push: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPushing: true })
    try {
      await gitApi.push(projectId)
      set({ isPushing: false })
      await get().fetchStatus()
    } catch {
      set({ isPushing: false })
    }
  },

  pull: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPulling: true })
    try {
      await gitApi.pull(projectId)
      set({ isPulling: false })
      await get().fetchStatus()
    } catch {
      set({ isPulling: false })
    }
  },

  stash: async (action) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.stash(projectId, action)
    await get().fetchStatus()
  },

  discardChanges: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    await gitApi.discardChanges(projectId, paths)
    await get().fetchStatus()
  },

  setSidebarTab: (tab) => {
    set({ sidebarTab: tab })
    if (tab === 'changes') {
      get().fetchStatus()
    }
  },

  setCommitMessage: (msg) => set({ commitMessage: msg }),
  toggleStagedCollapsed: () => set((s) => ({ stagedCollapsed: !s.stagedCollapsed })),
  toggleUnstagedCollapsed: () => set((s) => ({ unstagedCollapsed: !s.unstagedCollapsed })),
}))
