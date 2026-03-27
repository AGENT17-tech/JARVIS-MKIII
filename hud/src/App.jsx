import { useState, useEffect, useRef, useCallback } from 'react'
import './App.css'
import NetworkLinks from './components/NetworkLinks'
import WorldStatePanel from './WorldStatePanel'
import AgentFeed from './AgentFeed'
import AutonomousAlerts from './AutonomousAlerts'
import CalendarWeatherPanel from './CalendarWeatherPanel'
import GlobeNetwork from './components/GlobeNetwork'
import ProactiveNotifications from './ProactiveNotifications'
import IntelTab from './tabs/IntelTab'
import StrategyTab from './tabs/StrategyTab'
import MissionBoardTab from './tabs/MissionBoardTab'
import LifeOSTab from './tabs/LifeOSTab'
import CommsTab from './tabs/CommsTab'
import WhatsAppTab from './tabs/WhatsAppTab'
import VisionTab from './tabs/VisionTab'
import ProactiveTab from './tabs/ProactiveTab'
import MemoryTab from './tabs/MemoryTab'

const TABS = [
  { key:'BRIDGE',   label:'BRIDGE'   },
  { key:'INTEL',    label:'INTEL'    },
  { key:'STRATEGY', label:'STRATEGY' },
  { key:'MISSIONS', label:'MISSIONS' },
  { key:'LIFE OS',  label:'LIFE OS'  },
  { key:'COMMS',    label:'COMMS'    },
  { key:'WHATSAPP',   label:'WHATSAPP'   },
  { key:'VISION',     label:'VISION'     },
  { key:'PROACTIVE',  label:'PROACTIVE'  },
  { key:'MEMORY',     label:'MEMORY'     },
]

const BOOT_STEPS = [
  { key: 'scanline',   delay: 400  },
  { key: 'reactor',    delay: 900  },
  { key: 'title',      delay: 1400 },
  { key: 'corners',    delay: 1800 },
  { key: 'panelTL',    delay: 2200 },
  { key: 'panelTR',    delay: 2500 },
  { key: 'panelBR',    delay: 3400 },
  { key: 'cairo',      delay: 3700 },
  { key: 'github',     delay: 3900 },
  { key: 'ticker',     delay: 4200 },
  { key: 'ready',      delay: 4400 },
]

const API = 'http://localhost:8000'
const SESSION_ID = 'hud-' + Math.random().toString(36).slice(2, 9)

// ── Alert ticker — inline grid row ────────────────────────────────────────────
const AlertTicker = ({ visible }) => {
  const items = [
    '◈ ALL SYSTEMS NOMINAL','⬡ POWER CORE: 100%','◈ PERIMETER: SECURE','⬡ UPLINK: ESTABLISHED',
    '◈ AI CORE: MKIII ONLINE','⬡ THREAT LEVEL: MINIMAL','◈ MEMORY BANKS: ACTIVE','⬡ ENCRYPTION: AES-256',
    '◈ NETWORK: SECURE','⬡ FIRMWARE: CURRENT','◈ BIOMETRICS: VERIFIED','⬡ AGENT17-TECH AUTH OK',
    '◈ HINDSIGHT: CONNECTED','⬡ VAULT: ENCRYPTED','◈ SANDBOX: ENFORCED','⬡ SENSORS: 4 ACTIVE',
    '◈ SCHEDULER: 9 TRIGGERS','⬡ AGENTS: 6 ONLINE','◈ MKIII: PHASE 4 COMPLETE',
    '◈ LLAMA3.2: ACTIVE','⬡ BRITISH VOICE: bm_george','◈ WHISPER: CUDA ONLINE','⬡ KOKORO-82M: TTS ACTIVE',
  ]
  const text = items.join('   //   ') + '   //   ' + items.join('   //   ')
  return (
    <div style={{
      height: '100%', width: '100%',
      background: 'rgba(0,4,14,0.97)',
      borderTop: '1px solid rgba(0,212,255,0.18)',
      overflow: 'hidden',
      opacity: visible ? 1 : 0,
      transition: 'opacity 1s ease',
      display: 'flex',
      alignItems: 'center',
    }}>
      <div style={{flexShrink:0,height:'100%',background:'rgba(0,212,255,0.07)',borderRight:'1px solid rgba(0,212,255,0.18)',display:'flex',alignItems:'center',padding:'0 14px',fontFamily:'Orbitron',fontSize:8,fontWeight:700,color:'rgba(0,212,255,0.92)',letterSpacing:2.5,whiteSpace:'nowrap'}}>SYS FEED</div>
      <div style={{overflow:'hidden',flex:1,height:'100%',display:'flex',alignItems:'center'}}>
        <div style={{display:'inline-block',whiteSpace:'nowrap',fontFamily:'Share Tech Mono',fontSize:9,color:'rgba(0,185,255,0.68)',letterSpacing:1.5,animation:'tickerScroll 42s linear infinite'}}>{text}</div>
      </div>
      <div style={{flexShrink:0,height:'100%',borderLeft:'1px solid rgba(0,212,255,0.18)',display:'flex',alignItems:'center',padding:'0 14px',gap:6}}>
        <div style={{width:5,height:5,borderRadius:'50%',background:'#00ffc8',boxShadow:'0 0 7px #00ffc8',animation:'blink 2s ease-in-out infinite'}}/>
        <span style={{fontFamily:'Share Tech Mono',fontSize:8,color:'#00ffc8',letterSpacing:1.5}}>LIVE</span>
      </div>
    </div>
  )
}

// ── Corner brackets ────────────────────────────────────────────────────────────
const Corner = ({ pos }) => {
  const sz=50, th=2, c='rgba(0,212,255,0.65)'
  const p = {
    topLeft:     { top:14,  left:14,  borderTop:`${th}px solid ${c}`,    borderLeft:`${th}px solid ${c}`  },
    topRight:    { top:14,  right:14, borderTop:`${th}px solid ${c}`,    borderRight:`${th}px solid ${c}` },
    bottomLeft:  { bottom:30,left:14, borderBottom:`${th}px solid ${c}`, borderLeft:`${th}px solid ${c}`  },
    bottomRight: { bottom:30,right:14,borderBottom:`${th}px solid ${c}`, borderRight:`${th}px solid ${c}` },
  }
  return <div style={{position:'fixed',width:sz,height:sz,animation:'cornerPulse 3s ease-in-out infinite',...p[pos]}}/>
}

// ── Shared styles ──────────────────────────────────────────────────────────────
const S = {
  grid:      { position:'fixed',inset:0,backgroundImage:'linear-gradient(rgba(0,160,255,0.028) 1px,transparent 1px),linear-gradient(90deg,rgba(0,160,255,0.028) 1px,transparent 1px)',backgroundSize:'44px 44px',pointerEvents:'none' },
  scanlines: { position:'fixed',inset:0,background:'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.052) 2px,rgba(0,0,0,0.052) 4px)',pointerEvents:'none' },
  vignette:  { position:'fixed',inset:0,background:'radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,0.6) 100%)',pointerEvents:'none' },
  bootScanline: { position:'fixed',left:0,right:0,height:4,background:'linear-gradient(90deg,transparent,#00d4ff,transparent)',boxShadow:'0 0 24px #00d4ff,0 0 48px rgba(0,212,255,0.4)',animation:'bootScan 0.9s ease-in forwards',zIndex:100 },
  panelTitle: { fontFamily:'Orbitron',fontSize:9,fontWeight:700,letterSpacing:3.5,color:'rgba(0,200,255,0.9)',marginBottom:13,textShadow:'0 0 12px rgba(0,200,255,0.35)' },
  dimText:    { fontFamily:'Share Tech Mono',fontSize:10,color:'rgba(0,140,200,0.52)',letterSpacing:1.2 },
  divider:    { width:'100%',height:1,background:'linear-gradient(90deg,transparent,rgba(0,212,255,0.2),transparent)',margin:'11px 0' },
  chatLog:    { display:'flex',flexDirection:'column',gap:10,minHeight:100,maxHeight:170,overflowY:'auto',scrollbarWidth:'none' },
  chatMessage:{ display:'flex',gap:8,alignItems:'flex-start' },
  chatLabel:  { fontFamily:'Orbitron',fontSize:9,flexShrink:0,marginTop:2,letterSpacing:1 },
  chatText:   { fontFamily:'Share Tech Mono',fontSize:11,color:'rgba(160,215,255,0.88)',lineHeight:1.7 },
  cursor:     { animation:'blink 0.7s step-end infinite',color:'#00d4ff' },
  inputRow:   { display:'flex',alignItems:'center',gap:8 },
  input:      { background:'transparent',border:'none',outline:'none',color:'rgba(0,212,255,0.92)',fontFamily:'Share Tech Mono',fontSize:11,width:'100%',letterSpacing:1,caretColor:'#00d4ff' },
  arcLabel:   { fontFamily:'Orbitron',fontSize:14,fontWeight:900,letterSpacing:9,color:'rgba(0,212,255,0.96)',textShadow:'0 0 24px rgba(0,212,255,0.7)' },
  arcSub:     { fontFamily:'Share Tech Mono',fontSize:9,letterSpacing:5,color:'rgba(0,140,200,0.48)' },
}

// ── HUD root ───────────────────────────────────────────────────────────────────
const HUD = () => {
  const [messages,          setMessages]          = useState([])
  const [input,             setInput]             = useState('')
  const [isThinking,        setIsThinking]        = useState(false)
  const [isSpeaking,        setIsSpeaking]        = useState(false)
  const [isListening,       setIsListening]       = useState(false)
  const [boot,              setBoot]              = useState({})
  const [booted,            setBooted]            = useState(false)
  const [shutting,          setShutting]          = useState(false)
  const [shutStep,          setShutStep]          = useState(0)
  const [repos,             setRepos]             = useState([])
  const [activeRepo,        setActiveRepo]        = useState(null)
  const [activeTier,        setActiveTier]        = useState('local')
  const [proactiveAlerts,   setProactiveAlerts]   = useState([])
  const [activeTab,         setActiveTab]         = useState('BRIDGE')
  const [voiceState,        setVoiceState]        = useState(null)
  const chatEndRef     = useRef(null)
  const wsRef          = useRef(null)
  const pendingVoiceId = useRef(null)

  // WebSocket connect/reconnect
  const wsReconnectRef = useRef(null)
  const connectWS = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState < 2) wsRef.current.close()
    const ws = new WebSocket(`ws://localhost:8000/ws/${SESSION_ID}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'routing') setActiveTier(msg.tier)
        if (msg.type === 'token') {
          const jid = pendingVoiceId.current
          if (jid) setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: m.text === '...' ? msg.text : m.text + msg.text } : m))
        }
        if (msg.type === 'done') { setIsThinking(false); setIsSpeaking(false); pendingVoiceId.current = null }
        if (msg.type === 'proactive_alert' && msg.data) {
          setProactiveAlerts(prev => {
            const exists = prev.some(a => a.id === msg.data.id)
            return exists ? prev : [msg.data, ...prev]
          })
        }
      } catch {
        if (e.data === 'speaking:start')   setIsSpeaking(true)
        if (e.data === 'speaking:stop')    setIsSpeaking(false)
        if (e.data === 'voice:listening')  setIsListening(true)
        if (e.data === 'voice:processing') setIsListening(false)
        if (e.data.startsWith('voice:transcript:')) {
          const text = e.data.replace('voice:transcript:', '')
          const uid = Date.now(), jid = uid + 1
          pendingVoiceId.current = jid
          setMessages(prev => [...prev, { id:uid, text, type:'user' }, { id:jid, text:'...', type:'jarvis' }])
          setIsThinking(true)
        }
        if (e.data.startsWith('voice:response:')) {
          const text = e.data.replace('voice:response:', '')
          setMessages(prev => {
            if (prev.length === 1 && prev[0].text === 'Systems online, sir.') {
              return [{ id: Date.now(), text, type: 'jarvis' }]
            }
            const jid = pendingVoiceId.current
            if (jid) return prev.map(m => m.id === jid ? { ...m, text } : m)
            return [...prev, { id: Date.now(), text, type: 'jarvis' }]
          })
          setIsThinking(false)
          pendingVoiceId.current = null
        }
      }
    }
    ws.onerror = () => console.warn('[JARVIS-MKIII] WebSocket error')
    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsReconnectRef.current = setTimeout(connectWS, 3000)
      }
    }
  }, [])

  // Boot sequence
  useEffect(() => {
    const timers = []
    BOOT_STEPS.forEach(({ key, delay }) => {
      timers.push(setTimeout(() => {
        setBoot(prev => ({ ...prev, [key]: true }))
        if (key === 'ready') {
          setBooted(true)
          connectWS()
          setMessages([{ id: 1, text: 'Systems online, sir.', type: 'jarvis' }])
        }
      }, delay))
    })
    return () => {
      timers.forEach(clearTimeout)
      clearTimeout(wsReconnectRef.current)
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
    }
  }, [connectWS])

  // Emotion state polling (5s interval — BRIDGE chat panel indicator)
  useEffect(() => {
    const fetchEmotion = () =>
      fetch(`${API}/emotion/state`).then(r => r.json()).then(d => setVoiceState(d)).catch(() => {})
    fetchEmotion()
    const id = setInterval(fetchEmotion, 5000)
    return () => clearInterval(id)
  }, [])

  // GitHub polling
  useEffect(() => {
    const fg = () => fetch(`${API}/github`).then(r => r.json()).then(d => { if (Array.isArray(d)) setRepos(d) }).catch(() => {})
    fg()
    const id = setInterval(fg, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [])

  // Auto-scroll chat
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const triggerShutdown = async () => {
    if (shutting) return
    setShutting(true)
    setTimeout(() => setShutStep(1), 50)
    setTimeout(() => setShutStep(2), 400)
    setTimeout(() => setShutStep(3), 700)
    setTimeout(() => setShutStep(4), 1000)
    setTimeout(() => setShutStep(5), 1300)
    setTimeout(() => setShutStep(6), 1800)
    setTimeout(() => setShutStep(7), 2200)
    setTimeout(() => { if (window.require) { const { remote } = window.require('@electron/remote'); if (remote) remote.getCurrentWindow().close() } }, 2800)
  }

  const sendMessage = async () => {
    if (!input.trim() || isThinking) return
    const lower = input.trim().toLowerCase()
    if (['shutdown', 'power down', 'jarvis shutdown', 'offline'].includes(lower)) { setInput(''); triggerShutdown(); return }
    if (['calibrate', 'run calibration'].includes(lower)) {
      setInput('')
      const jid = Date.now() + 1
      setMessages(prev => [...prev, { id: Date.now(), text: input, type:'user' }, { id: jid, text:'Recording 10-second baseline. Speak normally, sir...', type:'jarvis' }])
      fetch(`${API}/emotion/calibrate`, { method:'POST' })
        .then(() => setMessages(prev => prev.map(m => m.id === jid ? { ...m, text:'Calibration complete, sir. Baseline locked.' } : m)))
        .catch(() => setMessages(prev => prev.map(m => m.id === jid ? { ...m, text:'Calibration failed, sir.' } : m)))
      return
    }
    const jid = Date.now() + 1
    setMessages(prev => [...prev, { id: Date.now(), text: input, type: 'user' }, { id: jid, text: '', type: 'jarvis' }])
    setInput('')
    setIsThinking(true)
    try {
      const res  = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: input, session_id: SESSION_ID }) })
      const data = await res.json()
      setActiveTier(data.tier || 'local')
      setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: data.response || 'No response received, sir.' } : m))
    } catch {
      setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: 'Connection to backend lost, sir.' } : m))
    } finally {
      setIsThinking(false)
    }
  }
  const handleKey = e => { if (e.key === 'Enter') sendMessage() }

  const scanScreen = async () => {
    if (isThinking) return
    const jid = Date.now() + 1
    setMessages(prev => [...prev, { id: Date.now(), text: 'What do you see on my screen?', type: 'user' }, { id: jid, text: '', type: 'jarvis' }])
    setIsThinking(true)
    try {
      const res  = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: 'What do you see on my screen right now?', session_id: SESSION_ID }) })
      const data = await res.json()
      setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: data.response || 'Vision scan failed, sir.' } : m))
    } catch {
      setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: 'Vision scan failed, sir.' } : m))
    } finally {
      setIsThinking(false)
    }
  }

  const tierColor = activeTier === 'reasoning' ? '#ffb900' : activeTier === 'local' ? '#00ffc8' : '#00d4ff'
  const tierLabel = activeTier === 'reasoning' ? 'LLAMA 3.3 — REASONING' : activeTier === 'local' ? 'LLAMA 3.2 — LOCAL' : 'LLAMA 3.3 — VOICE'

  const _vsColors = { focused:'#00ffc8', fatigued:'#4488ff', stressed:'#ffb900', elevated:'#ff6644', neutral:'rgba(0,140,200,0.4)' }
  const voiceStateColor = _vsColors[voiceState?.state] || _vsColors.neutral

  const handleProactiveDismiss = useCallback(async (alertId) => {
    setProactiveAlerts(prev => prev.filter(a => a.id !== alertId))
    try {
      await fetch(`${API}/proactive/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert_id: alertId }),
      })
    } catch { /**/ }
  }, [])

  const handleProactiveAcknowledge = useCallback((alert) => {
    // Dismiss the notification then inject an "acknowledged" message into chat
    setProactiveAlerts(prev => prev.filter(a => a.id !== alert.id))
    const ackText = `Acknowledged: ${alert.title || alert.type}`
    const jid = Date.now() + 1
    setMessages(prev => [...prev,
      { id: Date.now(), text: ackText, type: 'user' },
      { id: jid, text: '', type: 'jarvis' },
    ])
    setIsThinking(true)
    fetch(`${API}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: ackText, session_id: SESSION_ID }),
    })
      .then(r => r.json())
      .then(d => {
        setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: d.response || '' } : m))
      })
      .catch(() => {
        setMessages(prev => prev.map(m => m.id === jid ? { ...m, text: 'Acknowledged, sir.' } : m))
      })
      .finally(() => setIsThinking(false))
    // Also dismiss on backend
    fetch(`${API}/proactive/dismiss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_id: alert.id }),
    }).catch(() => {})
  }, [])

  return (
    <div style={{
      width: '100vw', height: '100vh',
      background: 'rgba(0,6,16,0.97)',
      overflow: 'hidden',
      display: 'grid',
      gridTemplateColumns: '300px 1fr 300px',
      gridTemplateRows: '36px 1fr 28px',
      filter: shutStep >= 7 ? 'brightness(0)' : shutStep >= 6 ? 'brightness(0.12)' : 'none',
      transition: 'filter 0.9s ease',
    }}>

      {/* Background overlays (position:fixed — outside grid flow) */}
      <div style={S.grid}/><div style={S.scanlines}/><div style={S.vignette}/>

      {/* Shutdown fade overlay */}
      {shutStep >= 6 && (
        <div style={{ position:'fixed',inset:0,zIndex:999,pointerEvents:'none',background:`rgba(0,0,0,${shutStep>=7?1:0.65})`,transition:'background 0.7s ease' }}/>
      )}

      {/* Shutdown button */}
      {booted && !shutting && (
        <div onClick={triggerShutdown} title="Shutdown JARVIS"
          style={{ position:'fixed',top:4,right:8,width:28,height:28,borderRadius:'50%',border:'1px solid rgba(255,60,60,0.38)',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',zIndex:200,background:'rgba(255,30,30,0.07)',transition:'all 0.25s ease' }}
          onMouseEnter={e => { e.currentTarget.style.borderColor='rgba(255,60,60,0.95)'; e.currentTarget.style.boxShadow='0 0 14px rgba(255,50,50,0.6)'; e.currentTarget.style.background='rgba(255,30,30,0.22)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(255,60,60,0.38)'; e.currentTarget.style.boxShadow='none'; e.currentTarget.style.background='rgba(255,30,30,0.07)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,80,80,0.9)" strokeWidth="2.5" strokeLinecap="round"><path d="M12 2v6M6.3 5.3A9 9 0 1 0 17.7 5.3"/></svg>
        </div>
      )}

      {/* Boot effects */}
      {boot.scanline && !boot.reactor && <div style={S.bootScanline}/>}
      {boot.corners && ['topLeft','topRight','bottomLeft','bottomRight'].map(p => <Corner key={p} pos={p}/>)}

      {/* ── TAB BAR ──────────────────────────────────────────────────────────── */}
      <div style={{
        gridColumn: '1 / -1', gridRow: '1',
        display: 'flex', alignItems: 'center',
        background: 'rgba(0,4,14,0.98)',
        borderBottom: '1px solid rgba(0,212,255,0.14)',
        padding: '0 50px 0 14px',
        gap: 2,
        opacity: boot.panelTL ? 1 : 0,
        transition: 'opacity 0.5s ease',
        zIndex: 10,
      }}>
        {/* Logo */}
        <div style={{ fontFamily:'Orbitron', fontSize:9, fontWeight:900, letterSpacing:3, color:'rgba(0,212,255,0.7)', marginRight:10, paddingRight:10, borderRight:'1px solid rgba(0,212,255,0.14)', whiteSpace:'nowrap' }}>
          ◈ J.A.R.V.I.S
        </div>
        {TABS.map(tab => {
          const active = activeTab === tab.key
          return (
            <div key={tab.key} onClick={() => setActiveTab(tab.key)}
              style={{
                fontFamily: 'Orbitron', fontSize: 7, fontWeight: 700, letterSpacing: 2,
                padding: '0 14px', height: '100%', display: 'flex', alignItems: 'center',
                cursor: 'pointer', whiteSpace: 'nowrap',
                color: active ? 'rgba(0,212,255,0.95)' : 'rgba(0,140,200,0.38)',
                borderBottom: active ? '2px solid rgba(0,212,255,0.9)' : '2px solid transparent',
                background: active ? 'rgba(0,212,255,0.06)' : 'transparent',
                transition: 'all 0.18s ease',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.color = 'rgba(0,212,255,0.7)' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.color = 'rgba(0,140,200,0.38)' }}
            >{tab.label}</div>
          )
        })}
      </div>

      {/* ── LEFT COLUMN ─────────────────────────────────────────────────────── */}
      <div style={{
        gridColumn: '1', gridRow: '2',
        overflowY: 'auto', scrollbarWidth: 'none',
        padding: '12px 12px 12px',
        display: activeTab === 'BRIDGE' ? 'flex' : 'none', flexDirection: 'column', gap: 12,
        transition: 'transform 0.7s cubic-bezier(0.16,1,0.3,1), opacity 0.7s ease',
        transform: boot.panelTL ? 'translateX(0)' : 'translateX(-130px)',
        opacity: shutStep >= 1 ? 0 : boot.panelTL ? 1 : 0,
      }}>
        <WorldStatePanel/>

        {/* GitHub panel */}
        <div style={{
          background: 'rgba(0,7,22,0.88)',
          border: '1px solid rgba(0,212,255,0.2)',
          borderRadius: 3,
          padding: '14px 18px',
          backdropFilter: 'blur(6px)',
          boxShadow: '0 0 22px rgba(0,80,180,0.08),inset 0 1px 0 rgba(0,212,255,0.07)',
          transition: 'opacity 0.9s ease, transform 0.9s cubic-bezier(0.16,1,0.3,1), border-color 0.2s ease',
          opacity: shutStep >= 2 ? 0 : boot.github ? 1 : 0,
          transform: boot.github ? 'translateX(0)' : 'translateX(-130px)',
        }}
          onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(0,102,170,0.8)'}
          onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(0,212,255,0.2)'}
        >
          <div style={S.panelTitle}>GITHUB — AGENT17-TECH</div>
          {repos.length === 0 ? (
            <div style={{ ...S.dimText, fontSize: 9 }}>Awaiting connection to AGENT17-tech, sir.</div>
          ) : (
            <div style={{ display:'flex',flexDirection:'column',gap:10,maxHeight:200,overflowY:'auto',scrollbarWidth:'none' }}>
              {repos.map((r, ri) => (
                <div key={ri} style={{ cursor:'pointer' }} onClick={() => setActiveRepo(activeRepo === ri ? null : ri)}>
                  <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:2 }}>
                    <span style={{ fontFamily:'Share Tech Mono',fontSize:10,color:'rgba(0,212,255,0.92)',letterSpacing:0.5 }}>{r.name}</span>
                    <span style={{ fontFamily:'Share Tech Mono',fontSize:7,color:'rgba(0,0,0,0.8)',background:'rgba(0,255,200,0.75)',borderRadius:2,padding:'1px 5px',letterSpacing:0.5 }}>{r.language || '—'}</span>
                  </div>
                  {activeRepo === ri && (
                    <div style={{ marginTop:6,paddingTop:6,borderTop:'1px solid rgba(0,212,255,0.1)' }}>
                      {r.commits && r.commits.length > 0 ? (
                        <div style={{ display:'flex',flexDirection:'column',gap:5 }}>
                          {r.commits.map((c, ci) => (
                            <div key={ci} style={{ display:'flex',gap:7,alignItems:'flex-start' }}>
                              <span style={{ fontFamily:'Share Tech Mono',fontSize:7.5,color:'rgba(0,255,200,0.45)',marginTop:1,flexShrink:0 }}>{c.sha}</span>
                              <div style={{ flex:1,minWidth:0 }}>
                                <div style={{ fontFamily:'Share Tech Mono',fontSize:8,color:'rgba(0,212,255,0.85)',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis' }}>{c.message}</div>
                                <div style={{ ...S.dimText,fontSize:7.5,marginTop:1 }}>{c.date}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ ...S.dimText,fontSize:8 }}>NO RECENT COMMITS</div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── CENTER COLUMN ────────────────────────────────────────────────────── */}
      <div style={{ gridColumn: '2', gridRow: '2', position: 'relative', overflow: 'hidden', display: activeTab === 'BRIDGE' ? 'block' : 'none' }}>

        {/* Globe fills the entire column */}
        <GlobeNetwork isActive={activeTab === 'BRIDGE'} isSpeaking={isSpeaking} isThinking={isThinking}/>

        {/* Network link status badges — top-right of globe column */}
        <NetworkLinks/>

        {/* JARVIS title — centered overlay */}
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: boot.reactor
            ? 'translate(-50%,-50%) scale(1)'
            : 'translate(-50%,-50%) scale(0.22)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          pointerEvents: 'none',
          opacity: shutStep >= 5 ? 0 : boot.reactor ? 1 : 0,
          transition: 'opacity 1.1s ease, transform 1.1s cubic-bezier(0.16,1,0.3,1)',
        }}>
          <div style={{ ...S.arcLabel, opacity: boot.title ? 1 : 0, transition: 'opacity 0.9s ease' }}>J.A.R.V.I.S</div>
          <div style={{ ...S.arcSub,   opacity: boot.title ? 1 : 0, transition: 'opacity 0.9s ease' }}>MARK III — ONLINE</div>
        </div>
      </div>

      {/* ── RIGHT COLUMN ─────────────────────────────────────────────────────── */}
      <div style={{
        gridColumn: '3', gridRow: '2',
        display: activeTab === 'BRIDGE' ? 'flex' : 'none',
        overflowY: 'auto', scrollbarWidth: 'none',
        padding: '12px 12px 12px',
        flexDirection: 'column', gap: 12,
      }}>
        <div style={{
          transition: 'transform 0.7s cubic-bezier(0.16,1,0.3,1), opacity 0.7s ease',
          transform: boot.panelTR ? 'translateX(0)' : 'translateX(130px)',
          opacity: shutStep >= 1 ? 0 : boot.panelTR ? 1 : 0,
        }}>
          <CalendarWeatherPanel/>
        </div>
        <div style={{
          transition: 'transform 0.7s cubic-bezier(0.16,1,0.3,1), opacity 0.7s ease',
          transform: boot.cairo ? 'translateX(0)' : 'translateX(130px)',
          opacity: shutStep >= 4 ? 0 : boot.cairo ? 1 : 0,
        }}>
          <AgentFeed/>
        </div>
      </div>

      {/* ── TICKER — bottom row spanning all columns ──────────────────────────── */}
      {/* ── NON-BRIDGE TABS — full width ─────────────────────────────────────── */}
      {activeTab === 'INTEL' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <IntelTab/>
        </div>
      )}
      {activeTab === 'STRATEGY' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <StrategyTab/>
        </div>
      )}
      {activeTab === 'MISSIONS' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <MissionBoardTab/>
        </div>
      )}
      {activeTab === 'LIFE OS' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <LifeOSTab/>
        </div>
      )}
      {activeTab === 'COMMS' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <CommsTab/>
        </div>
      )}
      {activeTab === 'WHATSAPP' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <WhatsAppTab/>
        </div>
      )}
      {activeTab === 'VISION' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <VisionTab/>
        </div>
      )}
      {activeTab === 'PROACTIVE' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <ProactiveTab/>
        </div>
      )}
      {activeTab === 'MEMORY' && (
        <div style={{ gridColumn: '1 / -1', gridRow: '2', overflow: 'hidden' }}>
          <MemoryTab/>
        </div>
      )}

      {/* ── TICKER — bottom row spanning all columns ──────────────────────────── */}
      <div style={{ gridColumn: '1 / -1', gridRow: '3' }}>
        <AlertTicker visible={!!(boot.ticker && shutStep < 2)}/>
      </div>

      {/* ── CHAT PANEL — fixed overlay over center, BRIDGE only ──────────────── */}
      <div style={{
        position: 'fixed', left: 308, bottom: 36,
        width: 380, height: 320,
        background: 'rgba(10,14,26,0.92)',
        border: '1px solid #0a3a5a',
        backdropFilter: 'blur(6px)',
        borderRadius: 3,
        padding: '14px 18px',
        zIndex: 100,
        transition: 'opacity 0.7s ease, border-color 0.2s ease',
        opacity: shutStep >= 1 || activeTab !== 'BRIDGE' ? 0 : boot.panelBR ? 1 : 0,
        pointerEvents: activeTab !== 'BRIDGE' ? 'none' : 'auto',
        boxShadow: '0 0 30px rgba(0,80,180,0.12)',
      }}
        onMouseEnter={e => e.currentTarget.style.borderColor = 'rgba(0,102,170,0.8)'}
        onMouseLeave={e => e.currentTarget.style.borderColor = '#0a3a5a'}
      >
        <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:13 }}>
          <div style={{ ...S.panelTitle, marginBottom:0 }}>J.A.R.V.I.S INTERFACE</div>
          <div style={{ display:'flex',alignItems:'center',gap:10 }}>
            <div style={{ display:'flex',alignItems:'center',gap:5 }}>
              <div style={{ width:5,height:5,borderRadius:'50%',background:tierColor,boxShadow:`0 0 6px ${tierColor}` }}/>
              <span style={{ fontFamily:'Share Tech Mono',fontSize:8,color:tierColor,letterSpacing:1 }}>{tierLabel}</span>
            </div>
            {voiceState && (
              <div style={{ display:'flex',alignItems:'center',gap:5 }}>
                <div style={{ width:5,height:5,borderRadius:'50%',background:voiceStateColor,boxShadow:`0 0 6px ${voiceStateColor}` }}/>
                <span style={{ fontFamily:'Share Tech Mono',fontSize:8,color:voiceStateColor,letterSpacing:1 }}>{(voiceState.state||'neutral').toUpperCase()}</span>
              </div>
            )}
          </div>
        </div>
        <div style={S.chatLog}>
          {messages.map(m => (
            <div key={m.id} style={S.chatMessage}>
              <span style={{ ...S.chatLabel, color:m.type==='user'?'#ffb900':'#00d4ff', textShadow:m.type==='user'?'0 0 8px rgba(255,185,0,0.5)':'0 0 8px rgba(0,212,255,0.5)' }}>
                {m.type === 'user' ? 'YOU >' : 'JARVIS >'}
              </span>
              <span style={S.chatText}>{m.text}{m.text === '' && isThinking && <span style={S.cursor}>▋</span>}</span>
            </div>
          ))}
          <div ref={chatEndRef}/>
        </div>
        {isListening && (
          <div style={{ display:'flex',alignItems:'center',gap:6,padding:'5px 0',marginBottom:4 }}>
            <div style={{ width:6,height:6,borderRadius:'50%',background:'#00ffc8',boxShadow:'0 0 8px #00ffc8',animation:'pulse 0.8s ease-in-out infinite' }}/>
            <span style={{ fontFamily:'Share Tech Mono',fontSize:9,color:'#00ffc8',letterSpacing:1.5 }}>LISTENING...</span>
          </div>
        )}
        <div style={S.divider}/>
        <div style={S.inputRow}>
          <span style={{ ...S.dimText, color:'rgba(0,212,255,0.45)' }}>&gt;</span>
          <input
            style={S.input}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder={isThinking ? 'JARVIS is responding...' : 'Enter command, sir...'}
            disabled={isThinking || !booted}
          />
          <button onClick={scanScreen} disabled={isThinking || !booted} title="Scan screen"
            style={{ background:'none',border:'1px solid rgba(0,212,255,0.25)',borderRadius:3,color:isThinking?'rgba(0,212,255,0.2)':'rgba(0,212,255,0.6)',fontFamily:'Share Tech Mono',fontSize:9,letterSpacing:1,padding:'4px 7px',cursor:isThinking?'not-allowed':'pointer',flexShrink:0,transition:'all 0.2s ease',textShadow:isThinking?'none':'0 0 6px rgba(0,212,255,0.4)' }}
            onMouseEnter={e => { if (!isThinking) e.target.style.borderColor = 'rgba(0,212,255,0.7)' }}
            onMouseLeave={e => { e.target.style.borderColor = 'rgba(0,212,255,0.25)' }}>
            👁 SCAN
          </button>
        </div>
      </div>

      <ProactiveNotifications
        alerts={proactiveAlerts}
        onDismiss={handleProactiveDismiss}
        onAcknowledge={handleProactiveAcknowledge}
      />

      <AutonomousAlerts/>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');
        @keyframes pulse    { 0%,100%{opacity:1;box-shadow:0 0 38px #00b4ff,0 0 76px rgba(0,180,255,0.3)} 50%{opacity:0.74;box-shadow:0 0 14px #00b4ff} }
        @keyframes blink    { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes cornerPulse { 0%,100%{opacity:0.5} 50%{opacity:1} }
        @keyframes bootScan { 0%{top:-4px;opacity:1} 100%{top:100vh;opacity:0} }
        @keyframes tickerScroll { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }
        input::placeholder { color:rgba(0,100,160,0.42); font-family:'Share Tech Mono',monospace; }
        ::-webkit-scrollbar { width:0; }
        * { box-sizing:border-box; }
      `}</style>
    </div>
  )
}

export default HUD
