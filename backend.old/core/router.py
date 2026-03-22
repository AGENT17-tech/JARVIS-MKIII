from __future__ import annotations
import re
from enum import Enum
from dataclasses import dataclass

class TaskTier(str, Enum):
    VOICE = "voice"
    REASONING = "reasoning"
    LOCAL = "local"

@dataclass
class RoutingDecision:
    tier: TaskTier
    reason: str
    confidence: float

_LOCAL_PATTERNS = [
    r"\bvault\b", r"\bsecret\b", r"\bencrypt\b", r"\bdecrypt\b",
    r"\boffline\b", r"\bsensitive\b", r"\bpassword\b",
]
_LOCAL_RE = re.compile("|".join(_LOCAL_PATTERNS), re.IGNORECASE)

def classify(prompt: str) -> RoutingDecision:
    if _LOCAL_RE.search(prompt):
        return RoutingDecision(
            tier=TaskTier.LOCAL,
            reason="Sensitive operation — local only",
            confidence=0.95,
        )
    return RoutingDecision(
        tier=TaskTier.VOICE,
        reason="Routing to Groq Llama 3.3 70B",
        confidence=0.9,
    )
