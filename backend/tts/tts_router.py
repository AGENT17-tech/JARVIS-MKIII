"""
JARVIS-MKIII — tts/tts_router.py
Kokoro TTS router. speak(text) is the single entry-point for all TTS in the system.
"""
from __future__ import annotations
import logging
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

PLAYBACK_RATE = 48000   # ALSA standard; Kokoro native is 24 kHz, resampled here

# ── Module state ───────────────────────────────────────────────────────────────
_kokoro_pipeline = None   # set by TTSEngine via register_pipeline()


# ── Pipeline registration (called by TTSEngine after Kokoro loads) ─────────────

def register_pipeline(pipeline) -> None:
    """Share TTSEngine's Kokoro pipeline with the router."""
    global _kokoro_pipeline
    _kokoro_pipeline = pipeline


# ── Internal helpers ───────────────────────────────────────────────────────────

def _resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio
    n_out = int(len(audio) * dst_rate / src_rate)
    x_old = np.linspace(0, 1, len(audio))
    x_new = np.linspace(0, 1, n_out)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _kokoro_speak(text: str) -> None:
    """Play text via the registered Kokoro pipeline (sentence-by-sentence)."""
    from voice.tts import _split_sentences, VOICE, SPEED, SAMPLE_RATE

    pipeline = _kokoro_pipeline
    if pipeline is None:
        logger.warning("[TTS] Kokoro pipeline not registered — cannot speak")
        return

    sentences = _split_sentences(text)
    for s in sentences:
        try:
            chunks = [a for _, _, a in pipeline(s, voice=VOICE, speed=SPEED) if a is not None]
            if chunks:
                audio = _resample(np.concatenate(chunks), SAMPLE_RATE, PLAYBACK_RATE)
                sd.play(audio, samplerate=PLAYBACK_RATE)
                sd.wait()
        except Exception as e:
            logger.warning("[TTS] Kokoro sentence error: %s", e)


# ── Public API ─────────────────────────────────────────────────────────────────

def speak(text: str) -> None:
    """
    Speak text via Kokoro TTS. Never raises — failures are logged and swallowed.
    """
    text = text.strip()
    if not text:
        return
    try:
        _kokoro_speak(text)
    except Exception as e:
        print(f"[TTS] Kokoro failed: {e}")


def get_status() -> dict:
    """Return current TTS engine status for the /tts/status endpoint."""
    return {
        "tier": "kokoro",
        "kokoro_ready": _kokoro_pipeline is not None,
    }
