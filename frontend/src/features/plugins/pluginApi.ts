import { apiClient } from '@/services/apiClient'
import type { Plugin, InstallPluginRequest } from '@/types/plugin'

export const pluginApi = {
  list: () => apiClient.get<Plugin[]>('/api/plugins'),
  install: (req: InstallPluginRequest) => apiClient.post('/api/plugins/install', req),
  uninstall: (name: string) => apiClient.delete(`/api/plugins/${name}`),
  update: (name: string) => apiClient.post(`/api/plugins/update/${name}`),
  updateAll: () => apiClient.post('/api/plugins/update'),
  skills: (name: string) => apiClient.get(`/api/plugins/${name}/skills`),
}
