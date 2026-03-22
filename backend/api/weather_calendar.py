"""
JARVIS-MKIII — weather_calendar.py
Endpoints: /weather  /calendar  /forecast  /github
"""

from __future__ import annotations
import httpx, datetime, os
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


def _weather_key() -> str:
    return _vault.get("OPENWEATHER_API_KEY")


def _github_headers() -> dict:
    try:
        token = _vault.get("GITHUB_TOKEN")
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    except Exception:
        return {"Accept": "application/vnd.github+json"}


@weather_router.get("/weather")
async def get_weather():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"lat": LAT, "lon": LON, "appid": _weather_key(), "units": "metric"}
            )
            resp.raise_for_status()
            d = resp.json()
        return {
            "temp":       round(d["main"]["temp"]),
            "feels_like": round(d["main"]["feels_like"]),
            "humidity":   d["main"]["humidity"],
            "condition":  d["weather"][0]["description"].title(),
            "icon":       d["weather"][0]["icon"],
            "wind":       round(d["wind"]["speed"] * 3.6),
            "city":       CITY,
            "error":      None,
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


@weather_router.get("/forecast")
async def get_forecast():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"lat": LAT, "lon": LON, "appid": _weather_key(), "units": "metric", "cnt": 5}
            )
            resp.raise_for_status()
            data = resp.json()
        days = []
        for item in data["list"]:
            dt = datetime.datetime.fromtimestamp(item["dt"])
            days.append({
                "day":      dt.strftime("%a"),
                "date":     dt.strftime("%d %b"),
                "temp_max": round(item["main"]["temp_max"]),
                "temp_min": round(item["main"]["temp_min"]),
                "condition":item["weather"][0]["description"].title(),
                "icon":     item["weather"][0]["icon"],
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
