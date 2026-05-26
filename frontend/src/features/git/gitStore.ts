import { create } from 'zustand'
import { gitApi } from '@/features/git/gitApi'
import { useProjectStore } from '@/stores/projectStore'
import { useToastStore } from '@/stores/toastStore'
import type { GitFileChange, GitBranchInfo, GitBranchItem, GitLogCommit } from '@/types/git'

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
  isFetching: boolean
  branches: GitBranchItem[]
  showBranchPicker: boolean
  logCommits: GitLogCommit[]
  isLoadingLog: boolean
  notGitRepo: boolean

  totalChanges: () => number

  fetchStatus: () => Promise<void>
  stageFiles: (paths: string[]) => Promise<void>
  stageAll: () => Promise<void>
  unstageFiles: (paths: string[]) => Promise<void>
  unstageAll: () => Promise<void>
  commit: (message: string, amend?: boolean) => Promise<void>
  push: () => Promise<void>
  pull: () => Promise<void>
  fetchRemote: () => Promise<void>
  stash: (action: 'push' | 'pop') => Promise<void>
  discardChanges: (paths: string[]) => Promise<void>
  discardAll: () => Promise<void>
  setCommitMessage: (msg: string) => void
  toggleStagedCollapsed: () => void
  toggleUnstagedCollapsed: () => void

  fetchBranches: () => Promise<void>
  setShowBranchPicker: (show: boolean) => void
  createBranch: (name: string, checkout?: boolean) => Promise<void>
  deleteBranch: (name: string, force?: boolean) => Promise<void>
  switchBranch: (name: string) => Promise<void>

  fetchLog: (maxCount?: number) => Promise<void>
}

function _getProjectId(): string | null {
  return useProjectStore.getState().currentProject?.id ?? null
}

function _toast(type: 'info' | 'error', msg: string) {
  useToastStore.getState().addToast(type, msg)
}

function _isNotGitRepo(err: unknown): boolean {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as { response?: { data?: { detail?: string } } }).response
    const msg = resp?.data?.detail ?? ''
    return msg.includes('不是 git 仓库') || msg.includes('not a git repository')
  }
  return false
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
  isFetching: false,
  branches: [],
  showBranchPicker: false,
  logCommits: [],
  isLoadingLog: false,
  notGitRepo: false,

  totalChanges: () => {
    const s = get()
    return s.stagedFiles.length + s.unstagedFiles.length + s.untrackedFiles.length
  },

  fetchStatus: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isLoading: true, notGitRepo: false })
    try {
      const resp = await gitApi.getStatus(projectId)
      const data = resp.data
      set({
        branchInfo: { name: data.branch, ahead: data.ahead, behind: data.behind },
        stagedFiles: data.staged,
        unstagedFiles: data.unstaged,
        untrackedFiles: data.untracked,
        isLoading: false,
        notGitRepo: false,
      })
    } catch (err) {
      set({
        isLoading: false,
        notGitRepo: _isNotGitRepo(err),
        branchInfo: null,
        stagedFiles: [],
        unstagedFiles: [],
        untrackedFiles: [],
      })
    }
  },

  stageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.stageFiles(projectId, paths)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Stage 失败'); return }
      await get().fetchStatus()
    } catch { _toast('error', 'Stage 请求失败') }
  },

  stageAll: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.stageAll(projectId)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Stage All 失败'); return }
      _toast('info', '已暂存所有变更')
      await get().fetchStatus()
    } catch { _toast('error', 'Stage All 请求失败') }
  },

  unstageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.unstageFiles(projectId, paths)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Unstage 失败'); return }
      await get().fetchStatus()
    } catch { _toast('error', 'Unstage 请求失败') }
  },

  unstageAll: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.unstageAll(projectId)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Unstage All 失败'); return }
      _toast('info', '已取消所有暂存')
      await get().fetchStatus()
    } catch { _toast('error', 'Unstage All 请求失败') }
  },

  commit: async (message, amend = false) => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isCommitting: true })
    try {
      const resp = await gitApi.commit(projectId, message, amend)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Commit 失败'); set({ isCommitting: false }); return }
      set({ commitMessage: '', isCommitting: false })
      _toast('info', amend ? 'Amend 成功' : '提交成功')
      await get().fetchStatus()
    } catch {
      set({ isCommitting: false })
      _toast('error', 'Commit 请求失败')
    }
  },

  push: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPushing: true })
    try {
      const resp = await gitApi.push(projectId)
      set({ isPushing: false })
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Push 失败'); return }
      _toast('info', '推送成功')
      await get().fetchStatus()
    } catch { set({ isPushing: false }); _toast('error', 'Push 请求失败') }
  },

  pull: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPulling: true })
    try {
      const resp = await gitApi.pull(projectId)
      set({ isPulling: false })
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Pull 失败'); return }
      _toast('info', '拉取成功')
      await get().fetchStatus()
    } catch { set({ isPulling: false }); _toast('error', 'Pull 请求失败') }
  },

  fetchRemote: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isFetching: true })
    try {
      const resp = await gitApi.fetch(projectId)
      set({ isFetching: false })
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Fetch 失败'); return }
      _toast('info', 'Fetch 成功')
      await get().fetchStatus()
    } catch { set({ isFetching: false }); _toast('error', 'Fetch 请求失败') }
  },

  stash: async (action) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.stash(projectId, action)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Stash 失败'); return }
      _toast('info', action === 'pop' ? 'Stash 恢复成功' : 'Stash 保存成功')
      await get().fetchStatus()
    } catch { _toast('error', 'Stash 请求失败') }
  },

  discardChanges: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.discardChanges(projectId, paths)
      if (!resp.data.success) { _toast('error', resp.data.error ?? '丢弃变更失败'); return }
      _toast('info', '已丢弃变更')
      await get().fetchStatus()
    } catch { _toast('error', '丢弃变更请求失败') }
  },

  discardAll: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.discardAll(projectId)
      if (!resp.data.success) { _toast('error', resp.data.error ?? '丢弃所有变更失败'); return }
      _toast('info', '已丢弃所有变更')
      await get().fetchStatus()
    } catch { _toast('error', '丢弃所有变更请求失败') }
  },

  setCommitMessage: (msg) => set({ commitMessage: msg }),
  toggleStagedCollapsed: () => set((s) => ({ stagedCollapsed: !s.stagedCollapsed })),
  toggleUnstagedCollapsed: () => set((s) => ({ unstagedCollapsed: !s.unstagedCollapsed })),

  fetchBranches: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.listBranches(projectId)
      set({ branches: resp.data.branches })
    } catch { /* silent */ }
  },

  setShowBranchPicker: (show) => set({ showBranchPicker: show }),

  createBranch: async (name, checkout = true) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.createBranch(projectId, name, checkout)
      if (!resp.data.success) { _toast('error', resp.data.error ?? '创建分支失败'); return }
      _toast('info', `分支 ${name} 已创建`)
      set({ showBranchPicker: false })
      await get().fetchStatus()
      await get().fetchBranches()
    } catch { _toast('error', '创建分支请求失败') }
  },

  deleteBranch: async (name, force = false) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.deleteBranch(projectId, name, force)
      if (!resp.data.success) { _toast('error', resp.data.error ?? '删除分支失败'); return }
      _toast('info', `分支 ${name} 已删除`)
      await get().fetchBranches()
    } catch { _toast('error', '删除分支请求失败') }
  },

  switchBranch: async (name) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.switchBranch(projectId, name)
      if (!resp.data.success) { _toast('error', resp.data.error ?? '切换分支失败'); return }
      _toast('info', `已切换到 ${name}`)
      set({ showBranchPicker: false })
      await get().fetchStatus()
      await get().fetchBranches()
    } catch { _toast('error', '切换分支请求失败') }
  },

  fetchLog: async (maxCount = 50) => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isLoadingLog: true })
    try {
      const resp = await gitApi.log(projectId, maxCount)
      set({ logCommits: resp.data.commits, isLoadingLog: false })
    } catch {
      set({ isLoadingLog: false })
    }
  },
}))
