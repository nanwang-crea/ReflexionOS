/**
 * 文件功能：文件相关 API 封装
 * 文件描述：封装文件内容读取、diff 内容读取、文件写入、文件树获取等后端接口调用
 * 核心逻辑：统一通过 apiClient 发起 HTTP 请求，project_id/path 等参数以 query 或 body 形式传递
 */

import { apiClient } from '@/services/apiClient'
import type {
  FileContentResponse,
  FileDiffContentResponse,
  FileWriteRequest,
  FileWriteResponse,
} from '@/types/file'
import type { FileTreeResponse } from '@/types/fileTree'

export const fileApi = {
  /** 获取指定项目下某文件的内容。入参：projectId（项目 id）、path（文件路径）。出参：文件内容响应 */
  getContent: (projectId: string, path: string) =>
    apiClient.get<FileContentResponse>('/api/files/content', {
      params: { project_id: projectId, path },
    }),

  /** 获取指定文件的 diff 内容（用于对比原始内容与修改后内容）。入参同 getContent。出参：diff 内容响应 */
  getDiffContent: (projectId: string, path: string) =>
    apiClient.get<FileDiffContentResponse>('/api/files/diff-content', {
      params: { project_id: projectId, path },
    }),

  /** 写入文件内容。入参：data（写入请求体，包含项目 id、路径、内容等）。出参：写入结果响应 */
  writeFile: (data: FileWriteRequest) =>
    apiClient.post<FileWriteResponse>('/api/files/write', data),

  /** 获取项目的文件树结构。入参：projectId（项目 id）。出参：文件树响应 */
  getTree: (projectId: string) =>
    apiClient.get<FileTreeResponse>('/api/files/tree', {
      params: { project_id: projectId },
    }),
}
