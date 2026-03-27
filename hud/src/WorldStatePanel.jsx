import { useState, useEffect } from 'react'
import MissionBoard from './MissionBoard'

const API = 'http://localhost:8000'

const S = {
  panel: {
    background: 'rgba(0,7,22,0.88)',
    border: '1px solid rgba(0,212,255,0.2)',
    borderRadius: 3,
    padding: '14px 18px',
    width: '100%',
    backdropFilter: 'blur(6px)',
    boxShadow: '0 0 22px rgba(0,80,180,0.08),inset 0 1px 0 rgba(0,212,255,0.07)',
  },
  title: {
    fontFamily: 'Orbitron',
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: 3.5,
    color: 'rgba(0,200,255,0.9)',
    marginBottom: 13,
    textShadow: '0 0 12px rgba(0,200,255,0.35)',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 5,
  },
  label: {
    fontFamily: 'Share Tech Mono',
    fontSize: 10,
    color: 'rgba(0,140,200,0.52)',
    letterSpacing: 1.2,
  },
  value: {
    fontFamily: 'Share Tech Mono',
    fontSize: 11,
    color: 'rgba(0,212,255,0.92)',
    textShadow: '0 0 8px rgba(0,212,255,0.3)',
  },
  barBg: {
    width: '100%',
    height: 2.5,
    background: 'rgba(0,120,220,0.12)',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 10,
  },
  divider: {
    width: '100%',
    height: 1,
    background: 'linear-gradient(90deg,transparent,rgba(0,212,255,0.2),transparent)',
    margin: '11px 0',
  },
}

const Bar = ({ value, max = 100, color }) => (
  <div style={S.barBg}>
    <div style={{
      height: '100%', borderRadius: 2,
      width: `${Math.min((value / max) * 100, 100)}%`,
      background: `linear-gradient(90deg,${color}88,${color})`,
      boxShadow: `0 0 8px ${color}`,
      transition: 'width 1.2s cubic-bezier(0.4,0,0.2,1)',
    }}/>
  </div>
)

// ── Diagnostic Overlay ────────────────────────────────────────────────────────
const DiagnosticOverlay = ({ data, onClose }) => {
  if (!data) return null
  const sys = data.system || {}
  const AGENT_NAMES = ['research','code','file','monitor','autogui','vision']

  const statusColor = v => {
    if (!v) return '#2a5a7a'
    if (v === 'online' || v === 'connected' || v === 'active' || v === 'unlocked') return '#00ff88'
    if (v === 'running') return '#00aaff'
    if (v === 'idle')    return '#2a5a7a'
    if (v === 'error' || v === 'offline') return '#ff3344'
    return '#ffb900'
  }

  const fmt = s => s?.replace(/_/g, ' ').toUpperCase()
  const fmtUptime = s => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 500,
      background: 'rgba(0,3,12,0.88)',
      backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      animation: 'fadeIn 0.3s ease',
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: 480, maxHeight: '80vh', overflowY: 'auto', scrollbarWidth: 'none',
          background: 'rgba(1,10,26,0.98)',
          border: '1px solid rgba(0,212,255,0.35)',
          borderRadius: 4, padding: '20px 24px',
          boxShadow: '0 0 60px rgba(0,100,200,0.2)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <div style={{ fontFamily: 'Orbitron', fontSize: 11, fontWeight: 700, letterSpacing: 3, color: 'rgba(0,212,255,0.95)', textShadow: '0 0 14px rgba(0,212,255,0.5)' }}>
            SYSTEM DIAGNOSTIC
          </div>
          <div onClick={onClose} style={{ cursor: 'pointer', fontFamily: 'Share Tech Mono', fontSize: 9, color: 'rgba(0,140,200,0.5)', letterSpacing: 1 }}>✕ CLOSE</div>
        </div>

        {/* Core systems */}
        <div style={{ fontFamily: 'Orbitron', fontSize: 7, letterSpacing: 2, color: 'rgba(0,140,200,0.45)', marginBottom: 8 }}>CORE SYSTEMS</div>
        {[
          ['BACKEND',         data.backend],
          ['VOICE PIPELINE',  data.voice_pipeline],
          ['VAULT',           data.vault],
          ['HINDSIGHT MEMORY',data.hindsight_memory],
        ].map(([label, val]) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <span style={S.label}>{label}</span>
            <span style={{ fontFamily: 'Share Tech Mono', fontSize: 9.5, color: statusColor(val), textShadow: `0 0 6px ${statusColor(val)}` }}>{fmt(val)}</span>
          </div>
        ))}

        <div style={S.divider}/>

        {/* Agents */}
        <div style={{ fontFamily: 'Orbitron', fontSize: 7, letterSpacing: 2, color: 'rgba(0,140,200,0.45)', marginBottom: 8 }}>AGENTS</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginBottom: 4 }}>
          {AGENT_NAMES.map(name => {
            const val = data.agents?.[name] || 'idle'
            return (
              <div key={name} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={S.label}>{name.toUpperCase()}</span>
                <span style={{ fontFamily: 'Share Tech Mono', fontSize: 9, color: statusColor(val) }}>{fmt(val)}</span>
              </div>
            )
          })}
        </div>

        <div style={S.divider}/>

        {/* System metrics */}
        <div style={{ fontFamily: 'Orbitron', fontSize: 7, letterSpacing: 2, color: 'rgba(0,140,200,0.45)', marginBottom: 8 }}>SYSTEM METRICS</div>
        {[
          ['CPU',      `${sys.cpu ?? '—'}%`,      sys.cpu > 80 ? '#ff3344' : sys.cpu > 60 ? '#ffb900' : '#00d4ff'],
          ['RAM',      `${sys.ram ?? '—'}%`,      sys.ram > 85 ? '#ff3344' : '#00d4ff'],
          ['DISK',     `${sys.disk ?? '—'}%`,     sys.disk > 90 ? '#ff3344' : '#00ffc8'],
          ['GPU VRAM', sys.gpu_vram != null ? `${sys.gpu_vram}%` : 'N/A', '#a78bfa'],
        ].map(([label, val, color]) => (
          <div key={label} style={{ marginBottom: 7 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={S.label}>{label}</span>
              <span style={{ fontFamily: 'Share Tech Mono', fontSize: 10, color }}>{val}</span>
            </div>
            {typeof sys[label.toLowerCase().replace(' ','')] === 'number' && (
              <Bar value={sys[label.toLowerCase().replace(' ','')]} color={color}/>
            )}
          </div>
        ))}

        <div style={S.divider}/>

        {/* Sensors */}
        <div style={{ fontFamily: 'Orbitron', fontSize: 7, letterSpacing: 2, color: 'rgba(0,140,200,0.45)', marginBottom: 8 }}>SENSORS</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginBottom: 4 }}>
          {Object.entries(data.sensors || {}).map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={S.label}>{k.toUpperCase()}</span>
              <span style={{ fontFamily: 'Share Tech Mono', fontSize: 9, color: statusColor(v) }}>{fmt(v)}</span>
            </div>
          ))}
        </div>

        <div style={S.divider}/>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={S.label}>UPTIME</span>
          <span style={S.value}>{fmtUptime(data.uptime || 0)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={S.label}>VERSION</span>
          <span style={{ ...S.value, color: '#a78bfa' }}>{data.version}</span>
        </div>
      </div>
    </div>
  )
}

// ── WorldStatePanel ───────────────────────────────────────────────────────────
export default function WorldStatePanel() {
  const [status,    setStatus]    = useState(null)
  const [uptime,    setUptime]    = useState(0)
  const [cpu,       setCpu]       = useState(0)
  const [ram,       setRam]       = useState(0)
  const [diagData,  setDiagData]  = useState(null)
  const [diagOpen,  setDiagOpen]  = useState(false)
  const [diagLoading, setDiagLoading] = useState(false)

  useEffect(() => {
    const poll = () =>
      fetch(`${API}/status`).then(r => r.json()).then(d => setStatus(d)).catch(() => {})
    poll()
    const id = setInterval(poll, 30000)
    return () => clearInterval(id)
  }, [])

  // Uptime counter — lightweight, no setState on CPU/RAM
  useEffect(() => {
    const id = setInterval(() => setUptime(u => u + 30), 30000)
    return () => clearInterval(id)
  }, [])

  // Real system stats — Electron IPC if available, HTTP /diagnostic fallback otherwise
  useEffect(() => {
    if (window.jarvis) {
      window.jarvis.onSystemStats(d => {
        if (d.cpu !== undefined) setCpu(d.cpu)
        if (d.ram !== undefined) setRam(d.ram)
      })
    } else {
      const poll = () =>
        fetch(`${API}/diagnostic`)
          .then(r => r.json())
          .then(d => {
            const sys = d.system || {}
            if (sys.cpu !== undefined) setCpu(sys.cpu)
            if (sys.ram !== undefined) setRam(sys.ram)
          })
          .catch(() => {})
      poll()
      const id = setInterval(poll, 10000)
      return () => clearInterval(id)
    }
  }, [])

  const runDiagnostic = async () => {
    setDiagLoading(true)
    try {
      const res  = await fetch(`${API}/diagnostic`)
      const data = await res.json()
      setDiagData(data)
      setDiagOpen(true)
    } catch { /**/ }
    setDiagLoading(false)
  }

  const fmtUptime = s => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
  }

  const online = status?.status === 'online'

  return (
    <>
      <div style={S.panel}>
        {/* ── Header row ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 13 }}>
          <div style={{ ...S.title, marginBottom: 0 }}>WORLD STATE</div>
          {/* Diagnostic button */}
          <div
            onClick={diagLoading ? undefined : runDiagnostic}
            title="Run system diagnostics"
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              cursor: diagLoading ? 'not-allowed' : 'pointer',
              opacity: diagLoading ? 0.5 : 1,
              padding: '3px 7px',
              border: '1px solid rgba(0,212,255,0.2)',
              borderRadius: 2,
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={e => {
              if (!diagLoading) {
                e.currentTarget.style.borderColor = 'rgba(0,212,255,0.65)'
                e.currentTarget.style.background  = 'rgba(0,212,255,0.06)'
              }
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'rgba(0,212,255,0.2)'
              e.currentTarget.style.background  = 'transparent'
            }}
          >
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: diagLoading ? '#ffb900' : '#00ffc8',
              boxShadow:  diagLoading ? '0 0 6px #ffb900' : '0 0 5px #00ffc8',
            }}/>
            <span style={{ fontFamily: 'Orbitron', fontSize: 6.5, letterSpacing: 1.5, color: 'rgba(0,200,255,0.7)' }}>
              {diagLoading ? 'SCANNING' : 'DIAG'}
            </span>
          </div>
        </div>

        {/* Backend status */}
        <div style={S.row}>
          <span style={S.label}>MKIII BACKEND</span>
          <span style={{
            fontFamily: 'Share Tech Mono', fontSize: 10, letterSpacing: 1,
            color: online ? '#00ffc8' : '#ff3c3c',
            textShadow: `0 0 8px ${online ? '#00ffc8' : '#ff3c3c'}`,
          }}>{online ? '● ONLINE' : '○ OFFLINE'}</span>
        </div>
        <div style={S.row}>
          <span style={S.label}>UPTIME</span>
          <span style={S.value}>{fmtUptime(uptime)}</span>
        </div>

        <div style={S.divider}/>

        {/* CPU */}
        <div style={S.row}>
          <span style={S.label}>CPU</span>
          <span style={{ ...S.value, color: cpu > 80 ? '#ff3c3c' : cpu > 60 ? '#ffb900' : '#00d4ff' }}>
            {Math.round(cpu)}%
          </span>
        </div>
        <Bar value={cpu} color={cpu > 80 ? '#ff3c3c' : cpu > 60 ? '#ffb900' : '#00d4ff'}/>

        {/* RAM */}
        <div style={S.row}>
          <span style={S.label}>RAM</span>
          <span style={{ ...S.value, color: ram > 85 ? '#ff3c3c' : '#00d4ff' }}>{Math.round(ram)}%</span>
        </div>
        <Bar value={ram} color={ram > 85 ? '#ff3c3c' : '#00d4ff'}/>

        <div style={S.divider}/>

        {/* Model tiers */}
        <div style={{ ...S.title, marginBottom: 8 }}>ACTIVE MODEL TIERS</div>
        {[
          { label: 'VOICE',     model: 'Llama 3.3 70B', color: '#00d4ff' },
          { label: 'REASONING', model: 'Llama 3.3 70B', color: '#ffb900' },
          { label: 'LOCAL',     model: 'Llama 3.2 3B',  color: '#00ffc8' },
        ].map(t => (
          <div key={t.label} style={{ ...S.row, marginBottom: 8 }}>
            <span style={S.label}>{t.label}</span>
            <span style={{ fontFamily: 'Share Tech Mono', fontSize: 9, color: t.color, letterSpacing: 0.8, textShadow: `0 0 6px ${t.color}` }}>
              {t.model}
            </span>
          </div>
        ))}

        <div style={S.divider}/>

        {/* Tool count + version */}
        <div style={S.row}>
          <span style={S.label}>TOOLS ARMED</span>
          <span style={{ ...S.value, color: '#00ffc8' }}>{status?.tools ?? '--'}</span>
        </div>
        <div style={S.row}>
          <span style={S.label}>VERSION</span>
          <span style={S.value}>{status?.version ?? '--'}</span>
        </div>

        <div style={S.divider}/>

        {/* ── Mission Board ── */}
        <div style={{ ...S.title, marginBottom: 8 }}>DAILY MISSIONS</div>
        <MissionBoard/>
      </div>

      {/* Diagnostic overlay (portal-style fixed overlay) */}
      {diagOpen && diagData && (
        <DiagnosticOverlay data={diagData} onClose={() => setDiagOpen(false)}/>
      )}
    </>
  )
}
