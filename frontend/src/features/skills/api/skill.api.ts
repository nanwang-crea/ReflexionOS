/**
 * 文件功能：技能（Skill）相关的后端 API 封装
 * 文件描述：定义技能列表查询、详情、分类、启用/禁用、刷新、安装、卸载等接口的请求参数与响应类型，
 *           并统一通过 apiClient 发起 HTTP 请求。
 * 核心逻辑：所有方法均为对 apiClient 的薄封装，不做额外的数据转换，接口路径均以 /api/skills 为前缀。
 */
import { apiClient } from '@/services/apiClient'
import type { Skill, SkillDetail, SkillCategories } from '@/types/skill'

// 技能列表查询参数：支持分页（offset/limit）、按分类/插件名/关键字过滤
export interface SkillListParams {
  offset?: number
  limit?: number
  category?: string
  plugin_name?: string
  search?: string
}

// 技能列表响应结构：items 为当前页数据，total 为总数，has_more 表示是否还有更多数据可加载
export interface SkillListResponse {
  items: Skill[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}

// 安装技能的请求体：specifier 为技能标识（如包名/路径等）
export interface InstallSkillRequest {
  specifier: string
}

// 技能相关接口集合：列表、详情、分类、启用、禁用、刷新、安装、删除
export const skillApi = {
  list: (params?: SkillListParams) => apiClient.get<SkillListResponse>('/api/skills', { params }),
  detail: (name: string) => apiClient.get<SkillDetail>(`/api/skills/${name}`),
  categories: () => apiClient.get<SkillCategories>('/api/skills/categories'),
  enable: (name: string) => apiClient.post(`/api/skills/${name}/enable`),
  disable: (name: string) => apiClient.post(`/api/skills/${name}/disable`),
  refresh: () => apiClient.post('/api/skills/refresh'),
  install: (req: InstallSkillRequest) => apiClient.post('/api/skills/install', req),
  remove: (name: string) => apiClient.delete(`/api/skills/${name}`),
}
