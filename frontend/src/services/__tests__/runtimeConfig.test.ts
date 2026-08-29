// runtimeConfig 的单测：验证 API 基础地址与会话对话 WebSocket 地址在开发态/生产态、以及有无显式后端源覆盖时的推导结果。
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getApiBaseUrl,
  getSessionConversationWebSocketUrl,
} from '../runtimeConfig'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('runtimeConfig', () => {
  // 参数：无。
  // 验证：开发态下未设置后端源覆盖时，API 请求走 Vite 代理，因此基础地址应为空字符串。
  it('uses the Vite proxy for API requests in dev when no override is present', () => {
    vi.stubEnv('DEV', true)

    expect(getApiBaseUrl()).toBe('')
  })

  // 参数：无。
  // 验证：开发态下未设置后端源覆盖时，WebSocket 地址基于当前页面 origin 推导（http -> ws）。
  it('uses the current app origin for websocket traffic in dev when no override is present', () => {
    vi.stubEnv('DEV', true)
    vi.stubGlobal('window', {
      location: {
        protocol: 'http:',
        origin: 'http://127.0.0.1:5173',
      },
    })

    expect(getSessionConversationWebSocketUrl('session-1')).toBe('ws://127.0.0.1:5173/ws/sessions/session-1/conversation')
  })

  // 参数：无。
  // 验证：非开发态（生产构建）下，未显式覆盖时会回退到本地后端固定地址（127.0.0.1:8000），HTTP 与 WS 均如此。
  it('falls back to the local backend origin outside dev', () => {
    vi.stubEnv('DEV', false)

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:8000')
    expect(getSessionConversationWebSocketUrl('session-1')).toBe('ws://127.0.0.1:8000/ws/sessions/session-1/conversation')
  })

  // 参数：无。
  // 验证：设置 VITE_BACKEND_ORIGIN 环境变量后，无论是否处于开发态，HTTP 与 WebSocket 地址都应优先使用该显式覆盖值（并正确转换协议前缀）。
  it('prefers an explicit backend origin override for both HTTP and WebSocket traffic', () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://example.com/')

    expect(getApiBaseUrl()).toBe('https://example.com')
    expect(getSessionConversationWebSocketUrl('session-1')).toBe('wss://example.com/ws/sessions/session-1/conversation')
  })
})
