import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getApiBaseUrl,
  getSessionConversationWebSocketUrl,
} from './runtimeConfig'

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('runtimeConfig', () => {
  it('uses the Vite proxy for API requests in dev when no override is present', () => {
    vi.stubEnv('DEV', true)

    expect(getApiBaseUrl()).toBe('')
  })

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

  it('falls back to the local backend origin outside dev', () => {
    vi.stubEnv('DEV', false)

    expect(getApiBaseUrl()).toBe('http://127.0.0.1:8000')
    expect(getSessionConversationWebSocketUrl('session-1')).toBe('ws://127.0.0.1:8000/ws/sessions/session-1/conversation')
  })

  it('prefers an explicit backend origin override for both HTTP and WebSocket traffic', () => {
    vi.stubEnv('DEV', true)
    vi.stubEnv('VITE_BACKEND_ORIGIN', 'https://example.com/')

    expect(getApiBaseUrl()).toBe('https://example.com')
    expect(getSessionConversationWebSocketUrl('session-1')).toBe('wss://example.com/ws/sessions/session-1/conversation')
  })
})
