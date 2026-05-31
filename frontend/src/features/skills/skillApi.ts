import { apiClient } from '@/services/apiClient'
import type { Skill, SkillDetail, SkillCategories, InstallRequest } from '@/types/skill'

export const skillApi = {
  list: () => apiClient.get<Skill[]>('/api/skills'),
  detail: (name: string) => apiClient.get<SkillDetail>(`/api/skills/${name}`),
  categories: () => apiClient.get<SkillCategories>('/api/skills/categories'),
  enable: (name: string) => apiClient.post(`/api/skills/${name}/enable`),
  disable: (name: string) => apiClient.post(`/api/skills/${name}/disable`),
  install: (req: InstallRequest) => apiClient.post('/api/skills/install', req),
  uninstall: (name: string) => apiClient.delete(`/api/skills/${name}`),
  refresh: () => apiClient.post('/api/skills/refresh'),
}
