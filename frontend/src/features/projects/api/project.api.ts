import { apiClient } from '@/services/apiClient'
import type { Project } from '@/types/project'

export const projectApi = {
  list: () => apiClient.get<Project[]>('/api/projects'),
  create: (data: { name: string; path: string }) =>
    apiClient.post<Project>('/api/projects', data),
  delete: (id: string) => apiClient.delete(`/api/projects/${id}`),
}
