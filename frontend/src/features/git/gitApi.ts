import { apiClient } from '@/services/apiClient'
import type { GitStatusResponse, GitSimpleResponse } from '@/types/git'

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

  unstageFiles: (projectId: string, paths: string[]) =>
    apiClient.post<GitSimpleResponse>('/api/git/unstage', {
      project_id: projectId,
      paths,
    }),

  commit: (projectId: string, message: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/commit', {
      project_id: projectId,
      message,
    }),

  push: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/push', {
      project_id: projectId,
    }),

  pull: (projectId: string) =>
    apiClient.post<GitSimpleResponse>('/api/git/pull', {
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
}
