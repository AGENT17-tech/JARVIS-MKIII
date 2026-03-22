"""
JARVIS-MKIII — tts.py
Text-to-Speech engine using Kokoro-82M (local, GPU-accelerated).
Kokoro is 82M parameters, runs on T1000 in real-time, sounds natural.

Pipeline:
  response text → Kokoro → audio array → sounddevice playback
"""

from __future__ import annotations
import threading
import queue
import numpy as np
import sounddevice as sd

# Kokoro import — install with: pip install kokoro
try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    print("[TTS] Kokoro not installed. Run: pip install kokoro")
    print("[TTS] Falling back to pyttsx3 if available.")

# Fallback TTS
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

SAMPLE_RATE = 24000   # Kokoro output sample rate
VOICE       = "bm_george"  # Kokoro voice — JARVIS-style deep voice
SPEED       = 1.05         # Slightly faster than default


class TTSEngine:
    """
    Queued TTS engine. Accepts text strings, synthesises them
    one at a time in a background thread so JARVIS never blocks.

    Usage:
        tts = TTSEngine(on_start=cb_start, on_stop=cb_stop)
        tts.start()
        tts.speak("All systems online, sir.")
    """

    def __init__(
        self,
        on_start: callable = None,
        on_stop:  callable = None,
    ):
        self.on_start  = on_start or (lambda: None)
        self.on_stop   = on_stop  or (lambda: None)
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._running  = False
        self._pipeline = None
        self._lock     = threading.Lock()

    def start(self) -> None:
        self._running = True
        if KOKORO_AVAILABLE:
            print("[TTS] Loading Kokoro-82M...")
            self._pipeline = KPipeline(lang_code="b", device="cpu")  # 'a' = American English
            print("[TTS] Kokoro ready.")
        elif PYTTSX3_AVAILABLE:
            print("[TTS] Using pyttsx3 fallback.")
        else:
            print("[TTS] No TTS engine available.")

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)  # sentinel

    def speak(self, text: str) -> None:
        """Queue text for speech. Non-blocking."""
        if text.strip():
            self._queue.put(text.strip())

    def interrupt(self) -> None:
        """Clear the queue — stop current and pending speech."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    # ── Internal ──────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while self._running:
            text = self._queue.get()
            if text is None:
                break
            self._synthesise(text)

    def _synthesise(self, text: str) -> None:
        self.on_start()
        try:
            if KOKORO_AVAILABLE and self._pipeline:
                self._play_kokoro(text)
            elif PYTTSX3_AVAILABLE:
                self._play_pyttsx3(text)
        except Exception as e:
            print(f"[TTS] Synthesis error: {e}")
        finally:
            self.on_stop()

    def _play_kokoro(self, text: str) -> None:
        """Synthesise with Kokoro and play via sounddevice."""
        audio_chunks = []
        generator = self._pipeline(text, voice=VOICE, speed=SPEED)

        for _, _, audio in generator:
            if audio is not None:
                audio_chunks.append(audio)

        if audio_chunks:
            full_audio = np.concatenate(audio_chunks)
            import subprocess
            subprocess.run(['pactl', 'set-source-mute', '@DEFAULT_SOURCE@', '1'], capture_output=True)
            sd.play(full_audio, samplerate=SAMPLE_RATE)
            sd.wait()
            subprocess.run(['pactl', 'set-source-mute', '@DEFAULT_SOURCE@', '0'], capture_output=True)

    def _play_pyttsx3(self, text: str) -> None:
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.say(text)
        engine.runAndWait()
