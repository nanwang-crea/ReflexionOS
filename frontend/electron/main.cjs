const fs = require('fs')
const path = require('path')
const { pathToFileURL } = require('url')
const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { BackendManager } = require('./backend-manager.cjs')
const os = require('os')
const pty = require('node-pty')

const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = app.isPackaged
  ? null
  : path.join(repoRoot, 'backend')
const rendererDistPath = path.join(frontendDir, 'dist', 'index.html')
const preloadPath = path.join(__dirname, 'preload.cjs')
const rendererDevUrl = process.env.ELECTRON_RENDERER_URL || null
const captureDir = process.env.REFLEXION_CAPTURE_DIR || null
const captureMode = Boolean(captureDir)
const captureScenes = (process.env.REFLEXION_CAPTURE_SCENES || 'agent,projects')
  .split(',')
  .map((scene) => scene.trim())
  .filter(Boolean)

const sceneConfig = {
  agent: {
    route: '/agent',
    filename: 'agent-workspace.png',
    width: 1600,
    height: 1060,
  },
  projects: {
    route: '/projects',
    filename: 'projects-board.png',
    width: 1600,
    height: 1060,
  },
}

let mainWindow = null

const backendManager = new BackendManager({
  appIsPackaged: app.isPackaged,
  backendDir,
  resourcesPath: process.resourcesPath,
})

function buildRendererUrl(route = '/agent', params = {}) {
  if (rendererDevUrl) {
    const url = new URL(rendererDevUrl)
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value))
      }
    })
    url.hash = route
    return url.toString()
  }

  const url = pathToFileURL(rendererDistPath)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value))
    }
  })
  url.hash = route
  return url.toString()
}

function createWindow(options = {}) {
  const route = options.route || '/agent'

  mainWindow = new BrowserWindow({
    width: options.width || 1440,
    height: options.height || 920,
    minWidth: 1180,
    minHeight: 760,
    title: 'ReflexionOS',
    backgroundColor: '#f8fafc',
    show: options.show !== false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  if (rendererDevUrl && !captureMode) {
    mainWindow.loadURL(buildRendererUrl(route))
    mainWindow.webContents.openDevTools({ mode: 'detach' })
    return
  }

  if (!fs.existsSync(rendererDistPath)) {
    dialog.showErrorBox(
      'Renderer Build Missing',
      '未找到前端构建产物，请先在 frontend 目录执行 pnpm build。',
    )
    return
  }

  mainWindow.loadURL(buildRendererUrl(route, options.query))
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function captureScene(scene) {
  const config = sceneConfig[scene]
  if (!config) {
    return
  }

  const screenshotWindow = new BrowserWindow({
    width: config.width,
    height: config.height,
    backgroundColor: '#f8fafc',
    show: false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  await screenshotWindow.loadURL(buildRendererUrl(config.route, {
    demo: '1',
    scene,
  }))
  await wait(1200)

  const image = await screenshotWindow.webContents.capturePage()
  fs.mkdirSync(captureDir, { recursive: true })
  fs.writeFileSync(path.join(captureDir, config.filename), image.toPNG())
  await screenshotWindow.close()
}

async function runCaptureMode() {
  for (const scene of captureScenes) {
    await captureScene(scene)
  }

  app.quit()
}

async function bootstrap() {
  if (!captureMode) {
    try {
      await backendManager.start()
    } catch (error) {
      dialog.showErrorBox(
        'Backend Startup Failed',
        error instanceof Error ? error.message : '未知后端启动错误',
      )
    }
  }

  if (captureMode) {
    await runCaptureMode()
    return
  }

  createWindow({ route: '/agent' })
}

const terminals = new Map()

function getShellCommand() {
  if (process.platform === 'win32') {
    return 'cmd.exe'
  }
  return process.env.SHELL || '/bin/zsh'
}

ipcMain.handle('terminal:create', (_event, id, cwd) => {
  const shell = getShellCommand()
  const args = process.platform === 'darwin' ? ['-i', '-l'] : []
  const effectiveCwd = (cwd && cwd.length > 0) ? cwd : os.homedir()
  const env = Object.assign({}, process.env, { TERM: 'xterm-256color' })

  let ptyProcess
  try {
    ptyProcess = pty.spawn(shell, args, {
      name: 'xterm-256color',
      cols: 80,
      rows: 24,
      cwd: effectiveCwd,
      env: env,
    })
  } catch (err) {
    console.error('[terminal] spawn failed:', err)
    return { pid: -1, error: err.message }
  }

  terminals.set(id, ptyProcess)

  ptyProcess.onData((data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('terminal:data', id, data)
    }
  })

  ptyProcess.onExit(({ exitCode }) => {
    console.error('[terminal] exited:', id, 'exitCode:', exitCode)
    if (terminals.get(id) === ptyProcess) {
      terminals.delete(id)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('terminal:exit', id, exitCode)
      }
    }
  })

  return { pid: ptyProcess.pid }
})

ipcMain.handle('terminal:write', (_event, id, data) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.write(data)
  }
})

ipcMain.handle('terminal:resize', (_event, id, cols, rows) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.resize(cols, rows)
  }
})

ipcMain.handle('terminal:kill', (_event, id) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.kill()
    terminals.delete(id)
  }
})

ipcMain.handle('terminal:isAlive', (_event, id) => {
  return terminals.has(id)
})

app.whenReady().then(bootstrap)

ipcMain.handle('dialog:select-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
  })

  if (result.canceled) {
    return null
  }

  return result.filePaths[0] || null
})

ipcMain.handle('backend:get-status', () => backendManager.getStatus())

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.on('before-quit', () => {
  for (const [, ptyProcess] of terminals) {
    try { ptyProcess.kill() } catch {}
  }
  terminals.clear()
  void backendManager.stop()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
