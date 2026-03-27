const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('jarvis', {
  onSystemStats: (callback) => {
    ipcRenderer.on('system-stats', (event, data) => callback(data))
  },
  onWindowBlur: (callback) => {
    ipcRenderer.on('window-blur', () => callback())
  },
  onWindowFocus: (callback) => {
    ipcRenderer.on('window-focus', () => callback())
  },
})