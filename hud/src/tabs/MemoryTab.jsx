import { useState, useEffect, useCallback } from 'react'

const API = 'http://localhost:8000'

const S = {
  container: {
    width: '100%', height: '100%',
    background: 'rgba(0,4,14,0.97)',
    display: 'flex', flexDirection: 'column',
    fontFamily: "'Share Tech Mono', monospace",
    color: '#00d4ff', overflow: 'hidden',
  },
  header: {
    padding: '16px 24px 12px',
    borderBottom: '1px solid rgba(0,212,255,0.15)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    flexShrink: 0,
  },
  title: {
    fontFamily: 'Orbitron, monospace', fontSize: 13, fontWeight: 700,
    color: '#00d4ff', letterSpacing: 3, textShadow: '0 0 12px rgba(0,212,255,0.5)',
  },
  statsBar: {
    display: 'flex', gap: 24, alignItems: 'center',
  },
  stat: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
  },
  statNum: {
    fontFamily: 'Orbitron, monospace', fontSize: 18, fontWeight: 700,
    color: '#00ffc8', textShadow: '0 0 10px rgba(0,255,200,0.4)',
  },
  statLabel: {
    fontSize: 8, color: 'rgba(0,212,255,0.5)', letterSpacing: 2, textTransform: 'uppercase',
  },
  body: {
    flex: 1, display: 'grid',
    gridTemplateColumns: '1fr 320px',
    gridTemplateRows: '1fr',
    overflow: 'hidden',
  },
  left: {
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    borderRight: '1px solid rgba(0,212,255,0.1)',
  },
  right: {
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  section: {
    padding: '10px 20px 6px',
    borderBottom: '1px solid rgba(0,212,255,0.08)',
  },
  sectionTitle: {
    fontFamily: 'Orbitron, monospace', fontSize: 8, letterSpacing: 2.5,
    color: 'rgba(0,212,255,0.5)', marginBottom: 8,
  },
  searchRow: {
    display: 'flex', gap: 8, alignItems: 'center',
  },
  input: {
    flex: 1, background: 'rgba(0,20,40,0.8)',
    border: '1px solid rgba(0,212,255,0.2)',
    borderRadius: 3, padding: '6px 10px',
    fontFamily: "'Share Tech Mono', monospace", fontSize: 11,
    color: '#00d4ff', outline: 'none',
  },
  btn: {
    background: 'rgba(0,212,255,0.08)',
    border: '1px solid rgba(0,212,255,0.3)',
    borderRadius: 3, padding: '6px 14px',
    fontFamily: "'Share Tech Mono', monospace", fontSize: 10,
    color: '#00d4ff', cursor: 'pointer', letterSpacing: 1,
    transition: 'all 0.2s ease', flexShrink: 0,
  },
  btnDanger: {
    background: 'rgba(255,60,60,0.08)',
    border: '1px solid rgba(255,60,60,0.3)',
    color: '#ff6060',
  },
  resultsList: {
    flex: 1, overflowY: 'auto', padding: '8px 20px',
    scrollbarWidth: 'none',
  },
  resultCard: {
    background: 'rgba(0,20,40,0.5)',
    border: '1px solid rgba(0,212,255,0.1)',
    borderRadius: 3, padding: '10px 12px', marginBottom: 8,
    transition: 'border-color 0.2s ease',
  },
  resultMeta: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: 5,
  },
  resultDate: { fontSize: 9, color: 'rgba(0,212,255,0.4)', letterSpacing: 1 },
  resultScore: { fontSize: 9, color: '#00ffc8', letterSpacing: 1 },
  resultText: {
    fontSize: 10, color: 'rgba(0,212,255,0.8)', lineHeight: 1.5,
    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  },
  emptyState: {
    padding: 24, textAlign: 'center', fontSize: 10,
    color: 'rgba(0,212,255,0.3)', letterSpacing: 1,
  },
  factCard: {
    background: 'rgba(0,255,200,0.04)',
    border: '1px solid rgba(0,255,200,0.12)',
    borderRadius: 3, padding: '8px 10px', marginBottom: 6,
  },
  factText: { fontSize: 10, color: 'rgba(0,212,255,0.75)', lineHeight: 1.4 },
  factMeta: { fontSize: 8, color: 'rgba(0,255,200,0.4)', marginTop: 3, letterSpacing: 0.5 },
  factInputRow: {
    padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 6,
  },
  tagRow: {
    display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center',
  },
  tag: {
    background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)',
    borderRadius: 2, padding: '1px 7px', fontSize: 8, color: '#00d4ff',
  },
  statusMsg: {
    padding: '4px 20px', fontSize: 9, letterSpacing: 1,
    color: '#00ffc8', borderBottom: '1px solid rgba(0,212,255,0.08)',
    flexShrink: 0, minHeight: 22,
  },
}

export default function MemoryTab() {
  const [stats, setStats]           = useState({ conversations: 0, facts: 0, missions: 0 })
  const [searchQ, setSearchQ]       = useState('')
  const [searchCol, setSearchCol]   = useState('conversations')
  const [results, setResults]       = useState([])
  const [searching, setSearching]   = useState(false)
  const [recentMems, setRecentMems] = useState([])
  const [facts, setFacts]           = useState([])
  const [factInput, setFactInput]   = useState('')
  const [factTags, setFactTags]     = useState('')
  const [statusMsg, setStatusMsg]   = useState('')
  const [confirmClear, setConfirmClear] = useState(false)

  const flash = (msg) => { setStatusMsg(msg); setTimeout(() => setStatusMsg(''), 3000) }

  const loadStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/rag/stats`)
      const d = await r.json()
      setStats(d)
    } catch {}
  }, [])

  const loadRecentMems = useCallback(async () => {
    try {
      const r = await fetch(`${API}/rag/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'conversation', n_results: 10, collection: 'conversations' }),
      })
      const d = await r.json()
      setRecentMems(d.results || [])
    } catch {}
  }, [])

  const loadFacts = useCallback(async () => {
    try {
      const r = await fetch(`${API}/rag/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'fact', n_results: 20, collection: 'facts' }),
      })
      const d = await r.json()
      setFacts(d.results || [])
    } catch {}
  }, [])

  useEffect(() => {
    loadStats()
    loadRecentMems()
    loadFacts()
    const t = setInterval(loadStats, 60000)
    return () => clearInterval(t)
  }, [loadStats, loadRecentMems, loadFacts])

  const handleSearch = async () => {
    if (!searchQ.trim()) return
    setSearching(true)
    try {
      const r = await fetch(`${API}/rag/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQ.trim(), n_results: 10, collection: searchCol }),
      })
      const d = await r.json()
      setResults(d.results || [])
      if (!d.results?.length) flash('No results found.')
    } catch (e) {
      flash(`Search failed: ${e.message}`)
    } finally {
      setSearching(false)
    }
  }

  const handleStoreFact = async () => {
    if (!factInput.trim()) return
    const tags = factTags.split(',').map(t => t.trim()).filter(Boolean)
    try {
      await fetch(`${API}/rag/store_fact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fact: factInput.trim(), source: 'hud', tags }),
      })
      flash('Fact stored in long-term memory.')
      setFactInput('')
      setFactTags('')
      loadFacts()
      loadStats()
    } catch (e) {
      flash(`Store failed: ${e.message}`)
    }
  }

  const handleClear = async () => {
    if (!confirmClear) { setConfirmClear(true); flash('Click CLEAR again to confirm erasure.'); return }
    try {
      const r = await fetch(`${API}/rag/clear`, {
        method: 'DELETE',
        headers: { 'X-Confirm': 'yes-clear-all-memory' },
      })
      const d = await r.json()
      flash(d.message || 'Memory cleared.')
      setResults([])
      setRecentMems([])
      setFacts([])
      loadStats()
    } catch (e) {
      flash(`Clear failed: ${e.message}`)
    }
    setConfirmClear(false)
  }

  const pct = (n) => `${Math.round(n * 100)}%`

  return (
    <div style={S.container}>
      {/* ── Header ── */}
      <div style={S.header}>
        <div style={S.title}>EPISODIC MEMORY</div>
        <div style={S.statsBar}>
          {[
            { num: stats.conversations, label: 'Conversations' },
            { num: stats.facts,         label: 'Facts'         },
            { num: stats.missions,      label: 'Missions'      },
          ].map(({ num, label }) => (
            <div key={label} style={S.stat}>
              <div style={S.statNum}>{num}</div>
              <div style={S.statLabel}>{label}</div>
            </div>
          ))}
          <button
            style={{ ...S.btn, ...S.btnDanger }}
            onClick={handleClear}
            title="Erase all RAG memory"
          >
            {confirmClear ? '⚠ CONFIRM' : 'CLEAR ALL'}
          </button>
        </div>
      </div>

      {statusMsg && <div style={S.statusMsg}>{statusMsg}</div>}

      <div style={S.body}>
        {/* ── LEFT: search + results ── */}
        <div style={S.left}>
          <div style={S.section}>
            <div style={S.sectionTitle}>SEMANTIC SEARCH</div>
            <div style={S.searchRow}>
              <input
                style={S.input}
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search memory..."
              />
              <select
                value={searchCol}
                onChange={e => setSearchCol(e.target.value)}
                style={{ ...S.input, flex: 'none', width: 130 }}
              >
                <option value="conversations">Conversations</option>
                <option value="facts">Facts</option>
                <option value="missions">Missions</option>
              </select>
              <button style={S.btn} onClick={handleSearch} disabled={searching}>
                {searching ? '...' : 'SEARCH'}
              </button>
            </div>
          </div>

          <div style={S.resultsList}>
            {results.length > 0 ? (
              <>
                <div style={{ ...S.sectionTitle, padding: '8px 0 4px' }}>
                  {results.length} RESULT{results.length !== 1 ? 'S' : ''} FOUND
                </div>
                {results.map((r, i) => (
                  <div key={i} style={S.resultCard}>
                    <div style={S.resultMeta}>
                      <span style={S.resultDate}>{r.metadata?.date || 'unknown'}</span>
                      <span style={S.resultScore}>{pct(r.relevance)} match</span>
                    </div>
                    <div style={S.resultText}>{r.document?.slice(0, 400)}</div>
                  </div>
                ))}
              </>
            ) : (
              <>
                <div style={{ ...S.sectionTitle, padding: '8px 0 4px' }}>RECENT CONVERSATIONS</div>
                {recentMems.length === 0 ? (
                  <div style={S.emptyState}>No conversations stored yet.</div>
                ) : (
                  recentMems.map((r, i) => (
                    <div key={i} style={S.resultCard}>
                      <div style={S.resultMeta}>
                        <span style={S.resultDate}>{r.metadata?.date || 'unknown'}</span>
                        <span style={S.resultScore}>{r.metadata?.session_id?.slice(0, 8)}</span>
                      </div>
                      <div style={S.resultText}>{r.document?.slice(0, 300)}</div>
                    </div>
                  ))
                )}
              </>
            )}
          </div>
        </div>

        {/* ── RIGHT: facts panel ── */}
        <div style={S.right}>
          <div style={S.section}>
            <div style={S.sectionTitle}>STORE FACT</div>
            <div style={S.factInputRow}>
              <textarea
                style={{ ...S.input, resize: 'vertical', minHeight: 54, lineHeight: 1.5 }}
                value={factInput}
                onChange={e => setFactInput(e.target.value)}
                placeholder="Enter fact to store..."
              />
              <input
                style={S.input}
                value={factTags}
                onChange={e => setFactTags(e.target.value)}
                placeholder="Tags (comma-separated)"
              />
              <button style={S.btn} onClick={handleStoreFact}>STORE</button>
            </div>
          </div>

          <div style={{ ...S.section, borderBottom: 'none' }}>
            <div style={S.sectionTitle}>STORED FACTS ({facts.length})</div>
          </div>
          <div style={{ ...S.resultsList, padding: '6px 12px' }}>
            {facts.length === 0 ? (
              <div style={S.emptyState}>No facts stored yet.</div>
            ) : (
              facts.map((f, i) => {
                let tags = []
                try { tags = JSON.parse(f.metadata?.tags || '[]') } catch {}
                return (
                  <div key={i} style={S.factCard}>
                    <div style={S.factText}>{f.document?.slice(0, 200)}</div>
                    <div style={S.factMeta}>
                      {f.metadata?.date} · {f.metadata?.source}
                      {tags.length > 0 && (
                        <span style={{ marginLeft: 6 }}>
                          {tags.map(t => <span key={t} style={S.tag}>{t}</span>)}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
