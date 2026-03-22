const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('jarvis', {
  onSystemStats: (callback) => {
    ipcRenderer.on('system-stats', (event, data) => callback(data))
  }
})