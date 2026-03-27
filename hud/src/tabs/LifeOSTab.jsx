import { useState, useEffect } from 'react'
import { QRCodeSVG } from 'qrcode.react'

const API = 'http://localhost:8000'

const T = {
  panel: { background:'rgba(0,7,22,0.88)', border:'1px solid rgba(0,212,255,0.18)', borderRadius:3, backdropFilter:'blur(6px)', boxShadow:'0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily:'Orbitron', fontSize:9, fontWeight:700, letterSpacing:3.5, color:'rgba(0,200,255,0.9)' },
  dim:   { fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.5)', letterSpacing:1 },
  body:  { fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.85)', lineHeight:1.7 },
}

const HABITS = [
  { label:'Morning workout',  done:true,  streak:7,  color:'#00ffc8' },
  { label:'Cold shower',      done:true,  streak:12, color:'#00d4ff' },
  { label:'Read 20 min',      done:false, streak:3,  color:'#ffb900' },
  { label:'No social media',  done:true,  streak:5,  color:'#aa88ff' },
  { label:'Code 2+ hrs',      done:true,  streak:14, color:'#00ffc8' },
  { label:'Sleep by 00:00',   done:false, streak:2,  color:'#ff6644' },
  { label:'Protein goal',     done:true,  streak:9,  color:'#ffb900' },
]

const PRINCIPLES = [
  'Discipline over motivation. Systems over willpower.',
  'Your future self is watching every decision you make today.',
  'Boredom is just impatience wearing a mask.',
  'Build things that matter. Ship constantly.',
  'Every idle hour is a debt paid with future regret.',
]

const PHANTOM_DOMAINS = [
  { key:'engineering', label:'ENGINEERING & ROBOTICS',  color:'#00d4ff', target:80 },
  { key:'programming', label:'PROGRAMMING & CYBER',     color:'#00ffc8', target:85 },
  { key:'combat',      label:'COMBAT & PHYSICAL',       color:'#ff6644', target:75 },
  { key:'strategy',    label:'STRATEGIC THINKING',      color:'#ffb900', target:70 },
  { key:'neuro',       label:'NEURO-PERFORMANCE',       color:'#a78bfa', target:75 },
]

export default function LifeOSTab() {
  const [briefing,      setBriefing]      = useState('Loading morning briefing...')
  const [loading,       setLoading]       = useState(true)
  const [question,      setQuestion]      = useState('')
  const [advice,        setAdvice]        = useState(null)
  const [asking,        setAsking]        = useState(false)
  const [habits,        setHabits]        = useState(HABITS)
  const [principle]                       = useState(() => PRINCIPLES[Math.floor(Math.random() * PRINCIPLES.length)])
  const [lastBriefing,  setLastBriefing]  = useState(null)
  const [briefingRunning, setBriefingRunning] = useState(false)
  const [ttsStatus,     setTtsStatus]     = useState(null)
  const [tunnelUrl,     setTunnelUrl]     = useState(null)
  const [tunnelCopied,  setTunnelCopied]  = useState(false)
  const [tunnelChecked, setTunnelChecked] = useState(false)
  const [phantomScores, setPhantomScores] = useState(null)
  const [phantomPriority, setPhantomPriority] = useState('')

  useEffect(() => {
    setLoading(true)
    const now = new Date()
    fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: `It is ${now.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'})} at ${now.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})}. Give me a sharp, motivating 3-sentence morning briefing for a focused young Egyptian tech entrepreneur working on JARVIS AI, IEEE research, and Enactus. Be direct. No fluff.`,
        session_id: 'hud-tab-lifeos-' + Date.now(),
      }),
    })
      .then(r => r.json())
      .then(d => setBriefing(d.response || 'Ready to execute, sir.'))
      .catch(() => setBriefing('Briefing uplink offline. Proceeding on discipline alone, sir.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetch(`${API}/briefing/last`)
      .then(r => r.json())
      .then(d => { if (d.spoken) setLastBriefing(d) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const fetchTts = () =>
      fetch(`${API}/tts/status`)
        .then(r => r.json())
        .then(d => setTtsStatus(d))
        .catch(() => {})
    fetchTts()
  }, [])

  useEffect(() => {
    const fetchTunnel = () =>
      fetch(`${API}/tunnel/status`)
        .then(r => r.json())
        .then(d => { setTunnelChecked(true); if (d.active && d.url) setTunnelUrl(d.url) })
        .catch(() => setTunnelChecked(true))
    fetchTunnel()
    const id = setInterval(fetchTunnel, 30000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const fetchPhantom = () => {
      fetch(`${API}/phantom/scores`)
        .then(r => r.json())
        .then(d => setPhantomScores(d))
        .catch(() => {})
      fetch(`${API}/phantom/priority`)
        .then(r => r.json())
        .then(d => setPhantomPriority(d.recommendation || ''))
        .catch(() => {})
    }
    fetchPhantom()
    const id = setInterval(fetchPhantom, 60000)
    return () => clearInterval(id)
  }, [])

  const copyTunnelUrl = () => {
    if (!tunnelUrl) return
    navigator.clipboard.writeText(`${tunnelUrl}/mobile`).then(() => {
      setTunnelCopied(true)
      setTimeout(() => setTunnelCopied(false), 2000)
    })
  }

  const runBriefing = async () => {
    if (briefingRunning) return
    setBriefingRunning(true)
    try {
      const res = await fetch(`${API}/briefing/run`)
      const d   = await res.json()
      if (d.spoken) setLastBriefing(d)
    } catch {
      // silently ignore — TTS and terminal output still happen server-side
    } finally {
      setBriefingRunning(false)
      fetch(`${API}/tts/status`).then(r => r.json()).then(d => setTtsStatus(d)).catch(() => {})
    }
  }

  const askAdvice = async () => {
    if (!question.trim() || asking) return
    setAsking(true)
    setAdvice(null)
    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: `Personal advice request from a focused, ambitious 20-something Egyptian tech entrepreneur: "${question}". Give direct, practical, no-BS advice in 3-4 sentences. Think like Marcus Aurelius meets Paul Graham.`,
          session_id: 'hud-tab-lifeos-' + Date.now(),
        }),
      })
      const d = await res.json()
      setAdvice(d.response || 'No signal, sir.')
    } catch {
      setAdvice('Backend offline, sir.')
    } finally {
      setAsking(false)
    }
  }

  const toggleHabit = (i) => {
    setHabits(prev => prev.map((h, idx) => idx === i ? { ...h, done: !h.done } : h))
  }

  const doneCount = habits.filter(h => h.done).length

  return (
    <div style={{ height:'100%', overflow:'hidden', padding:'10px 14px', display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, overflow:'hidden' }}>

        {/* Left */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, overflow:'hidden' }}>

          {/* Morning brief */}
          <div style={{ ...T.panel, padding:'14px 18px', flexShrink:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
              <div style={{ ...T.title }}>◈ MORNING BRIEFING</div>
              <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                  <div style={{ width:5, height:5, borderRadius:'50%', background: loading?'#ffb900':'#00ffc8', boxShadow:`0 0 7px ${loading?'#ffb900':'#00ffc8'}`, animation: loading?'blink 0.8s ease-in-out infinite':'none' }}/>
                  <span style={{ ...T.dim, fontSize:7 }}>{loading ? 'LOADING' : 'READY'}</span>
                </div>
                {ttsStatus && (
                  <div style={{ display:'flex', alignItems:'center', gap:4, padding:'3px 8px', border:`1px solid ${ttsStatus.kokoro_ready?'rgba(0,255,200,0.3)':'rgba(255,100,0,0.3)'}`, borderRadius:2 }}>
                    <div style={{ width:5, height:5, borderRadius:'50%', background: ttsStatus.kokoro_ready?'#00ffc8':'#ff6400', boxShadow:`0 0 6px ${ttsStatus.kokoro_ready?'#00ffc8':'#ff6400'}` }}/>
                    <span style={{ fontFamily:'Share Tech Mono', fontSize:7, color: ttsStatus.kokoro_ready?'rgba(0,255,200,0.8)':'rgba(255,100,0,0.8)', letterSpacing:1 }}>
                      {ttsStatus.kokoro_ready ? 'KOKORO' : 'TTS LOADING'}
                    </span>
                  </div>
                )}
                <button onClick={runBriefing} disabled={briefingRunning}
                  style={{ background:'none', border:'1px solid rgba(0,212,255,0.35)', borderRadius:2, color: briefingRunning?'rgba(0,212,255,0.35)':'rgba(0,212,255,0.8)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'4px 10px', cursor: briefingRunning?'default':'pointer', transition:'all 0.2s ease' }}>
                  {briefingRunning ? '...' : 'RUN BRIEFING'}
                </button>
              </div>
            </div>
            <div style={{ ...T.body, lineHeight:1.8, fontSize:10 }}>{briefing}</div>
            {lastBriefing && (
              <div style={{ marginTop:10, borderTop:'1px solid rgba(0,212,255,0.1)', paddingTop:10 }}>
                <div style={{ ...T.dim, fontSize:7, marginBottom:6 }}>
                  LAST BRIEFING — {lastBriefing.date} {lastBriefing.time}
                </div>
                <textarea
                  readOnly
                  value={lastBriefing.spoken || ''}
                  style={{ width:'100%', background:'rgba(0,4,14,0.5)', border:'1px solid rgba(0,212,255,0.12)', borderRadius:2, color:'rgba(120,190,255,0.75)', fontFamily:'Share Tech Mono', fontSize:9, lineHeight:1.6, padding:'8px 10px', resize:'none', outline:'none', minHeight:72, boxSizing:'border-box' }}
                />
              </div>
            )}
          </div>

          {/* Today's principle */}
          <div style={{ ...T.panel, padding:'12px 18px', flexShrink:0, borderLeft:'3px solid rgba(0,212,255,0.4)' }}>
            <div style={{ ...T.dim, marginBottom:5 }}>DAILY PRINCIPLE</div>
            <div style={{ fontFamily:'Share Tech Mono', fontSize:11, color:'rgba(0,212,255,0.9)', lineHeight:1.7, fontStyle:'italic' }}>"{principle}"</div>
          </div>

          {/* Life advisor */}
          <div style={{ ...T.panel, padding:'14px 18px', flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
            <div style={{ ...T.title, marginBottom:10 }}>⬡ LIFE ADVISOR</div>
            <div style={{ display:'flex', gap:6, marginBottom:advice?8:0 }}>
              <input
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && askAdvice()}
                placeholder="Ask anything, sir..."
                style={{ flex:1, background:'transparent', border:'1px solid rgba(0,212,255,0.2)', borderRadius:2, padding:'6px 10px', color:'rgba(0,212,255,0.9)', fontFamily:'Share Tech Mono', fontSize:10, outline:'none' }}
              />
              <button onClick={askAdvice} disabled={asking}
                style={{ background:'none', border:'1px solid rgba(0,212,255,0.3)', borderRadius:2, color:'rgba(0,212,255,0.7)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'6px 12px', cursor:'pointer' }}>
                {asking ? '...' : 'ASK'}
              </button>
            </div>
            {advice && (
              <div style={{ ...T.body, fontSize:10, lineHeight:1.7, flex:1, overflowY:'auto', scrollbarWidth:'none' }}>{advice}</div>
            )}
          </div>
        </div>

        {/* Right — Phantom Zero + Habit tracker */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, overflow:'hidden' }}>

          {/* PHANTOM ZERO — Domain Status */}
          <div style={{ ...T.panel, padding:'14px 18px', flexShrink:0 }}>
            <div style={{ ...T.title, marginBottom:10 }}>◈ PHANTOM ZERO — DOMAIN STATUS</div>
            {phantomScores ? (
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {PHANTOM_DOMAINS.map(d => {
                  const info  = phantomScores[d.key] || {}
                  const score = info.score ?? 25
                  const pct   = Math.min(100, score)
                  const tPct  = d.target
                  return (
                    <div key={d.key}>
                      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:3 }}>
                        <span style={{ fontFamily:'Orbitron', fontSize:8, letterSpacing:2, color:'rgba(160,215,255,0.7)' }}>{d.label}</span>
                        <span style={{ fontFamily:'Orbitron', fontSize:18, fontWeight:700, color:d.color, lineHeight:1 }}>{score}</span>
                      </div>
                      <div style={{ position:'relative', height:3, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'visible' }}>
                        <div style={{ height:'100%', width:`${pct}%`, background:d.color, boxShadow:`0 0 6px ${d.color}88`, borderRadius:2, transition:'width 0.6s ease' }}/>
                        {/* Target indicator */}
                        <div style={{ position:'absolute', top:-2, left:`${tPct}%`, width:1, height:7, background:'rgba(255,255,255,0.4)', borderRadius:1 }}/>
                      </div>
                    </div>
                  )
                })}
                {phantomPriority && (
                  <div style={{ marginTop:6, fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(160,215,255,0.55)', lineHeight:1.5, borderTop:'1px solid rgba(0,212,255,0.1)', paddingTop:6 }}>
                    {phantomPriority}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ ...T.dim }}>Loading domain scores...</div>
            )}
          </div>

          {/* Habit tracker */}
          <div style={{ ...T.panel, padding:'14px 18px', display:'flex', flexDirection:'column', overflow:'hidden', flex:1 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
            <div style={{ ...T.title }}>◇ HABIT TRACKER</div>
            <div style={{ fontFamily:'Orbitron', fontSize:18, fontWeight:700, color:'#00ffc8' }}>{doneCount}/{habits.length}</div>
          </div>

          <div style={{ height:4, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'hidden', marginBottom:14 }}>
            <div style={{ height:'100%', width:`${doneCount/habits.length*100}%`, background:'#00ffc8', boxShadow:'0 0 10px #00ffc8', borderRadius:2, transition:'width 0.4s ease' }}/>
          </div>

          <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:6 }}>
            {habits.map((h, i) => (
              <div key={i} onClick={() => toggleHabit(i)}
                style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', borderRadius:2, background: h.done?'rgba(0,255,200,0.04)':'rgba(0,4,14,0.4)', cursor:'pointer', border:`1px solid ${h.done?'rgba(0,255,200,0.15)':'rgba(0,212,255,0.06)'}`, transition:'all 0.2s ease' }}>
                <div style={{ width:16, height:16, borderRadius:2, border:`2px solid ${h.done?h.color:'rgba(0,212,255,0.25)'}`, background: h.done?h.color:'transparent', flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', transition:'all 0.2s ease' }}>
                  {h.done && <span style={{ fontSize:9, color:'#000', fontWeight:700 }}>✓</span>}
                </div>
                <span style={{ fontFamily:'Share Tech Mono', fontSize:10, flex:1, color: h.done?'rgba(160,215,255,0.9)':'rgba(0,140,200,0.45)', textDecoration: h.done?'none':'none' }}>{h.label}</span>
                <div style={{ display:'flex', alignItems:'center', gap:4 }}>
                  <span style={{ fontFamily:'Orbitron', fontSize:10, fontWeight:700, color: h.streak>=7?'#ffb900':'rgba(0,140,200,0.4)' }}>{h.streak}</span>
                  <span style={{ ...T.dim, fontSize:7 }}>days</span>
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop:10, paddingTop:10, borderTop:'1px solid rgba(0,212,255,0.1)' }}>
            <div style={{ display:'flex', justifyContent:'space-between' }}>
              <span style={{ ...T.dim }}>BEST STREAK</span>
              <span style={{ fontFamily:'Orbitron', fontSize:10, color:'#ffb900' }}>
                {Math.max(...habits.map(h=>h.streak))} days
              </span>
            </div>
          </div>
        </div>
        </div>{/* end right column */}
      </div>

      {/* Tunnel panel */}
      <div style={{ ...T.panel, padding:'12px 18px', flexShrink:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom: tunnelUrl ? 12 : 0 }}>
          <div style={{ ...T.title }}>◈ MOBILE ACCESS</div>
          <div style={{ display:'flex', alignItems:'center', gap:5, marginLeft:8 }}>
            <div style={{ width:5, height:5, borderRadius:'50%', background: tunnelUrl?'#00ffc8':'#ff6400', boxShadow:`0 0 6px ${tunnelUrl?'#00ffc8':'#ff6400'}`, animation: tunnelUrl?'none':'blink 1s ease-in-out infinite' }}/>
            <span style={{ ...T.dim, fontSize:7 }}>{tunnelUrl ? 'TUNNEL ACTIVE' : tunnelChecked ? 'OFFLINE' : 'CONNECTING...'}</span>
          </div>
          {tunnelUrl && (
            <div style={{ marginLeft:'auto', display:'flex', gap:6 }}>
              <button onClick={copyTunnelUrl}
                style={{ background:'none', border:'1px solid rgba(0,212,255,0.35)', borderRadius:2, color: tunnelCopied?'#00ffc8':'rgba(0,212,255,0.8)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'4px 10px', cursor:'pointer' }}>
                {tunnelCopied ? 'COPIED' : 'COPY URL'}
              </button>
              <a href={`${tunnelUrl}/mobile`} target="_blank" rel="noopener noreferrer"
                style={{ background:'none', border:'1px solid rgba(0,255,200,0.3)', borderRadius:2, color:'rgba(0,255,200,0.8)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'4px 10px', textDecoration:'none', display:'flex', alignItems:'center' }}>
                OPEN
              </a>
            </div>
          )}
        </div>
        {tunnelUrl && (
          <div style={{ display:'flex', gap:16, alignItems:'flex-start' }}>
            <div style={{ background:'#fff', padding:6, borderRadius:3, flexShrink:0 }}>
              <QRCodeSVG value={`${tunnelUrl}/mobile`} size={96} level="M" />
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:4, justifyContent:'center', paddingTop:4 }}>
              <div style={{ ...T.dim, fontSize:7, marginBottom:2 }}>SCAN TO ACCESS FROM PHONE</div>
              <div style={{ fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,212,255,0.7)', wordBreak:'break-all', lineHeight:1.5 }}>
                {tunnelUrl}/mobile
              </div>
              <div style={{ ...T.dim, fontSize:7, marginTop:4 }}>Token: phantom-zero-2026</div>
            </div>
          </div>
        )}
      </div>

      <style>{`@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }`}</style>
    </div>
  )
}
