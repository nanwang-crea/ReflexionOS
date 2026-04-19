import { describe, expect, it } from 'vitest'
import {
  DEFAULT_BACKEND_HTTP_ORIGIN,
  DEFAULT_BACKEND_WS_ORIGIN,
  resolveApiBaseUrl,
  resolveWebSocketBaseUrl,
} from './runtimeConfig'

describe('runtimeConfig', () => {
  it('uses the Vite proxy for API requests in dev when no override is present', () => {
    expect(resolveApiBaseUrl({ dev: true })).toBe('')
  })

  it('uses the current app origin for websocket traffic in dev when no override is present', () => {
    expect(resolveWebSocketBaseUrl({ dev: true, appOrigin: 'http://127.0.0.1:5173' })).toBe(
      'ws://127.0.0.1:5173'
    )
  })

  it('falls back to the local backend origin outside dev', () => {
    expect(resolveApiBaseUrl({ dev: false })).toBe(DEFAULT_BACKEND_HTTP_ORIGIN)
    expect(resolveWebSocketBaseUrl({ dev: false })).toBe(DEFAULT_BACKEND_WS_ORIGIN)
  })

  it('prefers an explicit backend origin override for both HTTP and WebSocket traffic', () => {
    expect(resolveApiBaseUrl({ dev: true, backendOrigin: 'https://example.com/' })).toBe(
      'https://example.com'
    )
    expect(resolveWebSocketBaseUrl({ dev: true, backendOrigin: 'https://example.com/' })).toBe(
      'wss://example.com'
    )
  })
})
