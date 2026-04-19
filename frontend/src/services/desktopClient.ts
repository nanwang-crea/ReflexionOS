export function isElectronRuntime() {
  return window.electronAPI?.isElectron === true
}

export function selectProjectDirectory() {
  return window.electronAPI?.selectDirectory() ?? Promise.resolve(null)
}
