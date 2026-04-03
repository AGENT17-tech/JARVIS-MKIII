"""
JARVIS-MKIII — core/time_parser.py
Natural language time expression → structured schedule descriptor.

Handles:
  "at 3pm"                   → once at 15:00 today (or tomorrow if past)
  "in 20 minutes"            → once, now + 20 min
  "tomorrow at noon"         → once at 12:00 tomorrow
  "every morning at 7"       → cron "0 7 * * *"
  "every day at 9am"         → cron "0 9 * * *"
  "every Monday at 9am"      → cron "0 9 * * 1"
  "every hour"               → interval 60 minutes
  "every 30 minutes"         → interval 30 minutes

Returns:
  {
    "type":     "once" | "cron" | "interval",
    "run_at":   datetime | None,   # for type=="once"
    "cron":     str | None,        # cron expression, for type=="cron"
    "interval_minutes": int | None # for type=="interval"
  }
  or None if unparseable.
"""

from __future__ import annotations
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_DAY_MAP = {
    "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
    "friday": 5, "saturday": 6, "sunday": 0,
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 0,
}

_MORNING_HOUR  = 7
_NOON_HOUR     = 12
_EVENING_HOUR  = 18
_MIDNIGHT_HOUR = 0


def _parse_clock(text: str) -> int | None:
    """
    Extract a 24h hour integer from a time phrase like "3pm", "7am",
    "14:30", "noon", "midnight", "morning", "evening".
    Returns the hour (0-23) or None.
    """
    text = text.strip().lower()
    if text in ("noon", "midday"):
        return _NOON_HOUR
    if text == "midnight":
        return _MIDNIGHT_HOUR
    if text in ("morning",):
        return _MORNING_HOUR
    if text in ("evening", "night"):
        return _EVENING_HOUR

    # "HH:MM am/pm" or "H am/pm" or "Ham"
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not m:
        return None
    hour   = int(m.group(1))
    ampm   = m.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return hour if 0 <= hour <= 23 else None


def parse_time_expression(expr: str) -> dict | None:
    """
    Parse a natural-language scheduling expression.
    Returns a schedule descriptor dict or None if unparseable.
    """
    text = expr.strip().lower()
    now  = datetime.now()

    # ── "in N minutes/hours" → one-shot ──────────────────────────────────────
    m = re.search(r"in\s+(\d+)\s+(minute|min|hour|hr)s?", text)
    if m:
        qty  = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(hours=qty) if unit.startswith("h") else timedelta(minutes=qty)
        return {"type": "once", "run_at": now + delta, "cron": None, "interval_minutes": None}

    # ── "every N minutes/hours" → interval ───────────────────────────────────
    m = re.search(r"every\s+(\d+)\s+(minute|min|hour|hr)s?", text)
    if m:
        qty  = int(m.group(1))
        unit = m.group(2)
        mins = qty * 60 if unit.startswith("h") else qty
        return {"type": "interval", "run_at": None, "cron": None, "interval_minutes": mins}

    # ── "every hour" → interval 60 ───────────────────────────────────────────
    if re.search(r"\bevery\s+hour\b", text):
        return {"type": "interval", "run_at": None, "cron": None, "interval_minutes": 60}

    # ── "every morning" / "every day at HH" / "every evening" → cron ─────────
    m = re.search(r"every\s+(morning|noon|evening|night|day|night|midnight)", text)
    if m:
        tod  = m.group(1)
        hour = _parse_clock(tod) or _MORNING_HOUR
        # look for "at <time>" override
        at_m = re.search(r"at\s+([\w:]+)", text)
        if at_m:
            h2 = _parse_clock(at_m.group(1))
            if h2 is not None:
                hour = h2
        cron = f"0 {hour} * * *"
        return {"type": "cron", "run_at": None, "cron": cron, "interval_minutes": None}

    # ── "every day at HH" (generic) ───────────────────────────────────────────
    m = re.search(r"every\s+day\s+at\s+([\w:]+)", text)
    if m:
        hour = _parse_clock(m.group(1))
        if hour is not None:
            return {"type": "cron", "run_at": None, "cron": f"0 {hour} * * *", "interval_minutes": None}

    # ── "every <weekday> at HH" ───────────────────────────────────────────────
    for day_name, day_num in _DAY_MAP.items():
        if day_name in text:
            at_m = re.search(r"at\s+([\w:]+)", text)
            hour = _parse_clock(at_m.group(1)) if at_m else _MORNING_HOUR
            if hour is None:
                hour = _MORNING_HOUR
            cron = f"0 {hour} * * {day_num}"
            return {"type": "cron", "run_at": None, "cron": cron, "interval_minutes": None}

    # ── "tomorrow at HH" ─────────────────────────────────────────────────────
    if "tomorrow" in text:
        at_m = re.search(r"at\s+([\w:]+)", text)
        hour = _parse_clock(at_m.group(1)) if at_m else _MORNING_HOUR
        if hour is None:
            hour = _MORNING_HOUR
        target = (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return {"type": "once", "run_at": target, "cron": None, "interval_minutes": None}

    # ── "at HH" / "at 3pm" → one-shot today (tomorrow if past) ──────────────
    m = re.search(r"\bat\s+([\w:]+(?:\s*(?:am|pm))?)", text)
    if m:
        hour = _parse_clock(m.group(1))
        if hour is not None:
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return {"type": "once", "run_at": target, "cron": None, "interval_minutes": None}

    logger.debug("[TIME_PARSER] Could not parse: %r", expr)
    return None
