/**
 * JARVIS-MKIII — WorldMapPanel.jsx
 * D3 + TopoJSON world map with data-driven country coloring.
 * Matches the HUD dark theme. All rendering is SVG-based for
 * hover interactivity.
 */
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import * as topojson from 'topojson-client'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

// ── ISO 3166-1 numeric ID → alpha-2 (world-atlas uses numeric feature IDs) ──
const NUM_TO_A2 = {
  4:'AF',8:'AL',12:'DZ',24:'AO',32:'AR',36:'AU',40:'AT',50:'BD',56:'BE',
  64:'BT',68:'BO',76:'BR',100:'BG',104:'MM',116:'KH',120:'CM',124:'CA',
  140:'CF',144:'LK',152:'CL',156:'CN',170:'CO',180:'CD',188:'CR',191:'HR',
  192:'CU',196:'CY',203:'CZ',208:'DK',218:'EC',818:'EG',222:'SV',231:'ET',
  246:'FI',250:'FR',266:'GA',276:'DE',288:'GH',300:'GR',320:'GT',324:'GN',
  332:'HT',340:'HN',348:'HU',356:'IN',360:'ID',364:'IR',368:'IQ',372:'IE',
  376:'IL',380:'IT',384:'CI',388:'JM',392:'JP',400:'JO',398:'KZ',404:'KE',
  410:'KR',408:'KP',414:'KW',418:'LA',422:'LB',430:'LR',434:'LY',450:'MG',
  484:'MX',496:'MN',504:'MA',508:'MZ',516:'NA',524:'NP',528:'NL',554:'NZ',
  558:'NI',562:'NE',566:'NG',578:'NO',586:'PK',275:'PS',591:'PA',598:'PG',
  600:'PY',604:'PE',608:'PH',616:'PL',620:'PT',642:'RO',643:'RU',646:'RW',
  682:'SA',686:'SN',694:'SL',706:'SO',710:'ZA',724:'ES',729:'SD',752:'SE',
  756:'CH',760:'SY',764:'TH',768:'TG',788:'TN',792:'TR',800:'UG',804:'UA',
  784:'AE',826:'GB',840:'US',858:'UY',860:'UZ',862:'VE',704:'VN',887:'YE',
  894:'ZM',716:'ZW',12:'DZ',434:'LY',788:'TN',504:'MA',729:'SD',706:'SO',
}

// ── Display names ──────────────────────────────────────────────────────────
const A2_TO_NAME = {
  AF:'Afghanistan',AL:'Albania',DZ:'Algeria',AO:'Angola',AR:'Argentina',
  AU:'Australia',AT:'Austria',BD:'Bangladesh',BE:'Belgium',BT:'Bhutan',
  BO:'Bolivia',BR:'Brazil',BG:'Bulgaria',MM:'Myanmar',KH:'Cambodia',
  CM:'Cameroon',CA:'Canada',CF:'Cent. African Rep.',LK:'Sri Lanka',
  CL:'Chile',CN:'China',CO:'Colombia',CD:'DR Congo',CR:'Costa Rica',
  HR:'Croatia',CU:'Cuba',CY:'Cyprus',CZ:'Czech Rep.',DK:'Denmark',
  EC:'Ecuador',EG:'Egypt',SV:'El Salvador',ET:'Ethiopia',FI:'Finland',
  FR:'France',GA:'Gabon',DE:'Germany',GH:'Ghana',GR:'Greece',
  GT:'Guatemala',GN:'Guinea',HT:'Haiti',HN:'Honduras',HU:'Hungary',
  IN:'India',ID:'Indonesia',IR:'Iran',IQ:'Iraq',IE:'Ireland',
  IL:'Israel',IT:'Italy',CI:"Côte d'Ivoire",JM:'Jamaica',JP:'Japan',
  JO:'Jordan',KZ:'Kazakhstan',KE:'Kenya',KR:'South Korea',KP:'North Korea',
  KW:'Kuwait',LA:'Laos',LB:'Lebanon',LR:'Liberia',LY:'Libya',
  MG:'Madagascar',MX:'Mexico',MN:'Mongolia',MA:'Morocco',MZ:'Mozambique',
  NA:'Namibia',NP:'Nepal',NL:'Netherlands',NZ:'New Zealand',NI:'Nicaragua',
  NE:'Niger',NG:'Nigeria',NO:'Norway',PK:'Pakistan',PS:'Palestine',
  PA:'Panama',PG:'Papua New Guinea',PY:'Paraguay',PE:'Peru',
  PH:'Philippines',PL:'Poland',PT:'Portugal',RO:'Romania',RU:'Russia',
  RW:'Rwanda',SA:'Saudi Arabia',SN:'Senegal',SL:'Sierra Leone',SO:'Somalia',
  ZA:'South Africa',ES:'Spain',SD:'Sudan',SE:'Sweden',CH:'Switzerland',
  SY:'Syria',TH:'Thailand',TG:'Togo',TN:'Tunisia',TR:'Turkey',UG:'Uganda',
  UA:'Ukraine',AE:'United Arab Emirates',GB:'United Kingdom',
  US:'United States',UY:'Uruguay',UZ:'Uzbekistan',VE:'Venezuela',
  VN:'Vietnam',YE:'Yemen',ZM:'Zambia',ZW:'Zimbabwe',
}

// ── Palette ────────────────────────────────────────────────────────────────
const C = {
  ocean:        '#0d1b2a',
  countryFill:  '#1a2744',
  countryBorder:'#0f2040',
  dataLow:      '#1a3a6b',
  dataHigh:     '#4fa3e0',
  hover:        '#5bb8ff',
  text:         'rgba(0,212,255,0.9)',
  dimText:      'rgba(0,140,200,0.52)',
  border:       'rgba(0,212,255,0.22)',
}

// ── Geo cache (survive HMR re-renders without re-fetching) ─────────────────
let _geoCache    = null
let _geoPending  = null

function fetchGeo() {
  if (_geoCache)   return Promise.resolve(_geoCache)
  if (_geoPending) return _geoPending
  _geoPending = fetch(GEO_URL)
    .then(r => r.json())
    .then(world => {
      _geoCache = topojson.feature(world, world.objects.countries)
      return _geoCache
    })
  return _geoPending
}


const WorldMapPanel = ({
  data  = {},
  title = 'Global Intelligence Map',
  width = 820,
}) => {
  const MAP_H        = 162
  const svgRef       = useRef(null)
  const containerRef = useRef(null)
  const [geo,     setGeo]     = useState(_geoCache)
  const [tooltip, setTooltip] = useState(null)
  const [loading, setLoading] = useState(!_geoCache)

  // ── Fetch GeoJSON ────────────────────────────────────────────────────────
  useEffect(() => {
    if (_geoCache) { setGeo(_geoCache); return }
    fetchGeo()
      .then(g => { setGeo(g); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // ── Render D3 map ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!geo || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Projection — Natural Earth, fitted to our SVG size
    const projection = d3.geoNaturalEarth1()
      .fitSize([width, MAP_H], geo)

    const path = d3.geoPath().projection(projection)

    // Color scale
    const vals    = Object.values(data).filter(v => typeof v === 'number')
    const minVal  = vals.length ? Math.min(...vals) : 0
    const maxVal  = vals.length ? Math.max(...vals) : 1
    const colorFn = d3.scaleSequential(
      [minVal, maxVal],
      d3.interpolate(C.dataLow, C.dataHigh)
    )

    const getFill = d => {
      const a2  = NUM_TO_A2[+d.id]
      const val = a2 !== undefined ? data[a2] : undefined
      return val !== undefined ? colorFn(val) : C.countryFill
    }

    // Ocean base
    svg.append('path')
      .datum({ type: 'Sphere' })
      .attr('d', path)
      .attr('fill', C.ocean)

    // Graticule — very faint 30° grid
    const graticule = d3.geoGraticule().step([30, 30])
    svg.append('path')
      .datum(graticule())
      .attr('d', path)
      .attr('fill', 'none')
      .attr('stroke', 'rgba(0,90,175,0.15)')
      .attr('stroke-width', 0.35)

    // Countries
    const countries = svg.selectAll('path.c')
      .data(geo.features)
      .join('path')
      .attr('class', 'c')
      .attr('d', path)
      .attr('fill', getFill)
      .attr('stroke', C.countryBorder)
      .attr('stroke-width', 0.5)
      .attr('stroke-linejoin', 'round')
      .style('cursor', 'crosshair')

    // ── Hover ──────────────────────────────────────────────────────────────
    countries
      .on('mouseenter', function (event, d) {
        const a2   = NUM_TO_A2[+d.id]
        const name = a2 ? (A2_TO_NAME[a2] || a2) : `#${d.id}`
        const val  = a2 !== undefined ? data[a2] : undefined

        d3.select(this)
          .raise()
          .attr('fill', C.hover)
          .attr('stroke', 'rgba(91,184,255,0.65)')
          .attr('stroke-width', 1.2)
          .style('filter', 'drop-shadow(0 0 6px rgba(91,184,255,0.7))')

        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top, name, val })
      })
      .on('mousemove', function (event) {
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) setTooltip(p => p ? { ...p, x: event.clientX - rect.left, y: event.clientY - rect.top } : null)
      })
      .on('mouseleave', function (event, d) {
        d3.select(this)
          .attr('fill', getFill(d))
          .attr('stroke', C.countryBorder)
          .attr('stroke-width', 0.5)
          .style('filter', null)
        setTooltip(null)
      })

  }, [geo, data, width])

  // Legend values
  const vals   = Object.values(data).filter(v => typeof v === 'number')
  const minVal = vals.length ? Math.min(...vals) : 0
  const maxVal = vals.length ? Math.max(...vals) : 0

  return (
    <div
      ref={containerRef}
      style={{
        width, position: 'relative', userSelect: 'none',
        background: '#0a0e1a',
        borderRadius: '0 0 5px 5px',
        overflow: 'hidden',
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div style={{
        padding: '5px 14px 4px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span style={{
          fontFamily: 'Orbitron, monospace', fontSize: 9, fontWeight: 700,
          letterSpacing: 3.5, color: C.text,
          textShadow: '0 0 12px rgba(0,200,255,0.35)',
        }}>
          {title.toUpperCase()}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{
            width: 4, height: 4, borderRadius: '50%',
            background: '#00ffc8', boxShadow: '0 0 6px #00ffc8',
            animation: 'blink 2s ease-in-out infinite',
          }}/>
          <span style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 8, color: '#00ffc8', letterSpacing: 1.5 }}>
            LIVE
          </span>
        </div>
      </div>

      {/* ── Map area ───────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', height: MAP_H, background: C.ocean, overflow: 'hidden' }}>

        {loading && (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: 'Share Tech Mono, monospace', fontSize: 10,
            color: 'rgba(0,180,255,0.38)', letterSpacing: 2,
          }}>
            LOADING SATELLITE DATA...
          </div>
        )}

        <svg ref={svgRef} width={width} height={MAP_H} style={{ display: 'block' }}/>

        {/* Scanline overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.065) 3px, rgba(0,0,0,0.065) 4px)',
        }}/>

        {/* HUD grid overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          backgroundImage: [
            'linear-gradient(rgba(0,160,255,0.022) 1px, transparent 1px)',
            'linear-gradient(90deg, rgba(0,160,255,0.022) 1px, transparent 1px)',
          ].join(','),
          backgroundSize: '55px 40px',
        }}/>

        {/* Vignette edge darkening */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.5) 100%)',
        }}/>

        {/* Coordinate corner labels */}
        {[
          { style: { top: 4, left: 6 },   label: '90°N' },
          { style: { bottom: 4, left: 6 }, label: '90°S' },
          { style: { top: 4, right: 6 },   label: '180°E' },
          { style: { bottom: 4, right: 6 },label: '180°W' },
        ].map(({ style, label }) => (
          <span key={label} style={{
            position: 'absolute', fontFamily: 'Share Tech Mono, monospace',
            fontSize: 7, color: 'rgba(0,120,190,0.32)', letterSpacing: 0.4,
            ...style,
          }}>{label}</span>
        ))}
      </div>

      {/* ── Legend ─────────────────────────────────────────────────────── */}
      {vals.length > 0 && (
        <div style={{
          padding: '5px 14px 6px',
          display: 'flex', alignItems: 'center', gap: 9,
          borderTop: '1px solid rgba(0,212,255,0.08)',
        }}>
          <span style={{
            fontFamily: 'Share Tech Mono, monospace', fontSize: 8,
            color: C.dimText, letterSpacing: 0.8, minWidth: 24, textAlign: 'right',
          }}>{minVal}</span>

          <div style={{
            flex: 1, height: 5, borderRadius: 3,
            background: `linear-gradient(90deg, ${C.dataLow}, ${C.dataHigh})`,
            boxShadow: '0 0 8px rgba(79,163,224,0.25)',
          }}/>

          <span style={{
            fontFamily: 'Share Tech Mono, monospace', fontSize: 8,
            color: C.dimText, letterSpacing: 0.8, minWidth: 24,
          }}>{maxVal}</span>

          <span style={{
            fontFamily: 'Share Tech Mono, monospace', fontSize: 7,
            color: 'rgba(0,100,160,0.38)', letterSpacing: 1,
            marginLeft: 4, whiteSpace: 'nowrap',
          }}>SIGNAL INTENSITY</span>
        </div>
      )}

      {/* ── Tooltip ────────────────────────────────────────────────────── */}
      {tooltip && (
        <div style={{
          position: 'absolute',
          left: Math.min(tooltip.x + 12, width - 160),
          top: Math.max(tooltip.y - 12, 4),
          background: 'rgba(3,10,28,0.97)',
          border: '1px solid rgba(0,212,255,0.4)',
          borderRadius: 3,
          padding: '5px 10px',
          pointerEvents: 'none',
          zIndex: 200,
          backdropFilter: 'blur(4px)',
          boxShadow: '0 2px 18px rgba(0,60,160,0.4)',
          minWidth: 110,
        }}>
          <div style={{
            fontFamily: 'Orbitron, monospace', fontSize: 8,
            color: 'rgba(0,212,255,0.92)', letterSpacing: 2, marginBottom: 4,
            whiteSpace: 'nowrap',
          }}>
            {tooltip.name.toUpperCase()}
          </div>
          {tooltip.val !== undefined ? (
            <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 11, letterSpacing: 1 }}>
              <span style={{ color: C.dimText, fontSize: 8 }}>SIGNAL  </span>
              <span style={{ color: C.dataHigh }}>{tooltip.val}</span>
            </div>
          ) : (
            <div style={{
              fontFamily: 'Share Tech Mono, monospace', fontSize: 9,
              color: 'rgba(0,100,160,0.45)', letterSpacing: 1,
            }}>NO DATA</div>
          )}
        </div>
      )}
    </div>
  )
}

export default WorldMapPanel
