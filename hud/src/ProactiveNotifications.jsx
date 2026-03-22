import { useState, useEffect, useRef, useCallback } from 'react'

const API = 'http://localhost:8000'

const PRIORITY_STYLE = {
  critical: {
    border:  '1px solid rgba(255,51,68,0.7)',
    borderLeft: '3px solid #ff3344',
    boxShadow: '0 0 24px rgba(255,51,68,0.22), inset 0 0 0 1px rgba(255,51,68,0.05)',
    dot: '#ff3344',
    dotGlow: '0 0 8px #ff3344',
    label: 'rgba(255,80,90,0.9)',
  },
  high: {
    border:  '1px solid rgba(255,136,0,0.6)',
    borderLeft: '3px solid #ff8800',
    boxShadow: '0 0 20px rgba(255,136,0,0.18)',
    dot: '#ff8800',
    dotGlow: '0 0 7px #ff8800',
    label: 'rgba(255,160,60,0.9)',
  },
  medium: {
    border:  '1px solid rgba(0,212,255,0.45)',
    borderLeft: '3px solid #00aaff',
    boxShadow: '0 0 18px rgba(0,180,255,0.12)',
    dot: '#00aaff',
    dotGlow: '0 0 6px #00aaff',
    label: 'rgba(0,200,255,0.85)',
  },
  low: {
    border:  '1px solid rgba(60,80,100,0.6)',
    borderLeft: '3px solid #3c5a78',
    boxShadow: '0 0 10px rgba(0,80,120,0.08)',
    dot: '#3c5a78',
    dotGlow: 'none',
    label: 'rgba(80,120,160,0.75)',
  },
}

const TYPE_ICON = {
  briefing: '◈',
  mission:  '⬡',
  calendar: '◇',
  system:   '⚡',
  github:   '◉',
  idle:     '◎',
  eod:      '◈',
}

const MAX_VISIBLE = 3

export default function ProactiveNotifications({ alerts, onDismiss, onAcknowledge }) {
  const [visible, setVisible] = useState([])
  const timerRefs = useRef({})

  // Sync external alerts into visible list, capped at MAX_VISIBLE
  useEffect(() => {
    setVisible(prev => {
      const existingIds = new Set(prev.map(a => a.id))
      const newAlerts   = alerts.filter(a => !existingIds.has(a.id))
      // Prepend new alerts, cap at MAX_VISIBLE
      const merged = [...newAlerts, ...prev].slice(0, MAX_VISIBLE)
      return merged
    })
  }, [alerts])

  // Auto-dismiss after 15 seconds
  useEffect(() => {
    visible.forEach(alert => {
      if (!timerRefs.current[alert.id]) {
        timerRefs.current[alert.id] = setTimeout(() => {
          handleDismiss(alert.id, false)
        }, 15000)
      }
    })
  }, [visible])

  const handleDismiss = useCallback((alertId, callApi = true) => {
    if (timerRefs.current[alertId]) {
      clearTimeout(timerRefs.current[alertId])
      delete timerRefs.current[alertId]
    }
    setVisible(prev => prev.filter(a => a.id !== alertId))
    if (callApi) {
      onDismiss(alertId)
    }
  }, [onDismiss])

  const handleAcknowledge = useCallback((alert) => {
    handleDismiss(alert.id, true)
    onAcknowledge(alert)
  }, [handleDismiss, onAcknowledge])

  if (visible.length === 0) return null

  return (
    <div style={{
      position: 'fixed',
      top: 60,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 400,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      pointerEvents: 'none',
      alignItems: 'center',
      minWidth: 400,
    }}>
      {visible.map((alert, idx) => {
        const ps = PRIORITY_STYLE[alert.priority] || PRIORITY_STYLE.medium
        const icon = TYPE_ICON[alert.type] || '◈'
        const timeStr = alert.timestamp
          ? new Date(alert.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
          : ''

        return (
          <div
            key={alert.id}
            style={{
              pointerEvents: 'all',
              width: 420,
              background: 'rgba(0,6,18,0.97)',
              ...( (() => {
                const { border: _b, boxShadow, borderLeft, ...rest } = ps
                return {}
              })() ),
              border: ps.border,
              borderLeft: ps.borderLeft,
              boxShadow: ps.boxShadow,
              borderRadius: 3,
              padding: '10px 14px',
              backdropFilter: 'blur(8px)',
              animation: 'proactiveSlideDown 0.35s cubic-bezier(0.16,1,0.3,1) forwards',
              opacity: 1,
            }}
          >
            {/* Header row */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 6,
            }}>
              {/* Priority dot */}
              <div style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                flexShrink: 0,
                background: ps.dot,
                boxShadow: ps.dotGlow,
              }}/>
              {/* Type icon */}
              <span style={{
                fontFamily: 'Share Tech Mono',
                fontSize: 11,
                color: ps.dot,
                flexShrink: 0,
              }}>{icon}</span>
              {/* Alert type label */}
              <span style={{
                fontFamily: 'Orbitron',
                fontSize: 7.5,
                letterSpacing: 2,
                color: ps.label,
                flex: 1,
              }}>{alert.title || alert.type?.toUpperCase()}</span>
              {/* Timestamp */}
              <span style={{
                fontFamily: 'Share Tech Mono',
                fontSize: 7.5,
                color: 'rgba(0,140,200,0.45)',
                flexShrink: 0,
              }}>{timeStr}</span>
              {/* Close ✕ */}
              <span
                onClick={() => handleDismiss(alert.id)}
                style={{
                  fontFamily: 'Share Tech Mono',
                  fontSize: 10,
                  color: 'rgba(0,140,200,0.45)',
                  cursor: 'pointer',
                  flexShrink: 0,
                  marginLeft: 6,
                  lineHeight: 1,
                }}
                onMouseEnter={e => e.target.style.color = 'rgba(255,80,80,0.8)'}
                onMouseLeave={e => e.target.style.color = 'rgba(0,140,200,0.45)'}
              >✕</span>
            </div>

            {/* Message */}
            <div style={{
              fontFamily: 'Share Tech Mono',
              fontSize: 9.5,
              color: 'rgba(180,225,255,0.9)',
              lineHeight: 1.55,
              marginBottom: 9,
            }}>
              {alert.hud_message || alert.message}
            </div>

            {/* Action buttons */}
            <div style={{
              display: 'flex',
              gap: 8,
              borderTop: '1px solid rgba(0,180,255,0.1)',
              paddingTop: 7,
            }}>
              <button
                onClick={() => handleDismiss(alert.id)}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: '1px solid rgba(0,180,255,0.2)',
                  borderRadius: 2,
                  padding: '4px 0',
                  fontFamily: 'Orbitron',
                  fontSize: 7,
                  letterSpacing: 1.5,
                  color: 'rgba(0,160,220,0.6)',
                  cursor: 'pointer',
                  transition: 'all 0.18s ease',
                }}
                onMouseEnter={e => {
                  e.target.style.borderColor = 'rgba(255,80,80,0.5)'
                  e.target.style.color = 'rgba(255,80,80,0.8)'
                }}
                onMouseLeave={e => {
                  e.target.style.borderColor = 'rgba(0,180,255,0.2)'
                  e.target.style.color = 'rgba(0,160,220,0.6)'
                }}
              >
                DISMISS
              </button>
              <button
                onClick={() => handleAcknowledge(alert)}
                style={{
                  flex: 1,
                  background: `rgba(${alert.priority === 'critical' ? '255,51,68' : alert.priority === 'high' ? '255,136,0' : '0,170,255'},0.08)`,
                  border: `1px solid ${ps.dot}44`,
                  borderRadius: 2,
                  padding: '4px 0',
                  fontFamily: 'Orbitron',
                  fontSize: 7,
                  letterSpacing: 1.5,
                  color: ps.label,
                  cursor: 'pointer',
                  transition: 'all 0.18s ease',
                }}
                onMouseEnter={e => {
                  e.target.style.background = `${ps.dot}22`
                  e.target.style.borderColor = `${ps.dot}88`
                }}
                onMouseLeave={e => {
                  e.target.style.background = `rgba(${alert.priority === 'critical' ? '255,51,68' : alert.priority === 'high' ? '255,136,0' : '0,170,255'},0.08)`
                  e.target.style.borderColor = `${ps.dot}44`
                }}
              >
                ACKNOWLEDGE
              </button>
            </div>
          </div>
        )
      })}

      <style>{`
        @keyframes proactiveSlideDown {
          from { opacity: 0; transform: translateY(-18px); }
          to   { opacity: 1; transform: translateY(0);     }
        }
      `}</style>
    </div>
  )
}
