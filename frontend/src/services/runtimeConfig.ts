// 文件功能：解析后端 API / WebSocket 基础地址的运行时配置
// 文件描述：根据当前运行环境（开发模式 dev / 生产模式，浏览器 origin，以及可选的
//           VITE_BACKEND_ORIGIN 覆盖配置）计算出 HTTP 与 WebSocket 请求应使用的 base URL
// 核心逻辑：
//   1. 若显式配置了 VITE_BACKEND_ORIGIN，则该覆盖值优先于其他推断逻辑
//   2. 开发模式下 HTTP 走空 baseURL（依赖 Vite dev server 代理），WS 则跟随浏览器当前 origin
//   3. 生产模式下（包括桌面端打包后的 file:// 环境）统一回退到本机默认地址 127.0.0.1:8000
//   4. window 不存在（如测试环境）或协议为 file:（桌面端打包页面）时，视为无浏览器 origin 可用
const DEFAULT_BACKEND_HTTP_ORIGIN = 'http://127.0.0.1:8000'
const DEFAULT_BACKEND_WS_ORIGIN = 'ws://127.0.0.1:8000'

interface ResolveRuntimeUrlOptions {
  dev: boolean
  appOrigin?: string | null
  backendOrigin?: string | null
}

/**
 * 函数名：normalizeOrigin
 * 入参：
 *   - origin (string): 原始 origin 字符串
 * 功能：去除 origin 末尾多余的斜杠，统一格式
 * 运行逻辑：使用正则将结尾连续的 '/' 替换为空
 * 出参：string - 规范化后的 origin
 */
function normalizeOrigin(origin: string) {
  return origin.replace(/\/+$/, '')
}

/**
 * 函数名：toWebSocketOrigin
 * 入参：
 *   - origin (string): HTTP/HTTPS 形式的 origin
 * 功能：将 HTTP(S) origin 转换为对应的 WebSocket（ws/wss）origin
 * 运行逻辑：https:// 前缀替换为 wss://，http:// 前缀替换为 ws://；
 *           若既不是 http 也不是 https（如已经是 ws/wss），原样返回
 * 出参：string - 转换后的 WebSocket origin
 */
function toWebSocketOrigin(origin: string) {
  if (origin.startsWith('https://')) {
    return `wss://${origin.slice('https://'.length)}`
  }

  if (origin.startsWith('http://')) {
    return `ws://${origin.slice('http://'.length)}`
  }

  return origin
}

/**
 * 函数名：resolveOverride
 * 入参：
 *   - backendOrigin (string | null | undefined): 用户显式配置的后端 origin（如环境变量值）
 * 功能：解析并规范化显式配置的后端 origin 覆盖值
 * 运行逻辑：先 trim 去除首尾空白，若结果非空则规范化后返回，否则返回 null 表示无覆盖
 * 出参：string | null - 规范化后的覆盖 origin，未配置或为空串时返回 null
 */
function resolveOverride(backendOrigin?: string | null) {
  const trimmed = backendOrigin?.trim()
  return trimmed ? normalizeOrigin(trimmed) : null
}

/**
 * 函数名：resolveApiBaseUrl
 * 入参：
 *   - options (ResolveRuntimeUrlOptions): 包含 dev（是否开发模式）、backendOrigin（显式覆盖）
 * 功能：计算 HTTP API 请求应使用的 base URL
 * 运行逻辑：
 *   1. 优先使用显式的 backendOrigin 覆盖值
 *   2. 否则：开发模式下返回空字符串（配合 Vite dev server 代理转发到后端）
 *   3. 非开发模式下回退到默认本机后端地址
 * 出参：string - HTTP 请求的 base URL
 */
function resolveApiBaseUrl(options: ResolveRuntimeUrlOptions) {
  const override = resolveOverride(options.backendOrigin)
  if (override) {
    return override
  }

  return options.dev ? '' : DEFAULT_BACKEND_HTTP_ORIGIN
}

/**
 * 函数名：resolveWebSocketBaseUrl
 * 入参：
 *   - options (ResolveRuntimeUrlOptions): 包含 dev、appOrigin（浏览器当前 origin）、
 *     backendOrigin（显式覆盖）
 * 功能：计算 WebSocket 连接应使用的 base URL
 * 运行逻辑：
 *   1. 优先使用显式的 backendOrigin 覆盖值（转换为 ws/wss 协议）
 *   2. 开发模式下若存在浏览器 appOrigin，则跟随当前页面 origin（同样转换协议）
 *   3. 否则回退到默认本机后端 WebSocket 地址
 * 出参：string - WebSocket 连接的 base URL
 */
function resolveWebSocketBaseUrl(options: ResolveRuntimeUrlOptions) {
  const override = resolveOverride(options.backendOrigin)
  if (override) {
    return toWebSocketOrigin(override)
  }

  if (options.dev && options.appOrigin) {
    return toWebSocketOrigin(normalizeOrigin(options.appOrigin))
  }

  return DEFAULT_BACKEND_WS_ORIGIN
}

/**
 * 函数名：readBrowserOrigin
 * 入参：无
 * 功能：读取当前浏览器页面的 origin，供开发模式下 WebSocket 地址推断使用
 * 运行逻辑：
 *   1. 若 window 未定义（如 Node 测试环境），返回 undefined
 *   2. 若页面协议为 file:（Electron 打包后直接加载本地文件的场景），
 *      浏览器 origin 无意义，返回 undefined
 *   3. 否则返回 window.location.origin
 * 出参：string | undefined - 浏览器当前 origin，不可用时为 undefined
 */
function readBrowserOrigin() {
  if (typeof window === 'undefined') {
    return undefined
  }

  if (window.location.protocol === 'file:') {
    return undefined
  }

  return window.location.origin
}

/**
 * 函数名：readBackendOriginOverride
 * 入参：无
 * 功能：读取用户通过环境变量显式配置的后端 origin 覆盖值
 * 运行逻辑：从 import.meta.env.VITE_BACKEND_ORIGIN 读取，仅当其为字符串类型时返回，否则为 undefined
 * 出参：string | undefined - 环境变量配置的后端 origin
 */
function readBackendOriginOverride() {
  const value = import.meta.env.VITE_BACKEND_ORIGIN
  return typeof value === 'string' ? value : undefined
}

/**
 * 函数名：getApiBaseUrl
 * 入参：无
 * 功能：对外导出的 HTTP API base URL 获取入口
 * 运行逻辑：组装 dev 标志与环境变量覆盖值，委托 resolveApiBaseUrl 完成实际计算
 * 出参：string - 供 axios 等 HTTP 客户端使用的 baseURL
 */
export function getApiBaseUrl() {
  return resolveApiBaseUrl({
    dev: import.meta.env.DEV,
    backendOrigin: readBackendOriginOverride(),
  })
}

/**
 * 函数名：getWebSocketBaseUrl
 * 入参：无
 * 功能：内部使用的 WebSocket base URL 获取入口
 * 运行逻辑：组装 dev 标志、浏览器 origin 与环境变量覆盖值，委托 resolveWebSocketBaseUrl 完成计算
 * 出参：string - WebSocket 连接使用的 base URL
 */
function getWebSocketBaseUrl() {
  return resolveWebSocketBaseUrl({
    dev: import.meta.env.DEV,
    appOrigin: readBrowserOrigin(),
    backendOrigin: readBackendOriginOverride(),
  })
}

/**
 * 函数名：getSessionConversationWebSocketUrl
 * 入参：
 *   - sessionId (string): 会话 ID
 * 功能：拼接出指定会话对话 WebSocket 连接的完整 URL
 * 运行逻辑：在 WebSocket base URL 后追加会话对话专用路径，sessionId 经 encodeURIComponent
 *           编码以避免特殊字符破坏 URL 结构
 * 出参：string - 可直接传给 `new WebSocket()` 的完整连接地址
 */
export function getSessionConversationWebSocketUrl(sessionId: string) {
  return `${getWebSocketBaseUrl()}/ws/sessions/${encodeURIComponent(sessionId)}/conversation`
}
