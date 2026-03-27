import { useState, useEffect, useRef } from 'react'

const API = 'http://localhost:8000'
const POLL_INTERVAL = 30_000   // 30 s

const T = {
  panel:  { background: 'rgba(0,7,22,0.88)', border: '1px solid rgba(0,212,255,0.18)', borderRadius: 3, backdropFilter: 'blur(6px)', boxShadow: '0 0 22px rgba(0,80,180,0.08)' },
  title:  { fontFamily: 'Orbitron', fontSize: 9, fontWeight: 700, letterSpacing: 3.5, color: 'rgba(0,200,255,0.9)' },
  dim:    { fontFamily: 'Share Tech Mono', fontSize: 9, color: 'rgba(0,140,200,0.5)', letterSpacing: 1 },
  body:   { fontFamily: 'Share Tech Mono', fontSize: 10, color: 'rgba(160,215,255,0.85)', lineHeight: 1.7 },
  input:  { background: 'rgba(0,20,50,0.7)', border: '1px solid rgba(0,212,255,0.22)', borderRadius: 2, color: 'rgba(160,215,255,0.9)', fontFamily: 'Share Tech Mono', fontSize: 11, padding: '6px 10px', outline: 'none', width: '100%', boxSizing: 'border-box' },
  btn:    { background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.35)', borderRadius: 2, color: 'rgba(0,212,255,0.9)', fontFamily: 'Orbitron', fontSize: 8, fontWeight: 700, letterSpacing: 2, padding: '6px 18px', cursor: 'pointer', whiteSpace: 'nowrap' },
}

function StatusBadge({ status }) {
  const connected = status === 'connected'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: connected ? '#00ffc8' : '#ff4444',
        boxShadow: connected ? '0 0 8px #00ffc8' : '0 0 8px #ff4444',
        animation: connected ? 'blink 2s ease-in-out infinite' : 'none',
      }}/>
      <span style={{ ...T.dim, color: connected ? 'rgba(0,255,200,0.7)' : 'rgba(255,80,80,0.7)' }}>
        {connected ? 'CONNECTED' : status?.toUpperCase() || 'DISCONNECTED'}
      </span>
    </div>
  )
}

function MessageRow({ msg }) {
  const ts = msg.timestamp
    ? new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''
  const unread = !msg.read
  return (
    <div style={{
      padding: '8px 12px',
      borderBottom: '1px solid rgba(0,212,255,0.08)',
      background: unread ? 'rgba(0,212,255,0.04)' : 'transparent',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ ...T.body, fontSize: 10, color: unread ? 'rgba(0,212,255,0.9)' : 'rgba(120,180,220,0.7)', fontWeight: unread ? 700 : 400 }}>
          {msg.from_name || msg.from || 'Unknown'}
          {msg.is_group && <span style={{ ...T.dim, marginLeft: 6 }}>GROUP</span>}
        </span>
        <span style={T.dim}>{ts}</span>
      </div>
      <div style={{ ...T.body, fontSize: 10, color: 'rgba(140,195,240,0.75)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>
        {msg.body || '(media)'}
      </div>
    </div>
  )
}

export default function WhatsAppTab() {
  const [status,   setStatus]   = useState('disconnected')
  const [phone,    setPhone]    = useState(null)
  const [unread,   setUnread]   = useState(0)
  const [messages, setMessages] = useState([])
  const [contact,  setContact]  = useState('')
  const [text,     setText]     = useState('')
  const [sending,  setSending]  = useState(false)
  const [sendMsg,  setSendMsg]  = useState('')
  const timerRef = useRef(null)

  async function fetchStatus() {
    try {
      const r = await fetch(`${API}/whatsapp/status`)
      if (!r.ok) return
      const d = await r.json()
      setStatus(d.status || 'disconnected')
      setPhone(d.phone || null)
      setUnread(d.unread_count || 0)
    } catch { /* bridge not up yet */ }
  }

  async function fetchMessages() {
    try {
      const r = await fetch(`${API}/whatsapp/messages?limit=10`)
      if (!r.ok) return
      const d = await r.json()
      setMessages(d.messages || [])
      setUnread(d.unread || 0)
    } catch { /* ignore */ }
  }

  async function refresh() {
    await Promise.all([fetchStatus(), fetchMessages()])
  }

  useEffect(() => {
    refresh()
    timerRef.current = setInterval(refresh, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [])

  async function handleSend(e) {
    e.preventDefault()
    if (!contact.trim() || !text.trim()) return
    setSending(true)
    setSendMsg('')
    try {
      const r = await fetch(`${API}/whatsapp/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contact: contact.trim(), message: text.trim() }),
      })
      const d = await r.json()
      if (r.ok) {
        setSendMsg('Message sent.')
        setText('')
        setTimeout(() => setSendMsg(''), 3000)
      } else {
        setSendMsg(`Error: ${d.detail || d.error || 'send failed'}`)
      }
    } catch (err) {
      setSendMsg(`Network error: ${err.message}`)
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16, height: '100%', boxSizing: 'border-box', overflowY: 'auto' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{ ...T.panel, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={T.title}>WHATSAPP</div>
          {phone && <div style={{ ...T.dim, marginTop: 4 }}>+{phone}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {unread > 0 && (
            <div style={{ background: 'rgba(255,100,60,0.85)', borderRadius: 10, padding: '2px 9px', fontFamily: 'Orbitron', fontSize: 8, fontWeight: 700, color: '#fff' }}>
              {unread} UNREAD
            </div>
          )}
          <StatusBadge status={status}/>
          <button style={T.btn} onClick={refresh}>REFRESH</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>

        {/* ── Messages ─────────────────────────────────────────────────────── */}
        <div style={{ ...T.panel, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ ...T.title, padding: '12px 14px', borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            MESSAGES
          </div>
          <div style={{ flex: 1, overflowY: 'auto', scrollbarWidth: 'none' }}>
            {messages.length === 0 ? (
              <div style={{ ...T.dim, padding: '24px 14px', textAlign: 'center' }}>
                {status === 'connected' ? 'No messages yet.' : 'Connect WhatsApp to see messages.'}
              </div>
            ) : (
              messages.map((m, i) => <MessageRow key={i} msg={m}/>)
            )}
          </div>
        </div>

        {/* ── Send form ────────────────────────────────────────────────────── */}
        <div style={{ ...T.panel, width: 320, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={T.title}>SEND MESSAGE</div>
          <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <div style={{ ...T.dim, marginBottom: 5 }}>CONTACT (name or number)</div>
              <input
                style={T.input}
                value={contact}
                onChange={e => setContact(e.target.value)}
                placeholder="e.g. Khalid or +201001234567"
                disabled={sending}
              />
            </div>
            <div>
              <div style={{ ...T.dim, marginBottom: 5 }}>MESSAGE</div>
              <textarea
                style={{ ...T.input, resize: 'vertical', minHeight: 90 }}
                value={text}
                onChange={e => setText(e.target.value)}
                placeholder="Type your message…"
                disabled={sending}
              />
            </div>
            <button
              type="submit"
              style={{ ...T.btn, opacity: sending || status !== 'connected' ? 0.5 : 1 }}
              disabled={sending || status !== 'connected'}
            >
              {sending ? 'SENDING…' : 'SEND'}
            </button>
            {status !== 'connected' && (
              <div style={{ ...T.dim, color: 'rgba(255,120,80,0.7)', fontSize: 9 }}>
                WhatsApp not connected
              </div>
            )}
            {sendMsg && (
              <div style={{ ...T.body, fontSize: 10, color: sendMsg.startsWith('Error') ? 'rgba(255,100,60,0.85)' : 'rgba(0,255,200,0.7)' }}>
                {sendMsg}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  )
}
