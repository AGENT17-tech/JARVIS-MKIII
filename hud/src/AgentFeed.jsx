import { useState, useEffect, useRef } from 'react'

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
    marginBottom: 10,
    textShadow: '0 0 12px rgba(0,200,255,0.35)',
  },
  label: {
    fontFamily: 'Share Tech Mono',
    fontSize: 10,
    color: 'rgba(0,140,200,0.52)',
    letterSpacing: 1.2,
  },
  divider: {
    width: '100%', height: 1,
    background: 'linear-gradient(90deg,transparent,rgba(0,212,255,0.2),transparent)',
    margin: '10px 0',
  },
}

// ── Pipeline agents (fixed, simulated) ───────────────────────────────────────
const PIPELINE_AGENTS = [
  { id: 'RTR', name: 'INTENT ROUTER',  color: '#00d4ff' },
  { id: 'SNT', name: 'SONNET 4.6',     color: '#00d4ff' },
  { id: 'OPS', name: 'OPUS 4.6',       color: '#ffb900' },
  { id: 'DSK', name: 'DEEPSEEK-R1',    color: '#00ffc8' },
  { id: 'MEM', name: 'HINDSIGHT MEM',  color: '#a78bfa' },
  { id: 'SBX', name: 'SANDBOX',        color: '#f472b6' },
]
const ACTIVITIES = [
  'Routing intent...', 'Processing prompt...', 'Distilling memory...',
  'Executing tool...', 'Classifying tier...', 'Fetching context...',
  'Consolidating session...', 'Checking vault...', 'Running sandbox...',
  'Generating response...', 'Idle', 'Idle', 'Idle', 'Idle',
]

const STATUS_COLOR = {
  running:  '#00d4ff',
  complete: '#00ff88',
  error:    '#ff4444',
  idle:     'rgba(0,120,180,0.3)',
  alert:    '#ff4444',
}
const AGENT_COLOR = {
  RESEARCH:  '#00ccff',
  'FILE-OPS': '#a78bfa',
  CODE:       '#00ffc8',
  MONITOR:    '#ffb900',
}

export default function AgentFeed() {
  // ── Pipeline simulation ────────────────────────────────────────────────────
  const [pipelineStates, setPipelineStates] = useState(
    PIPELINE_AGENTS.map(a => ({ ...a, status: 'idle', activity: 'Idle' }))
  )
  const [log, setLog] = useState([])

  useEffect(() => {
    const id = setInterval(() => {
      const idx      = Math.floor(Math.random() * PIPELINE_AGENTS.length)
      const activity = ACTIVITIES[Math.floor(Math.random() * ACTIVITIES.length)]
      const isActive = activity !== 'Idle'
      setPipelineStates(prev => prev.map((a, i) =>
        i === idx ? { ...a, status: isActive ? 'active' : 'idle', activity } : a
      ))
      if (isActive) {
        setLog(prev => [{
          id:    Date.now(),
          agent: PIPELINE_AGENTS[idx].id,
          color: PIPELINE_AGENTS[idx].color,
          text:  activity,
          time:  new Date().toLocaleTimeString('en-US', { hour12: false }),
        }, ...prev].slice(0, 8))
      }
    }, 1800)
    return () => clearInterval(id)
  }, [])

  // ── Operative agents (real — from /ws/agents) ──────────────────────────────
  const [agents,    setAgents]    = useState([])    // {agent_id, name, status, task, result, summary, elapsed, timestamp, severity}
  const [alerts,    setAlerts]    = useState([])    // monitor alerts — pinned
  const [expanded,  setExpanded]  = useState(null)  // agent_id of expanded row
  const wsRef = useRef(null)

  useEffect(() => {
    let ws, reconnectTimer

    const connect = () => {
      try {
        ws = new WebSocket('ws://localhost:8000/ws/agents')
        wsRef.current = ws

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)

            if (msg.type === 'monitor_alert') {
              setAlerts(prev => [{
                id:        Date.now(),
                message:   msg.result || msg.summary,
                severity:  msg.severity,
                timestamp: msg.timestamp,
              }, ...prev].slice(0, 5))
              return
            }

            // Handle both agent_event (progress) and agent_update (completion)
            if (msg.type === 'agent_event' || msg.type === 'agent_update') {
              setAgents(prev => {
                const idx = prev.findIndex(a => a.agent_id === msg.agent_id)
                const entry = {
                  agent_id:  msg.agent_id,
                  name:      msg.name,
                  status:    msg.status,
                  task:      msg.task,
                  result:    msg.result,
                  summary:   msg.summary,
                  elapsed:   msg.elapsed,
                  timestamp: msg.timestamp,
                  severity:  msg.severity || 'normal',
                }
                if (idx >= 0) {
                  const next = [...prev]
                  next[idx] = entry
                  return next
                }
                return [entry, ...prev].slice(0, 10)
              })
            }
          } catch { /* ignore parse errors */ }
        }

        ws.onerror = () => {}
        ws.onclose = () => {
          reconnectTimer = setTimeout(connect, 5000)
        }
      } catch { /* ignore connect errors if backend not running */ }
    }

    // Polling fallback — syncs agent state from REST when WS may have missed events
    const poll = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return
      fetch('http://localhost:8000/agents')
        .then(r => r.json())
        .then(data => {
          if (!Array.isArray(data.agents)) return
          setAgents(prev => {
            const merged = [...prev]
            data.agents.forEach(a => {
              const idx = merged.findIndex(x => x.agent_id === a.agent_id)
              if (idx >= 0) merged[idx] = a
              else merged.unshift(a)
            })
            return merged.slice(0, 10)
          })
        })
        .catch(() => {})
    }
    const pollTimer = setInterval(poll, 5000)

    connect()
    return () => {
      clearTimeout(reconnectTimer)
      clearInterval(pollTimer)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  const dismissAlert = (id) => setAlerts(prev => prev.filter(a => a.id !== id))
  const toggleExpand = (id) => setExpanded(prev => prev === id ? null : id)

  const fmtTime = (ts) => ts
    ? new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false })
    : ''

  return (
    <div style={S.panel}>
      <div style={S.title}>AGENT FEED</div>

      {/* ── Monitor alerts — pinned, dismissible ── */}
      {alerts.length > 0 && (
        <>
          {alerts.map(a => (
            <div key={a.id} style={{
              background: 'rgba(255,40,40,0.08)',
              border: '1px solid rgba(255,60,60,0.35)',
              borderRadius: 2,
              padding: '5px 8px',
              marginBottom: 5,
              display: 'flex',
              alignItems: 'flex-start',
              gap: 7,
            }}>
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginTop: 3,
                background: '#ff4444', boxShadow: '0 0 6px #ff4444',
              }}/>
              <span style={{
                fontFamily: 'Share Tech Mono', fontSize: 8.5, color: 'rgba(255,120,120,0.9)',
                flex: 1, lineHeight: 1.4,
              }}>{a.message}</span>
              <button onClick={() => dismissAlert(a.id)} style={{
                background: 'none', border: 'none', color: 'rgba(255,80,80,0.5)',
                cursor: 'pointer', fontSize: 10, lineHeight: 1, flexShrink: 0, padding: '0 2px',
              }}>✕</button>
            </div>
          ))}
          <div style={S.divider}/>
        </>
      )}

      {/* ── Operative agents ── */}
      {agents.length > 0 && (
        <>
          <div style={{ ...S.title, marginBottom: 8 }}>OPERATIVE AGENTS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {agents.map(a => {
              const color = AGENT_COLOR[a.name] || '#00d4ff'
              const sColor = STATUS_COLOR[a.status] || '#888'
              const isExpanded = expanded === a.agent_id
              return (
                <div key={a.agent_id}>
                  <div
                    onClick={() => toggleExpand(a.agent_id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 7,
                      cursor: 'pointer', padding: '4px 0',
                      borderBottom: '1px solid rgba(0,212,255,0.06)',
                    }}
                  >
                    {/* Status dot */}
                    <div style={{
                      width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                      background: sColor,
                      boxShadow: a.status === 'running' ? `0 0 8px ${sColor}` : 'none',
                      animation: a.status === 'running' ? 'pulse 1s ease-in-out infinite' : 'none',
                    }}/>
                    {/* Agent name */}
                    <span style={{
                      fontFamily: 'Share Tech Mono', fontSize: 9.5, fontWeight: 700,
                      color, letterSpacing: 1, width: 72, flexShrink: 0,
                    }}>{a.name}</span>
                    {/* Task */}
                    <span style={{
                      fontFamily: 'Share Tech Mono', fontSize: 8,
                      color: 'rgba(0,180,255,0.6)', flex: 1,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{a.task}</span>
                    {/* Status tag */}
                    <span style={{
                      fontFamily: 'Share Tech Mono', fontSize: 7.5,
                      color: sColor, letterSpacing: 0.5, flexShrink: 0,
                    }}>{a.status.toUpperCase()}</span>
                    {/* Elapsed */}
                    {a.elapsed != null && (
                      <span style={{
                        fontFamily: 'Share Tech Mono', fontSize: 7,
                        color: 'rgba(0,120,180,0.4)', flexShrink: 0, marginLeft: 3,
                      }}>{a.elapsed}s</span>
                    )}
                  </div>
                  {/* Expanded result */}
                  {isExpanded && a.result && (
                    <div style={{
                      background: 'rgba(0,20,50,0.6)',
                      border: '1px solid rgba(0,180,255,0.12)',
                      borderRadius: 2,
                      padding: '7px 10px',
                      margin: '4px 0 6px',
                      fontFamily: 'Share Tech Mono',
                      fontSize: 8.5,
                      color: 'rgba(180,230,255,0.8)',
                      lineHeight: 1.5,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 200,
                      overflowY: 'auto',
                      scrollbarWidth: 'none',
                    }}>
                      {a.result}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <div style={S.divider}/>
        </>
      )}

      {/* ── Pipeline agents (simulated) ── */}
      <div style={{ ...S.title, marginBottom: 8 }}>PIPELINE</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {pipelineStates.map(a => (
          <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: a.status === 'active' ? a.color : 'rgba(0,120,180,0.3)',
              boxShadow: a.status === 'active' ? `0 0 8px ${a.color}` : 'none',
              transition: 'all 0.4s ease',
            }}/>
            <span style={{
              ...S.label, flex: 1,
              color: a.status === 'active' ? 'rgba(0,212,255,0.85)' : 'rgba(0,140,200,0.52)',
            }}>
              {a.name}
            </span>
            <span style={{
              fontFamily: 'Share Tech Mono', fontSize: 8, letterSpacing: 0.8,
              color: a.status === 'active' ? a.color : 'rgba(0,100,160,0.35)',
              maxWidth: 90, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {a.activity}
            </span>
          </div>
        ))}
      </div>

      <div style={S.divider}/>

      {/* ── Activity log ── */}
      <div style={{ ...S.title, marginBottom: 8 }}>ACTIVITY LOG</div>
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 6,
        maxHeight: 120, overflowY: 'auto', scrollbarWidth: 'none',
      }}>
        {log.length === 0
          ? <span style={{ ...S.label, fontSize: 9 }}>AWAITING ACTIVITY...</span>
          : log.map(entry => (
            <div key={entry.id} style={{ display: 'flex', gap: 7, alignItems: 'flex-start' }}>
              <span style={{
                fontFamily: 'Share Tech Mono', fontSize: 8, color: entry.color,
                flexShrink: 0, marginTop: 1,
              }}>[{entry.agent}]</span>
              <span style={{
                fontFamily: 'Share Tech Mono', fontSize: 9,
                color: 'rgba(150,210,255,0.75)', flex: 1,
              }}>{entry.text}</span>
              <span style={{
                fontFamily: 'Share Tech Mono', fontSize: 7.5,
                color: 'rgba(0,120,180,0.4)', flexShrink: 0,
              }}>{entry.time}</span>
            </div>
          ))
        }
      </div>
    </div>
  )
}
