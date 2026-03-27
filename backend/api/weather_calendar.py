"""
JARVIS-MKIII — weather_calendar.py
Endpoints: /weather  /calendar  /forecast  /github  /gcal/events
"""

from __future__ import annotations
import httpx, datetime, os, asyncio
from fastapi import APIRouter
from core.vault import Vault
from config.settings import LAT, LON, CITY

GITHUB_USER = os.environ.get("GITHUB_USER", "Agent17-Tech")
GITHUB_REPOS_LIMIT = 6   # repos shown in HUD panel
GITHUB_COMMITS_LIMIT = 3  # recent commits per repo

weather_router = APIRouter()
_vault = Vault()
_github_cache: list = []
_github_last_ok: bool = False


def _github_headers() -> dict:
    try:
        token = _vault.get("GITHUB_TOKEN")
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    except Exception:
        return {"Accept": "application/vnd.github+json"}


_WEATHER_CODE_MAP = {
    0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy",
    3: "Overcast", 45: "Foggy", 48: "Foggy",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    80: "Rain Showers", 81: "Rain Showers", 82: "Heavy Showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}


@weather_router.get("/weather")
async def get_weather():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": LAT,
                    "longitude": LON,
                    "current": "temperature_2m,weathercode,relative_humidity_2m,windspeed_10m",
                    "timezone": "Africa/Cairo",
                }
            )
            resp.raise_for_status()
            data = resp.json()
        current = data["current"]
        code = current["weathercode"]
        return {
            "temp":      round(current["temperature_2m"]),
            "condition": _WEATHER_CODE_MAP.get(code, "Unknown"),
            "humidity":  current.get("relative_humidity_2m"),
            "windspeed": current.get("windspeed_10m"),
            "city":      CITY,
            "error":     None,
        }
    except Exception as e:
        return {"error": str(e), "temp": None, "condition": None}


@weather_router.get("/calendar")
async def get_calendar():
    now = datetime.datetime.now()
    days_in_month = (datetime.date(now.year, now.month % 12 + 1, 1) - datetime.timedelta(days=1)).day \
        if now.month != 12 else 31
    return {
        "time":          now.strftime("%H:%M:%S"),
        "date":          now.strftime("%Y-%m-%d"),
        "day":           now.strftime("%A"),
        "month":         now.strftime("%B"),
        "month_num":     now.month,
        "year":          now.year,
        "day_of_month":  now.day,
        "day_of_year":   now.timetuple().tm_yday,
        "week_number":   now.isocalendar()[1],
        "days_in_month": days_in_month,
        "quarter":       f"Q{(now.month - 1) // 3 + 1}",
    }


@weather_router.get("/gcal/events")
async def get_gcal_events():
    """Return today's Google Calendar events. Requires OAuth2 setup."""
    try:
        from config.google_calendar import get_today_events, is_configured
        if not is_configured():
            return {"events": [], "error": "Google Calendar not configured. Place credentials.json in backend/config/.", "configured": False}
        events = await asyncio.to_thread(get_today_events)
        # Strip internal datetime objects (not JSON-serialisable)
        clean = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]
        return {"events": clean, "error": None, "configured": True}
    except FileNotFoundError as e:
        return {"events": [], "error": str(e), "configured": False}
    except Exception as e:
        return {"events": [], "error": str(e), "configured": True}


@weather_router.get("/forecast")
async def get_forecast():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": LAT,
                    "longitude": LON,
                    "daily": "weathercode,temperature_2m_max,temperature_2m_min",
                    "timezone": "Africa/Cairo",
                    "forecast_days": 5,
                }
            )
            resp.raise_for_status()
            data = resp.json()
        daily = data["daily"]
        days = []
        for i in range(len(daily["time"])):
            dt = datetime.date.fromisoformat(daily["time"][i])
            code = daily["weathercode"][i]
            days.append({
                "day":       dt.strftime("%a"),
                "date":      dt.strftime("%d %b"),
                "temp_max":  round(daily["temperature_2m_max"][i]),
                "temp_min":  round(daily["temperature_2m_min"][i]),
                "condition": _WEATHER_CODE_MAP.get(code, "Unknown"),
            })
        return {"forecast": days, "error": None}
    except Exception as e:
        return {"forecast": [], "error": str(e)}


@weather_router.get("/github")
async def get_github():
    global _github_cache, _github_last_ok
    headers = _github_headers()
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            repos_resp = await client.get(
                f"https://api.github.com/users/{GITHUB_USER}/repos",
                params={"sort": "pushed", "per_page": GITHUB_REPOS_LIMIT}
            )
            repos_resp.raise_for_status()
            repos_data = repos_resp.json()

        result = []
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            for repo in repos_data:
                commits_resp = await client.get(
                    f"https://api.github.com/repos/{GITHUB_USER}/{repo['name']}/commits",
                    params={"per_page": GITHUB_COMMITS_LIMIT}
                )
                commits = []
                if commits_resp.status_code == 200:
                    for c in commits_resp.json():
                        commits.append({
                            "sha":     c["sha"][:7],
                            "message": c["commit"]["message"].split("\n")[0][:60],
                            "date":    c["commit"]["author"]["date"][:10],
                        })
                result.append({
                    "name":     repo["name"],
                    "language": repo.get("language"),
                    "commits":  commits,
                })
        _github_cache = result
        _github_last_ok = True
        return result
    except Exception:
        _github_last_ok = False
        return _github_cache
