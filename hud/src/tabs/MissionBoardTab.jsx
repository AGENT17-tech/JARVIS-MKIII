import { useState } from 'react'
import MissionBoard from '../MissionBoard'

const T = {
  panel: { background:'rgba(0,7,22,0.88)', border:'1px solid rgba(0,212,255,0.18)', borderRadius:3, backdropFilter:'blur(6px)', boxShadow:'0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily:'Orbitron', fontSize:9, fontWeight:700, letterSpacing:3.5, color:'rgba(0,200,255,0.9)' },
  dim:   { fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.5)', letterSpacing:1 },
  body:  { fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.85)', lineHeight:1.7 },
}

const METRICS = [
  { label:'PULL-UPS',    val:'12',  unit:'reps',  target:'15',  color:'#00ffc8', progress:80 },
  { label:'PUSH-UPS',   val:'45',  unit:'reps',  target:'60',  color:'#00d4ff', progress:75 },
  { label:'RUN',        val:'4.2', unit:'km',    target:'5.0', color:'#ffb900', progress:84 },
  { label:'WEIGHT',     val:'72',  unit:'kg',    target:'75',  color:'#aa88ff', progress:96 },
  { label:'SLEEP',      val:'6.5', unit:'hrs',   target:'8.0', color:'#ff6644', progress:81 },
  { label:'WATER',      val:'1.8', unit:'L',     target:'3.0', color:'#00ffc8', progress:60 },
]

const IEEE_MILESTONES = [
  { label:'Topic finalised',     done:true  },
  { label:'Literature review',   done:true  },
  { label:'Methodology drafted', done:true  },
  { label:'Experiments run',     done:false },
  { label:'Results section',     done:false },
  { label:'Full draft complete', done:false },
  { label:'Internal review',     done:false },
  { label:'Submission',          done:false },
]

const ENACTUS_MILESTONES = [
  { label:'Team assembled',      done:true  },
  { label:'Problem identified',  done:true  },
  { label:'Solution prototype',  done:false },
  { label:'Pilot test',          done:false },
  { label:'Impact measurement',  done:false },
  { label:'Regional pitch',      done:false },
]

export default function MissionBoardTab() {
  const [activeSection, setActiveSection] = useState('phantom')

  const doneIEEE = IEEE_MILESTONES.filter(m => m.done).length
  const doneEnactus = ENACTUS_MILESTONES.filter(m => m.done).length

  return (
    <div style={{ height:'100%', overflow:'hidden', padding:'10px 14px', display:'flex', flexDirection:'column', gap:10 }}>

      {/* Section tabs */}
      <div style={{ display:'flex', gap:5, flexShrink:0 }}>
        {[
          { key:'phantom', label:'PHANTOM ZERO' },
          { key:'fitness', label:'FITNESS' },
          { key:'ieee',    label:'IEEE' },
          { key:'enactus', label:'ENACTUS' },
        ].map(s => (
          <div key={s.key} onClick={() => setActiveSection(s.key)}
            style={{
              fontFamily:'Orbitron', fontSize:7, fontWeight:700, letterSpacing:2,
              padding:'5px 12px', cursor:'pointer', borderRadius:2,
              border:`1px solid ${activeSection===s.key?'rgba(0,212,255,0.7)':'rgba(0,212,255,0.14)'}`,
              background: activeSection===s.key?'rgba(0,212,255,0.12)':'transparent',
              color: activeSection===s.key?'rgba(0,212,255,0.95)':'rgba(0,140,200,0.4)',
              transition:'all 0.18s ease',
            }}>{s.label}</div>
        ))}
      </div>

      {/* PHANTOM ZERO — mission board */}
      {activeSection === 'phantom' && (
        <div style={{ flex:1, overflow:'hidden' }}>
          <MissionBoard/>
        </div>
      )}

      {/* FITNESS */}
      {activeSection === 'fitness' && (
        <div style={{ flex:1, overflow:'auto', scrollbarWidth:'none', display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, alignContent:'start' }}>
          {METRICS.map(m => (
            <div key={m.label} style={{ ...T.panel, padding:'14px 16px' }}>
              <div style={{ ...T.title, marginBottom:4, fontSize:8 }}>{m.label}</div>
              <div style={{ display:'flex', alignItems:'baseline', gap:4, marginBottom:8 }}>
                <span style={{ fontFamily:'Orbitron', fontSize:28, fontWeight:700, color:m.color, textShadow:`0 0 18px ${m.color}` }}>{m.val}</span>
                <span style={{ ...T.dim, fontSize:8 }}>{m.unit}</span>
              </div>
              <div style={{ height:3, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'hidden', marginBottom:4 }}>
                <div style={{ height:'100%', width:`${m.progress}%`, background:m.color, boxShadow:`0 0 8px ${m.color}`, borderRadius:2 }}/>
              </div>
              <div style={{ display:'flex', justifyContent:'space-between' }}>
                <span style={{ ...T.dim, fontSize:7 }}>TODAY</span>
                <span style={{ ...T.dim, fontSize:7 }}>TARGET: {m.target} {m.unit}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* IEEE */}
      {activeSection === 'ieee' && (
        <div style={{ flex:1, overflow:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:10 }}>
          <div style={{ ...T.panel, padding:'14px 18px' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
              <div style={{ ...T.title }}>IEEE PAPER — PROGRESS</div>
              <div style={{ fontFamily:'Orbitron', fontSize:18, fontWeight:700, color:'#00d4ff' }}>
                {Math.round(doneIEEE/IEEE_MILESTONES.length*100)}%
              </div>
            </div>
            <div style={{ height:4, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'hidden', marginBottom:14 }}>
              <div style={{ height:'100%', width:`${doneIEEE/IEEE_MILESTONES.length*100}%`, background:'#00d4ff', boxShadow:'0 0 10px #00d4ff', borderRadius:2 }}/>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {IEEE_MILESTONES.map((m,i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <div style={{ width:14, height:14, borderRadius:'50%', border:`2px solid ${m.done?'#00ffc8':'rgba(0,212,255,0.2)'}`, background:m.done?'#00ffc8':'transparent', flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
                    {m.done && <span style={{ fontSize:8, color:'#000' }}>✓</span>}
                  </div>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:10, color: m.done?'rgba(0,255,200,0.9)':'rgba(0,140,200,0.5)', textDecoration: m.done?'line-through':'none' }}>{m.label}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ ...T.panel, padding:'14px 18px' }}>
            <div style={{ ...T.title, marginBottom:8 }}>PAPER ABSTRACT (DRAFT)</div>
            <div style={{ ...T.body, fontSize:9, color:'rgba(0,140,200,0.55)', lineHeight:1.7, fontStyle:'italic' }}>
              This paper investigates [topic]. We propose [methodology] and demonstrate [result] on [dataset/benchmark].
              Results show [key finding], outperforming baselines by [X]%. Applications include [domain].
              Full abstract pending experimental completion.
            </div>
          </div>
        </div>
      )}

      {/* ENACTUS */}
      {activeSection === 'enactus' && (
        <div style={{ flex:1, overflow:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:10 }}>
          <div style={{ ...T.panel, padding:'14px 18px' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
              <div style={{ ...T.title }}>ENACTUS — PROGRESS</div>
              <div style={{ fontFamily:'Orbitron', fontSize:18, fontWeight:700, color:'#00ffc8' }}>
                {Math.round(doneEnactus/ENACTUS_MILESTONES.length*100)}%
              </div>
            </div>
            <div style={{ height:4, background:'rgba(0,212,255,0.1)', borderRadius:2, overflow:'hidden', marginBottom:14 }}>
              <div style={{ height:'100%', width:`${doneEnactus/ENACTUS_MILESTONES.length*100}%`, background:'#00ffc8', boxShadow:'0 0 10px #00ffc8', borderRadius:2 }}/>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {ENACTUS_MILESTONES.map((m,i) => (
                <div key={i} style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <div style={{ width:14, height:14, borderRadius:'50%', border:`2px solid ${m.done?'#00ffc8':'rgba(0,212,255,0.2)'}`, background:m.done?'#00ffc8':'transparent', flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
                    {m.done && <span style={{ fontSize:8, color:'#000' }}>✓</span>}
                  </div>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:10, color: m.done?'rgba(0,255,200,0.9)':'rgba(0,140,200,0.5)', textDecoration: m.done?'line-through':'none' }}>{m.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
