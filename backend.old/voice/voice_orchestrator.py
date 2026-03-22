"""
JARVIS-MKIII — voice_orchestrator.py
"""

from __future__ import annotations
import asyncio
import threading
import httpx
import websockets
import json
import datetime
from voice.stt import STTEngine
from voice.tts import TTSEngine

API_BASE   = "http://localhost:8000"
WS_BASE    = "ws://localhost:8000"
SESSION_ID = "voice-pipeline"
HUD_WS_URL = f"{WS_BASE}/ws/hud-voice-bridge"

SELF_PHRASES = [
    "i'm here to help", "how can i help", "feel free to ask",
    "i'm having trouble", "all systems online", "let me know",
    "i'm glad", "thanks for watching", "you're welcome",
    "is there something", "i can assist", "what can i do",
    "good morning", "good afternoon", "good evening",
]


def _time_greeting() -> str:
    hour = datetime.datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


class VoiceOrchestrator:
    def __init__(self):
        self._tts = TTSEngine(
            on_start=self._on_speaking_start,
            on_stop=self._on_speaking_stop,
        )
        self._stt = STTEngine(on_transcript=self._on_transcript)
        self._hud_ws = None
        self._loop   = asyncio.new_event_loop()
        self._busy   = False

    def start(self) -> None:
        print("[VOICE] Starting voice pipeline...")
        self._tts.start()
        threading.Thread(target=self._run_loop, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._connect_hud(), self._loop)
        import time; time.sleep(8)
        self._stt.start()
        self._speak_greeting()
        print("[VOICE] Voice pipeline online.")

    def stop(self) -> None:
        self._stt.stop()
        self._tts.stop()
        self._loop.stop()

    def _on_transcript(self, text: str) -> None:
        if any(p in text.lower() for p in SELF_PHRASES):
            print(f"[VOICE] Ignored self-phrase: {text[:40]}")
            return
        if self._busy:
            return
        self._busy = True
        self._send_hud(f"voice:transcript:{text}")
        self._send_hud("voice:processing")
        threading.Thread(target=self._query_mkiii, args=(text,), daemon=True).start()

    def _on_speaking_start(self) -> None:
        self._send_hud("speaking:start")

    def _on_speaking_stop(self) -> None:
        self._send_hud("speaking:stop")
        self._busy = False
        self._send_hud("voice:listening")

    def _query_mkiii(self, prompt: str) -> None:
        try:
            resp = httpx.post(
                f"{API_BASE}/chat",
                json={"prompt": prompt, "session_id": SESSION_ID},
                timeout=120.0,
            )
            data = resp.json()
            response_text = data.get("response", "")
            tier = data.get("tier", "voice")
            if response_text:
                self._send_hud(f"voice:response:{response_text}")
                print(f"[VOICE] [{tier.upper()}] {response_text}")
                self._tts.speak(response_text)
            else:
                self._busy = False
        except Exception as e:
            print(f"[VOICE] Query failed: {e}")
            self._busy = False

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect_hud(self) -> None:
        while True:
            try:
                async with websockets.connect(HUD_WS_URL) as ws:
                    self._hud_ws = ws
                    print("[VOICE] HUD WebSocket connected.")
                    async for _ in ws:
                        pass
            except Exception as e:
                print(f"[VOICE] HUD WS disconnected: {e} — retrying in 3s")
                self._hud_ws = None
                await asyncio.sleep(3)

    def _send_hud(self, message: str) -> None:
        async def _send():
            if self._hud_ws:
                try:
                    await self._hud_ws.send(message)
                except Exception:
                    pass
        if self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), self._loop)

    def _speak_greeting(self) -> None:
        greeting_word = _time_greeting()
        try:
            resp = httpx.post(
                f"{API_BASE}/chat",
                json={
                    "prompt": f"Give a one-sentence JARVIS boot greeting to Agent 17 starting with '{greeting_word}'. Be brief and British.",
                    "session_id": SESSION_ID,
                },
                timeout=30.0,
            )
            greeting = resp.json().get("response", f"{greeting_word}, sir. All systems online.")
        except Exception:
            greeting = f"{greeting_word}, sir. All systems online."
        self._send_hud(f"voice:response:{greeting}")
        self._tts.speak(greeting)


if __name__ == "__main__":
    import signal, time
    orch = VoiceOrchestrator()
    orch.start()

    def shutdown(sig, frame):
        print("\n[VOICE] Shutting down...")
        orch.stop()
        exit(0)

    signal.signal(signal.SIGINT, shutdown)

    print("[VOICE] Running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
