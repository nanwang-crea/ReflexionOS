import { isElectronRuntime } from './desktopClient'

function getApi() {
  if (!isElectronRuntime()) {
    return null
  }
  return window.electronAPI?.terminal ?? null
}

export const terminalIpc = {
  isAvailable(): boolean {
    return getApi() !== null
  },

  async create(id: string, cwd: string): Promise<{ pid: number }> {
    const api = getApi()
    if (!api) throw new Error('Terminal IPC not available')
    return api.create(id, cwd)
  },

  async write(id: string, data: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.write(id, data)
  },

  async resize(id: string, cols: number, rows: number): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.resize(id, cols, rows)
  },

  async kill(id: string): Promise<void> {
    const api = getApi()
    if (!api) return
    return api.kill(id)
  },

  async isAlive(id: string): Promise<boolean> {
    const api = getApi()
    if (!api) return false
    return api.isAlive(id)
  },

  onData(callback: (id: string, data: string) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onData(callback)
  },

  onExit(callback: (id: string, exitCode: number) => void): () => void {
    const api = getApi()
    if (!api) return () => {}
    return api.onExit(callback)
  },
}
