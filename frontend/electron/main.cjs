const fs = require('fs')
const path = require('path')
const { app, BrowserWindow, dialog, ipcMain } = require('electron')
const { BackendManager } = require('./backend-manager.cjs')

const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')
const backendDir = path.join(repoRoot, 'backend')
const rendererDistPath = path.join(frontendDir, 'dist', 'index.html')
const preloadPath = path.join(__dirname, 'preload.cjs')
const rendererDevUrl = process.env.ELECTRON_RENDERER_URL || null

let mainWindow = null

const backendManager = new BackendManager({ backendDir })

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    title: 'ReflexionOS',
    backgroundColor: '#f8fafc',
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  if (rendererDevUrl) {
    mainWindow.loadURL(rendererDevUrl)
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

  mainWindow.loadFile(rendererDistPath)
}

async function bootstrap() {
  try {
    await backendManager.start()
  } catch (error) {
    dialog.showErrorBox(
      'Backend Startup Failed',
      error instanceof Error ? error.message : '未知后端启动错误',
    )
  }

  createWindow()
}

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
  void backendManager.stop()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
