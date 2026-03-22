from __future__ import annotations
import threading, queue, subprocess, re
import numpy as np
import sounddevice as sd

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

SAMPLE_RATE    = 24000   # Kokoro native output rate
PLAYBACK_RATE  = 48000   # ALSA universally supports 48 kHz; resample before playback
VOICE          = "bm_george"
SPEED          = 1.25
OUTPUT_DEVICE  = None    # None = system default; set to an int to override (see: python -m sounddevice)


def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resample — no extra dependencies required."""
    if src_rate == dst_rate:
        return audio
    n_out = int(len(audio) * dst_rate / src_rate)
    x_old = np.linspace(0, 1, len(audio))
    x_new = np.linspace(0, 1, n_out)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _split_sentences(text):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    result, buf = [], ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        buf = (buf + " " + part).strip() if buf else part
        if len(buf) > 20:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result if result else [text]


class TTSEngine:
    def __init__(self, on_start=None, on_stop=None):
        self.on_start  = on_start or (lambda: None)
        self.on_stop   = on_stop  or (lambda: None)
        self._queue    = queue.Queue()
        self._running  = False
        self._pipeline = None
        self._ready    = threading.Event()  # gates greeting until Kokoro is loaded

    def start(self):
        self._running = True
        if KOKORO_AVAILABLE:
            print("[TTS] Loading Kokoro-82M (British, CUDA)...")
            try:
                self._pipeline = KPipeline(lang_code="b", device="cuda")  # was cpu
                print("[TTS] Kokoro ready on CUDA.")
            except Exception as e:
                print(f"[TTS] CUDA failed ({e}), falling back to CPU...")
                self._pipeline = KPipeline(lang_code="b", device="cpu")
                print("[TTS] Kokoro ready on CPU.")

            # Warm-up: run one silent inference so the first real utterance plays instantly.
            # Kokoro lazily loads weights on first call; without this the greeting is delayed.
            print("[TTS] Running warm-up inference...")
            try:
                _ = list(self._pipeline("hello", voice=VOICE, speed=SPEED))
                print("[TTS] Warm-up complete.")
            except Exception as e:
                print(f"[TTS] Warm-up failed (non-fatal): {e}")
        else:
            print("[TTS] WARNING: Kokoro not available.")

        self._ready.set()  # unblock wait_until_ready() callers
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self._running = False
        self._queue.put(None)

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """Block the caller until Kokoro is fully loaded. Returns True if ready."""
        return self._ready.wait(timeout=timeout)

    def speak(self, text: str):
        if text.strip():
            self._queue.put(text.strip())

    def interrupt(self):
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _worker(self):
        while self._running:
            text = self._queue.get()
            if text is None:
                break
            self._stream_speak(text)

    def _stream_speak(self, text: str):
        sentences = _split_sentences(text)
        self.on_start()
        subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"], capture_output=True)
        try:
            for s in sentences:
                if not self._running:
                    break
                self._play_sentence(s)
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"], capture_output=True)
            self.on_stop()

    def _play_sentence(self, sentence: str):
        if not KOKORO_AVAILABLE or not self._pipeline:
            return
        chunks = [a for _, _, a in self._pipeline(sentence, voice=VOICE, speed=SPEED) if a is not None]
        if chunks:
            audio = _resample(np.concatenate(chunks), SAMPLE_RATE, PLAYBACK_RATE)
            sd.play(audio, samplerate=PLAYBACK_RATE, device=OUTPUT_DEVICE)
            sd.wait()
