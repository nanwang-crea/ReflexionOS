import { create } from 'zustand'
import { gitApi } from '@/features/git/gitApi'
import { useProjectStore } from '@/stores/projectStore'
import { useToastStore } from '@/stores/toastStore'
import type { GitFileChange, GitBranchInfo } from '@/types/git'

interface GitState {
  branchInfo: GitBranchInfo | null
  stagedFiles: GitFileChange[]
  unstagedFiles: GitFileChange[]
  untrackedFiles: GitFileChange[]
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
    try {
      const resp = await gitApi.stageFiles(projectId, paths)
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Stage 失败')
        return
      }
      await get().fetchStatus()
    } catch {
      useToastStore.getState().addToast('error', 'Stage 请求失败')
    }
  },

  unstageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.unstageFiles(projectId, paths)
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Unstage 失败')
        return
      }
      await get().fetchStatus()
    } catch {
      useToastStore.getState().addToast('error', 'Unstage 请求失败')
    }
  },

  commit: async (message) => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isCommitting: true })
    try {
      const resp = await gitApi.commit(projectId, message)
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Commit 失败')
        set({ isCommitting: false })
        return
      }
      set({ commitMessage: '', isCommitting: false })
      useToastStore.getState().addToast('info', '提交成功')
      await get().fetchStatus()
    } catch {
      set({ isCommitting: false })
      useToastStore.getState().addToast('error', 'Commit 请求失败')
    }
  },

  push: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPushing: true })
    try {
      const resp = await gitApi.push(projectId)
      set({ isPushing: false })
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Push 失败')
        return
      }
      useToastStore.getState().addToast('info', '推送成功')
      await get().fetchStatus()
    } catch {
      set({ isPushing: false })
      useToastStore.getState().addToast('error', 'Push 请求失败')
    }
  },

  pull: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPulling: true })
    try {
      const resp = await gitApi.pull(projectId)
      set({ isPulling: false })
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Pull 失败')
        return
      }
      useToastStore.getState().addToast('info', '拉取成功')
      await get().fetchStatus()
    } catch {
      set({ isPulling: false })
      useToastStore.getState().addToast('error', 'Pull 请求失败')
    }
  },

  stash: async (action) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.stash(projectId, action)
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? 'Stash 失败')
        return
      }
      useToastStore.getState().addToast('info', action === 'pop' ? 'Stash 恢复成功' : 'Stash 保存成功')
      await get().fetchStatus()
    } catch {
      useToastStore.getState().addToast('error', 'Stash 请求失败')
    }
  },

  discardChanges: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.discardChanges(projectId, paths)
      if (!resp.data.success) {
        useToastStore.getState().addToast('error', resp.data.error ?? '丢弃变更失败')
        return
      }
      useToastStore.getState().addToast('info', '已丢弃变更')
      await get().fetchStatus()
    } catch {
      useToastStore.getState().addToast('error', '丢弃变更请求失败')
    }
  },

  setCommitMessage: (msg) => set({ commitMessage: msg }),
  toggleStagedCollapsed: () => set((s) => ({ stagedCollapsed: !s.stagedCollapsed })),
  toggleUnstagedCollapsed: () => set((s) => ({ unstagedCollapsed: !s.unstagedCollapsed })),
}))
