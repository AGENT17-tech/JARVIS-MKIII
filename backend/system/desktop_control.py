"""
JARVIS-MKIII — system/desktop_control.py
Direct desktop control — fast, no LLM planning needed.

Provides:
  take_screenshot()         → ~/Pictures/jarvis/<timestamp>.png
  type_text(text)           → xdotool type at current focus
  press_shortcut(shortcut)  → xdotool key (e.g. "ctrl+s", "ctrl+alt+t")
  youtube_control(action)   → send keypress to YouTube browser window
  get_time_date()           → TTS-safe current time and date string

Requires: xdotool, wmctrl, scrot (sudo apt install xdotool wmctrl scrot)
Falls back gracefully if tools are not installed.
"""
from __future__ import annotations
import datetime, os, pathlib, subprocess, time

_SCREENSHOT_DIR = pathlib.Path.home() / "Pictures" / "jarvis"


def _display_env() -> dict:
    """Build env dict with DISPLAY set — evaluated at call time so the service's
    runtime value (e.g. set after import) is always picked up."""
    return {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}


# ── xdotool helper ─────────────────────────────────────────────────────────────

def _xdotool(*args: str, timeout: int = 5) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["xdotool", *args],
            capture_output=True, text=True, timeout=timeout,
            env=_display_env(),
        )
        return r.returncode == 0, (r.stdout.strip() or r.stderr.strip())
    except FileNotFoundError:
        return False, "xdotool not installed — run: sudo apt install xdotool"
    except subprocess.TimeoutExpired:
        return False, "xdotool timed out"
    except Exception as e:
        return False, str(e)


# ── Screenshot ─────────────────────────────────────────────────────────────────

def take_screenshot() -> dict:
    """Capture full desktop, save to ~/Pictures/jarvis/ with timestamp."""
    try:
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SCREENSHOT_DIR / f"jarvis_{ts}.png"

        # 1. scrot
        r = subprocess.run(
            ["scrot", str(path)],
            capture_output=True, text=True, timeout=10,
            env=_display_env(),
        )
        if r.returncode == 0 and path.exists():
            return {"success": True, "result": f"Screenshot saved to {path}", "path": str(path)}

        # 2. pyautogui fallback (no extra tool required)
        import pyautogui
        img = pyautogui.screenshot()
        img.save(str(path))
        return {"success": True, "result": f"Screenshot saved to {path}", "path": str(path)}

    except Exception as e:
        return {"success": False, "result": "", "error": str(e)}


# ── Type text ──────────────────────────────────────────────────────────────────

def type_text(text: str) -> dict:
    """Type text at the current cursor position."""
    ok, msg = _xdotool("type", "--clearmodifiers", "--delay", "50", "--", text)
    if ok:
        preview = text[:50] + ("..." if len(text) > 50 else "")
        return {"success": True, "result": f"Typed: {preview}"}
    return {"success": False, "result": "", "error": msg}


# ── Press shortcut / key ───────────────────────────────────────────────────────

# Single-key aliases for voice: "press enter" → xdotool key "Return"
_KEY_ALIASES: dict[str, str] = {
    "enter":     "Return",
    "return":    "Return",
    "escape":    "Escape",
    "esc":       "Escape",
    "backspace": "BackSpace",
    "delete":    "Delete",
    "del":       "Delete",
    "tab":       "Tab",
    "space":     "space",
    "up":        "Up",
    "down":      "Down",
    "left":      "Left",
    "right":     "Right",
    "home":      "Home",
    "end":       "End",
    "page up":   "Prior",
    "page down": "Next",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}


def press_shortcut(shortcut: str) -> dict:
    """
    Press a keyboard shortcut string.
    Accepts: "ctrl+s", "ctrl+alt+t", "f5", "enter", "ctrl shift p", etc.
    Normalises spaces and mixed case before passing to xdotool.
    """
    # Normalise: spaces between modifiers → "+", lower case
    normalised = shortcut.lower().strip()
    # "ctrl s"  → "ctrl+s",  "ctrl alt t" → "ctrl+alt+t"
    normalised = "+".join(p.strip() for p in normalised.replace("+", " ").split())
    # Apply single-key aliases  (e.g. "ctrl+enter" → "ctrl+Return")
    parts = normalised.split("+")
    parts = [_KEY_ALIASES.get(p, p) for p in parts]
    xkey  = "+".join(parts)

    ok, msg = _xdotool("key", "--clearmodifiers", xkey)
    if ok:
        return {"success": True, "result": f"Pressed: {shortcut}"}
    return {"success": False, "result": "", "error": msg}


# ── YouTube browser control ────────────────────────────────────────────────────

# Maps action names to YouTube keyboard shortcuts
_YOUTUBE_KEYS: dict[str, str] = {
    "pause":           "k",
    "play":            "k",
    "play pause":      "k",
    "toggle":          "k",
    "mute":            "m",
    "unmute":          "m",
    "fullscreen":      "f",
    "full screen":     "f",
    "exit fullscreen": "f",
    "next":            "shift+n",
    "previous":        "shift+p",
    "forward":         "l",
    "rewind":          "j",
    "skip":            "l",
    "captions":        "c",
    "subtitles":       "c",
    "volume up":       "Up",
    "volume down":     "Down",
    "like":            "shift+slash",  # not standard but harmless
}

_YOUTUBE_ACTION_LABELS: dict[str, str] = {
    "k":       "play/pause toggled",
    "m":       "mute toggled",
    "f":       "fullscreen toggled",
    "shift+n": "skipped to next",
    "shift+p": "went to previous",
    "l":       "skipped forward 10 seconds",
    "j":       "rewound 10 seconds",
    "c":       "captions toggled",
    "Up":      "volume up",
    "Down":    "volume down",
}


def youtube_control(action: str) -> dict:
    """Send a keypress to the browser window that has YouTube open."""
    action_lower = action.lower().strip()
    key = _YOUTUBE_KEYS.get(action_lower)

    if not key:
        # Partial match
        for k_name, k_val in _YOUTUBE_KEYS.items():
            if k_name in action_lower or action_lower in k_name:
                key = k_val
                break

    if not key:
        return {"success": False, "result": "",
                "error": f"Unknown YouTube action: '{action}'. "
                         f"Try: pause, play, mute, fullscreen, next, previous, forward, rewind"}

    # Find a window whose title contains "YouTube"
    ok, wids = _xdotool("search", "--name", "YouTube")
    if not ok or not wids:
        return {"success": False, "result": "",
                "error": "No YouTube window found. Please open YouTube in your browser first."}

    window_id = wids.split()[0]

    # Activate the window, then send the key
    _xdotool("windowactivate", "--sync", window_id)
    time.sleep(0.15)
    ok2, msg2 = _xdotool("key", "--window", window_id, "--clearmodifiers", key)

    if ok2:
        label = _YOUTUBE_ACTION_LABELS.get(key, action)
        return {"success": True, "result": f"YouTube: {label}."}
    return {"success": False, "result": "", "error": f"Key send failed: {msg2}"}


# ── Time and date ──────────────────────────────────────────────────────────────

def get_time_date() -> dict:
    """Return current time and date as a TTS-friendly string."""
    now  = datetime.datetime.now()
    hour = now.hour
    ampm = "AM" if hour < 12 else "PM"
    h12  = hour % 12 or 12
    time_str = f"{h12}:{now.minute:02d} {ampm}"

    day    = now.day
    suffix = ("th" if 11 <= day <= 13
              else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th"))
    date_str = now.strftime(f"%A, %B {day}{suffix}, %Y")

    result = f"It is {time_str} on {date_str}."
    return {"success": True, "result": result, "time": time_str, "date": date_str}
