"""
JARVIS-MKIII — stt.py
Faster-whisper small with WebRTC VAD.
Listens on microphone, detects speech, transcribes each utterance.
"""
from __future__ import annotations
import queue, threading
import numpy as np
import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel

SAMPLE_RATE        = 16000   # Whisper + WebRTC VAD native rate
CAPTURE_RATE       = 48000   # ALSA capture rate (hardware-supported); downsampled to SAMPLE_RATE
CHANNELS           = 1
BLOCK_MS           = 30
# Capture blocksize is at CAPTURE_RATE; after downsampling we get BLOCK_SAMPLES at SAMPLE_RATE
CAPTURE_BLOCK      = int(CAPTURE_RATE * BLOCK_MS / 1000)   # 1440 samples @ 48 kHz
BLOCK_SAMPLES      = int(SAMPLE_RATE  * BLOCK_MS / 1000)   # 480  samples @ 16 kHz
_DS_RATIO          = CAPTURE_RATE // SAMPLE_RATE            # 3
VAD_AGGRESSIVENESS = 2
SILENCE_THRESHOLD  = 40
MIN_SPEECH_FRAMES  = 10
WHISPER_MODEL      = "small"          # was large-v3 — T1000 cannot fit it in VRAM


class STTEngine:
    def __init__(self, on_transcript: callable, language: str = "en"):
        self.on_transcript = on_transcript
        self.language      = language
        self._running      = False
        self._audio_q: queue.Queue[bytes] = queue.Queue()

        print("[STT] Loading faster-whisper small (CUDA)...")
        try:
            self._model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
            print("[STT] CUDA loaded.")
        except Exception as e:
            print(f"[STT] CUDA failed ({e}), falling back to CPU...")
            self._model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            print("[STT] CPU fallback loaded.")

        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        threading.Thread(target=self._vad_loop,     daemon=True).start()
        print("[STT] Listening...")

    def stop(self) -> None:
        self._running = False

    def _capture_loop(self) -> None:
        def callback(indata, frames, time, status):
            if self._running:
                # Downsample from CAPTURE_RATE to SAMPLE_RATE by decimation (3:1)
                pcm = (indata[::_DS_RATIO, 0] * 32767).astype(np.int16).tobytes()
                self._audio_q.put(pcm)

        with sd.InputStream(samplerate=CAPTURE_RATE, channels=CHANNELS,
                             blocksize=CAPTURE_BLOCK, dtype="float32", callback=callback):
            while self._running:
                sd.sleep(100)

    def _vad_loop(self) -> None:
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
                speech_frames.append(frame)
                if silence_count >= SILENCE_THRESHOLD:
                    if len(speech_frames) >= MIN_SPEECH_FRAMES:
                        self._transcribe(speech_frames)
                    speech_frames = []
                    silence_count = 0
                    in_speech     = False

    def _transcribe(self, frames: list[bytes]) -> None:
        pcm   = b"".join(frames)
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if text:
            print(f"[STT] Transcript: {text}")
            self.on_transcript(text)
