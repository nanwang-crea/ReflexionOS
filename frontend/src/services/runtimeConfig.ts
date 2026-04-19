export const DEFAULT_BACKEND_HTTP_ORIGIN = 'http://127.0.0.1:8000'
export const DEFAULT_BACKEND_WS_ORIGIN = 'ws://127.0.0.1:8000'

interface ResolveRuntimeUrlOptions {
  dev: boolean
  appOrigin?: string | null
  backendOrigin?: string | null
}

function normalizeOrigin(origin: string) {
  return origin.replace(/\/+$/, '')
}

function toWebSocketOrigin(origin: string) {
  if (origin.startsWith('https://')) {
    return `wss://${origin.slice('https://'.length)}`
  }

  if (origin.startsWith('http://')) {
    return `ws://${origin.slice('http://'.length)}`
  }

  return origin
}

function resolveOverride(backendOrigin?: string | null) {
  const trimmed = backendOrigin?.trim()
  return trimmed ? normalizeOrigin(trimmed) : null
}

export function resolveApiBaseUrl(options: ResolveRuntimeUrlOptions) {
  const override = resolveOverride(options.backendOrigin)
  if (override) {
    return override
  }

  return options.dev ? '' : DEFAULT_BACKEND_HTTP_ORIGIN
}

export function resolveWebSocketBaseUrl(options: ResolveRuntimeUrlOptions) {
  const override = resolveOverride(options.backendOrigin)
  if (override) {
    return toWebSocketOrigin(override)
  }

  if (options.dev && options.appOrigin) {
    return toWebSocketOrigin(normalizeOrigin(options.appOrigin))
  }

  return DEFAULT_BACKEND_WS_ORIGIN
}

function readBrowserOrigin() {
  if (typeof window === 'undefined') {
    return undefined
  }

  if (window.location.protocol === 'file:') {
    return undefined
  }

  return window.location.origin
}

function readBackendOriginOverride() {
  const value = import.meta.env.VITE_BACKEND_ORIGIN
  return typeof value === 'string' ? value : undefined
}

export function getApiBaseUrl() {
  return resolveApiBaseUrl({
    dev: import.meta.env.DEV,
    backendOrigin: readBackendOriginOverride(),
  })
}

export function getWebSocketBaseUrl() {
  return resolveWebSocketBaseUrl({
    dev: import.meta.env.DEV,
    appOrigin: readBrowserOrigin(),
    backendOrigin: readBackendOriginOverride(),
  })
}

export function getExecutionWebSocketUrl(executionId: string) {
  return `${getWebSocketBaseUrl()}/ws/execution/${encodeURIComponent(executionId)}`
}
