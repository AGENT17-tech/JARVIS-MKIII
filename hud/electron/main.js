const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const si = require('systeminformation')

let mainWindow
let statsInterval

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1920,
    height: 1080,
    frame: false,
    transparent: true,
    alwaysOnTop: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  mainWindow.loadURL('http://localhost:5173')
  mainWindow.setIgnoreMouseEvents(false)

  mainWindow.on('closed', () => {
    clearInterval(statsInterval)
    statsInterval = null
    mainWindow = null
  })

  statsInterval = setInterval(async () => {
    if (!mainWindow || mainWindow.isDestroyed()) return
    try {
      const [cpu, mem, temp] = await Promise.all([
        si.currentLoad(),
        si.mem(),
        si.cpuTemperature()
      ])
      if (!mainWindow || mainWindow.isDestroyed()) return
      mainWindow.webContents.send('system-stats', {
        cpu: Math.round(cpu.currentLoad),
        ram: Math.round((mem.used / mem.total) * 100),
        temp: Math.round(temp.main) || 0
      })
    } catch (_) {}
  }, 2000)
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})