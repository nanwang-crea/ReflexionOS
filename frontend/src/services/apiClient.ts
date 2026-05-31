import axios from 'axios'
import { getApiBaseUrl } from './runtimeConfig'

export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  const url = config.url
  if (url && !url.endsWith('/')) {
    config.url = url + '/'
  }
  return config
})

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
