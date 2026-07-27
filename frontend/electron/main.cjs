/**
 * Electron 主进程入口：负责创建浏览器窗口、管理后端进程生命周期、
 * 提供 IPC 终端通信（node-pty）和系统对话框能力。
 * 跨平台支持：Windows（cmd.exe）和 macOS（zsh/默认 SHELL）。
 */

const fs = require('fs')
const path = require('path')
const { pathToFileURL } = require('url')
const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { BackendManager } = require('./backend-manager.cjs')
const os = require('os')
const pty = require('node-pty')

const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
// 打包后 backendDir 为 null，BackendManager 会从 resourcesPath 加载打包的后端
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

// 截图模式的场景配置：路由、输出文件名、窗口尺寸
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

/**
 * 构建渲染进程 URL，支持开发模式（Vite dev server）和生产模式（本地 dist 文件）。
 * 输入：route（hash 路由，默认 '/agent'）、params（附加 query 参数对象）
 * 输出：完整的 URL 字符串（开发时为 http://，生产时为 file://）
 */
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

/**
 * 创建主窗口（或截图窗口）并加载渲染进程 URL。
 * 输入：options.route（路由）、options.width/height（窗口尺寸）、
 *       options.show（是否立即显示）、options.query（额外 query 参数）
 * 副作用：生产模式下若构建产物缺失，弹出错误对话框；开发模式下自动打开 DevTools。
 */
function createWindow(options = {}) {
  const route = options.route || '/agent'

  mainWindow = new BrowserWindow({
    width: options.width || 1440,
    height: options.height || 920,
    // minWidth 满足代码面板三项宽度预算：MIN_CODE_PANEL(320) + MAX_SIDEBAR(480) + MIN_CHAT(400) = 1200，额外 20px 留给 Windows resize border
    minWidth: 1220,
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

/**
 * 简单的 Promise 延时工具函数。
 * 输入：ms（毫秒数）
 * 输出：在指定时间后 resolve 的 Promise
 */
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 在无头窗口中截取指定场景的截图并保存到 captureDir。
 * 输入：scene（场景名，对应 sceneConfig 的 key）
 * 流程：创建隐藏窗口 → 加载 demo 路由 → 等待 1200ms 渲染稳定 → 截图 → 关闭窗口
 */
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

/**
 * 截图模式入口：依次截取所有配置场景后退出应用。
 * 由环境变量 REFLEXION_CAPTURE_DIR 触发（非空时进入截图模式）。
 */
async function runCaptureMode() {
  for (const scene of captureScenes) {
    await captureScene(scene)
  }

  app.quit()
}

/**
 * 应用启动主流程：启动后端服务（非截图模式），然后进入截图模式或创建主窗口。
 * 输入：无
 * 流程：start backend → (captureMode ? runCaptureMode : createWindow)
 */
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

// 终端实例 Map：terminalId → node-pty 进程
const terminals = new Map()

/**
 * 根据平台获取默认 Shell 命令。
 * Windows 使用 cmd.exe，macOS/Linux 使用 $SHELL 或 /bin/zsh。
 * 输出：shell 可执行文件路径字符串
 */
function getShellCommand() {
  if (process.platform === 'win32') {
    return 'cmd.exe'
  }
  return process.env.SHELL || '/bin/zsh'
}

/**
 * IPC 处理器：terminal:create
 * 创建一个新的伪终端（pty）并绑定到指定 id。
 * 输入：id（终端唯一标识）、cwd（工作目录，为空时使用用户 home 目录）
 * 输出：{pid: number}（成功）或 {pid: -1, error: string}（失败）
 * 副作用：将 pty 输出通过 terminal:data 事件转发到渲染进程
 */
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

/**
 * IPC 处理器：terminal:write
 * 向指定终端写入用户输入数据。
 * 输入：id（终端 id）、data（输入字符串）
 */
ipcMain.handle('terminal:write', (_event, id, data) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.write(data)
  }
})

/**
 * IPC 处理器：terminal:resize
 * 调整终端行列数（跟随 xterm.js 窗口大小变化）。
 * 输入：id（终端 id）、cols（列数）、rows（行数）
 */
ipcMain.handle('terminal:resize', (_event, id, cols, rows) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.resize(cols, rows)
  }
})

/**
 * IPC 处理器：terminal:kill
 * 销毁指定终端进程并从 Map 中移除。
 * 输入：id（终端 id）
 */
ipcMain.handle('terminal:kill', (_event, id) => {
  const ptyProcess = terminals.get(id)
  if (ptyProcess) {
    ptyProcess.kill()
    terminals.delete(id)
  }
})

/**
 * IPC 处理器：terminal:isAlive
 * 检查指定终端是否仍在运行。
 * 输入：id（终端 id）
 * 输出：boolean
 */
ipcMain.handle('terminal:isAlive', (_event, id) => {
  return terminals.has(id)
})

app.whenReady().then(bootstrap)

/**
 * IPC 处理器：dialog:select-directory
 * 弹出系统目录选择对话框，返回用户选中的目录路径。
 * 输出：目录路径字符串，取消时返回 null
 */
ipcMain.handle('dialog:select-directory', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory'],
  })

  if (result.canceled) {
    return null
  }

  return result.filePaths[0] || null
})

/**
 * IPC 处理器：backend:get-status
 * 返回后端进程当前状态（running/stopped/error 等），供渲染进程展示。
 */
ipcMain.handle('backend:get-status', () => backendManager.getStatus())

// macOS：所有窗口关闭后点击 Dock 图标时重新创建窗口
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

// 退出前清理所有 pty 进程并停止后端，避免僵尸进程
app.on('before-quit', () => {
  for (const [, ptyProcess] of terminals) {
    try { ptyProcess.kill() } catch {}
  }
  terminals.clear()
  void backendManager.stop()
})

// Windows/Linux：所有窗口关闭后直接退出
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
