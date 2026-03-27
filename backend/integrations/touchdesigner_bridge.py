"""
JARVIS-MKIII — integrations/touchdesigner_bridge.py
OSC bridge to TouchDesigner for real-time reactive visuals.

TouchDesigner should be running and listening on TD_PORT (default 9000).
All sends fail silently if TD is not running — JARVIS continues normally.

OSC address map:
  /jarvis/speaking  int(0|1)  str(text)   — TTS start/stop
  /jarvis/listening int(0|1)              — STT start/stop
  /jarvis/alert     str(priority) str(msg) — proactive alert fired
  /jarvis/vision    str(description)      — LLaVA analysis result
  /jarvis/briefing/weather int(temp) str(condition)
  /jarvis/custom    ...                   — arbitrary via API
"""
from __future__ import annotations
import os

TD_HOST = os.getenv("TD_HOST", "127.0.0.1")
TD_PORT = int(os.getenv("TD_PORT", "9000"))

_client = None
_available = False


def _get_client():
    global _client, _available
    if _client is not None:
        return _client
    try:
        from pythonosc import udp_client
        _client = udp_client.SimpleUDPClient(TD_HOST, TD_PORT)
        _available = True
        print(f"[TD] OSC client ready → {TD_HOST}:{TD_PORT}")
    except Exception as e:
        print(f"[TD] OSC client unavailable: {e}")
        _available = False
    return _client


def send_event(address: str, *args) -> None:
    """Send an OSC message to TouchDesigner. Fails silently if TD not running."""
    client = _get_client()
    if client is None:
        return
    try:
        client.send_message(address, list(args))
    except Exception as e:
        print(f"[TD] OSC send failed ({address}): {e}")


# ── Standard JARVIS event hooks ───────────────────────────────────────────────

def on_speaking_start(text: str = "") -> None:
    send_event("/jarvis/speaking", 1, text[:100])


def on_speaking_stop() -> None:
    send_event("/jarvis/speaking", 0, "")


def on_listening_start() -> None:
    send_event("/jarvis/listening", 1)


def on_listening_stop() -> None:
    send_event("/jarvis/listening", 0)


def on_alert(priority: str, message: str) -> None:
    send_event("/jarvis/alert", priority, message[:100])


def on_vision_result(description: str) -> None:
    send_event("/jarvis/vision", description[:200])


def on_briefing_weather(temp: int | str, condition: str) -> None:
    try:
        send_event("/jarvis/briefing/weather", int(temp), condition)
    except (ValueError, TypeError):
        send_event("/jarvis/briefing/weather", 0, condition)


def is_available() -> bool:
    return _available
