export {}

declare global {
  interface Window {
    electronAPI?: {
      isElectron: boolean
      selectDirectory: () => Promise<string | null>
      getBackendStatus: () => Promise<{ state: string; url: string; pid: number | null; managed: boolean; error: string | null }>
      terminal: {
        create: (id: string, cwd: string) => Promise<{ pid: number }>
        write: (id: string, data: string) => Promise<void>
        resize: (id: string, cols: number, rows: number) => Promise<void>
        kill: (id: string) => Promise<void>
        onData: (callback: (id: string, data: string) => void) => () => void
        onExit: (callback: (id: string, exitCode: number) => void) => () => void
      }
    }
  }
}
