from __future__ import annotations
import re
from enum import Enum
from dataclasses import dataclass


class TaskTier(str, Enum):
    VOICE     = "voice"    # Groq — fast, smart, free
    REASONING = "reasoning" # Groq — same model, flagged for deep tasks
    LOCAL     = "local"    # Ollama — sensitive/offline only
    COMPLEX   = "complex"  # Claude Haiku — long/multi-step reasoning


@dataclass
class RoutingDecision:
    tier:       TaskTier
    reason:     str
    confidence: float


_LOCAL_RE = re.compile(
    r"\bvault\b|\bsecret\b|\bencrypt\b|\bdecrypt\b|\boffline\b|\bpassword\b|\bsensitive\b",
    re.IGNORECASE
)

_REASONING_RE = re.compile(
    r"\banalyse\b|\banalyze\b|\bexplain\b|\bplan\b|\bstrategy\b|\bcompare\b|\bdesign\b"
    r"|\bsolve\b|\bdebug\b|\brefactor\b|\barchitect\b|\bwhy\b|\bhow does\b|\bwrite a\b"
    r"|\bsummarise\b|\bsummarize\b|\bresearch\b|\bevaluate\b|\breview\b",
    re.IGNORECASE
)


def classify(prompt: str) -> RoutingDecision:
    if _LOCAL_RE.search(prompt):
        return RoutingDecision(
            tier=TaskTier.LOCAL,
            reason="Sensitive operation — local only",
            confidence=0.95,
        )

    # Complex routing — check word count and keyword list from settings
    try:
        from config.settings import MODEL_CFG
        if MODEL_CFG.complex_routing_enabled:
            word_count = len(prompt.split())
            kw_hit     = any(kw.lower() in prompt.lower() for kw in MODEL_CFG.complex_keywords)
            if word_count >= MODEL_CFG.complex_threshold_words or kw_hit:
                return RoutingDecision(
                    tier=TaskTier.COMPLEX,
                    reason="Long/complex prompt — routing to Claude",
                    confidence=0.88,
                )
    except Exception:
        pass

    if _REASONING_RE.search(prompt) or len(prompt.split()) > 30:
        return RoutingDecision(
            tier=TaskTier.REASONING,
            reason="Complex task — deep reasoning mode",
            confidence=0.85,
        )
    return RoutingDecision(
        tier=TaskTier.VOICE,
        reason="Routing to Groq Llama 3.3 70B",
        confidence=0.9,
    )
