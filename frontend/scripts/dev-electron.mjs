import http from 'node:http'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
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
        request.destroy()
      })

      request.setTimeout(1500)
    }

    attempt()
  })
}

function terminateChild(child) {
  if (!child || child.killed) {
    return
  }

  child.kill('SIGTERM')
}

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

async function main() {
  viteProcess = spawn(pnpmCommand, ['dev:web'], {
    cwd: frontendDir,
    env: {
      ...process.env,
      BROWSER: 'none',
    },
    stdio: 'inherit',
  })

  viteProcess.on('exit', (code) => {
    if (!shuttingDown) {
      shutdown(code ?? 1)
    }
  })

  await waitForServer('http://127.0.0.1:5173')

  electronProcess = spawn(electronBinary, ['./electron/main.cjs'], {
    cwd: frontendDir,
    env: {
      ...process.env,
      ELECTRON_RENDERER_URL: 'http://127.0.0.1:5173',
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
