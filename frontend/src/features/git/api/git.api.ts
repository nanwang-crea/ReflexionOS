import { apiClient } from '@/services/apiClient'
import type { GitStatusResponse, GitSimpleResponse, GitBranchListResponse, GitLogResponse } from '@/types/git'

export const gitApi = {
  getStatus: (projectId: string) =>
    apiClient.get<GitStatusResponse>('/api/git/status', {
      params: { project_id: projectId },
    }),

  stageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/stage', {
      project_id: projectId,
      paths,
    }),

  stageAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/stage-all', {
      project_id: projectId,
    }),

  unstageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage', {
      project_id: projectId,
      paths,
    }),

  unstageAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage-all', {
      project_id: projectId,
    }),

  commit: (projectId: string, message: string, amend: boolean = false) =>
    apiClient.post<GitSimpleResponse>('/api/git/commit', {
      project_id: projectId,
      message,
      amend,
    }),

  push: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/push', {
      project_id: projectId,
    }),

  pull: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/pull', {
      project_id: projectId,
    }),

  fetch: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/fetch', {
      project_id: projectId,
    }),

  stash: (projectId: string, action: 'push' | 'pop') =>
    apiClient.post<GitSimpleResponse>('/api/git/stash', {
      project_id: projectId,
      action,
    }),

  discardChanges: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/discard', {
      project_id: projectId,
      paths,
    }),

  discardAll: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/discard-all', {
      project_id: projectId,
    }),

  listBranches: (projectId: string) =>
    apiClient.get<GitBranchListResponse>('/api/git/branches', {
      params: { project_id: projectId },
    }),

  createBranch: (projectId: string, name: string, checkout: boolean = true) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/create', {
      project_id: projectId,
      name,
      checkout,
    }),

  deleteBranch: (projectId: string, name: string, force: boolean = false) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/delete', {
      project_id: projectId,
      name,
      force,
    }),

  switchBranch: (projectId: string, name: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/branch/switch', {
      project_id: projectId,
      name,
    }),

  log: (projectId: string, maxCount: number = 50) =>
    apiClient.post<GitLogResponse>('/api/git/log', {
      project_id: projectId,
      max_count: maxCount,
    }),
}
