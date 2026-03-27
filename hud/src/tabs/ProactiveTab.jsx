import { useState, useEffect, useRef, useCallback } from 'react'

const API = 'http://localhost:8000'
const WS  = 'ws://localhost:8000/ws/proactive-hud'

const T = {
  panel:  { background: 'rgba(0,7,22,0.88)', border: '1px solid rgba(0,212,255,0.18)', borderRadius: 3, backdropFilter: 'blur(6px)', boxShadow: '0 0 22px rgba(0,80,180,0.08)' },
  title:  { fontFamily: 'Orbitron', fontSize: 9, fontWeight: 700, letterSpacing: 3.5, color: 'rgba(0,200,255,0.9)', textTransform: 'uppercase' },
  dim:    { fontFamily: 'Share Tech Mono', fontSize: 9, color: 'rgba(0,140,200,0.5)', letterSpacing: 1 },
  body:   { fontFamily: 'Share Tech Mono', fontSize: 10, color: 'rgba(160,215,255,0.85)', lineHeight: 1.7 },
  btn:    { background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.35)', borderRadius: 2, color: 'rgba(0,212,255,0.9)', fontFamily: 'Orbitron', fontSize: 8, fontWeight: 700, letterSpacing: 2, padding: '6px 18px', cursor: 'pointer', whiteSpace: 'nowrap' },
  btnRed: { background: 'rgba(255,51,68,0.12)', border: '1px solid rgba(255,51,68,0.35)', borderRadius: 2, color: 'rgba(255,80,90,0.9)', fontFamily: 'Orbitron', fontSize: 8, fontWeight: 700, letterSpacing: 2, padding: '6px 18px', cursor: 'pointer', whiteSpace: 'nowrap' },
  input:  { background: 'rgba(0,20,50,0.7)', border: '1px solid rgba(0,212,255,0.22)', borderRadius: 2, color: 'rgba(160,215,255,0.9)', fontFamily: 'Share Tech Mono', fontSize: 11, padding: '4px 8px', outline: 'none', width: '100%', boxSizing: 'border-box' },
}

const PRIORITY_COLOR = {
  critical: { dot: '#ff3344', text: 'rgba(255,80,90,0.95)', border: 'rgba(255,51,68,0.5)',  bg: 'rgba(255,20,40,0.07)'  },
  high:     { dot: '#ff8800', text: 'rgba(255,160,60,0.95)', border: 'rgba(255,136,0,0.5)', bg: 'rgba(255,100,0,0.06)'  },
  medium:   { dot: '#00aaff', text: 'rgba(0,200,255,0.9)',   border: 'rgba(0,180,255,0.4)', bg: 'rgba(0,120,200,0.05)'  },
  low:      { dot: '#00ffc8', text: 'rgba(0,220,180,0.85)',  border: 'rgba(0,200,160,0.35)',bg: 'rgba(0,180,140,0.04)'  },
}

const SOURCE_ICON = {
  calendar:     '📅',
  github:       '🐙',
  system_health:'💻',
  system:       '💻',
  weather:      '🌤',
  missions:     '🎯',
  whatsapp:     '💬',
}

const INTERVAL_OPTIONS = [
  { label: '30s',  value: 30  },
  { label: '1m',   value: 60  },
  { label: '2m',   value: 120 },
  { label: '5m',   value: 300 },
]

function AgentStatusBadge({ status }) {
  if (!status) return null
  const silenced = status.silenced
  const running  = status.running
  const color    = silenced ? '#ffb900' : running ? '#00ffc8' : '#ff4444'
  const label    = silenced ? 'SILENCED' : running ? 'AGENT ACTIVE' : 'AGENT OFFLINE'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: color,
        boxShadow: `0 0 8px ${color}`,
        animation: running && !silenced ? 'blink 2s ease-in-out infinite' : 'none',
      }}/>
      <span style={{ ...T.dim, color, letterSpacing: 2 }}>{label}</span>
      {silenced && status.silenced_until && (
        <span style={{ ...T.dim, color: 'rgba(255,185,0,0.6)' }}>
          until {new Date(status.silenced_until).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
        </span>
      )}
    </div>
  )
}

function AlertEntry({ alert }) {
  const p   = PRIORITY_COLOR[alert.priority] || PRIORITY_COLOR.low
  const src = alert.source || 'system'
  const ts  = alert.timestamp
    ? new Date(alert.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''
  return (
    <div style={{
      padding: '9px 12px',
      borderBottom: `1px solid rgba(0,212,255,0.07)`,
      borderLeft: `3px solid ${p.dot}`,
      background: p.bg,
      marginBottom: 2,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 13 }}>{SOURCE_ICON[src] || '🔔'}</span>
        <span style={{ ...T.dim, color: p.text, fontWeight: 700, letterSpacing: 1.5 }}>
          {alert.priority?.toUpperCase()}
        </span>
        <span style={{ ...T.dim, color: 'rgba(0,180,255,0.5)', fontSize: 8 }}>
          {src.replace('_', ' ').toUpperCase()}
        </span>
        <span style={{ ...T.dim, marginLeft: 'auto' }}>{ts}</span>
      </div>
      <div style={{ ...T.body, fontSize: 10, color: 'rgba(180,220,255,0.8)' }}>
        {alert.message}
      </div>
    </div>
  )
}

function ToastAlert({ alert, onDismiss }) {
  const p = PRIORITY_COLOR[alert.priority] || PRIORITY_COLOR.medium
  useEffect(() => {
    const t = setTimeout(onDismiss, 8000)
    return () => clearTimeout(t)
  }, [onDismiss])
  return (
    <div style={{
      position: 'fixed', bottom: 80, right: 20, zIndex: 9999,
      width: 340,
      background: 'rgba(5,12,30,0.96)',
      border: `1px solid ${p.dot}`,
      borderLeft: `4px solid ${p.dot}`,
      borderRadius: 3,
      padding: '12px 16px',
      boxShadow: `0 0 30px rgba(0,0,0,0.8), 0 0 15px ${p.dot}33`,
      backdropFilter: 'blur(10px)',
      animation: 'slideInRight 0.3s ease-out',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 16 }}>{SOURCE_ICON[alert.source] || '🔔'}</span>
        <span style={{ ...T.title, color: p.text, fontSize: 8 }}>
          {alert.source?.replace('_',' ').toUpperCase()} — {alert.priority?.toUpperCase()}
        </span>
        <button onClick={onDismiss} style={{
          marginLeft: 'auto', background: 'none', border: 'none',
          color: 'rgba(0,180,255,0.5)', cursor: 'pointer', fontSize: 14, lineHeight: 1,
        }}>×</button>
      </div>
      <div style={{ ...T.body, fontSize: 11, color: 'rgba(200,230,255,0.9)' }}>
        {alert.message}
      </div>
    </div>
  )
}

export default function ProactiveTab() {
  const [status,      setStatus]      = useState(null)
  const [history,     setHistory]     = useState([])
  const [toast,       setToast]       = useState(null)
  const [scanning,    setScanning]    = useState(false)
  const [silencing,   setSilencing]   = useState(false)
  const [silenceMins, setSilenceMins] = useState(30)
  const [configOpen,  setConfigOpen]  = useState(false)
  const [cfgCpu,      setCfgCpu]      = useState('')
  const [cfgRam,      setCfgRam]      = useState('')
  const [cfgCalMin,   setCfgCalMin]   = useState('')
  const [cfgInterval, setCfgInterval] = useState(60)
  const [unreadCount, setUnreadCount] = useState(0)

  // Poll status + history
  const poll = useCallback(() => {
    fetch(`${API}/proactive/status`)
      .then(r => r.json())
      .then(d => {
        setStatus(d)
        setCfgCpu(d.config?.cpu_threshold     ?? 80)
        setCfgRam(d.config?.ram_threshold     ?? 85)
        setCfgCalMin(d.config?.calendar_warn_minutes ?? 20)
        setCfgInterval(d.config?.check_interval ?? 60)
      })
      .catch(() => {})

    fetch(`${API}/proactive/history`)
      .then(r => r.json())
      .then(d => setHistory(d.alerts || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    poll()
    const id = setInterval(poll, 30000)
    return () => clearInterval(id)
  }, [poll])

  // WebSocket — listen for real-time proactive alerts
  useEffect(() => {
    const wsUrl = `ws://localhost:8000/ws/hud-${Math.random().toString(36).slice(2,7)}`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => {
      try {
        const msg = typeof e.data === 'string' ? JSON.parse(e.data) : e.data
        if (msg?.type === 'proactive_alert') {
          const alert = {
            id:        msg.id || Date.now().toString(),
            timestamp: msg.timestamp || new Date().toISOString(),
            source:    msg.source   || msg.data?.type || 'system',
            priority:  msg.priority || msg.data?.priority || 'medium',
            message:   msg.message  || msg.data?.message  || '',
          }
          setToast(alert)
          setUnreadCount(n => n + 1)
          setHistory(prev => [alert, ...prev].slice(0, 20))
        }
      } catch (_) {}
    }
    ws.onerror = () => {}
    return () => ws.close()
  }, [])

  // Dismiss toast
  const dismissToast = useCallback(() => setToast(null), [])

  // ── Actions ────────────────────────────────────────────────────────────────

  async function handleScanNow() {
    setScanning(true)
    try {
      await fetch(`${API}/proactive/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'all' }),
      })
      setTimeout(poll, 3000)
    } finally {
      setTimeout(() => setScanning(false), 4000)
    }
  }

  async function handleSilence() {
    setSilencing(true)
    try {
      await fetch(`${API}/proactive/silence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_minutes: silenceMins }),
      })
      await poll()
    } finally {
      setSilencing(false)
    }
  }

  async function handleResume() {
    await fetch(`${API}/proactive/resume`, { method: 'POST' })
    await poll()
  }

  async function handleSaveConfig() {
    await fetch(`${API}/proactive/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cpu_threshold:         Number(cfgCpu)      || undefined,
        ram_threshold:         Number(cfgRam)      || undefined,
        calendar_warn_minutes: Number(cfgCalMin)   || undefined,
        check_interval:        Number(cfgInterval) || undefined,
      }),
    })
    poll()
  }

  const lastScanLabel = status?.last_scan
    ? new Date(status.last_scan).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'Never'

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gridTemplateRows: 'auto 1fr', gap: 10, padding: 12, height: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>

      {/* ── STATUS BAR ─────────────────────────────────────────────────────── */}
      <div style={{ ...T.panel, gridColumn: '1 / -1', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
        <AgentStatusBadge status={status} />

        <div style={{ display: 'flex', gap: 16, marginLeft: 'auto', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={T.dim}>
            LAST SCAN: <span style={{ color: 'rgba(0,212,255,0.8)' }}>{lastScanLabel}</span>
          </div>
          <div style={T.dim}>
            ALERTS TODAY: <span style={{ color: 'rgba(255,160,60,0.9)' }}>{status?.alerts_fired_today ?? 0}</span>
          </div>
          <div style={T.dim}>
            INTERVAL: <span style={{ color: 'rgba(0,200,255,0.7)' }}>{status?.check_interval ?? 60}s</span>
          </div>
          {unreadCount > 0 && (
            <div
              onClick={() => setUnreadCount(0)}
              style={{ ...T.dim, background: 'rgba(255,80,80,0.2)', border: '1px solid rgba(255,51,68,0.5)', borderRadius: 10, padding: '2px 8px', color: 'rgba(255,100,100,0.9)', cursor: 'pointer' }}
            >
              {unreadCount} NEW
            </div>
          )}
        </div>
      </div>

      {/* ── ALERT HISTORY ──────────────────────────────────────────────────── */}
      <div style={{ ...T.panel, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '10px 14px 8px', borderBottom: '1px solid rgba(0,212,255,0.1)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={T.title}>Alert History</span>
          <span style={{ ...T.dim, marginLeft: 'auto' }}>{history.length} alerts</span>
        </div>

        <div style={{ overflowY: 'auto', flex: 1 }}>
          {history.length === 0 ? (
            <div style={{ padding: 20, ...T.dim, textAlign: 'center', color: 'rgba(0,180,255,0.3)' }}>
              No alerts on record. Agent is monitoring.
            </div>
          ) : (
            history.map((a, i) => <AlertEntry key={a.id || i} alert={a} />)
          )}
        </div>
      </div>

      {/* ── CONTROLS ───────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* Scan + Silence controls */}
        <div style={{ ...T.panel, padding: '14px 16px' }}>
          <div style={{ ...T.title, marginBottom: 14 }}>Controls</div>

          <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
            <button
              onClick={handleScanNow}
              disabled={scanning}
              style={{ ...T.btn, flex: 1, opacity: scanning ? 0.6 : 1 }}
            >
              {scanning ? 'SCANNING...' : '⚡ SCAN NOW'}
            </button>
          </div>

          <div style={{ ...T.dim, marginBottom: 6 }}>SILENCE DURATION</div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
            {[15, 30, 60, 120].map(m => (
              <button
                key={m}
                onClick={() => setSilenceMins(m)}
                style={{
                  ...T.btn,
                  flex: 1,
                  fontSize: 7,
                  padding: '4px 6px',
                  borderColor: silenceMins === m ? 'rgba(255,185,0,0.7)' : undefined,
                  color: silenceMins === m ? 'rgba(255,200,0,0.9)' : undefined,
                }}
              >
                {m < 60 ? `${m}m` : `${m / 60}h`}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            {status?.silenced ? (
              <button onClick={handleResume} style={{ ...T.btn, flex: 1, borderColor: 'rgba(0,255,140,0.5)', color: 'rgba(0,255,180,0.9)' }}>
                ▶ RESUME
              </button>
            ) : (
              <button
                onClick={handleSilence}
                disabled={silencing}
                style={{ ...T.btnRed, flex: 1, opacity: silencing ? 0.6 : 1 }}
              >
                🔕 SILENCE {silenceMins < 60 ? `${silenceMins}m` : `${silenceMins/60}h`}
              </button>
            )}
          </div>
        </div>

        {/* Check interval */}
        <div style={{ ...T.panel, padding: '14px 16px' }}>
          <div style={{ ...T.title, marginBottom: 10 }}>Scan Interval</div>
          <div style={{ display: 'flex', gap: 6 }}>
            {INTERVAL_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={async () => {
                  setCfgInterval(opt.value)
                  await fetch(`${API}/proactive/config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ check_interval: opt.value }),
                  })
                  poll()
                }}
                style={{
                  ...T.btn, flex: 1, fontSize: 7, padding: '4px 4px',
                  borderColor: cfgInterval === opt.value ? 'rgba(0,255,200,0.7)' : undefined,
                  color: cfgInterval === opt.value ? 'rgba(0,255,200,0.9)' : undefined,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Active monitors */}
        <div style={{ ...T.panel, padding: '14px 16px' }}>
          <div style={{ ...T.title, marginBottom: 10 }}>Active Monitors</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {(status?.active_monitors || ['calendar','github','system_health','weather','missions','whatsapp']).map(m => (
              <div key={m} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00ffc8', boxShadow: '0 0 5px #00ffc8', flexShrink: 0 }}/>
                <span style={{ ...T.dim, color: 'rgba(0,200,255,0.6)' }}>{SOURCE_ICON[m] || '●'}</span>
                <span style={{ ...T.body, fontSize: 9, color: 'rgba(140,200,255,0.7)' }}>
                  {m.replace('_', ' ').toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Config panel */}
        <div style={{ ...T.panel, padding: '14px 16px' }}>
          <div
            style={{ ...T.title, marginBottom: configOpen ? 12 : 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
            onClick={() => setConfigOpen(v => !v)}
          >
            {configOpen ? '▾' : '▸'} Config
          </div>

          {configOpen && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div>
                <div style={{ ...T.dim, marginBottom: 3 }}>CALENDAR WARNING (min)</div>
                <input style={T.input} type="number" value={cfgCalMin} onChange={e => setCfgCalMin(e.target.value)} min={1} max={60}/>
              </div>
              <div>
                <div style={{ ...T.dim, marginBottom: 3 }}>CPU THRESHOLD (%)</div>
                <input style={T.input} type="number" value={cfgCpu} onChange={e => setCfgCpu(e.target.value)} min={50} max={100}/>
              </div>
              <div>
                <div style={{ ...T.dim, marginBottom: 3 }}>RAM THRESHOLD (%)</div>
                <input style={T.input} type="number" value={cfgRam} onChange={e => setCfgRam(e.target.value)} min={50} max={100}/>
              </div>
              <button onClick={handleSaveConfig} style={{ ...T.btn, marginTop: 4 }}>
                SAVE CONFIG
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── TOAST ──────────────────────────────────────────────────────────── */}
      {toast && <ToastAlert alert={toast} onDismiss={dismissToast} />}

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes slideInRight { from{transform:translateX(100%);opacity:0} to{transform:translateX(0);opacity:1} }
      `}</style>
    </div>
  )
}
