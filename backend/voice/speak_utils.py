"""
JARVIS-MKIII — voice/speak_utils.py
Utilities for converting datetime values into natural spoken English.
"""
from __future__ import annotations
import datetime

# ── Word tables ───────────────────────────────────────────────────────────────

_ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]


def _minute_words(m: int) -> str:
    """Return the spoken form of a minute value (1–59)."""
    if m < 10:
        return f"oh {_ONES[m]}"          # 5  → "oh five"
    if m < 20:
        return _ONES[m]                   # 14 → "fourteen"
    t, o = divmod(m, 10)
    return f"{_TENS[t]}-{_ONES[o]}" if o else _TENS[t]  # 54 → "fifty-four"


def speak_time(dt: datetime.datetime) -> str:
    """
    Convert a datetime to natural spoken English.

    Examples
    --------
    03:54 → "three fifty-four AM"
    15:07 → "three oh seven PM"
    12:00 → "twelve noon"
    00:00 → "twelve midnight"
    09:05 → "nine oh five AM"
    10:00 → "ten AM"
    """
    h, m = dt.hour, dt.minute

    # ── Special cases ─────────────────────────────────────────────────────────
    if h == 0 and m == 0:
        return "twelve midnight"
    if h == 12 and m == 0:
        return "twelve noon"

    # ── General case ──────────────────────────────────────────────────────────
    period    = "AM" if h < 12 else "PM"
    h12       = h % 12 or 12          # 0 → 12,  13 → 1,  12 → 12
    hour_word = _ONES[h12]

    if m == 0:
        return f"{hour_word} {period}"                      # "ten AM"
    return f"{hour_word} {_minute_words(m)} {period}"      # "three fifty-four AM"
