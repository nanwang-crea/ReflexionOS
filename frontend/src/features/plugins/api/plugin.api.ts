/**
 * 文件功能：插件相关 API 封装
 * 文件描述：封装插件列表查询、安装、卸载、单个/全部更新、查询插件下 skills 等后端接口调用
 * 核心逻辑：统一通过 apiClient 发起 HTTP 请求，插件以 name 作为唯一标识
 */

import { apiClient } from '@/services/apiClient'
import type { Plugin, InstallPluginRequest } from '@/types/plugin'

export const pluginApi = {
  /** 获取已安装插件列表。出参：插件数组 */
  list: () => apiClient.get<Plugin[]>('/api/plugins'),
  /** 安装插件。入参：req（安装请求体，包含插件来源等信息） */
  install: (req: InstallPluginRequest) => apiClient.post('/api/plugins/install', req),
  /** 卸载插件。入参：name（插件名） */
  uninstall: (name: string) => apiClient.delete(`/api/plugins/${name}`),
  /** 更新单个插件。入参：name（插件名） */
  update: (name: string) => apiClient.post(`/api/plugins/update/${name}`),
  /** 更新所有插件 */
  updateAll: () => apiClient.post('/api/plugins/update'),
  /** 获取指定插件提供的 skills 列表。入参：name（插件名） */
  skills: (name: string) => apiClient.get(`/api/plugins/${name}/skills`),
}
