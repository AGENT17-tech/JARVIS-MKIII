"""
JARVIS-MKIII — config/google_calendar.py
Google Calendar API integration via OAuth2.

OAuth flow:
  - credentials.json  → OAuth2 client credentials (from Google Cloud Console)
  - token.json        → cached access/refresh token (generated on first auth)

First run: call `authenticate()` in a terminal — it opens the browser once.
Subsequent calls: token auto-refreshes silently.
"""
from __future__ import annotations
import os, datetime
from pathlib import Path
from typing import List, Dict, Any

# ── Paths ──────────────────────────────────────────────────────────────────────
_CONFIG_DIR    = Path(__file__).parent
CREDENTIALS    = _CONFIG_DIR / "credentials.json"
TOKEN_PATH     = _CONFIG_DIR / "token.json"

# Google Calendar API scope (read-only)
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _get_credentials():
    """Return valid Google OAuth2 credentials, refreshing if necessary."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDENTIALS}. "
                    "Download OAuth2 credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def is_configured() -> bool:
    """Returns True if credentials.json exists (token.json optional — will be created)."""
    return CREDENTIALS.exists()


# ── Event fetching ─────────────────────────────────────────────────────────────

def get_today_events() -> List[Dict[str, Any]]:
    """
    Fetch today's Google Calendar events (primary calendar).
    Returns list of dicts: {time, title, type, color, start_dt, end_dt, location}
    Raises on auth failure.
    """
    from googleapiclient.discovery import build

    creds   = _get_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now   = datetime.datetime.utcnow()
    start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0).isoformat() + "Z"
    end   = datetime.datetime(now.year, now.month, now.day, 23, 59, 59).isoformat() + "Z"

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = result.get("items", [])
    return [_parse_event(e) for e in events]


def get_upcoming_events(minutes_ahead: int = 30) -> List[Dict[str, Any]]:
    """
    Fetch events starting within the next `minutes_ahead` minutes.
    Used by the proactive engine for reminders.
    """
    from googleapiclient.discovery import build

    creds   = _get_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.datetime.utcnow()
    window_end = now + datetime.timedelta(minutes=minutes_ahead)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=window_end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = result.get("items", [])
    return [_parse_event(e) for e in events]


# ── Event parser ───────────────────────────────────────────────────────────────

_EVENT_COLORS = {
    "meeting":  "#00ffc8",
    "call":     "#00ffc8",
    "standup":  "#00ffc8",
    "sync":     "#00ffc8",
    "interview":"#ff6644",
    "gym":      "#ffb900",
    "workout":  "#ffb900",
    "fitness":  "#ffb900",
    "focus":    "#aa88ff",
    "deep":     "#aa88ff",
    "work":     "#00d4ff",
    "default":  "#00d4ff",
}

_EVENT_TYPES = {
    "meeting":   "MEETING",
    "call":      "MEETING",
    "standup":   "MEETING",
    "sync":      "MEETING",
    "interview": "MEETING",
    "gym":       "FITNESS",
    "workout":   "FITNESS",
    "fitness":   "FITNESS",
    "focus":     "FOCUS",
    "deep work": "FOCUS",
    "study":     "FOCUS",
    "work":      "WORK",
}


def _parse_event(event: dict) -> Dict[str, Any]:
    title    = event.get("summary", "Untitled Event")
    location = event.get("location", "")

    start_raw = event["start"].get("dateTime", event["start"].get("date", ""))
    end_raw   = event["end"].get("dateTime",   event["end"].get("date",   ""))

    # Parse start time
    if "T" in start_raw:
        # Full datetime (non all-day)
        start_dt = datetime.datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        # Convert to local time (naive, drop tz info for display)
        try:
            import zoneinfo
            local_tz = zoneinfo.ZoneInfo("Africa/Cairo")
            start_local = start_dt.astimezone(local_tz)
        except Exception:
            start_local = start_dt
        time_str = start_local.strftime("%H:%M")
        is_all_day = False
    else:
        # All-day event
        start_dt    = datetime.datetime.fromisoformat(start_raw)
        start_local = start_dt
        time_str    = "All day"
        is_all_day  = True

    # Parse end time
    if "T" in end_raw:
        end_dt = datetime.datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        try:
            end_dt = end_dt.astimezone(local_tz)
        except Exception:
            pass
    else:
        end_dt = datetime.datetime.fromisoformat(end_raw)

    # Classify type and color
    title_lower = title.lower()
    event_type  = "WORK"
    color       = _EVENT_COLORS["default"]
    for keyword, etype in _EVENT_TYPES.items():
        if keyword in title_lower:
            event_type = etype
            break
    for keyword, clr in _EVENT_COLORS.items():
        if keyword in title_lower:
            color = clr
            break

    return {
        "id":         event.get("id", ""),
        "time":       time_str,
        "title":      title,
        "type":       event_type,
        "color":      color,
        "location":   location,
        "is_all_day": is_all_day,
        "start_iso":  start_raw,
        "end_iso":    end_raw,
        # Stored as datetime objects for proactive engine comparisons
        "_start_dt":  start_local,
        "_end_dt":    end_dt,
    }
