"""
JARVIS-MKIII — voice_orchestrator.py
Central nerve of the voice pipeline.

Flow:
  Mic → STT → VoiceOrchestrator → POST /chat → TTS → Speaker
                                ↓
                          WebSocket /ws/hud-voice-bridge → HUD
"""

from __future__ import annotations
import asyncio, platform, threading, httpx, websockets, json, datetime, time, signal, re
from voice.stt import STTEngine
from voice.news import get_morning_briefing
from voice.tts import TTSEngine
from voice.wake_word import WakeWordDetector

API_BASE   = "http://localhost:8000"
SESSION_ID = "voice-pipeline"
HUD_WS_URL = "ws://localhost:8000/ws/hud-voice-bridge"

SELF_PHRASES = [
    "i'm here to help", "how can i help", "feel free to ask",
    "i'm having trouble", "all systems online", "let me know",
    "i'm glad", "thanks for watching", "you're welcome",
    "is there something", "i can assist", "what can i do",
    "good morning", "good afternoon", "good evening",
    "we're both dead", "non-existent", "existential",
]


def _time_greeting() -> str:
    hour = datetime.datetime.now().hour
    if hour < 12:   return "Good morning"
    elif hour < 17: return "Good afternoon"
    else:           return "Good evening"


class VoiceOrchestrator:
    def __init__(self):
        self._tts        = TTSEngine(on_start=self._on_speaking_start, on_stop=self._on_speaking_stop)
        self._stt        = STTEngine(on_transcript=self._on_transcript)
        self._wake       = WakeWordDetector(on_detected=self._on_wake)
        self._hud_ws     = None
        self._loop       = asyncio.new_event_loop()
        self._busy       = False
        self._is_speaking = False   # echo guard flag

    def start(self) -> None:
        print("[VOICE] Starting voice pipeline...")

        # Start TTS loading in background (Kokoro CUDA init takes a few seconds)
        self._tts.start()

        # Start HUD event loop
        loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        loop_thread.start()
        # Wait until event loop is actually running before scheduling coroutine
        while not self._loop.is_running():
            time.sleep(0.05)
        asyncio.run_coroutine_threadsafe(self._connect_hud(), self._loop)

        # Block until Kokoro confirms ready — no blind sleep
        print("[VOICE] Waiting for TTS to initialize...")
        if not self._tts.wait_until_ready(timeout=60):
            print("[VOICE] WARNING: TTS did not initialize within 60s — proceeding anyway.")
        else:
            print("[VOICE] TTS confirmed ready.")

        # STT starts after TTS is confirmed — prevents transcription before we can respond
        self._stt.start()

        # Wake word starts alongside STT — independent mic stream
        self._wake.start()

        # Greeting fires only after both pipelines are live
        self._speak_greeting()
        print("[VOICE] Voice pipeline online.")

    def stop(self) -> None:
        self._wake.stop()
        self._stt.stop()
        self._tts.stop()
        self._loop.stop()

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_transcript(self, text: str) -> None:
        # Echo guard: discard anything captured while JARVIS is speaking
        if self._is_speaking:
            print(f"[STT] Echo discarded (speaking): {text[:60]}")
            return
        if any(p in text.lower() for p in SELF_PHRASES):
            print(f"[VOICE] Ignored self-phrase: {text[:50]}")
            return
        if self._busy:
            return
        self._busy = True
        self._send_hud(f"voice:transcript:{text}")
        self._send_hud("voice:processing")
        threading.Thread(
            target=lambda: asyncio.run(self._query_mkiii(text)),
            daemon=True,
        ).start()

    def _on_speaking_start(self) -> None:
        self._is_speaking = True
        self._send_hud("speaking:start")
        # Pause STT processing during speech to prevent mic bleed
        if hasattr(self._stt, "_speaking_guard"):
            self._stt._speaking_guard = True

    def _on_speaking_stop(self) -> None:
        self._send_hud("speaking:stop")
        self._is_speaking = False
        # Wait after TTS stops before accepting new STT input — longer on Windows for mic bleed
        cooldown = 1.5 if platform.system() == "Windows" else 0.5
        threading.Timer(cooldown, self._resume_listening).start()

    def _resume_listening(self) -> None:
        if hasattr(self._stt, "_speaking_guard"):
            self._stt._speaking_guard = False
        self._busy = False
        self._send_hud("voice:listening")

    def _on_wake(self) -> None:
        if not self._busy and not self._is_speaking:
            print("[WAKE] Hey JARVIS detected")
            self._send_hud("voice:wake")
            self._tts.speak("Yes, sir.")
            self._busy = False  # keep STT open for follow-up

    # ── MKIII query ───────────────────────────────────────────────────────────

    async def _query_mkiii(self, prompt: str) -> None:
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(
                        f"{API_BASE}/chat",
                        json={"prompt": prompt, "session_id": SESSION_ID},
                    )
                    if r.status_code != 200:
                        print(f"[VOICE] Chat returned {r.status_code} (attempt {attempt+1})")
                        await asyncio.sleep(2)
                        continue
                    if not r.text.strip():
                        print(f"[VOICE] Empty response (attempt {attempt+1})")
                        await asyncio.sleep(2)
                        continue
                    data = r.json()
                    text = data.get("response", "")
                    tier = data.get("tier", "voice")
                    if text:
                        self._send_hud(f"voice:response:{text}")
                        print(f"[VOICE] [{tier.upper()}] {text}")
                        try:
                            from core.text_sanitizer import sanitize_for_tts
                            text = sanitize_for_tts(text)
                        except Exception:
                            pass
                        self._tts.speak(text)
                    else:
                        self._busy = False
                    return
            except Exception as e:
                print(f"[VOICE] Query failed (attempt {attempt+1}): {e}")
                await asyncio.sleep(2)
        print("[VOICE] All retries exhausted — skipping response")
        self._busy = False

    # ── HUD WebSocket ─────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect_hud(self) -> None:
        delay   = 1       # seconds, doubles each retry
        attempt = 0
        MAX_RETRIES = 10
        MAX_DELAY   = 30

        while True:
            try:
                async with websockets.connect(HUD_WS_URL) as ws:
                    self._hud_ws = ws
                    delay   = 1   # reset backoff on successful connect
                    attempt = 0
                    print("[VOICE] HUD WebSocket connected.")
                    async for msg in ws:
                        # Backend requests TTS for typed HUD messages
                        if isinstance(msg, str) and msg.startswith("speak:"):
                            text = msg[6:].strip()
                            if text:
                                self._tts.speak(text)
            except Exception as e:
                self._hud_ws = None
                attempt += 1
                if attempt > MAX_RETRIES:
                    print(f"[VOICE] HUD WS failed after {MAX_RETRIES} retries — giving up. Backend may not be running.")
                    return
                print(f"[VOICE] HUD WS disconnected: {e} — retry {attempt}/{MAX_RETRIES} in {delay}s")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_DELAY)

    def _send_hud(self, message: str) -> None:
        async def _send():
            if self._hud_ws:
                try:
                    await self._hud_ws.send(message)
                except Exception:
                    pass
        if self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), self._loop)

    # ── Boot greeting ─────────────────────────────────────────────────────────

    def _speak_greeting(self) -> None:
        # Brief system-ready announcement only.
        # The full briefing (weather + calendar + missions + news) is delivered
        # separately via the morning_briefing pipeline — speaking it here would
        # cause a duplicate since run_briefing() queues it via request_speak().
        greeting = "All systems online."
        self._send_hud(f"voice:response:{greeting}")
        self._tts.speak(greeting)

        # If the briefing cache is already populated (backend ran before voice
        # service started) and the voice bridge was not yet connected when
        # run_briefing() executed, speak it now so it is not lost.
        try:
            from briefing.morning_briefing import get_today_spoken_briefing
            spoken = get_today_spoken_briefing()
            if spoken:
                self._send_hud(f"voice:response:{spoken}")
                self._tts.speak(spoken)
        except Exception as e:
            print(f"[NEWS] Briefing cache read failed: {e}")


if __name__ == "__main__":
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
