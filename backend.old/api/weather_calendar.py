"""
JARVIS-MKIII — weather_calendar.py
Provides real-time weather and calendar data endpoints.
Add to api/main.py with:
    from api.weather_calendar import weather_router
    app.include_router(weather_router)
"""

from __future__ import annotations
import httpx
import datetime
from fastapi import APIRouter
from core.vault import Vault

weather_router = APIRouter()
_vault = Vault()

# Cairo coordinates — update if needed
LAT = 30.0444
LON = 31.2357
CITY = "Cairo"


def _get_weather_key() -> str:
    import os
    return os.environ.get("OPENWEATHER_API_KEY") or _vault.get("OPENWEATHER_API_KEY")


@weather_router.get("/weather")
async def get_weather():
    """Real-time weather from OpenWeatherMap."""
    try:
        key = _get_weather_key()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "lat": LAT, "lon": LON,
                    "appid": key,
                    "units": "metric",
                }
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "temp":      round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "humidity":  data["main"]["humidity"],
            "condition": data["weather"][0]["description"].title(),
            "icon":      data["weather"][0]["icon"],
            "wind":      round(data["wind"]["speed"] * 3.6),  # m/s → km/h
            "city":      CITY,
            "sunrise":   data["sys"]["sunrise"],
            "sunset":    data["sys"]["sunset"],
            "error":     None,
        }
    except Exception as e:
        return {"error": str(e), "temp": None, "condition": None}


@weather_router.get("/calendar")
async def get_calendar():
    """Current date, time, and calendar context."""
    now = datetime.datetime.now()

    # Day of year and week number
    day_of_year  = now.timetuple().tm_yday
    week_number  = now.isocalendar()[1]
    days_in_month = (datetime.date(now.year, now.month % 12 + 1, 1) -
                     datetime.timedelta(days=1)).day if now.month != 12 else 31

    return {
        "time":          now.strftime("%H:%M:%S"),
        "time_12":       now.strftime("%I:%M %p"),
        "date":          now.strftime("%Y-%m-%d"),
        "day":           now.strftime("%A"),
        "day_short":     now.strftime("%a"),
        "month":         now.strftime("%B"),
        "month_short":   now.strftime("%b"),
        "month_num":     now.month,
        "year":          now.year,
        "day_of_month":  now.day,
        "day_of_year":   day_of_year,
        "week_number":   week_number,
        "days_in_month": days_in_month,
        "quarter":       f"Q{(now.month - 1) // 3 + 1}",
        "timestamp":     now.isoformat(),
    }


@weather_router.get("/forecast")
async def get_forecast():
    """5-day weather forecast."""
    try:
        key = _get_weather_key()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={
                    "lat": LAT, "lon": LON,
                    "appid": key,
                    "units": "metric",
                    "cnt": 5,
                }
            )
            resp.raise_for_status()
            data = resp.json()

        days = []
        for item in data["list"]:
            dt = datetime.datetime.fromtimestamp(item["dt"])
            days.append({
                "day":       dt.strftime("%a"),
                "date":      dt.strftime("%d %b"),
                "temp_max":  round(item["main"]["temp_max"]),
                "temp_min":  round(item["main"]["temp_min"]),
                "condition": item["weather"][0]["description"].title(),
                "icon":      item["weather"][0]["icon"],
            })
        return {"forecast": days, "error": None}
    except Exception as e:
        return {"forecast": [], "error": str(e)}
