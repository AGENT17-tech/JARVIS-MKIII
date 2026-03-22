#!/usr/bin/env python3
"""
JARVIS-MKIII — patch_weather_calendar.py
Wires weather_calendar router into main.py and updates
dispatcher to inject live weather + time into system prompt.
Run from ~/jarvis-mkiii/
"""

import os, re

BASE = os.path.expanduser("~/jarvis-mkiii")

# ── 1. Patch api/main.py to include weather_router ──────────────────────────

main_path = os.path.join(BASE, "api/main.py")
with open(main_path, "r") as f:
    main = f.read()

if "weather_calendar" not in main:
    main = main.replace(
        "from api.voice_bridge import voice_router\napp.include_router(voice_router)",
        "from api.voice_bridge import voice_router\napp.include_router(voice_router)\n\nfrom api.weather_calendar import weather_router\napp.include_router(weather_router)"
    )
    with open(main_path, "w") as f:
        f.write(main)
    print("✅ main.py patched — weather_router added")
else:
    print("ℹ️  main.py already has weather_router")


# ── 2. Patch dispatcher.py to inject live weather + time ─────────────────────

disp_path = os.path.join(BASE, "core/dispatcher.py")
with open(disp_path, "r") as f:
    disp = f.read()

new_system = '''def _default_system(model_name: str) -> str:
    import datetime, httpx, os
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%A, %d %B %Y")

    # Try to get live weather
    weather_str = ""
    try:
        r = httpx.get("http://localhost:8000/weather", timeout=3.0)
        w = r.json()
        if not w.get("error"):
            weather_str = f"Current weather in Cairo: {w['temp']}°C, {w['condition']}, humidity {w['humidity']}%, wind {w['wind']} km/h. "
    except Exception:
        pass

    return (
        f"You are JARVIS, a British AI assistant for Agent 17. "
        f"Current time: {time_str}. Today is {date_str}. "
        f"{weather_str}"
        f"You are running on the {model_name} tier. "
        "RULES: Max 1-2 sentences. No lists. No explanations unless asked. "
        "Be direct, precise, and British. State facts immediately."
    )
'''

# Replace existing _default_system
disp = re.sub(
    r'def _default_system\(model_name: str\) -> str:.*?(?=\n[^\s]|\Z)',
    new_system.strip(),
    disp,
    flags=re.DOTALL
)

with open(disp_path, "w") as f:
    f.write(disp)
print("✅ dispatcher.py patched — live weather + time in system prompt")

print("\n✅ All patches applied. Now:")
print("   1. Copy CalendarWeatherPanel.jsx to ~/jarvis-hud/src/")
print("   2. Copy api/weather_calendar.py to ~/jarvis-mkiii/api/")
print("   3. sudo systemctl restart jarvis-mkiii")
print("   4. Add <CalendarWeatherPanel/> to App.jsx")
