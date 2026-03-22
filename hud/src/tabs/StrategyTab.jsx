import { useState } from 'react'

const API = 'http://localhost:8000'

const T = {
  panel: { background:'rgba(0,7,22,0.88)', border:'1px solid rgba(0,212,255,0.18)', borderRadius:3, backdropFilter:'blur(6px)', boxShadow:'0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily:'Orbitron', fontSize:9, fontWeight:700, letterSpacing:3.5, color:'rgba(0,200,255,0.9)' },
  dim:   { fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.5)', letterSpacing:1 },
  body:  { fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.85)', lineHeight:1.7 },
}

const PROJECTS = [
  { id:1, name:'PHANTOM ZERO',   status:'ACTIVE',   priority:'CRITICAL', phase:'Phase 4 / 7', progress:57, color:'#ff6644' },
  { id:2, name:'JARVIS-MKIII',   status:'ACTIVE',   priority:'HIGH',     phase:'Phase 2 / 5', progress:40, color:'#00d4ff' },
  { id:3, name:'IEEE PAPER',     status:'PENDING',  priority:'HIGH',     phase:'Draft / Review', progress:25, color:'#ffb900' },
  { id:4, name:'ENACTUS PITCH',  status:'ACTIVE',   priority:'MEDIUM',   phase:'Prototype',   progress:35, color:'#00ffc8' },
  { id:5, name:'PORTFOLIO SITE', status:'PAUSED',   priority:'LOW',      phase:'Design',      progress:15, color:'#aa88ff' },
]

const DECISIONS = [
  { q:'Should I use Groq or Anthropic as the primary API for JARVIS reasoning?',  rec:'Groq for latency, Anthropic for quality — use routing logic to select per-query.', conf:88 },
  { q:'Should I pursue IEEE publication this semester or defer to next?',           rec:'Push for submission. Deadline pressure drives quality. Use JARVIS to accelerate drafting.', conf:74 },
  { q:'What is the highest-leverage technical skill to develop in Q2 2025?',        rec:'Agentic systems architecture — directly applicable to JARVIS, IEEE, and career differentiation.', conf:82 },
]

export default function StrategyTab() {
  const [ideaInput, setIdeaInput] = useState('')
  const [ideaResult, setIdeaResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeDecision, setActiveDecision] = useState(null)

  const evaluateIdea = async () => {
    if (!ideaInput.trim() || loading) return
    setLoading(true)
    setIdeaResult(null)
    try {
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: `Evaluate this idea for a smart, ambitious young Egyptian tech entrepreneur: "${ideaInput}".
Rate it on: Feasibility (0-10), Impact (0-10), Alignment with technical skills (0-10), Market timing (0-10).
Give a concise verdict in 3-4 sentences. Format: SCORES: F:X I:X A:X T:X | VERDICT: [text]`,
          session_id: 'hud-tab-strategy-' + Date.now(),
        }),
      })
      const d = await res.json()
      setIdeaResult(d.response || 'Evaluation failed, sir.')
    } catch {
      setIdeaResult('Connection lost, sir.')
    } finally {
      setLoading(false)
    }
  }

  const parseScores = (text) => {
    const m = text?.match(/F:(\d+)\s+I:(\d+)\s+A:(\d+)\s+T:(\d+)/)
    if (!m) return null
    return { F: parseInt(m[1]), I: parseInt(m[2]), A: parseInt(m[3]), T: parseInt(m[4]) }
  }

  const getVerdict = (text) => {
    const m = text?.match(/VERDICT:\s*(.+)/s)
    return m ? m[1].trim() : text
  }

  const scores = parseScores(ideaResult)
  const verdict = getVerdict(ideaResult)

  return (
    <div style={{ height:'100%', overflow:'hidden', padding:'10px 14px', display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, flex:1, overflow:'hidden' }}>

        {/* Left column */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, overflow:'hidden' }}>

          {/* Idea Evaluator */}
          <div style={{ ...T.panel, padding:'14px 18px', flexShrink:0 }}>
            <div style={{ ...T.title, marginBottom:10 }}>◈ IDEA EVALUATOR</div>
            <div style={{ display:'flex', gap:6, marginBottom:8 }}>
              <input
                value={ideaInput}
                onChange={e => setIdeaInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && evaluateIdea()}
                placeholder="Describe your idea, sir..."
                style={{ flex:1, background:'transparent', border:'1px solid rgba(0,212,255,0.2)', borderRadius:2, padding:'6px 10px', color:'rgba(0,212,255,0.9)', fontFamily:'Share Tech Mono', fontSize:10, outline:'none' }}
              />
              <button onClick={evaluateIdea} disabled={loading}
                style={{ background:'none', border:'1px solid rgba(0,212,255,0.3)', borderRadius:2, color:'rgba(0,212,255,0.7)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'6px 12px', cursor:'pointer' }}>
                {loading ? '...' : 'EVAL'}
              </button>
            </div>
            {ideaResult && (
              <div style={{ borderTop:'1px solid rgba(0,212,255,0.1)', paddingTop:8 }}>
                {scores && (
                  <div style={{ display:'flex', gap:12, marginBottom:8 }}>
                    {Object.entries(scores).map(([k,v]) => (
                      <div key={k} style={{ textAlign:'center' }}>
                        <div style={{ fontFamily:'Orbitron', fontSize:16, fontWeight:700, color: v>=7?'#00ffc8':v>=5?'#ffb900':'#ff6644', textShadow:`0 0 12px ${v>=7?'#00ffc8':v>=5?'#ffb900':'#ff6644'}` }}>{v}</div>
                        <div style={{ ...T.dim, fontSize:7 }}>{ {F:'FEASIB',I:'IMPACT',A:'ALIGN',T:'TIMING'}[k] }</div>
                      </div>
                    ))}
                    <div style={{ marginLeft:'auto', textAlign:'center' }}>
                      <div style={{ fontFamily:'Orbitron', fontSize:16, fontWeight:700, color:'#00d4ff' }}>
                        {scores ? Math.round((scores.F+scores.I+scores.A+scores.T)/4) : '?'}
                      </div>
                      <div style={{ ...T.dim, fontSize:7 }}>AVG</div>
                    </div>
                  </div>
                )}
                <div style={{ ...T.body, fontSize:9, color:'rgba(160,215,255,0.7)', lineHeight:1.6 }}>{verdict}</div>
              </div>
            )}
          </div>

          {/* Decision Engine */}
          <div style={{ ...T.panel, padding:'14px 18px', flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
            <div style={{ ...T.title, marginBottom:10 }}>⬡ PENDING DECISIONS</div>
            <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:6 }}>
              {DECISIONS.map((d,i) => (
                <div key={i} onClick={() => setActiveDecision(activeDecision===i?null:i)}
                  style={{ ...T.panel, padding:'10px 12px', cursor:'pointer', border:`1px solid ${activeDecision===i?'rgba(0,212,255,0.4)':'rgba(0,212,255,0.1)'}` }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
                    <div style={{ ...T.body, fontSize:9, color:'rgba(0,212,255,0.88)', flex:1 }}>{d.q}</div>
                    <div style={{ fontFamily:'Orbitron', fontSize:9, fontWeight:700, color:'#00ffc8', flexShrink:0 }}>{d.conf}%</div>
                  </div>
                  {activeDecision===i && (
                    <div style={{ marginTop:8, paddingTop:8, borderTop:'1px solid rgba(0,212,255,0.1)' }}>
                      <div style={{ ...T.dim, fontSize:8, marginBottom:4 }}>REC:</div>
                      <div style={{ ...T.body, fontSize:9, lineHeight:1.6 }}>{d.rec}</div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right column — Project Tracker */}
        <div style={{ ...T.panel, padding:'14px 18px', display:'flex', flexDirection:'column', overflow:'hidden' }}>
          <div style={{ ...T.title, marginBottom:10 }}>◇ PROJECT TRACKER</div>
          <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:8 }}>
            {PROJECTS.map(p => (
              <div key={p.id} style={{ padding:'10px 12px', background:'rgba(0,4,14,0.6)', borderRadius:2, borderLeft:`3px solid ${p.color}` }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
                  <span style={{ fontFamily:'Orbitron', fontSize:9, fontWeight:700, color:p.color }}>{p.name}</span>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:7, color: p.status==='ACTIVE'?'#00ffc8':p.status==='PAUSED'?'#ffb900':'rgba(0,140,200,0.5)', letterSpacing:1 }}>{p.status}</span>
                </div>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
                  <span style={{ ...T.dim, fontSize:8 }}>{p.phase}</span>
                  <span style={{ ...T.dim, fontSize:8, color: p.priority==='CRITICAL'?'#ff6644':p.priority==='HIGH'?'#ffb900':'rgba(0,140,200,0.5)' }}>{p.priority}</span>
                </div>
                <div style={{ height:3, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'hidden' }}>
                  <div style={{ height:'100%', width:`${p.progress}%`, background:p.color, boxShadow:`0 0 8px ${p.color}`, transition:'width 1s ease', borderRadius:2 }}/>
                </div>
                <div style={{ ...T.dim, fontSize:7, marginTop:3, textAlign:'right' }}>{p.progress}%</div>
              </div>
            ))}
          </div>

          {/* Velocity meter */}
          <div style={{ marginTop:10, paddingTop:10, borderTop:'1px solid rgba(0,212,255,0.1)' }}>
            <div style={{ ...T.dim, marginBottom:6 }}>OPERATIONAL VELOCITY</div>
            <div style={{ display:'flex', gap:8 }}>
              {[
                { label:'FOCUS', val:72, color:'#00d4ff' },
                { label:'OUTPUT', val:85, color:'#00ffc8' },
                { label:'ENERGY', val:64, color:'#ffb900' },
              ].map(m => (
                <div key={m.label} style={{ flex:1, textAlign:'center' }}>
                  <div style={{ fontFamily:'Orbitron', fontSize:14, fontWeight:700, color:m.color }}>{m.val}</div>
                  <div style={{ ...T.dim, fontSize:7 }}>{m.label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
