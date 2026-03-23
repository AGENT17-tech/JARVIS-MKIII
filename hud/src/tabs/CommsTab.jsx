import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const T = {
  panel: { background:'rgba(0,7,22,0.88)', border:'1px solid rgba(0,212,255,0.18)', borderRadius:3, backdropFilter:'blur(6px)', boxShadow:'0 0 22px rgba(0,80,180,0.08)' },
  title: { fontFamily:'Orbitron', fontSize:9, fontWeight:700, letterSpacing:3.5, color:'rgba(0,200,255,0.9)' },
  dim:   { fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,140,200,0.5)', letterSpacing:1 },
  body:  { fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.85)', lineHeight:1.7 },
}

// Sample data — replace with real API calls when integrations are ready
const EMAILS = [
  { id:1, from:'IEEE Notifications',   subject:'Your submission deadline is approaching',  time:'09:14', unread:true,  priority:'HIGH',   tag:'IEEE'    },
  { id:2, from:'GitHub',               subject:'New issue opened: voice pipeline dropout',  time:'08:50', unread:true,  priority:'MEDIUM', tag:'JARVIS'  },
  { id:3, from:'Enactus Egypt',        subject:'Regional round registration now open',       time:'07:22', unread:false, priority:'HIGH',   tag:'ENACTUS' },
  { id:4, from:'Coursera',             subject:'Certificate: Generative AI with LLMs',       time:'Yesterday', unread:false, priority:'LOW', tag:'LEARNING' },
  { id:5, from:'Dr. Ahmed Sayed',      subject:'RE: Research supervision — follow up',      time:'2d ago', unread:false, priority:'MEDIUM', tag:'IEEE'    },
]

const DISCORD_MSGS = [
  { server:'JARVIS Dev', channel:'general',  user:'System', msg:'Voice pipeline up 99.1% uptime this week', time:'11m' },
  { server:'IEEE Egypt', channel:'collab',   user:'@Nour',  msg:'Did you get the template from last year\'s winners?', time:'44m' },
  { server:'Enactus',    channel:'team',     user:'@Layla', msg:'Prototype demo scheduled for Thursday', time:'2h'  },
]

const TAG_COLORS = { IEEE:'#00d4ff', JARVIS:'#00ffc8', ENACTUS:'#ffb900', LEARNING:'#aa88ff' }
const PRIORITY_COLORS = { HIGH:'#ff6644', MEDIUM:'#ffb900', LOW:'rgba(0,140,200,0.45)' }

export default function CommsTab() {
  const [activeEmail, setActiveEmail]   = useState(null)
  const [summary, setSummary]           = useState(null)
  const [summarising, setSummarising]   = useState(false)
  const [calEvents, setCalEvents]       = useState([])
  const [calError, setCalError]         = useState(null)
  const [calConfigured, setCalConfigured] = useState(true)
  const [calLoading, setCalLoading]     = useState(true)

  // Fetch Google Calendar events on mount and every 5 minutes
  useEffect(() => {
    const fetchCalendar = async () => {
      try {
        const res  = await fetch(`${API}/gcal/events`)
        const data = await res.json()
        setCalEvents(data.events || [])
        setCalError(data.error || null)
        setCalConfigured(data.configured !== false)
      } catch {
        setCalError('Backend offline')
        setCalEvents([])
      } finally {
        setCalLoading(false)
      }
    }
    fetchCalendar()
    const id = setInterval(fetchCalendar, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [])

  const summariseInbox = async () => {
    setSummarising(true)
    setSummary(null)
    try {
      const subjects = EMAILS.map(e => `• [${e.tag}] ${e.subject} — from ${e.from}`).join('\n')
      const res = await fetch(`${API}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: `Summarise this inbox for a focused tech entrepreneur. Prioritise actions needed. Be terse, 2-3 sentences max:\n${subjects}`,
          session_id: 'hud-tab-comms-' + Date.now(),
        }),
      })
      const d = await res.json()
      setSummary(d.response || 'Summary unavailable.')
    } catch {
      setSummary('Backend offline, sir.')
    } finally {
      setSummarising(false)
    }
  }

  const unreadCount = EMAILS.filter(e => e.unread).length

  // Determine which calendar events are upcoming vs past
  const now = new Date()
  const isEventPast = (timeStr) => {
    if (!timeStr || timeStr === 'All day') return false
    const [h, m] = timeStr.split(':').map(Number)
    return now.getHours() > h || (now.getHours() === h && now.getMinutes() > m)
  }

  // Find the next upcoming event
  const nextEvent = calEvents.find(e => !isEventPast(e.time) && e.time !== 'All day')

  return (
    <div style={{ height:'100%', overflow:'hidden', padding:'10px 14px', display:'grid', gridTemplateColumns:'1fr 300px', gap:10 }}>

      {/* Left — Email + Discord */}
      <div style={{ display:'flex', flexDirection:'column', gap:10, overflow:'hidden' }}>

        {/* Email panel */}
        <div style={{ ...T.panel, padding:'14px 18px', flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ ...T.title }}>◈ INBOX</div>
              {unreadCount > 0 && (
                <div style={{ fontFamily:'Orbitron', fontSize:8, color:'#000', background:'#ff6644', borderRadius:10, padding:'1px 6px', fontWeight:700 }}>{unreadCount}</div>
              )}
            </div>
            <button onClick={summariseInbox} disabled={summarising}
              style={{ background:'none', border:'1px solid rgba(0,212,255,0.25)', borderRadius:2, color:'rgba(0,212,255,0.6)', fontFamily:'Orbitron', fontSize:7, letterSpacing:2, padding:'4px 10px', cursor:'pointer' }}>
              {summarising ? '...' : '⬡ BRIEF'}
            </button>
          </div>

          {summary && (
            <div style={{ ...T.body, fontSize:9, padding:'8px 12px', background:'rgba(0,212,255,0.04)', borderRadius:2, border:'1px solid rgba(0,212,255,0.12)', marginBottom:10, lineHeight:1.7 }}>
              {summary}
            </div>
          )}

          <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:4 }}>
            {EMAILS.map(e => (
              <div key={e.id} onClick={() => setActiveEmail(activeEmail===e.id?null:e.id)}
                style={{ padding:'9px 12px', borderRadius:2, cursor:'pointer', transition:'all 0.15s ease',
                  background: e.unread?'rgba(0,212,255,0.04)':'transparent',
                  border:`1px solid ${activeEmail===e.id?'rgba(0,212,255,0.4)':e.unread?'rgba(0,212,255,0.12)':'rgba(0,212,255,0.05)'}` }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:2 }}>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:10, color: e.unread?'rgba(0,212,255,0.95)':'rgba(0,140,200,0.55)', fontWeight: e.unread?'bold':'normal' }}>
                    {e.from}
                  </span>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <span style={{ fontFamily:'Share Tech Mono', fontSize:7, color: PRIORITY_COLORS[e.priority] }}>{e.priority}</span>
                    <span style={{ ...T.dim, fontSize:7 }}>{e.time}</span>
                  </div>
                </div>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(160,215,255,0.65)', flex:1, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis', paddingRight:8 }}>{e.subject}</span>
                  <span style={{ fontFamily:'Orbitron', fontSize:6, color: TAG_COLORS[e.tag]||'#00d4ff', background:`${TAG_COLORS[e.tag]||'#00d4ff'}18`, borderRadius:2, padding:'1px 5px', letterSpacing:1, flexShrink:0 }}>{e.tag}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Discord panel */}
        <div style={{ ...T.panel, padding:'14px 18px', flexShrink:0 }}>
          <div style={{ ...T.title, marginBottom:10 }}>⬡ DISCORD</div>
          <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
            {DISCORD_MSGS.map((m,i) => (
              <div key={i} style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                <div style={{ flexShrink:0 }}>
                  <div style={{ fontFamily:'Orbitron', fontSize:7, color:'rgba(0,212,255,0.45)', letterSpacing:1 }}>{m.server}</div>
                  <div style={{ ...T.dim, fontSize:7, color:'rgba(0,140,200,0.35)' }}>#{m.channel}</div>
                </div>
                <div style={{ flex:1, minWidth:0 }}>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:8, color:'#00ffc8' }}>{m.user}: </span>
                  <span style={{ fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(160,215,255,0.7)' }}>{m.msg}</span>
                </div>
                <span style={{ ...T.dim, fontSize:7, flexShrink:0 }}>{m.time}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop:8, paddingTop:8, borderTop:'1px solid rgba(0,212,255,0.08)', display:'flex', alignItems:'center', gap:6 }}>
            <div style={{ width:5, height:5, borderRadius:'50%', background:'rgba(0,140,200,0.3)' }}/>
            <span style={{ ...T.dim, fontSize:8 }}>INTEGRATION PENDING — READ-ONLY</span>
          </div>
        </div>
      </div>

      {/* Right — Calendar */}
      <div style={{ ...T.panel, padding:'14px 18px', display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:6 }}>
          <div style={{ ...T.title }}>◇ TODAY'S SCHEDULE</div>
          {/* Live indicator */}
          {calConfigured && !calError && (
            <div style={{ display:'flex', alignItems:'center', gap:4 }}>
              <div style={{ width:5, height:5, borderRadius:'50%', background:'#00ffc8', boxShadow:'0 0 6px #00ffc8' }}/>
              <span style={{ fontFamily:'Orbitron', fontSize:6, color:'rgba(0,255,200,0.6)', letterSpacing:1 }}>LIVE</span>
            </div>
          )}
        </div>

        <div style={{ ...T.dim, marginBottom:12, fontSize:8 }}>
          {now.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'})}
        </div>

        {/* Next event highlight */}
        {nextEvent && (
          <div style={{ marginBottom:10, padding:'8px 10px', background:'rgba(0,255,200,0.04)', borderRadius:2, border:'1px solid rgba(0,255,200,0.15)' }}>
            <div style={{ fontFamily:'Orbitron', fontSize:6, color:'rgba(0,255,200,0.55)', letterSpacing:1.5, marginBottom:3 }}>NEXT EVENT</div>
            <div style={{ fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(0,255,200,0.9)' }}>{nextEvent.title}</div>
            <div style={{ fontFamily:'Share Tech Mono', fontSize:8, color:'rgba(0,212,255,0.5)', marginTop:2 }}>{nextEvent.time}{nextEvent.location ? ` · ${nextEvent.location}` : ''}</div>
          </div>
        )}

        {/* Event list */}
        <div style={{ flex:1, overflowY:'auto', scrollbarWidth:'none', display:'flex', flexDirection:'column', gap:6 }}>
          {calLoading ? (
            <div style={{ ...T.dim, fontSize:8, textAlign:'center', marginTop:20 }}>SYNCING...</div>
          ) : !calConfigured ? (
            <div style={{ padding:'10px 0' }}>
              <div style={{ ...T.dim, fontSize:8, color:'rgba(255,90,60,0.7)', marginBottom:4 }}>NOT CONFIGURED</div>
              <div style={{ fontFamily:'Share Tech Mono', fontSize:8, color:'rgba(160,215,255,0.5)', lineHeight:1.6 }}>
                Place credentials.json in backend/config/ to enable Google Calendar.
              </div>
            </div>
          ) : calError ? (
            <div style={{ ...T.dim, fontSize:8, color:'rgba(255,90,60,0.6)', marginTop:10 }}>
              ERROR: {calError.slice(0,60)}
            </div>
          ) : calEvents.length === 0 ? (
            <div style={{ ...T.dim, fontSize:9, textAlign:'center', marginTop:20, color:'rgba(0,212,255,0.35)' }}>
              No events today
            </div>
          ) : (
            calEvents.map((e, i) => {
              const past = isEventPast(e.time)
              return (
                <div key={e.id || i} style={{ display:'flex', gap:10, alignItems:'flex-start', opacity: past ? 0.4 : 1, transition:'opacity 0.3s' }}>
                  <div style={{ flexShrink:0, textAlign:'right', minWidth:44 }}>
                    <div style={{ fontFamily:'Share Tech Mono', fontSize:9, color:'rgba(0,212,255,0.6)' }}>{e.time}</div>
                  </div>
                  <div style={{ width:2, alignSelf:'stretch', background: e.color || '#00d4ff', flexShrink:0, borderRadius:1 }}/>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontFamily:'Share Tech Mono', fontSize:10, color:'rgba(160,215,255,0.88)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{e.title}</div>
                    <div style={{ display:'flex', gap:6, marginTop:2, alignItems:'center' }}>
                      <div style={{ fontFamily:'Orbitron', fontSize:6, color: e.color || '#00d4ff', letterSpacing:1.5 }}>{e.type}</div>
                      {e.location && (
                        <div style={{ fontFamily:'Share Tech Mono', fontSize:7, color:'rgba(0,140,200,0.5)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:110 }}>
                          {e.location}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Status footer */}
        <div style={{ marginTop:10, paddingTop:10, borderTop:'1px solid rgba(0,212,255,0.1)' }}>
          {calConfigured && !calError ? (
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ ...T.dim, fontSize:7, color:'rgba(0,255,200,0.45)' }}>
                GOOGLE CALENDAR CONNECTED
              </div>
              <div style={{ fontFamily:'Orbitron', fontSize:7, color:'rgba(0,212,255,0.45)' }}>
                {calEvents.length} EVENTS
              </div>
            </div>
          ) : (
            <div style={{ padding:'6px 10px', background:'rgba(0,212,255,0.04)', borderRadius:2, border:'1px solid rgba(0,212,255,0.08)' }}>
              <div style={{ ...T.dim, fontSize:7 }}>CALENDAR SYNC</div>
              <div style={{ ...T.dim, fontSize:7, color: calConfigured ? 'rgba(255,90,60,0.6)' : 'rgba(255,150,60,0.6)', marginTop:2 }}>
                {calConfigured ? 'Auth error — check token' : 'Google Calendar integration pending'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
