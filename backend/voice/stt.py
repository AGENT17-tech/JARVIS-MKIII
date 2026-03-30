"""
JARVIS-MKIII — stt.py
Faster-whisper small with webrtcvad.
Listens on microphone, detects speech, transcribes each utterance.
"""
from __future__ import annotations
import queue, re, threading
import numpy as np
import webrtcvad
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE        = 16000   # Whisper native rate
CAPTURE_RATE       = 48000   # ALSA capture rate (hardware-supported); downsampled to SAMPLE_RATE
CHANNELS           = 1
BLOCK_MS           = 30
# Capture blocksize is at CAPTURE_RATE; after downsampling we get BLOCK_SAMPLES at SAMPLE_RATE
CAPTURE_BLOCK      = int(CAPTURE_RATE * BLOCK_MS / 1000)   # 1440 samples @ 48 kHz
BLOCK_SAMPLES      = int(SAMPLE_RATE  * BLOCK_MS / 1000)   # 480  samples @ 16 kHz
_DS_RATIO          = CAPTURE_RATE // SAMPLE_RATE            # 3
VAD_AGGRESSIVENESS = 1
SILENCE_THRESHOLD  = 12
MIN_SPEECH_FRAMES  = 8     # minimum speech frames before transcribing (8 × 30ms = 240ms)
MIN_TRANSCRIPT_LEN = 3   # skip transcripts shorter than this (noise artifacts)
LANG_CONF_MIN      = 0.5 # skip if Whisper language confidence is below this
WHISPER_MODEL      = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"


class STTEngine:
    def __init__(self, on_transcript: callable, language: str | None = None):
        self.on_transcript = on_transcript
        self.language      = language
        self._running      = False
        self._audio_q: queue.Queue[bytes] = queue.Queue()

        print(f"[STT] Loading faster-whisper {WHISPER_MODEL} (CUDA)...")
        try:
            self._model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
            print("[STT] CUDA loaded.")
        except Exception as e:
            print(f"[STT] CUDA failed ({e}), falling back to CPU...")
            self._model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            print("[STT] CPU fallback loaded.")

        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

        # CUDA warm-up — pre-compile kernels so first real query is fast
        print("[STT] Running CUDA warm-up...")
        try:
            dummy = np.zeros(16000, dtype=np.float32)  # 1 second of silence
            segments, _ = self._model.transcribe(dummy, language="en")
            list(segments)  # consume generator to trigger actual inference
            print("[STT] CUDA warm-up complete.")
        except Exception as e:
            print(f"[STT] Warm-up skipped: {e}")

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
                pcm = (indata[::_DS_RATIO, 0] * 32767 * 1.5).clip(-32767, 32767).astype(np.int16).tobytes()
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

        # EMOTION — save raw PCM to temp file and analyse in background (non-blocking)
        try:
            import tempfile as _tf
            import os as _os
            from scipy.io import wavfile as _wf
            _wav_path = _os.path.join(_tf.gettempdir(), "jarvis_voice_sample.wav")
            _pcm_int16 = np.frombuffer(pcm, dtype=np.int16)
            _wf.write(_wav_path, SAMPLE_RATE, _pcm_int16)

            def _run_emotion_analysis():
                try:
                    import sys as _sys
                    from pathlib import Path as _Path
                    _root = _Path(__file__).parent.parent.parent
                    if str(_root) not in _sys.path:
                        _sys.path.insert(0, str(_root))
                    from emotion.voice_state import get_analyzer
                    get_analyzer().analyze_audio(_wav_path)
                except Exception as _ee:
                    print(f"[EMOTION] Background analysis error: {_ee}")

            import threading as _threading
            _threading.Thread(target=_run_emotion_analysis, daemon=True).start()
        except Exception as _se:
            print(f"[EMOTION] Save failed: {_se}")

        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_speech_duration_ms": 500,
                "min_silence_duration_ms": 300,
                "speech_pad_ms":          400,
                "threshold":              0.6,
            },
        )
        text = " ".join(s.text.strip() for s in segments).strip()

        # Skip noise artifacts and low-confidence detections
        if len(text) < MIN_TRANSCRIPT_LEN:
            return
        if re.fullmatch(r"[\W\d\s]+", text):
            return
        if info.language_probability < LANG_CONF_MIN:
            print(f"[STT] Low lang confidence ({info.language_probability:.2f}) — skipped: {text[:40]}")
            return

        print(f"[STT] Transcript: {text}")
        try:
            from integrations.touchdesigner_bridge import on_listening_stop
            on_listening_stop()
        except Exception:
            pass
        self.on_transcript(text)
