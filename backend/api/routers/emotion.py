"""
JARVIS-MKIII — api/routers/emotion.py
Emotion / voice state endpoints.

  GET  /emotion/state      → current detected voice state
  POST /emotion/calibrate  → record 10s baseline from microphone
  GET  /emotion/history    → last 20 state readings
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter

# Ensure project root is on sys.path so emotion.voice_state can be imported
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

emotion_router = APIRouter(prefix="/emotion", tags=["emotion"])


@emotion_router.get("/state")
async def emotion_state():
    """Return the most recently detected voice state."""
    from emotion.voice_state import get_current_state
    return get_current_state()


@emotion_router.get("/history")
async def emotion_history():
    """Return the last 20 voice state readings with timestamps."""
    from emotion.voice_state import get_history
    return {"history": get_history()}


@emotion_router.post("/calibrate")
async def emotion_calibrate():
    """
    Record 10 seconds from the microphone and save as the voice baseline.
    The recording happens in a worker thread so FastAPI stays responsive.
    """
    wav_path = "/tmp/jarvis_calibration.wav"

    def _record_and_calibrate() -> dict:
        import numpy as np
        import sounddevice as sd
        from scipy.io import wavfile

        sr       = 16000
        duration = 10
        print("[EMOTION] Recording 10-second calibration sample — speak normally...")
        data = sd.rec(int(duration * sr), samplerate=sr, channels=1, dtype="float32")
        sd.wait()
        pcm = (data * 32767).astype(np.int16)
        wavfile.write(wav_path, sr, pcm)

        from emotion.voice_state import get_analyzer
        features = get_analyzer().calibrate(wav_path)
        return features

    features = await asyncio.to_thread(_record_and_calibrate)
    return {"status": "calibrated", "baseline_features": features}
