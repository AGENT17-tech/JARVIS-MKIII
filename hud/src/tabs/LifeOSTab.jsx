import { useState, useEffect } from 'react'

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

export default function LifeOSTab() {
  const [briefing, setBriefing]   = useState('Loading morning briefing...')
  const [loading,  setLoading]    = useState(true)
  const [question, setQuestion]   = useState('')
  const [advice,   setAdvice]     = useState(null)
  const [asking,   setAsking]     = useState(false)
  const [habits,   setHabits]     = useState(HABITS)
  const [principle] = useState(() => PRINCIPLES[Math.floor(Math.random() * PRINCIPLES.length)])

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
              <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:5 }}>
                <div style={{ width:5, height:5, borderRadius:'50%', background: loading?'#ffb900':'#00ffc8', boxShadow:`0 0 7px ${loading?'#ffb900':'#00ffc8'}`, animation: loading?'blink 0.8s ease-in-out infinite':'none' }}/>
                <span style={{ ...T.dim, fontSize:7 }}>{loading ? 'LOADING' : 'READY'}</span>
              </div>
            </div>
            <div style={{ ...T.body, lineHeight:1.8, fontSize:10 }}>{briefing}</div>
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

        {/* Right — Habit tracker */}
        <div style={{ ...T.panel, padding:'14px 18px', display:'flex', flexDirection:'column', overflow:'hidden' }}>
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
      </div>

      <style>{`@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }`}</style>
    </div>
  )
}
