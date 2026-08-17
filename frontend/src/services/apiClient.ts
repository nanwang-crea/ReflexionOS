// 文件功能：封装全局唯一的 axios HTTP 客户端实例
// 文件描述：统一设置后端 API 的 baseURL、超时时间与默认请求头，并通过响应拦截器
//           兼容后端错误响应体格式，供全项目的接口调用复用
// 核心逻辑：baseURL 由 runtimeConfig 按运行环境（开发/生产、桌面端/浏览器）动态解析；
//           响应拦截器在后端返回 { code, message } 结构时补充 detail 字段，
//           以兼容历史上依赖 error.response.data.detail 的调用方
import axios from 'axios'
import { getApiBaseUrl } from './runtimeConfig'

// 全局共享的 axios 实例：所有服务模块通过它发起 HTTP 请求
export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * 函数名：响应拦截器（成功回调 / 错误回调）
 * 入参：
 *   - response (AxiosResponse): 请求成功时的响应对象，原样返回
 *   - error (unknown): 请求失败时抛出的错误对象（可能是 AxiosError）
 * 功能：在错误响应体存在 message/code 字段时，补充 detail 字段以兼容旧的错误处理逻辑
 * 运行逻辑：
 *   1. 判断是否为 axios 错误且带有响应体
 *   2. 若响应体的 message 和 code 均为字符串，说明是后端标准错误结构
 *   3. 在原数据基础上追加 detail = message，不破坏原始字段
 *   4. 无论是否命中兼容分支，最终都以 Promise.reject 继续向上抛出错误
 * 出参：成功时返回原始 response；失败时返回被拒绝的 Promise
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.data) {
      const data = error.response.data as Record<string, unknown>
      if (typeof data.message === 'string' && typeof data.code === 'string') {
        error.response.data = {
          ...data,
          detail: data.message,
        }
      }
    }
    return Promise.reject(error)
  }
)
