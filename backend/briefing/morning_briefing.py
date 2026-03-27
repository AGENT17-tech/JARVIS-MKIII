"""
JARVIS-MKIII — briefing/morning_briefing.py
Morning briefing system.

Aggregates weather, calendar, missions, and news into a single spoken+visual
briefing delivered via TTS, HUD, terminal, and hindsight memory.

Auto-runs once per day on startup (date comparison, not time).
"""
from __future__ import annotations
import asyncio, datetime, json, os
from pathlib import Path

# ── Concurrency guard — prevents duplicate briefing runs on startup ────────────
_briefing_lock = asyncio.Lock()

# Read GROQ key at import time (service env is fully loaded here, not lazily later)
_GROQ_KEY = os.getenv("GROQ_API_KEY", "")

_DATA_DIR = Path(__file__).parent.parent / "data"
_LAST_RUN = _DATA_DIR / "briefing_last_run.json"

# ── WMO weather code → human label ───────────────────────────────────────────

_WMO_LABELS: dict[int, str] = {
    0:  "clear",
    1:  "mainly clear",
    2:  "partly cloudy",
    3:  "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "heavy rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "heavy thunderstorm",
}


def _weathercode_label(code: int) -> str:
    return _WMO_LABELS.get(code, f"code {code}")


# ── Data fetchers — each wrapped in try/except, never raises ─────────────────

async def _fetch_weather() -> dict:
    """Fetch current Cairo weather from Open-Meteo (no API key required)."""
    try:
        import httpx
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=30.0444&longitude=31.2357"
            "&current=temperature_2m,weathercode"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        data    = resp.json()
        current = data["current"]
        temp    = round(current["temperature_2m"])
        code    = int(current["weathercode"])
        return {"temp": temp, "condition": _weathercode_label(code)}
    except Exception as e:
        print(f"[BRIEFING] Weather fetch failed: {e}")
        return {"temp": "data unavailable", "condition": ""}


async def _fetch_calendar() -> list[dict]:
    """Fetch today's Google Calendar events."""
    try:
        from config.google_calendar import get_today_events, is_configured
        if not is_configured():
            return []
        events = await asyncio.to_thread(get_today_events)
        return events or []
    except Exception as e:
        print(f"[BRIEFING] Calendar fetch failed: {e}")
        return []


def _count_active_missions() -> int | str:
    """Count active (pending + in_progress) missions from SQLite."""
    try:
        import sqlite3
        from core.mission_board import DB_PATH
        if not DB_PATH.exists():
            return "mission data unavailable"
        conn  = sqlite3.connect(str(DB_PATH))
        cur   = conn.execute(
            "SELECT COUNT(*) FROM missions WHERE status IN ('pending','in_progress')"
        )
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"[BRIEFING] Mission count failed: {e}")
        return "mission data unavailable"


def _text_fallback(headline: str) -> str:
    """Clean a headline without LLM: strip non-ASCII, punctuation symbols, truncate."""
    import re as _re
    text = headline.encode('ascii', 'ignore').decode('ascii')
    text = _re.sub(r'[^\w\s,.\'-]', ' ', text)   # remove symbols except basic punct
    text = _re.sub(r'\s+', ' ', text).strip()
    words = text.split()
    if len(words) > 12:
        text = ' '.join(words[:12])
    if text and not text.endswith('.'):
        text += '.'
    return text


def _get_groq_key() -> str:
    """Resolve GROQ_API_KEY: module-level cache first, then live env, then vault."""
    return _GROQ_KEY or os.getenv("GROQ_API_KEY", "")


async def _summarize_headline(headline: str) -> str:
    """Pass a raw headline through Groq directly."""
    import httpx
    api_key = _get_groq_key()
    if not api_key:
        print("[BRIEFING] No GROQ_API_KEY available — using text fallback for headline")
        return _text_fallback(headline)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You output only one plain spoken sentence, maximum 12 words. No markdown, no symbols, no emojis, no colons, no dashes."},
                        {"role": "user", "content": f"Convert this news headline into one short spoken sentence. No symbols, no emojis, no asterisks, no punctuation except periods. Plain speech only. Max 12 words. Headline: {headline}"}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.3
                }
            )
            data = r.json()
            result = data["choices"][0]["message"]["content"].strip()
            if result:
                return result
    except Exception as e:
        print(f"[BRIEFING] Headline summarization failed ({type(e).__name__}: {e}) — using text fallback")
    return _text_fallback(headline)


async def _fetch_news() -> list[str]:
    """
    Fetch top 3 headlines, then summarize each to one spoken sentence via LLM.
    Primary: RSS feeds. Fallback: DuckDuckGo.
    """
    raw: list[str] = []

    try:
        from voice.news import fetch_feed, FEEDS
        results = await asyncio.gather(
            fetch_feed(FEEDS["tech"],   max_items=1),
            fetch_feed(FEEDS["world"],  max_items=1),
            fetch_feed(FEEDS["egypt"],  max_items=1),
        )
        for feed_results in results:
            raw.extend(feed_results)
        raw = raw[:3]
    except Exception:
        pass

    if not raw:
        try:
            from mcp.mcp_hub import ddg_raw
            results = await ddg_raw("Egypt tech news today", count=5, news=True)
            raw = [r["title"] for r in results if r.get("title")][:3]
            if not raw:
                results = await ddg_raw("world news today", count=5, news=True)
                raw = [r["title"] for r in results if r.get("title")][:3]
        except Exception as e:
            print(f"[BRIEFING] News fetch failed: {e}")
            return []

    # Summarize each headline concurrently
    summarized = await asyncio.gather(*(_summarize_headline(h) for h in raw))
    return list(summarized)


# ── Event time helpers ────────────────────────────────────────────────────────

def _fmt_event_time(time_str: str) -> str:
    """Convert 'HH:MM' (24-hour) to '10:30 AM' format."""
    if time_str in ("All day", "all day", ""):
        return "all day"
    try:
        h, m   = map(int, time_str.split(":"))
        period = "AM" if h < 12 else "PM"
        h12    = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except Exception:
        return time_str


# ── Main briefing assembly ────────────────────────────────────────────────────

async def run_briefing() -> dict:
    """
    Gather all data sources, compose the spoken briefing string, deliver via
    TTS + HUD + terminal + memory, and persist the result.

    Returns the full briefing dict (also written to data/briefing_last_run.json).
    Always produces a partial result even if individual sources fail.
    """
    now     = datetime.datetime.now()
    weekday = now.strftime("%A")
    month   = now.strftime("%B")
    day     = now.day

    print(f"[BRIEFING] Running morning briefing for {now.strftime('%Y-%m-%d')}...")

    # Gather all async sources concurrently
    weather_data, events, news_headlines = await asyncio.gather(
        _fetch_weather(),
        _fetch_calendar(),
        _fetch_news(),
    )
    # Missions is synchronous DB access
    mission_count = await asyncio.to_thread(_count_active_missions)

    # ── Weather ───────────────────────────────────────────────────────────────
    temp      = weather_data.get("temp", "data unavailable")
    condition = weather_data.get("condition", "")
    if condition:
        weather_str = f"{temp} degrees, {condition}"
    else:
        weather_str = str(temp)

    # ── Calendar ──────────────────────────────────────────────────────────────
    n_events = len(events)
    if n_events == 0:
        calendar_spoken = "You have no events scheduled today"
    else:
        event_parts = []
        for ev in events[:2]:
            title    = ev.get("title", "event")
            time_fmt = _fmt_event_time(ev.get("time", ""))
            event_parts.append(f"{title} at {time_fmt}")
        joined = ", ".join(event_parts)
        calendar_spoken = f"You have {n_events} event{'s' if n_events != 1 else ''} today: {joined}"

    # ── Missions ──────────────────────────────────────────────────────────────
    if isinstance(mission_count, str):
        mission_spoken = mission_count
    else:
        plural = "s" if mission_count != 1 else ""
        mission_spoken = f"{mission_count} active mission{plural} on the board"

    # ── News ──────────────────────────────────────────────────────────────────
    while len(news_headlines) < 3:
        news_headlines.append("data unavailable")
    h1 = news_headlines[0].rstrip(". ")
    h2 = news_headlines[1].rstrip(". ")
    h3 = news_headlines[2].rstrip(". ")

    # ── PHANTOM ZERO domain addendum ─────────────────────────────────────────
    _phantom_addendum = ""
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _phantom_root = _Path(__file__).parent.parent.parent / "phantom"
        if str(_phantom_root.parent) not in _sys.path:
            _sys.path.insert(0, str(_phantom_root.parent))
        from phantom.phantom_os import get_phantom as _get_phantom
        _phantom_addendum = _get_phantom().generate_daily_brief_addendum()
    except Exception as _pe:
        print(f"[BRIEFING] Phantom addendum failed: {_pe}")

    # ── Spoken string (sanitized — no emojis, no markdown) ───────────────────
    from core.text_sanitizer import sanitize_for_tts
    spoken = sanitize_for_tts(
        f"Good morning sir. It is {weekday} {month} {day}. "
        f"Weather in Cairo is {weather_str}. "
        f"{calendar_spoken}. "
        f"{mission_spoken}. "
        f"Top news: {h1}. {h2}. {h3}."
        + (f" {_phantom_addendum}" if _phantom_addendum else "")
    )

    # ── Briefing dict ─────────────────────────────────────────────────────────
    briefing_dict = {
        "spoken":        spoken,
        "date":          now.strftime("%Y-%m-%d"),
        "time":          now.strftime("%H:%M"),
        "weekday":       weekday,
        "weather":       weather_data,
        "events":        [{"title": e.get("title"), "time": e.get("time")} for e in events],
        "mission_count": mission_count,
        "news":          news_headlines[:3],
        "timestamp":     now.isoformat(),
    }

    # ── Terminal output ───────────────────────────────────────────────────────
    print(f"\n{'='*62}")
    print(f"  JARVIS MORNING BRIEFING  —  {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*62}")
    print(spoken)
    print(f"{'='*62}\n")

    # ── TTS ───────────────────────────────────────────────────────────────────
    # TTS is delivered by the voice orchestrator after it reads the cached
    # briefing_last_run.json on startup (see voice_orchestrator._speak_greeting).
    # request_speak is only used here when the orchestrator is already connected
    # (e.g. manual /briefing/run from the HUD).
    try:
        from api.voice_bridge import request_speak, _voice_ws as _vws
        if _vws is not None:
            await request_speak(spoken)
        else:
            print("[BRIEFING] Voice orchestrator not connected — TTS will be picked up on boot.")
    except Exception as e:
        print(f"[BRIEFING] TTS delivery failed: {e}")

    # ── HUD event ─────────────────────────────────────────────────────────────
    try:
        from api.voice_bridge import broadcast_to_hud
        await broadcast_to_hud({"type": "briefing", "payload": briefing_dict})
    except Exception as e:
        print(f"[BRIEFING] HUD broadcast failed: {e}")

    # ── Hindsight memory ──────────────────────────────────────────────────────
    try:
        from memory.hindsight import memory
        memory.consolidate(
            "briefing",
            spoken,
            ["briefing", "daily", weekday.lower(), month.lower()],
        )
    except Exception as e:
        print(f"[BRIEFING] Memory store failed: {e}")

    # ── TouchDesigner weather event ───────────────────────────────────────────
    try:
        from integrations.touchdesigner_bridge import on_briefing_weather
        on_briefing_weather(
            weather_data.get("temp", 0),
            weather_data.get("condition", ""),
        )
    except Exception:
        pass

    # ── RAG long-term memory ──────────────────────────────────────────────────
    try:
        from memory.rag_memory import get_rag
        get_rag().store_fact(
            f"Morning briefing on {now.strftime('%Y-%m-%d')}: {spoken}",
            source="briefing",
            tags=["briefing", "daily", weekday.lower(), month.lower()],
        )
    except Exception as e:
        print(f"[BRIEFING] RAG store failed: {e}")

    # ── Persist last-run record ───────────────────────────────────────────────
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _LAST_RUN.write_text(json.dumps(briefing_dict, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[BRIEFING] Failed to write {_LAST_RUN}: {e}")

    print(f"[BRIEFING] Done.")
    return briefing_dict


# ── Cache reader for voice orchestrator ──────────────────────────────────────

def get_today_spoken_briefing() -> str:
    """
    Return today's pre-generated spoken briefing text from the cache, or empty
    string if no briefing has been generated yet for today.

    Called by the voice orchestrator after TTS is ready so it can speak the
    comprehensive briefing (weather + calendar + news + missions) directly
    through Kokoro without a network round-trip.
    """
    today = datetime.date.today().isoformat()
    try:
        if _LAST_RUN.exists():
            data = json.loads(_LAST_RUN.read_text())
            if data.get("date") == today:
                return data.get("spoken", "")
    except Exception:
        pass
    return ""


# ── Auto-run guard ────────────────────────────────────────────────────────────

async def auto_run_if_new_day() -> None:
    """
    Called from the startup hook in main.py lifespan.
    Runs the full briefing only if it has not already run today.
    Silently skips if already ran today.
    Lock ensures only one instance runs even when called concurrently on boot.
    """
    if _briefing_lock.locked():
        print("[BRIEFING] Another instance is already running — skipping.")
        return
    async with _briefing_lock:
        today = datetime.date.today().isoformat()
        try:
            if _LAST_RUN.exists():
                data = json.loads(_LAST_RUN.read_text())
                if data.get("date") == today:
                    print(f"[BRIEFING] Already ran today ({today}) — skipping auto briefing.")
                    return
        except Exception:
            pass  # Corrupt file or missing → run the briefing anyway

        print(f"[BRIEFING] New day ({today}) — auto-running morning briefing...")
        await run_briefing()
