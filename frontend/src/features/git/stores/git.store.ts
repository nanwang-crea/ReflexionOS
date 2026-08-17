/**
 * 文件功能：Git 操作 Zustand Store
 * 文件描述：管理 Git 状态（分支信息、暂存/未暂存/未跟踪文件）、提交信息、
 * 各类操作的 loading 标志（commit/push/pull/fetch/log）、分支列表与分支选择器展示状态、
 * 提交日志列表；并封装 stage/unstage/commit/push/pull/fetch/stash/discard/分支管理等操作。
 * 核心逻辑：所有写操作调用对应 gitApi 接口，成功后统一刷新 Git 状态（fetchStatus），
 * 失败时通过 toast 提示错误；部分操作（pull/fetch/switchBranch）还会触发文件树刷新。
 */

import { create } from 'zustand'
import { gitApi } from '@/features/git/api/git.api'
import { useProjectStore } from '@/features/projects/stores/project.store'
import { useToastStore } from '@/shared/stores/toast.store'
import { useCodeTabStore } from '@/features/code/stores/codeTab.store'
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

/** 获取当前项目 id。出参：当前项目 id，无当前项目时为 null */
function _getProjectId(): string | null {
  return useProjectStore.getState().currentProject?.id ?? null
}

/** 弹出全局 toast 提示。入参：type（'info' | 'error'）、msg（提示文本） */
function _toast(type: 'info' | 'error', msg: string) {
  useToastStore.getState().addToast(type, msg)
}

/** 触发文件树刷新（Git 操作可能改变文件系统内容，需通知代码面板重新加载文件树） */
function _refreshFileTree() {
  useCodeTabStore.getState().refreshFileTree()
}

/**
 * 判断请求错误是否为“非 Git 仓库”错误。
 * 输入：err（catch 到的异常，类型未知）
 * 运行逻辑：从 err.response.data.detail 中取出错误信息文本，匹配中英文两种“不是 git 仓库”提示
 * 出参：boolean - 是否为非 Git 仓库错误
 */
function _isNotGitRepo(err: unknown): boolean {
  if (err && typeof err === 'object' && 'response' in err) {
    const errObj = err as Record<string, unknown>
    const response = errObj.response
    if (response && typeof response === 'object' && 'data' in response) {
      const respObj = response as Record<string, unknown>
      const data = respObj.data
      if (data && typeof data === 'object' && 'detail' in data) {
        const dataObj = data as Record<string, unknown>
        const msg = typeof dataObj.detail === 'string' ? dataObj.detail : ''
        return msg.includes('不是 git 仓库') || msg.includes('not a git repository')
      }
    }
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

  /** 计算总变更文件数（已暂存 + 未暂存 + 未跟踪）。出参：number */
  totalChanges: () => {
    const s = get()
    return s.stagedFiles.length + s.unstagedFiles.length + s.untrackedFiles.length
  },

  /**
   * 拉取当前项目的 Git 状态（分支信息、staged/unstaged/untracked 文件）。
   * 运行逻辑：无当前项目时直接返回；请求成功写入状态并清空 notGitRepo 标记；
   * 请求失败时判断是否为非 Git 仓库错误，并清空文件列表。
   */
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

  /** 暂存指定文件。入参：paths（文件路径数组）。运行逻辑：调用接口后刷新 Git 状态，失败提示 toast */
  stageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.stageFiles(projectId, paths)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Stage 失败'); return }
      await get().fetchStatus()
    } catch { _toast('error', 'Stage 请求失败') }
  },

  /** 暂存所有变更文件。运行逻辑：调用接口后提示成功并刷新 Git 状态 */
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

  /** 取消暂存指定文件。入参：paths（文件路径数组） */
  unstageFiles: async (paths) => {
    const projectId = _getProjectId()
    if (!projectId) return
    try {
      const resp = await gitApi.unstageFiles(projectId, paths)
      if (!resp.data.success) { _toast('error', resp.data.error ?? 'Unstage 失败'); return }
      await get().fetchStatus()
    } catch { _toast('error', 'Unstage 请求失败') }
  },

  /** 取消暂存所有文件 */
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

  /**
   * 提交暂存区变更。入参：message（提交信息）、amend（是否为 amend 提交，默认 false）
   * 运行逻辑：设置 isCommitting 为 true，请求完成后清空提交信息并刷新状态，无论成功失败都复位 isCommitting
   */
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

  /** 推送到远程仓库。运行逻辑：设置 isPushing 标志，成功后提示并刷新状态 */
  push: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPushing: true })
    try {
      const resp = await gitApi.push(projectId)
      if (!resp.data.success) { set({ isPushing: false }); _toast('error', resp.data.error ?? 'Push 失败'); return }
      _toast('info', '推送成功')
      await get().fetchStatus()
      set({ isPushing: false })
    } catch { set({ isPushing: false }); _toast('error', 'Push 请求失败') }
  },

  /** 从远程仓库拉取变更。运行逻辑：成功后刷新 Git 状态、文件树和提交日志（拉取可能引入新文件/新提交） */
  pull: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isPulling: true })
    try {
      const resp = await gitApi.pull(projectId)
      if (!resp.data.success) { set({ isPulling: false }); _toast('error', resp.data.error ?? 'Pull 失败'); return }
      _toast('info', '拉取成功')
      await get().fetchStatus()
      _refreshFileTree()
      await get().fetchLog()
      set({ isPulling: false })
    } catch { set({ isPulling: false }); _toast('error', 'Pull 请求失败') }
  },

  /** 从远程仓库执行 fetch（拉取元数据但不合并）。运行逻辑：成功后刷新 Git 状态和文件树 */
  fetchRemote: async () => {
    const projectId = _getProjectId()
    if (!projectId) return
    set({ isFetching: true })
    try {
      const resp = await gitApi.fetch(projectId)
      if (!resp.data.success) { set({ isFetching: false }); _toast('error', resp.data.error ?? 'Fetch 失败'); return }
      _toast('info', 'Fetch 成功')
      await get().fetchStatus()
      _refreshFileTree()
      set({ isFetching: false })
    } catch { set({ isFetching: false }); _toast('error', 'Fetch 请求失败') }
  },

  /** 执行 stash push/pop。入参：action（'push' 保存现场 / 'pop' 恢复现场） */
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

  /** 丢弃指定文件的未提交变更。入参：paths（文件路径数组） */
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

  /** 丢弃所有未提交变更 */
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

  /** 更新提交信息输入框内容。入参：msg */
  setCommitMessage: (msg) => set({ commitMessage: msg }),
  /** 切换“已暂存”分组的折叠状态 */
  toggleStagedCollapsed: () => set((s) => ({ stagedCollapsed: !s.stagedCollapsed })),
  /** 切换“未暂存”分组的折叠状态 */
  toggleUnstagedCollapsed: () => set((s) => ({ unstagedCollapsed: !s.unstagedCollapsed })),

  /** 获取分支列表，失败时静默忽略（不打断用户操作） */
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
      _refreshFileTree()
      await get().fetchLog()
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
