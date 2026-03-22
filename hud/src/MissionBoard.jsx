import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const PRIORITY_COLOR = {
  critical: '#ff3344',
  high:     '#ff8800',
  medium:   '#00aaff',
  low:      '#2a5a7a',
}
const STATUS_DOT = {
  in_progress: { color: '#00aaff', glow: '0 0 8px #00aaff' },
  complete:    { color: '#00ff88', glow: '0 0 6px #00ff88' },
  pending:     { color: '#2a5a7a', glow: 'none'            },
  deferred:    { color: '#44446a', glow: 'none'            },
}

const S = {
  label:  { fontFamily: 'Share Tech Mono', fontSize: 9,  color: 'rgba(0,140,200,0.52)', letterSpacing: 1.2 },
  dimTxt: { fontFamily: 'Share Tech Mono', fontSize: 8.5,color: 'rgba(0,140,200,0.4)'                      },
  divider:{ width: '100%', height: 1, background: 'linear-gradient(90deg,transparent,rgba(0,212,255,0.15),transparent)', margin: '8px 0' },
}

export default function MissionBoard() {
  const [missions, setMissions] = useState([])
  const [input,    setInput]    = useState('')
  const [priority, setPriority] = useState('medium')
  const [loading,  setLoading]  = useState(false)
  const [eodResult,setEodResult]= useState(null)

  const fetchMissions = () =>
    fetch(`${API}/missions`)
      .then(r => r.json())
      .then(d => Array.isArray(d) && setMissions(d))
      .catch(() => {})

  useEffect(() => {
    fetchMissions()
    const id = setInterval(fetchMissions, 30_000)
    return () => clearInterval(id)
  }, [])

  const addMission = async () => {
    const t = input.trim()
    if (!t) return
    await fetch(`${API}/missions`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: t, priority }),
    })
    setInput('')
    fetchMissions()
  }

  const toggleStatus = async (m) => {
    const next = m.status === 'complete' ? 'pending' : 'complete'
    await fetch(`${API}/missions/${m.id}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ status: next }),
    })
    fetchMissions()
  }

  const endOfDay = async () => {
    setLoading(true)
    try {
      const res  = await fetch(`${API}/missions/eod`, { method: 'POST' })
      const data = await res.json()
      setEodResult(data)
    } catch { /**/ }
    setLoading(false)
  }

  const completed = missions.filter(m => m.status === 'complete').length
  const total     = missions.length
  const pct       = total > 0 ? Math.round(completed / total * 100) : 0

  return (
    <div>
      {/* ── Completion bar ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1, height: 3, background: 'rgba(0,120,220,0.12)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width:  `${pct}%`,
            background: pct === 100
              ? '#00ff88'
              : 'linear-gradient(90deg,#004488,#00aaff)',
            transition: 'width 0.7s cubic-bezier(0.4,0,0.2,1)',
            borderRadius: 2,
          }}/>
        </div>
        <span style={{
          ...S.dimTxt,
          color: pct === 100 ? '#00ff88' : 'rgba(0,170,255,0.65)',
          flexShrink: 0,
        }}>{completed}/{total}</span>
      </div>

      {/* ── Mission list ── */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 3,
        maxHeight: 170, overflowY: 'auto', scrollbarWidth: 'none',
        marginBottom: 8,
      }}>
        {missions.length === 0 && (
          <span style={S.dimTxt}>NO MISSIONS TODAY, SIR.</span>
        )}
        {missions.map(m => {
          const dot = STATUS_DOT[m.status] || STATUS_DOT.pending
          return (
            <div
              key={m.id}
              onClick={() => toggleStatus(m)}
              title={`Click to ${m.status === 'complete' ? 'reopen' : 'complete'}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 7,
                cursor: 'pointer', padding: '3px 0',
                borderBottom: '1px solid rgba(0,212,255,0.05)',
              }}
              onMouseEnter={e => e.currentTarget.style.opacity = '0.72'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background:  dot.color,
                boxShadow:   dot.glow,
              }}/>
              <span style={{
                fontFamily:     'Share Tech Mono',
                fontSize:       9,
                flex:           1,
                color:          m.status === 'complete' ? 'rgba(0,255,136,0.45)' : 'rgba(200,232,255,0.88)',
                textDecoration: m.status === 'complete' ? 'line-through' : 'none',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>{m.title}</span>
              <span style={{
                fontFamily: 'Share Tech Mono', fontSize: 7,
                color:      PRIORITY_COLOR[m.priority] || '#2a5a7a',
                flexShrink: 0, letterSpacing: 0.5,
              }}>{m.priority?.toUpperCase()}</span>
            </div>
          )
        })}
      </div>

      {/* ── Add mission input ── */}
      <div style={{ display: 'flex', gap: 5, alignItems: 'center', marginBottom: 8 }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addMission()}
          placeholder="add mission..."
          style={{
            flex: 1, background: 'transparent', border: 'none',
            borderBottom: '1px solid rgba(0,212,255,0.2)', outline: 'none',
            color: 'rgba(0,212,255,0.9)', fontFamily: 'Share Tech Mono',
            fontSize: 9, padding: '3px 0', caretColor: '#00aaff',
          }}
        />
        <select
          value={priority}
          onChange={e => setPriority(e.target.value)}
          style={{
            background: 'rgba(0,8,22,0.9)', border: '1px solid rgba(0,212,255,0.2)',
            color: PRIORITY_COLOR[priority], fontFamily: 'Share Tech Mono',
            fontSize: 7.5, padding: '2px 4px', borderRadius: 2,
            cursor: 'pointer', outline: 'none',
          }}
        >
          {['critical','high','medium','low'].map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </div>

      {/* ── End of Day button ── */}
      <div
        onClick={loading ? undefined : endOfDay}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '5px 10px',
          border: '1px solid rgba(0,212,255,0.22)',
          borderRadius: 2,
          cursor:  loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.5 : 1,
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={e => {
          if (!loading) {
            e.currentTarget.style.borderColor  = 'rgba(0,212,255,0.65)'
            e.currentTarget.style.background   = 'rgba(0,212,255,0.05)'
          }
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = 'rgba(0,212,255,0.22)'
          e.currentTarget.style.background  = 'transparent'
        }}
      >
        <span style={{
          fontFamily: 'Orbitron', fontSize: 7, letterSpacing: 2,
          color: 'rgba(0,200,255,0.7)',
        }}>
          {loading ? 'PROCESSING...' : 'END OF DAY BRIEFING'}
        </span>
      </div>

      {/* ── EOD result ── */}
      {eodResult && (
        <div style={{
          marginTop: 8, padding: '6px 8px',
          background: 'rgba(0,18,44,0.7)',
          border: '1px solid rgba(0,180,255,0.14)',
          borderRadius: 2,
          animation: 'fadeIn 0.4s ease',
        }}>
          <div style={{
            fontFamily: 'Share Tech Mono', fontSize: 8.5,
            color: 'rgba(180,232,255,0.85)', lineHeight: 1.6,
          }}>
            {eodResult.briefing}
          </div>
          <div style={{
            ...S.dimTxt, marginTop: 5, cursor: 'pointer',
            borderTop: '1px solid rgba(0,180,255,0.08)', paddingTop: 4,
          }} onClick={() => setEodResult(null)}>
            ✕ dismiss
          </div>
        </div>
      )}
    </div>
  )
}
