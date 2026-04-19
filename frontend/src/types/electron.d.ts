interface ElectronAPI {
  isElectron: boolean
  selectDirectory: () => Promise<string | null>
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
