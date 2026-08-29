/**
 * 文件功能：Git 相关 API 封装
 * 文件描述：封装 Git 状态查询、暂存/取消暂存、提交、推送/拉取/fetch、stash、丢弃变更、
 * 分支管理（列表/创建/删除/切换）、提交日志查询等后端接口调用
 * 核心逻辑：统一通过 apiClient 发起 HTTP 请求，project_id 作为项目标识贯穿所有请求
 */

import { apiClient } from '@/services/apiClient'
import type { GitStatusResponse, GitSimpleResponse, GitBranchListResponse, GitLogResponse } from '@/types/git'

export const gitApi = {
  /** 获取项目 Git 状态（分支、ahead/behind、staged/unstaged/untracked 文件）。入参：projectId */
  getStatus: (projectId: string) =>
    apiClient.get<GitStatusResponse>('/api/git/status', {
      params: { project_id: projectId },
    }),

  /** 暂存指定文件。入参：projectId、paths（待暂存文件路径列表） */
  stageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/stage', {
      project_id: projectId,
      paths,
    }),

  /** 暂存所有变更文件。入参：projectId */
  stageAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/stage-all', {
      project_id: projectId,
    }),

  /** 取消暂存指定文件。入参：projectId、paths（待取消暂存文件路径列表） */
  unstageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage', {
      project_id: projectId,
      paths,
    }),

  /** 取消暂存所有文件。入参：projectId */
  unstageAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage-all', {
      project_id: projectId,
    }),

  /** 提交暂存区变更。入参：projectId、message（提交信息）、amend（是否为 amend 提交，默认 false） */
  commit: (projectId: string, message: string, amend: boolean = false) =>
    apiClient.post<GitSimpleResponse>('/api/git/commit', {
      project_id: projectId,
      message,
      amend,
    }),

  /** 推送到远程仓库。入参：projectId */
  push: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/push', {
      project_id: projectId,
    }),

  /** 从远程仓库拉取变更。入参：projectId */
  pull: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/pull', {
      project_id: projectId,
    }),

  /** 从远程仓库拉取元数据但不合并（fetch）。入参：projectId */
  fetch: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/fetch', {
      project_id: projectId,
    }),

  /** 执行 stash push 或 pop 操作。入参：projectId、action（'push' 保存现场 / 'pop' 恢复现场） */
  stash: (projectId: string, action: 'push' | 'pop') =>
    apiClient.post<GitSimpleResponse>('/api/git/stash', {
      project_id: projectId,
      action,
    }),

  /** 丢弃指定文件的未提交变更。入参：projectId、paths（待丢弃变更的文件路径列表） */
  discardChanges: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/discard', {
      project_id: projectId,
      paths,
    }),

  /** 丢弃所有未提交变更。入参：projectId */
  discardAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/discard-all', {
      project_id: projectId,
    }),

  /** 获取分支列表。入参：projectId */
  listBranches: (projectId: string) =>
    apiClient.get<GitBranchListResponse>('/api/git/branches', {
      params: { project_id: projectId },
    }),

  /** 创建新分支。入参：projectId、name（分支名）、checkout（创建后是否切换到该分支，默认 true） */
  createBranch: (projectId: string, name: string, checkout: boolean = true) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/create', {
      project_id: projectId,
      name,
      checkout,
    }),

  /** 删除分支。入参：projectId、name（分支名）、force（是否强制删除，默认 false） */
  deleteBranch: (projectId: string, name: string, force: boolean = false) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/delete', {
      project_id: projectId,
      name,
      force,
    }),

  /** 切换到指定分支。入参：projectId、name（目标分支名） */
  switchBranch: (projectId: string, name: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/switch', {
      project_id: projectId,
      name,
    }),

  /** 获取提交日志。入参：projectId、maxCount（最大返回条数，默认 50） */
  log: (projectId: string, maxCount: number = 50) =>
    apiClient.post<GitLogResponse>('/api/git/log', {
      project_id: projectId,
      max_count: maxCount,
    }),
}
