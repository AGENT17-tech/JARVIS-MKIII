"""
JARVIS-MKIII — emotion/voice_state.py
Voice state analysis and behavioral adaptation.

Reads prosodic features from captured speech segments to detect:
  focused / fatigued / stressed / elevated / neutral

The detected state is stored in a shared module-level variable so the
/chat endpoint can inject the appropriate system prompt modifier
without round-tripping through HTTP.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── State definitions ──────────────────────────────────────────────────────────

STATES: dict[str, dict] = {
    "focused":  {"speed_modifier": 0.9, "brevity": "high",   "interruption_threshold": "low"},
    "fatigued": {"speed_modifier": 0.7, "brevity": "high",   "interruption_threshold": "medium"},
    "stressed": {"speed_modifier": 1.0, "brevity": "medium", "interruption_threshold": "low"},
    "elevated": {"speed_modifier": 1.1, "brevity": "low",    "interruption_threshold": "medium"},
    "neutral":  {"speed_modifier": 1.0, "brevity": "medium", "interruption_threshold": "medium"},
}

_EMOTION_DIR   = Path(__file__).parent
_BASELINE_PATH = _EMOTION_DIR / "baseline.json"

# ── Shared pipeline state ──────────────────────────────────────────────────────
# Read by /chat endpoint; written by the STT background thread.

_current_state: dict = {
    "state":      "neutral",
    "confidence": 0.5,
    "timestamp":  datetime.now().isoformat(),
}
_state_history: list[dict] = []
_state_lock = threading.Lock()


def get_current_state() -> dict:
    with _state_lock:
        return dict(_current_state)


def _set_state(state: str, confidence: float = 0.7) -> None:
    global _current_state
    entry = {
        "state":      state,
        "confidence": round(confidence, 3),
        "timestamp":  datetime.now().isoformat(),
    }
    with _state_lock:
        _current_state = entry
        _state_history.append(entry)
        if len(_state_history) > 20:
            _state_history.pop(0)


def get_history() -> list[dict]:
    with _state_lock:
        return list(_state_history)


# ── Audio loading ──────────────────────────────────────────────────────────────

def _load_audio_numpy(wav_path: str):
    """Load a wav file → (sample_rate: int, audio: np.ndarray float32 mono)."""
    import numpy as np

    # Try soundfile first (handles all common formats)
    try:
        import soundfile as sf
        audio, sr = sf.read(wav_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return int(sr), audio
    except Exception:
        pass

    # Fallback: scipy.io.wavfile
    try:
        from scipy.io import wavfile
        sr, data = wavfile.read(wav_path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if data.dtype == np.int16:
            audio = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            audio = data.astype(np.float32) / 2147483648.0
        else:
            audio = data.astype(np.float32)
        return int(sr), audio
    except Exception as e:
        raise RuntimeError(f"Cannot load audio from {wav_path}: {e}")


# ── Feature extraction ─────────────────────────────────────────────────────────

def _extract_features(wav_path: str) -> dict[str, float]:
    """
    Extract energy (RMS), speech_rate (ZCR proxy), and pitch_variance
    from a wav file.

    Uses pyAudioAnalysis for energy/ZCR and librosa.yin for pitch.
    Falls back to pure numpy if pyAudioAnalysis is unavailable.
    """
    import numpy as np

    sr, audio = _load_audio_numpy(wav_path)
    if len(audio) == 0:
        raise ValueError("Empty audio array")

    # ── Energy (RMS) ──────────────────────────────────────────────────────────
    # Try pyAudioAnalysis mid-term features first
    energy = 0.0
    zcr    = 0.0
    try:
        from pyAudioAnalysis import audioBasicIO as aIO
        from pyAudioAnalysis import MidTermFeatures as mF
        _sr_pa, _audio_pa = aIO.read_audio_file(wav_path)
        if _audio_pa.ndim > 1:
            _audio_pa = _audio_pa.mean(axis=1)
        _mt_feats, _names, _ = mF.mid_term_feature_extraction(
            _audio_pa, _sr_pa, mid_window=1.0, mid_step=0.5,
            short_window=0.05, short_step=0.025,
        )
        # Feature 0 = short-term energy mean; feature 1 = ZCR mean
        energy = float(np.mean(_mt_feats[0])) if _mt_feats.shape[0] > 0 else 0.0
        zcr    = float(np.mean(_mt_feats[1])) if _mt_feats.shape[0] > 1 else 0.0
    except Exception:
        # Pure numpy fallback
        energy = float(np.sqrt(np.mean(audio ** 2)))
        signs  = np.sign(audio)
        signs[signs == 0] = 1
        energy = float(np.sqrt(np.mean(audio ** 2)))
        zero_crossings = np.sum(np.diff(signs) != 0)
        zcr = float(zero_crossings / max(len(audio), 1))

    # ── Pitch variance (librosa.yin) ──────────────────────────────────────────
    pitch_variance = 0.0
    try:
        import librosa
        f0 = librosa.yin(audio, fmin=60.0, fmax=400.0, sr=sr, hop_length=512)
        voiced = f0[(f0 > 60.0) & (f0 < 400.0)]
        if len(voiced) > 2:
            pitch_variance = float(np.std(voiced))
    except Exception:
        pass

    return {
        "energy":         energy,
        "zcr":            zcr,
        "pitch_variance": pitch_variance,
    }


# ── Classification ─────────────────────────────────────────────────────────────

def _classify(features: dict, baseline: Optional[dict]) -> tuple[str, float]:
    """
    Map extracted features to a state label + confidence score.

    When a baseline is available the thresholds are relative (ratio vs baseline).
    Otherwise absolute thresholds calibrated for typical speech recordings are used.
    """
    energy = features["energy"]
    zcr    = features["zcr"]
    pv     = features["pitch_variance"]

    if baseline:
        e_ratio = energy / max(baseline.get("energy", energy), 1e-9)
        z_ratio = zcr    / max(baseline.get("zcr",    zcr),    1e-9)
        pv_diff = pv     - baseline.get("pitch_variance", pv)

        high_energy = e_ratio > 1.3
        low_energy  = e_ratio < 0.7
        high_zcr    = z_ratio > 1.2
        low_zcr     = z_ratio < 0.8
        high_pv     = pv_diff > 15.0
    else:
        # Absolute thresholds — tuned for 16 kHz normalised speech
        high_energy = energy > 0.04
        low_energy  = energy < 0.015
        high_zcr    = zcr    > 0.08
        low_zcr     = zcr    < 0.03
        high_pv     = pv     > 30.0

    if high_energy and high_zcr:
        return "elevated", 0.78
    if low_energy and low_zcr:
        return "fatigued", 0.74
    if high_pv and high_zcr:
        return "stressed", 0.72
    if not high_pv and not high_energy and not high_zcr and not low_zcr:
        return "focused", 0.68
    return "neutral", 0.60


# ── VoiceStateAnalyzer ─────────────────────────────────────────────────────────

class VoiceStateAnalyzer:
    def __init__(self) -> None:
        _EMOTION_DIR.mkdir(parents=True, exist_ok=True)
        self._baseline: Optional[dict] = self._load_baseline()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_baseline(self) -> Optional[dict]:
        if _BASELINE_PATH.exists():
            try:
                return json.loads(_BASELINE_PATH.read_text())
            except Exception:
                pass
        return None

    def _save_baseline(self, features: dict) -> None:
        _BASELINE_PATH.write_text(json.dumps(features, indent=2, ensure_ascii=False))
        self._baseline = features

    # ── Core analysis ─────────────────────────────────────────────────────────

    def analyze_audio(self, wav_file_path: str) -> str:
        """
        Analyse a wav file and return the detected state name.
        Also updates the global shared state read by the /chat endpoint.
        Non-blocking by design — should always be called from a background thread.
        """
        try:
            features = _extract_features(wav_file_path)
            state, confidence = _classify(features, self._baseline)
            _set_state(state, confidence)
            print(
                f"[EMOTION] {state.upper()} ({confidence:.2f}) | "
                f"e={features['energy']:.4f}  zcr={features['zcr']:.4f}  "
                f"pv={features['pitch_variance']:.1f}"
            )
            return state
        except Exception as e:
            print(f"[EMOTION] Analysis failed: {e}")
            return "neutral"

    def calibrate(self, wav_file_path: str) -> dict:
        """
        Set the baseline from a wav sample (ideally ~10 s of calm speech).
        Returns the extracted baseline features dict.
        """
        features = _extract_features(wav_file_path)
        self._save_baseline(features)
        print(f"[EMOTION] Baseline calibrated: {features}")
        return features

    # ── System prompt modifier ────────────────────────────────────────────────

    def get_system_prompt_modifier(self, state_name: str) -> str:
        """Return the system prompt instruction for a given state (empty for neutral)."""
        _modifiers: dict[str, str] = {
            "focused":  "The user is in a focused state. Be maximally concise. No preamble.",
            "fatigued": "The user sounds tired. Keep responses short. Suggest rest if relevant.",
            "stressed": "The user sounds stressed. Use a calm, measured tone. Deprioritize non-critical info.",
            "elevated": "The user is energized. Match their energy. Be dynamic.",
            "neutral":  "",
        }
        return _modifiers.get(state_name, "")


# ── Singleton ──────────────────────────────────────────────────────────────────

_analyzer: Optional[VoiceStateAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_analyzer() -> VoiceStateAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = VoiceStateAnalyzer()
    return _analyzer
