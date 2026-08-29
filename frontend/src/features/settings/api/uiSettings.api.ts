/**
 * 文件功能：UI 设置相关 API 封装
 * 文件描述：封装“过程展示”相关 UI 偏好设置（是否默认展开过程、是否自动折叠过程）的读取与更新接口调用
 * 核心逻辑：统一通过 apiClient 发起 HTTP 请求，设置项以整体对象形式读写
 */

import { apiClient } from '@/services/apiClient'

/** UI 设置响应结构：是否默认展开处理过程、是否自动折叠处理过程 */
interface UISettingsResponse {
  show_process_expanded: boolean
  auto_collapse_process: boolean
}

export const uiSettingsApi = {
  /** 获取当前 UI 设置。出参：UISettingsResponse */
  get: () => apiClient.get<UISettingsResponse>('/api/ui-settings'),
  /** 更新 UI 设置。入参：data（完整的 UI 设置对象）。出参：更新后的 UISettingsResponse */
  update: (data: UISettingsResponse) => apiClient.put<UISettingsResponse>('/api/ui-settings', data),
}
