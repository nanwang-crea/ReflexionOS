import { apiClient } from '@/services/apiClient'
import type {
  FileContentResponse,
  FileDiffContentResponse,
  FileWriteRequest,
  FileWriteResponse,
} from '@/types/file'

export const fileApi = {
  getContent: (projectId: string, path: string) =>
    apiClient.get<FileContentResponse>('/api/files/content', {
      params: { project_id: projectId, path },
    }),

  getDiffContent: (projectId: string, path: string) =>
    apiClient.get<FileDiffContentResponse>('/api/files/diff-content', {
      params: { project_id: projectId, path },
    }),

  writeFile: (data: FileWriteRequest) =>
    apiClient.post<FileWriteResponse>('/api/files/write', data),
}
