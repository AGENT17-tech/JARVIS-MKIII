"""
JARVIS-MKIII — stt.py
Speech-to-Text engine using faster-whisper large-v3.
Uses WebRTC VAD for voice activity detection so JARVIS only
transcribes when you're actually speaking, not continuously.

Pipeline:
  Microphone → VAD → faster-whisper → transcript string
"""

from __future__ import annotations
import io
import queue
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
import webrtcvad
from faster_whisper import WhisperModel

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000   # Whisper expects 16kHz
CHANNELS       = 1
BLOCK_MS       = 30      # VAD frame size: 10, 20, or 30 ms
BLOCK_SAMPLES  = int(SAMPLE_RATE * BLOCK_MS / 1000)
VAD_AGGRESSIVENESS = 2   # 0–3, higher = more aggressive filtering
SILENCE_THRESHOLD  = 40  # frames of silence before cutting utterance (~1.2s)
MIN_SPEECH_FRAMES  = 10  # ignore very short blips (~300ms)
WHISPER_MODEL      = "large-v3"
DEVICE             = "cuda"   # falls back to "cpu" automatically
COMPUTE_TYPE       = "int8_float16"


class STTEngine:
    """
    Listens on the microphone, detects speech via WebRTC VAD,
    and transcribes each utterance with faster-whisper.

    Usage:
        stt = STTEngine(on_transcript=my_callback)
        stt.start()
        # ... stt.stop() to shut down
    """

    def __init__(self, on_transcript: callable, language: str = "en"):
        self.on_transcript = on_transcript
        self.language      = language
        self._running      = False
        self._audio_q: queue.Queue[bytes] = queue.Queue()

        print("[STT] Loading faster-whisper large-v3...")
        try:
            self._model = WhisperModel(
                WHISPER_MODEL,
                device=DEVICE,
                compute_type=COMPUTE_TYPE,
            )
        except Exception:
            print("[STT] CUDA unavailable — falling back to CPU (int8)")
            self._model = WhisperModel(
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
        print("[STT] Model loaded.")

        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._process_thread = threading.Thread(target=self._vad_loop,     daemon=True)
        self._capture_thread.start()
        self._process_thread.start()
        print("[STT] Listening...")

    def stop(self) -> None:
        self._running = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Continuously read from microphone into the audio queue."""
        def callback(indata, frames, time, status):
            if self._running:
                # Convert float32 → int16 PCM for VAD
                pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
                self._audio_q.put(pcm)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SAMPLES,
            dtype="float32",
            callback=callback,
        ):
            while self._running:
                sd.sleep(100)

    def _vad_loop(self) -> None:
        """
        Consume PCM frames from the queue.
        Collect speech frames between silences into utterances,
        then transcribe each utterance.
        """
        speech_frames: list[bytes] = []
        silence_count = 0
        in_speech     = False

        while self._running:
            try:
                frame = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            is_speech = self._vad.is_speech(frame, SAMPLE_RATE)

            if is_speech:
                speech_frames.append(frame)
                silence_count = 0
                in_speech     = True
            elif in_speech:
                silence_count += 1
                speech_frames.append(frame)  # include trailing silence
                if silence_count >= SILENCE_THRESHOLD:
                    if len(speech_frames) >= MIN_SPEECH_FRAMES:
                        self._transcribe(speech_frames)
                    speech_frames = []
                    silence_count = 0
                    in_speech     = False

    def _transcribe(self, frames: list[bytes]) -> None:
        """Convert raw PCM frames → numpy array → transcribe with Whisper."""
        pcm = b"".join(frames)
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,  # Whisper's built-in VAD as second pass
        )

        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            print(f"[STT] Transcript: {text}")
            self.on_transcript(text)
