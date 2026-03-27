import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const ALERT_POOL = [
  { msg: 'Hindsight memory consolidated',     color: '#a78bfa', icon: '◈' },
  { msg: 'Intent routed → Llama 3.3 70B',      color: '#ffb900', icon: '⬡' },
  { msg: 'Intent routed → Llama 3.3 70B',      color: '#00d4ff', icon: '⬡' },
  { msg: 'Intent routed → Llama 3.2 3B',       color: '#00ffc8', icon: '⬡' },
  { msg: 'Vault access granted',              color: '#00ffc8', icon: '◈' },
  { msg: 'Sandbox tool executed',             color: '#f472b6', icon: '⬡' },
  { msg: 'Session context updated',           color: '#00d4ff', icon: '◈' },
  { msg: 'Long-term memory recalled',         color: '#a78bfa', icon: '◈' },
  { msg: 'Backend health check — nominal',    color: '#00ffc8', icon: '◈' },
  { msg: 'Extended thinking engaged',         color: '#ffb900', icon: '⬡' },
]

let alertId = 0

export default function AutonomousAlerts() {
  const [alerts, setAlerts] = useState([])

  const pushAlert = (msg, color, icon) => {
    const id = ++alertId
    setAlerts(prev => [...prev, { id, msg, color, icon, visible: true }])
    setTimeout(() => {
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, visible: false } : a))
      setTimeout(() => setAlerts(prev => prev.filter(a => a.id !== id)), 600)
    }, 4000)
  }

  // Simulated alerts removed — real events come from backend WebSocket

  // Poll MKIII status and alert on state change
  useEffect(() => {
    let lastStatus = null
    const id = setInterval(() => {
      fetch(`${API}/status`)
        .then(r => r.json())
        .then(d => {
          if (lastStatus === null) {
            lastStatus = d.status
            return
          }
          if (d.status !== lastStatus) {
            pushAlert(
              d.status === 'online' ? 'MKIII backend reconnected' : 'MKIII backend unreachable',
              d.status === 'online' ? '#00ffc8' : '#ff3c3c',
              '◈'
            )
            lastStatus = d.status
          }
        })
        .catch(() => {
          if (lastStatus === 'online') {
            pushAlert('MKIII backend unreachable', '#ff3c3c', '◈')
            lastStatus = 'offline'
          }
        })
    }, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      position: 'fixed',
      top: 60,
      right: 36,
      zIndex: 300,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      pointerEvents: 'none',
      alignItems: 'flex-end',
    }}>
      {alerts.map(alert => (
        <div key={alert.id} style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'rgba(0,7,22,0.96)',
          border: `1px solid ${alert.color}44`,
          borderLeft: `3px solid ${alert.color}`,
          borderRadius: 3,
          padding: '7px 14px',
          boxShadow: `0 0 18px ${alert.color}22`,
          opacity: alert.visible ? 1 : 0,
          transform: alert.visible ? 'translateX(0)' : 'translateX(24px)',
          transition: 'opacity 0.4s ease, transform 0.4s ease',
          maxWidth: 280,
        }}>
          <span style={{
            fontFamily: 'Share Tech Mono',
            fontSize: 11,
            color: alert.color,
            textShadow: `0 0 8px ${alert.color}`,
            flexShrink: 0,
          }}>
            {alert.icon}
          </span>
          <span style={{
            fontFamily: 'Share Tech Mono',
            fontSize: 9,
            color: 'rgba(160,215,255,0.88)',
            letterSpacing: 0.8,
            whiteSpace: 'nowrap',
          }}>
            {alert.msg}
          </span>
        </div>
      ))}
    </div>
  )
}
