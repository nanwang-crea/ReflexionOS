const http = require('http')
const path = require('path')
const { spawn, spawnSync } = require('child_process')
const { buildImportProbeCode, readProbeModuleNames } = require('./backend-runtime-requirements.cjs')

const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 8000
const HEALTH_PATH = '/health'
const SHUTDOWN_TIMEOUT_MS = 5000

function probeHealth(timeoutMs = 1500) {
  return new Promise((resolve) => {
    const request = http.get(
      {
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        path: HEALTH_PATH,
        timeout: timeoutMs,
      },
      (response) => {
        response.resume()
        resolve(response.statusCode === 200)
      },
    )

    request.on('error', () => resolve(false))
    request.on('timeout', () => {
      request.destroy()
      resolve(false)
    })
  })
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function resolveVirtualEnvPython() {
  const virtualEnv = process.env.VIRTUAL_ENV
  if (!virtualEnv) {
    return null
  }

  return process.platform === 'win32'
    ? path.join(virtualEnv, 'Scripts', 'python.exe')
    : path.join(virtualEnv, 'bin', 'python')
}

function findPythonCommand(requirementsPath) {
  const moduleNames = readProbeModuleNames(requirementsPath)
  const probeCode = buildImportProbeCode(moduleNames)
  const candidates = [
    process.env.REFLEXION_PYTHON_PATH,
    process.env.PYTHON_PATH,
    resolveVirtualEnvPython(),
    'python',
    'python3',
    process.platform === 'win32' ? 'py' : null,
  ].filter(Boolean)

  for (const command of candidates) {
    const args = command === 'py'
      ? ['-3', '-c', probeCode]
      : ['-c', probeCode]
    const result = spawnSync(command, args, { stdio: 'ignore' })

    if (result.status === 0) {
      return command
    }
  }

  return null
}

class BackendManager {
  constructor(options = {}) {
    this.backendDir = options.backendDir
    this.requirementsPath = path.join(this.backendDir, 'requirements.txt')
    this.childProcess = null
    this.state = 'stopped'
    this.error = null
    this.managed = false
    this.pythonCommand = findPythonCommand(this.requirementsPath)
  }

  get url() {
    return `http://${BACKEND_HOST}:${BACKEND_PORT}`
  }

  getStatus() {
    return {
      state: this.state,
      url: this.url,
      pid: this.childProcess ? this.childProcess.pid : null,
      managed: this.managed,
      error: this.error,
    }
  }

  async start() {
    if (await probeHealth()) {
      this.state = 'running'
      this.error = null
      this.managed = false
      return this.getStatus()
    }

    if (!this.pythonCommand) {
      this.state = 'error'
      this.error = '未找到满足 backend/requirements.txt 的 Python 环境，请设置 REFLEXION_PYTHON_PATH。'
      throw new Error(this.error)
    }

    if (this.childProcess) {
      return this.waitUntilHealthy()
    }

    this.state = 'starting'
    this.error = null
    this.managed = true

    const args = this.pythonCommand === 'py'
      ? ['-3', '-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)]
      : ['-m', 'uvicorn', 'app.main:app', '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)]

    this.childProcess = spawn(this.pythonCommand, args, {
      cwd: this.backendDir,
      env: process.env,
      stdio: 'pipe',
    })

    this.childProcess.stdout.on('data', (chunk) => {
      process.stdout.write(`[backend] ${chunk}`)
    })

    this.childProcess.stderr.on('data', (chunk) => {
      process.stderr.write(`[backend] ${chunk}`)
    })

    this.childProcess.on('exit', (code, signal) => {
      this.childProcess = null

      if (this.state === 'stopped') {
        return
      }

      this.state = 'error'
      this.error = `后端进程已退出 (code=${code}, signal=${signal})`
    })

    return this.waitUntilHealthy()
  }

  async waitUntilHealthy(timeoutMs = 15000) {
    const deadline = Date.now() + timeoutMs

    while (Date.now() < deadline) {
      if (await probeHealth()) {
        this.state = 'running'
        this.error = null
        return this.getStatus()
      }

      if (!this.childProcess && this.managed) {
        break
      }

      await wait(300)
    }

    this.state = 'error'
    this.error = this.error || '后端启动超时，请确认已安装 backend 依赖。'
    throw new Error(this.error)
  }

  async stop() {
    if (!this.childProcess || !this.managed) {
      this.state = 'stopped'
      return
    }

    const child = this.childProcess
    this.state = 'stopped'
    this.error = null

    child.kill('SIGTERM')

    const stopped = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), SHUTDOWN_TIMEOUT_MS)

      child.once('exit', () => {
        clearTimeout(timer)
        resolve(true)
      })
    })

    if (!stopped) {
      child.kill('SIGKILL')
    }

    this.childProcess = null
  }
}

module.exports = {
  BACKEND_HOST,
  BACKEND_PORT,
  BackendManager,
}
