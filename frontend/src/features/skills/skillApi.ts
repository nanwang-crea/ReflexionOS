import { apiClient } from '@/services/apiClient'
import type { Skill, SkillDetail, SkillCategories } from '@/types/skill'

export interface InstallSkillRequest {
  specifier: string
}

export const skillApi = {
  list: () => apiClient.get<Skill[]>('/api/skills'),
  detail: (name: string) => apiClient.get<SkillDetail>(`/api/skills/${name}`),
  categories: () => apiClient.get<SkillCategories>('/api/skills/categories'),
  enable: (name: string) => apiClient.post(`/api/skills/${name}/enable`),
  disable: (name: string) => apiClient.post(`/api/skills/${name}/disable`),
  refresh: () => apiClient.post('/api/skills/refresh'),
  install: (req: InstallSkillRequest) => apiClient.post('/api/skills/install', req),
  remove: (name: string) => apiClient.delete(`/api/skills/${name}`),
}
