export function isElectronRuntime() {
  return window.electronAPI?.isElectron === true
}

export function selectProjectDirectory() {
  return window.electronAPI?.selectDirectory() ?? Promise.resolve(null)
}

export function getBackendStatus() {
  return window.electronAPI?.getBackendStatus() ?? Promise.resolve(null)
}
