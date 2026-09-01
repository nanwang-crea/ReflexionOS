/**
 * 文件功能：项目相关 API 封装
 * 文件描述：封装项目列表查询、创建、删除等后端接口调用
 * 核心逻辑：统一通过 apiClient 发起 HTTP 请求，项目以 id 作为唯一标识
 */

import { apiClient } from '@/services/apiClient'
import type { Project } from '@/types/project'

export const projectApi = {
  /** 获取项目列表。出参：项目数组 */
  list: () => apiClient.get<Project[]>('/api/projects'),
  /** 创建项目。入参：data（包含项目名 name 和路径 path）。出参：新建的项目 */
  create: (data: { name: string; path: string }) =>
    apiClient.post<Project>('/api/projects', data),
  /** 删除项目。入参：id（项目 id） */
  delete: (id: string) => apiClient.delete(`/api/projects/${id}`),
}
