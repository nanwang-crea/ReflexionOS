interface ElectronBackendStatus {
  state: 'stopped' | 'starting' | 'running' | 'error'
  url: string
  pid: number | null
  managed: boolean
  error: string | null
}

interface ElectronAPI {
  isElectron: boolean
  selectDirectory: () => Promise<string | null>
  getBackendStatus: () => Promise<ElectronBackendStatus | null>
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
