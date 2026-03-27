"""
JARVIS-MKIII — core/language_detector.py
Detect whether input text is Arabic-script or English.
Arabic, Urdu, and Persian all share Arabic Unicode range — treat all as "ar"
for TTS routing purposes (gTTS ar voice handles Egyptian Arabic).
"""
from __future__ import annotations
import re

# Arabic Unicode block: U+0600–U+06FF covers Arabic, Urdu, Persian etc.
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')


def detect_language(text: str) -> str:
    """Returns 'ar' or 'en'. Arabic-script characters → 'ar'."""
    if _ARABIC_RE.search(text):
        return "ar"
    # langdetect as secondary signal for non-ASCII Latin-script languages
    try:
        from langdetect import detect
        lang = detect(text)
        return "ar" if lang in ("ar", "ur", "fa") else "en"
    except Exception:
        pass
    return "en"
