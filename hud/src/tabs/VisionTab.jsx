import { useState, useEffect, useRef } from 'react'

const API = 'http://localhost:8000'
const MAX_HISTORY = 5

const T = {
  panel: { background: 'rgba(0,7,22,0.88)', border: '1px solid rgba(0,212,255,0.18)', borderRadius: 3, backdropFilter: 'blur(6px)', boxShadow: '0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily: 'Orbitron', fontSize: 9, fontWeight: 700, letterSpacing: 3.5, color: 'rgba(0,200,255,0.9)', textTransform: 'uppercase' },
  dim:   { fontFamily: 'Share Tech Mono', fontSize: 9, color: 'rgba(0,140,200,0.5)', letterSpacing: 1 },
  body:  { fontFamily: 'Share Tech Mono', fontSize: 10, color: 'rgba(160,215,255,0.85)', lineHeight: 1.7 },
  input: { background: 'rgba(0,20,50,0.7)', border: '1px solid rgba(0,212,255,0.22)', borderRadius: 2, color: 'rgba(160,215,255,0.9)', fontFamily: 'Share Tech Mono', fontSize: 11, padding: '6px 10px', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:   { background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.35)', borderRadius: 2, color: 'rgba(0,212,255,0.9)', fontFamily: 'Orbitron', fontSize: 8, fontWeight: 700, letterSpacing: 2, padding: '6px 18px', cursor: 'pointer', whiteSpace: 'nowrap' },
}

function VisionBadge({ available }) {
  const color   = available === null ? '#ffb900' : available ? '#00ffc8' : '#ff4444'
  const shadow  = available === null ? '#ffb900' : available ? '#00ffc8' : '#ff4444'
  const label   = available === null ? 'CHECKING...' : available ? 'LLaVA ACTIVE' : 'VISION OFFLINE'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 8px ${shadow}`, animation: available ? 'blink 2s ease-in-out infinite' : 'none' }}/>
      <span style={{ ...T.dim, color: available ? 'rgba(0,255,200,0.7)' : available === null ? 'rgba(255,185,0,0.7)' : 'rgba(255,80,80,0.7)' }}>
        {label}
      </span>
    </div>
  )
}

function HistoryEntry({ entry }) {
  const ts = new Date(entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return (
    <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(0,212,255,0.07)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ ...T.dim, color: 'rgba(0,212,255,0.5)' }}>{entry.source?.toUpperCase()}</span>
        <span style={T.dim}>{ts}</span>
      </div>
      {entry.prompt && (
        <div style={{ ...T.dim, color: 'rgba(0,200,255,0.45)', marginBottom: 3, fontStyle: 'italic' }}>
          &gt; {entry.prompt}
        </div>
      )}
      <div style={{ ...T.body, fontSize: 10, color: 'rgba(140,195,240,0.75)' }}>
        {entry.description}
      </div>
    </div>
  )
}

export default function VisionTab() {
  const [visionStatus, setVisionStatus] = useState(null)   // null=checking, true/false
  const [prompt,       setPrompt]       = useState('Describe what you see.')
  const [description,  setDescription]  = useState('')
  const [imageSrc,     setImageSrc]     = useState(null)
  const [loading,      setLoading]      = useState(false)
  const [history,      setHistory]      = useState([])
  const fileRef = useRef(null)

  // ── Check LLaVA status on mount ───────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/vision/status`)
      .then(r => r.json())
      .then(d => setVisionStatus(d.available))
      .catch(() => setVisionStatus(false))
  }, [])

  // ── Push result to history ────────────────────────────────────────────────
  function pushHistory(source, desc, pmt) {
    setHistory(prev => [{ ts: Date.now(), source, description: desc, prompt: pmt }, ...prev].slice(0, MAX_HISTORY))
  }

  // ── Refresh the screenshot image ──────────────────────────────────────────
  async function refreshImage() {
    // cache-bust so browser reloads the PNG
    setImageSrc(`${API}/vision/image?t=${Date.now()}`)
  }

  // ── Capture & Analyse ─────────────────────────────────────────────────────
  async function handleCapture() {
    setLoading(true)
    setDescription('')
    try {
      const r = await fetch(`${API}/vision/screenshot`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ prompt }),
      })
      const d = await r.json()
      setDescription(d.description || 'No response.')
      pushHistory('screenshot', d.description, prompt)
      await refreshImage()
    } catch (err) {
      setDescription(`Error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // ── Upload image ──────────────────────────────────────────────────────────
  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setDescription('')
    try {
      const form = new FormData()
      form.append('file',   file)
      form.append('prompt', prompt)
      const r = await fetch(`${API}/vision/analyze`, { method: 'POST', body: form })
      const d = await r.json()
      setDescription(d.description || 'No response.')
      pushHistory('upload', d.description, prompt)
      // preview the uploaded file locally
      setImageSrc(URL.createObjectURL(file))
    } catch (err) {
      setDescription(`Error: ${err.message}`)
    } finally {
      setLoading(false)
      e.target.value = ''
    }
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', scrollbarWidth: 'none', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10, boxSizing: 'border-box' }}>

      {/* ── Header ── */}
      <div style={{ ...T.panel, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={T.title}>VISION SYSTEM</div>
          <div style={{ ...T.dim, marginTop: 3 }}>LLaVA · LOCAL MODEL · OLLAMA</div>
        </div>
        <VisionBadge available={visionStatus}/>
      </div>

      {/* ── Controls ── */}
      <div style={{ ...T.panel, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={T.title}>ANALYSIS PROMPT</div>
        <input
          style={T.input}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Describe what you see."
          onKeyDown={e => e.key === 'Enter' && handleCapture()}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            style={{ ...T.btn, flex: 1, opacity: loading ? 0.5 : 1 }}
            onClick={handleCapture}
            disabled={loading}
          >
            {loading ? 'ANALYSING...' : 'CAPTURE & ANALYSE'}
          </button>
          <button
            style={{ ...T.btn, opacity: loading ? 0.5 : 1 }}
            onClick={() => fileRef.current?.click()}
            disabled={loading}
          >
            UPLOAD IMAGE
          </button>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUpload}/>
        </div>
      </div>

      {/* ── Image preview + description ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>

        {/* Screenshot preview */}
        <div style={{ ...T.panel, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={T.title}>VISUAL FEED</div>
          {imageSrc ? (
            <img
              src={imageSrc}
              alt="Vision capture"
              style={{ width: '100%', borderRadius: 2, border: '1px solid rgba(0,212,255,0.14)', objectFit: 'contain', maxHeight: 220 }}
            />
          ) : (
            <div style={{ ...T.dim, height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed rgba(0,212,255,0.12)', borderRadius: 2 }}>
              NO CAPTURE YET
            </div>
          )}
        </div>

        {/* Description output */}
        <div style={{ ...T.panel, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={T.title}>ANALYSIS OUTPUT</div>
          {loading ? (
            <div style={{ ...T.dim, display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00ffc8', boxShadow: '0 0 8px #00ffc8', animation: 'blink 0.6s ease-in-out infinite' }}/>
              PROCESSING...
            </div>
          ) : description ? (
            <div style={{ ...T.body, overflowY: 'auto', maxHeight: 220, scrollbarWidth: 'none' }}>
              {description}
            </div>
          ) : (
            <div style={{ ...T.dim, color: 'rgba(0,140,200,0.3)' }}>
              Awaiting capture, sir.
            </div>
          )}
        </div>
      </div>

      {/* ── History ── */}
      {history.length > 0 && (
        <div style={{ ...T.panel, overflow: 'hidden' }}>
          <div style={{ ...T.title, padding: '12px 14px', borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            RECENT ANALYSES
          </div>
          {history.map((entry, i) => <HistoryEntry key={i} entry={entry}/>)}
        </div>
      )}

    </div>
  )
}
