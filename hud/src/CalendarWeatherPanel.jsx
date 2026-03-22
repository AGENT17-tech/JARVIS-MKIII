import { useState, useEffect } from 'react'

const API = 'http://localhost:8000'

const WEATHER_ICONS = {
  '01d': '☀️', '01n': '🌙',
  '02d': '⛅', '02n': '⛅',
  '03d': '☁️', '03n': '☁️',
  '04d': '☁️', '04n': '☁️',
  '09d': '🌧️', '09n': '🌧️',
  '10d': '🌦️', '10n': '🌦️',
  '11d': '⛈️', '11n': '⛈️',
  '13d': '❄️', '13n': '❄️',
  '50d': '🌫️', '50n': '🌫️',
}

const S = {
  panel: {
    background: 'rgba(0,7,22,0.88)',
    border: '1px solid rgba(0,212,255,0.2)',
    borderRadius: 3,
    padding: '14px 18px',
    width: '100%',
    backdropFilter: 'blur(6px)',
    boxShadow: '0 0 22px rgba(0,80,180,0.08),inset 0 1px 0 rgba(0,212,255,0.07)',
  },
  title: {
    fontFamily: 'Orbitron',
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: 3.5,
    color: 'rgba(0,200,255,0.9)',
    marginBottom: 13,
    textShadow: '0 0 12px rgba(0,200,255,0.35)',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  label: {
    fontFamily: 'Share Tech Mono',
    fontSize: 10,
    color: 'rgba(0,140,200,0.52)',
    letterSpacing: 1.2,
  },
  value: {
    fontFamily: 'Share Tech Mono',
    fontSize: 11,
    color: 'rgba(0,212,255,0.92)',
    textShadow: '0 0 8px rgba(0,212,255,0.3)',
  },
  divider: {
    width: '100%',
    height: 1,
    background: 'linear-gradient(90deg,transparent,rgba(0,212,255,0.2),transparent)',
    margin: '10px 0',
  },
  bigTime: {
    fontFamily: 'Orbitron',
    fontSize: 32,
    fontWeight: 700,
    color: 'rgba(0,220,255,0.97)',
    textShadow: '0 0 24px rgba(0,212,255,0.5)',
    letterSpacing: 3,
    lineHeight: 1,
    marginBottom: 4,
  },
  bigDate: {
    fontFamily: 'Share Tech Mono',
    fontSize: 11,
    color: 'rgba(0,180,255,0.8)',
    letterSpacing: 1.5,
    marginBottom: 2,
  },
  sub: {
    fontFamily: 'Share Tech Mono',
    fontSize: 9,
    color: 'rgba(0,140,200,0.52)',
    letterSpacing: 1,
  },
  barBg: {
    width: '100%',
    height: 2,
    background: 'rgba(0,120,220,0.12)',
    borderRadius: 2,
    overflow: 'hidden',
    marginTop: 3,
  },
}

// Mini calendar grid
const MiniCalendar = ({ cal }) => {
  if (!cal) return null
  const { day_of_month, days_in_month, month_short, year, day_short } = cal

  // Build weeks
  const firstDay = new Date(cal.year, cal.month_num - 1, 1).getDay()
  const cells = []
  for (let i = 0; i < firstDay; i++) cells.push(null)
  for (let i = 1; i <= days_in_month; i++) cells.push(i)
  while (cells.length % 7 !== 0) cells.push(null)

  const weeks = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        {['S','M','T','W','T','F','S'].map((d, i) => (
          <span key={i} style={{
            fontFamily: 'Share Tech Mono', fontSize: 8,
            color: 'rgba(0,140,200,0.45)', width: 24, textAlign: 'center',
          }}>{d}</span>
        ))}
      </div>
      {weeks.map((week, wi) => (
        <div key={wi} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          {week.map((day, di) => (
            <span key={di} style={{
              fontFamily: 'Share Tech Mono',
              fontSize: 9,
              width: 24,
              height: 18,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 2,
              background: day === day_of_month ? 'rgba(0,212,255,0.2)' : 'transparent',
              border: day === day_of_month ? '1px solid rgba(0,212,255,0.5)' : '1px solid transparent',
              color: day === day_of_month
                ? 'rgba(0,255,220,0.95)'
                : day ? 'rgba(0,180,255,0.55)' : 'transparent',
              textShadow: day === day_of_month ? '0 0 8px rgba(0,212,255,0.8)' : 'none',
            }}>{day || ''}</span>
          ))}
        </div>
      ))}
    </div>
  )
}

// Weather bar
const WeatherBar = ({ label, value, max, color }) => (
  <div style={{ marginBottom: 8 }}>
    <div style={S.row}>
      <span style={S.label}>{label}</span>
      <span style={{ ...S.value, color, fontSize: 10 }}>{value}</span>
    </div>
    {max && (
      <div style={S.barBg}>
        <div style={{
          height: '100%', borderRadius: 2,
          width: `${Math.min((parseInt(value) / max) * 100, 100)}%`,
          background: `linear-gradient(90deg,${color}88,${color})`,
          boxShadow: `0 0 6px ${color}`,
          transition: 'width 1s ease',
        }}/>
      </div>
    )}
  </div>
)

export default function CalendarWeatherPanel() {
  const [cal, setCal]             = useState(null)
  const [weather, setWeather]     = useState(null)
  const [weatherErr, setWeatherErr] = useState(false)
  const [time, setTime]           = useState(new Date())
  const [forecast, setForecast]   = useState([])

  // Live clock — updates every second
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // Calendar — updates every minute
  useEffect(() => {
    const fetch_cal = () => {
      fetch(`${API}/calendar`)
        .then(r => r.json())
        .then(d => setCal(d))
        .catch(() => {})
    }
    fetch_cal()
    const id = setInterval(fetch_cal, 60000)
    return () => clearInterval(id)
  }, [])

  // Weather — updates every 10 minutes
  useEffect(() => {
    const fetch_weather = () => {
      fetch(`${API}/weather`)
        .then(r => r.json())
        .then(d => {
          if (!d.error) { setWeather(d); setWeatherErr(false) }
          else setWeatherErr(true)
        })
        .catch(() => setWeatherErr(true))
    }
    fetch_weather()
    const id = setInterval(fetch_weather, 600000)
    return () => clearInterval(id)
  }, [])

  // Forecast — updates every 30 minutes
  useEffect(() => {
    const fetch_forecast = () => {
      fetch(`${API}/forecast`)
        .then(r => r.json())
        .then(d => { if (!d.error && d.forecast) setForecast(d.forecast) })
        .catch(() => {})
    }
    fetch_forecast()
    const id = setInterval(fetch_forecast, 1800000)
    return () => clearInterval(id)
  }, [])

  const fmt_time = d => d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const fmt_day  = d => d.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase()
  const fmt_date = d => d.toLocaleDateString('en-US', { day: 'numeric', month: 'long', year: 'numeric' })

  const temp_color = !weather ? '#00d4ff' :
    weather.temp > 35 ? '#ff3c3c' :
    weather.temp > 25 ? '#ffb900' :
    weather.temp < 10 ? '#00d4ff' : '#00ffc8'

  const icon = weather?.icon ? (WEATHER_ICONS[weather.icon] || '🌡️') : '🌡️'

  return (
    <div style={S.panel}>

      {/* ── CLOCK ── */}
      <div style={S.title}>CHRONOS — CAIRO OPS</div>
      <div style={S.bigTime}>{fmt_time(time)}</div>
      <div style={S.bigDate}>{fmt_day(time)}</div>
      <div style={S.sub}>{fmt_date(time)}</div>

      {cal && (
        <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
          {[
            { l: 'WEEK',    v: `W${cal.week_number}` },
            { l: 'DAY',     v: `D${cal.day_of_year}` },
            { l: 'QUARTER', v: cal.quarter },
          ].map(item => (
            <div key={item.l} style={{ textAlign: 'center', flex: 1 }}>
              <div style={S.label}>{item.l}</div>
              <div style={{ ...S.value, fontSize: 13, color: '#00ffc8' }}>{item.v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={S.divider}/>

      {/* ── MINI CALENDAR ── */}
      <div style={{ ...S.title, marginBottom: 8 }}>
        {cal ? `${cal.month.toUpperCase()} ${cal.year}` : 'CALENDAR'}
      </div>
      <MiniCalendar cal={cal}/>

      <div style={S.divider}/>

      {/* ── WEATHER ── */}
      <div style={{ ...S.title, marginBottom: 10 }}>WEATHER — CAIRO</div>

      {weather ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{ fontSize: 32 }}>{icon}</span>
            <div>
              <div style={{ fontFamily: 'Orbitron', fontSize: 26, fontWeight: 700, color: temp_color, textShadow: `0 0 16px ${temp_color}`, lineHeight: 1 }}>
                {weather.temp}°C
              </div>
              <div style={{ ...S.sub, marginTop: 2 }}>{weather.condition}</div>
            </div>
          </div>

          <WeatherBar label="FEELS LIKE" value={`${weather.feels_like}°C`} color={temp_color}/>
          <WeatherBar label="HUMIDITY"   value={`${weather.humidity}%`}    max={100} color="#00d4ff"/>
          <WeatherBar label="WIND"       value={`${weather.wind} km/h`}    max={120} color="#a78bfa"/>

          {forecast.length > 0 && (
            <>
              <div style={S.divider}/>
              <div style={{ ...S.title, marginBottom: 8 }}>FORECAST</div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                {forecast.map((f, i) => (
                  <div key={i} style={{ textAlign: 'center', flex: 1 }}>
                    <div style={S.label}>{f.day}</div>
                    <div style={{ fontSize: 14, margin: '3px 0' }}>{WEATHER_ICONS[f.icon] || '🌡️'}</div>
                    <div style={{ fontFamily: 'Share Tech Mono', fontSize: 9, color: '#ffb900' }}>{f.temp_max}°</div>
                    <div style={{ fontFamily: 'Share Tech Mono', fontSize: 8, color: 'rgba(0,140,200,0.5)' }}>{f.temp_min}°</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      ) : (
        <div style={{ ...S.label, fontSize: 9, color: weatherErr ? 'rgba(255,80,80,0.55)' : 'rgba(0,140,200,0.52)' }}>
          {weatherErr ? '⚠ WEATHER UPLINK OFFLINE' : 'FETCHING WEATHER DATA...'}
        </div>
      )}
    </div>
  )
}
