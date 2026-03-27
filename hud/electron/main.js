const { app, BrowserWindow, ipcMain } = require('electron')

if (process.platform === 'linux') {
  app.commandLine.appendSwitch('disable-gpu-sandbox')
  app.commandLine.appendSwitch('no-sandbox')
  app.commandLine.appendSwitch('disable-dev-shm-usage')
  app.commandLine.appendSwitch('disable-setuid-sandbox')
  app.commandLine.appendSwitch('in-process-gpu')
  app.commandLine.appendSwitch('js-flags', '--max-old-space-size=512')
}

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
      nodeIntegration: false,
      sandbox: false,
      backgroundThrottling: true,
      offscreen: false
    }
  })

  if (process.env.NODE_ENV === 'production') {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  } else {
    mainWindow.loadURL('http://localhost:5173')
  }
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
      try { mainWindow.webContents.send('system-stats', {
        cpu: Math.round(cpu.currentLoad),
        ram: Math.round((mem.used / mem.total) * 100),
        temp: Math.round(temp.main) || 0
      }) } catch (_) {}
    } catch (_) {}
  }, 3000)
}

app.whenReady().then(createWindow)

app.on('browser-window-blur', () => {
  try {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('window-blur')
  } catch (_) {}
})

app.on('browser-window-focus', () => {
  try {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('window-focus')
  } catch (_) {}
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})