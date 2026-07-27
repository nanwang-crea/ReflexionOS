/**
 * 开发模式启动脚本：依次启动 Vite dev server 和 Electron，并管理两个子进程的生命周期。
 * 流程：spawn vite → 等待 URL 就绪 → HTTP 探测可达 → 运行 fix-electron（macOS Gatekeeper 修复）→ spawn electron
 * 跨平台：Windows 使用 pnpm.cmd / electron.cmd，macOS/Linux 直接用 pnpm / electron。
 */

import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import process from 'node:process'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const frontendDir = path.resolve(__dirname, '..')
const pnpmCommand = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm'
const electronBinary = path.join(
  frontendDir,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'electron.cmd' : 'electron',
)

let viteProcess = null
let electronProcess = null
let shuttingDown = false

/**
 * 轮询 HTTP 接口，直到成功响应或超时。
 * 修复说明：Node.js socket timeout 只触发 'timeout' 事件，不触发 'error'，
 * 因此需要在 timeout 回调中手动 destroy 并继续重试，而不是依赖 error 事件。
 * 输入：url（要探测的 URL 字符串）、timeoutMs（总超时毫秒数，默认 30000）
 * 输出：Promise<void>，超时则 reject
 */
function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs

  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(url, (response) => {
        response.resume()
        resolve()
      })

      request.on('error', () => {
        if (Date.now() >= deadline) {
          reject(new Error(`Timed out waiting for ${url}`))
          return
        }

        setTimeout(attempt, 300)
      })

      request.on('timeout', () => {
        // socket timeout 不会自动触发 error，需手动 destroy 并继续重试
        request.destroy()
        if (Date.now() >= deadline) {
          reject(new Error(`Timed out waiting for ${url}`))
          return
        }
        setTimeout(attempt, 300)
      })

      request.setTimeout(1500)
    }

    attempt()
  })
}

/**
 * 从 Vite 的控制台输出（已剥离 ANSI 转义码）中提取本地监听 URL。
 * 输入：output（Vite stdout/stderr 累积字符串）
 * 输出：URL 字符串，未匹配到时返回 null
 */
function parseViteUrl(output) {
  const stripped = output.replace(/\x1b\[[0-9;]*m/g, '')
  const match = stripped.match(/Local:\s+(https?:\/\/[^\s]+)/)
  return match ? match[1] : null
}

/**
 * 安全终止子进程（发送 SIGTERM）。
 * 输入：child（child_process 实例或 null）
 */
function terminateChild(child) {
  if (!child || child.killed) {
    return
  }

  child.kill('SIGTERM')
}

/**
 * 优雅关闭：先发 SIGTERM，250ms 后强制退出。
 * 使用 shuttingDown 标志防止重入（例如 vite 退出触发 electron 退出再触发 shutdown）。
 * 输入：code（进程退出码，默认 0）
 */
function shutdown(code = 0) {
  if (shuttingDown) {
    return
  }

  shuttingDown = true
  terminateChild(electronProcess)
  terminateChild(viteProcess)

  setTimeout(() => {
    terminateChild(electronProcess)
    terminateChild(viteProcess)
    process.exit(code)
  }, 250)
}

/**
 * 主入口：启动 Vite，等待就绪后启动 Electron。
 * 流程：
 * 1. spawn vite dev:web，监听 stdout/stderr 提取 URL
 * 2. waitForServer 探测 HTTP 可达（最长 30s）
 * 3. 运行 fix-electron.mjs（若存在，修复 macOS Gatekeeper 问题）
 * 4. spawn electron，传入 ELECTRON_RENDERER_URL 环境变量
 */
async function main() {
  viteProcess = spawn(pnpmCommand, ['dev:web'], {
    cwd: frontendDir,
    env: {
      ...process.env,
      BROWSER: 'none',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  let viteOutput = ''
  let resolvedUrl = null
  let urlResolve = null
  const urlPromise = new Promise((resolve) => { urlResolve = resolve })

  // 监听 Vite 输出，解析出 Local URL 后 resolve urlPromise
  const onViteData = (chunk) => {
    const text = chunk.toString()
    process.stdout.write(text)
    viteOutput += text

    if (!resolvedUrl) {
      const url = parseViteUrl(viteOutput)
      if (url) {
        resolvedUrl = url
        urlResolve(url)
      }
    }
  }

  viteProcess.stdout.on('data', onViteData)
  viteProcess.stderr.on('data', onViteData)

  viteProcess.on('exit', (code) => {
    if (!shuttingDown) {
      shutdown(code ?? 1)
    }
  })

  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Timed out waiting for Vite to report URL')), 30000),
  )

  const viteUrl = await Promise.race([urlPromise, timeout])
  console.log(`\nVite ready at ${viteUrl}\n`)

  await waitForServer(viteUrl)

  // macOS 26+ 上，Gatekeeper 可能静默移除未签名的 Electron.app，fix-electron.mjs 负责检测和修复
  const fixScript = path.resolve(__dirname, 'fix-electron.mjs')
  if (fs.existsSync(fixScript)) {
    spawnSync('node', [fixScript], { stdio: 'inherit' })
  }

  // ELECTRON_RUN_AS_NODE 会让 Electron 以纯 Node.js 模式运行（不显示 GUI），需从环境中移除
  const { ELECTRON_RUN_AS_NODE, ...childEnv } = process.env

  electronProcess = spawn(electronBinary, ['./electron/main.cjs'], {
    cwd: frontendDir,
    env: {
      ...childEnv,
      ELECTRON_RENDERER_URL: viteUrl,
    },
    stdio: 'inherit',
  })

  electronProcess.on('exit', (code) => {
    shutdown(code ?? 0)
  })
}

process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error)
  shutdown(1)
})
