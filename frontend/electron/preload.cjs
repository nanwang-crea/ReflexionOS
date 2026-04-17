const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  selectDirectory: () => ipcRenderer.invoke('dialog:select-directory'),
  getBackendStatus: () => ipcRenderer.invoke('backend:get-status'),
})
