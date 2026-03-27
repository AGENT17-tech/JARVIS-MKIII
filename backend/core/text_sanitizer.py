"""
JARVIS-MKIII — core/text_sanitizer.py
Strip markdown formatting before passing text to TTS.
"""
from __future__ import annotations
import re


def sanitize_for_tts(text: str) -> str:
    text = text.encode('ascii', 'ignore').decode('ascii')   # strip emojis + all non-ASCII
    text = re.sub(r'\*+', '', text)                         # asterisks / bold
    text = re.sub(r'#+\s*', '', text)                       # headers
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links → label only
    text = re.sub(r'`+', '', text)                          # backticks / code
    text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)     # bold/italic underscores
    text = re.sub(r'\.{2,}', '.', text)                # collapse .. or ... → single period
    text = re.sub(r'\s+', ' ', text).strip()
    return text
