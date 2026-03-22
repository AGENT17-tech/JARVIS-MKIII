import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const T = {
  panel: { background:'rgba(0,7,22,0.88)', border:'1px solid rgba(0,212,255,0.18)', borderRadius:3, backdropFilter:'blur(6px)', boxShadow:'0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily:'Orbitron', fontSize:9, fontWeight:700, letterSpacing:3.5, color:'rgba(0,200,255,0.9)' },
  dim:   { fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.5)', letterSpacing:1 },
  body:  { fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.85)', lineHeight:1.7 },
}

const FEED = [
  { id:1,  cat:'TECH',        headline:'Meta releases Llama 3.3 with improved reasoning and 70B weights',                                   time:'14:32', summary:'New model surpasses prior benchmarks on MMLU and HumanEval. Supports 128K context window natively.' },
  { id:2,  cat:'SCIENCE',     headline:'CERN reports anomalous particle behaviour at 13.6 TeV collision energy',                             time:'13:18', summary:'Physicists observe unexpected quantum interactions at the LHC suggesting a potential new force mediator.' },
  { id:3,  cat:'GEOPOLITICS', headline:'G7 nations agree on joint AI safety framework for frontier model deployment',                        time:'12:45', summary:'Framework mandates red-teaming and incident reporting for models above 10^26 FLOPs training compute.' },
  { id:4,  cat:'FINANCE',     headline:'Egypt central bank holds interest rate at 27.25% amid inflation concerns',                          time:'11:54', summary:'MPC cites sticky core inflation and currency stabilisation as primary considerations for the hold.' },
  { id:5,  cat:'TECH',        headline:'Google DeepMind publishes AlphaFold 3 open weights for non-commercial research',                   time:'10:20', summary:'Full model weights released under CC-BY-NC 4.0. Covers proteins, DNA, RNA, and small molecules.' },
  { id:6,  cat:'WORLD',       headline:'UN Security Council votes on resolution addressing autonomous weapons systems',                      time:'09:35', summary:'Resolution calls for international moratorium on fully autonomous lethal systems pending treaty negotiations.' },
  { id:7,  cat:'SCIENCE',     headline:'MIT develops room-temperature superconductor composite with 0.12% efficiency loss',                  time:'08:50', summary:'Material operates at 22°C under 1.4 GPa pressure. Potential applications in power transmission and MRI.' },
  { id:8,  cat:'FINANCE',     headline:'Bitcoin ETF inflows exceed $800M in single trading session',                                        time:'08:12', summary:'Institutional demand continues following regulatory clarity. Options market showing strong call skew.' },
  { id:9,  cat:'TECH',        headline:'OpenAI o3 pro mode benchmark results leaked ahead of official release',                             time:'07:40', summary:'Internal scores suggest significant leap on ARC-AGI and FrontierMath relative to o1 and o3 standard.' },
  { id:10, cat:'WORLD',       headline:'Cairo ranked top emerging tech hub in Africa by Global Startup Ecosystem Report 2025',              time:'07:00', summary:'Report cites growing AI talent pool, government investment in digital infrastructure, and fintech growth.' },
  { id:11, cat:'GEOPOLITICS', headline:'BRICS nations announce common payment rail bypassing SWIFT for member states',                      time:'06:22', summary:'System will go live Q3 2026. Covers $4.7T in annual trade volume across the bloc.' },
  { id:12, cat:'SCIENCE',     headline:'James Webb telescope confirms water vapour in atmosphere of K2-18b super-Earth',                    time:'05:50', summary:'Finding strengthens case for habitability. Follow-up with ELT expected to begin late 2026.' },
]

const CAT_COLOR = { TECH:'#00d4ff', SCIENCE:'#00ffc8', FINANCE:'#ffb900', WORLD:'#aa88ff', GEOPOLITICS:'#ff6644' }
const CAT_ICON  = { TECH:'⬡', SCIENCE:'◈', FINANCE:'◎', WORLD:'◇', GEOPOLITICS:'⚡' }
const CATS      = ['ALL', 'TECH', 'SCIENCE', 'FINANCE', 'WORLD', 'GEOPOLITICS']

export default function IntelTab() {
  const [filter,   setFilter]   = useState('ALL')
  const [briefing, setBriefing] = useState('Analysing global intelligence feeds...')
  const [loading,  setLoading]  = useState(true)
  const [refresh,  setRefresh]  = useState(0)

  useEffect(() => {
    setLoading(true)
    setBriefing('Analysing global intelligence feeds...')
    fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: 'Give me exactly 3 headline intelligence items, one sentence each. Format: "1. [TECH/GEO/SCI]: sentence. 2. [TECH/GEO/SCI]: sentence. 3. [TECH/GEO/SCI]: sentence." No preamble.',
        session_id: 'hud-tab-intel-' + Date.now(),
      }),
    })
      .then(r => r.json())
      .then(d => setBriefing(d.response || 'Intel feeds nominal. No critical advisories.'))
      .catch(() => setBriefing('Intel feed uplink degraded, sir. Cached data displayed.'))
      .finally(() => setLoading(false))
  }, [refresh])

  const displayed = filter === 'ALL' ? FEED : FEED.filter(i => i.cat === filter)

  return (
    <div style={{ height:'100%', overflow:'hidden', padding:'10px 14px', display:'flex', flexDirection:'column', gap:10 }}>

      {/* Daily brief */}
      <div style={{ ...T.panel, padding:'12px 18px', flexShrink:0, display:'flex', alignItems:'flex-start', gap:14 }}>
        <div style={{ flexShrink:0 }}>
          <div style={{ ...T.title, marginBottom:6 }}>◈ DAILY INTEL BRIEF</div>
          <div style={{ display:'flex', gap:6 }}>
            <div style={{ width:5, height:5, borderRadius:'50%', background: loading ? '#ffb900' : '#00ffc8', boxShadow:`0 0 7px ${loading ? '#ffb900' : '#00ffc8'}`, marginTop:4, animation: loading ? 'blink 0.8s ease-in-out infinite' : 'none', flexShrink:0 }}/>
            <div style={{ ...T.body, flex:1 }}>{briefing}</div>
          </div>
        </div>
        <button onClick={() => setRefresh(r => r+1)} style={{ marginLeft:'auto', flexShrink:0, background:'none', border:'1px solid rgba(0,212,255,0.25)', borderRadius:3, color:'rgba(0,212,255,0.6)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'4px 10px', cursor:'pointer' }}
          onMouseEnter={e => e.currentTarget.style.borderColor='rgba(0,212,255,0.7)'}
          onMouseLeave={e => e.currentTarget.style.borderColor='rgba(0,212,255,0.25)'}
        >⟳ REFRESH</button>
      </div>

      {/* Category filter */}
      <div style={{ display:'flex', gap:5, flexShrink:0 }}>
        {CATS.map(c => {
          const active = filter === c
          return (
            <div key={c} onClick={() => setFilter(c)} style={{
              fontFamily:'Orbitron', fontSize:7, fontWeight:700, letterSpacing:2,
              padding:'4px 11px', cursor:'pointer', borderRadius:2,
              border:`1px solid ${active ? (CAT_COLOR[c] || 'rgba(0,212,255,0.7)') : 'rgba(0,212,255,0.14)'}`,
              background: active ? `${CAT_COLOR[c] || 'rgba(0,212,255,1)'}18` : 'transparent',
              color: active ? (CAT_COLOR[c] || 'rgba(0,212,255,0.95)') : 'rgba(0,140,200,0.4)',
              transition:'all 0.18s ease',
            }}>{c}</div>
          )
        })}
        <div style={{ marginLeft:'auto', ...T.dim, fontSize:8, display:'flex', alignItems:'center', gap:4 }}>
          <div style={{ width:4, height:4, borderRadius:'50%', background:'#00ffc8', animation:'blink 2s ease-in-out infinite' }}/>
          LIVE · {displayed.length} ITEMS
        </div>
      </div>

      {/* Cards grid */}
      <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, alignContent:'start' }}>
        {displayed.map(item => <NewsCard key={item.id} item={item}/>)}
      </div>
    </div>
  )
}

function NewsCard({ item }) {
  const c = CAT_COLOR[item.cat] || '#00d4ff'
  return (
    <div style={{
      ...T.panel, borderLeft:`2px solid ${c}`, padding:'12px 14px',
      display:'flex', flexDirection:'column', gap:8, cursor:'pointer',
      transition:'border-color 0.2s ease, box-shadow 0.2s ease',
    }}
      onMouseEnter={e => { e.currentTarget.style.borderColor=`${c}88`; e.currentTarget.style.boxShadow=`0 0 18px ${c}18` }}
      onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(0,212,255,0.18)'; e.currentTarget.style.boxShadow='0 0 22px rgba(0,80,180,0.08)' }}
    >
      {/* Image placeholder */}
      <div style={{ height:72, background:`linear-gradient(135deg,rgba(0,20,45,0.9),rgba(0,8,22,0.95))`, borderRadius:2, border:`1px solid ${c}22`, display:'flex', alignItems:'center', justifyContent:'center' }}>
        <span style={{ fontSize:28, opacity:0.35 }}>{CAT_ICON[item.cat] || '◇'}</span>
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <span style={{ fontFamily:'Orbitron', fontSize:7, fontWeight:700, letterSpacing:2, color:c }}>{item.cat}</span>
        <span style={{ ...T.dim, fontSize:8 }}>{item.time}</span>
      </div>
      <div style={{ fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(0,212,255,0.92)', lineHeight:1.5, letterSpacing:0.2 }}>{item.headline}</div>
      <div style={{ fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.58)', lineHeight:1.6 }}>{item.summary}</div>
    </div>
  )
}
