import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const LINKS = [
  { key: 'backend',   label: 'MKIII BACKEND',  url: `${API}/health`,         check: d => d?.status === 'online' },
  { key: 'groq',      label: 'GROQ API',        url: `${API}/status`,         check: d => !!d?.models?.primary },
  { key: 'ollama',    label: 'OLLAMA LOCAL',    url: 'http://localhost:11434', check: d => !!d },
  { key: 'kokoro',    label: 'KOKORO TTS',      url: `${API}/tts/status`,     check: d => d?.kokoro_ready },
  { key: 'cloudflare',label: 'CLOUDFLARE TUNNEL',url: `${API}/tunnel/status`,  check: d => d?.active },
  { key: 'calendar',  label: 'GOOGLE CALENDAR', url: `${API}/calendar`,       check: d => !!d?.date },
  { key: 'vision',    label: 'LLAVA VISION',    url: `${API}/vision/status`,  check: d => d?.available },
]

export default function NetworkLinks() {
  const [statuses, setStatuses] = useState({})

  useEffect(() => {
    const poll = async () => {
      const results = await Promise.allSettled(
        LINKS.map(link =>
          fetch(link.url, { signal: AbortSignal.timeout(4000) })
            .then(r => r.json())
            .then(d => ({ key: link.key, ok: link.check(d) }))
            .catch(() => ({ key: link.key, ok: false }))
        )
      )
      const next = {}
      results.forEach(r => {
        if (r.status === 'fulfilled') next[r.value.key] = r.value.ok
      })
      setStatuses(next)
    }
    poll()
    const id = setInterval(poll, 10000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      position: 'absolute',
      top: 10,
      right: 10,
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      pointerEvents: 'none',
      zIndex: 10,
    }}>
      {LINKS.map(link => {
        const ok = statuses[link.key]
        const known = link.key in statuses
        const color = !known ? '#2a5a7a' : ok ? '#00ffc8' : '#ff3344'
        const glow  = !known ? 'none'    : ok ? '0 0 6px #00ffc8' : '0 0 6px #ff3344'
        return (
          <div key={link.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: color, boxShadow: glow,
              animation: ok ? 'linkPulse 2s ease-in-out infinite' : 'none',
              flexShrink: 0,
            }}/>
            <span style={{
              fontFamily: 'Share Tech Mono',
              fontSize: 8,
              letterSpacing: 1.2,
              color: ok ? 'rgba(0,220,255,0.75)' : 'rgba(0,120,160,0.45)',
            }}>{link.label}</span>
            <span style={{
              fontFamily: 'Share Tech Mono',
              fontSize: 7,
              color,
              letterSpacing: 1,
              textShadow: glow,
              marginLeft: 2,
            }}>{!known ? '···' : ok ? '●' : '○'}</span>
          </div>
        )
      })}
      <style>{`
        @keyframes linkPulse {
          0%,100% { opacity:1; }
          50%      { opacity:0.45; }
        }
      `}</style>
    </div>
  )
}
