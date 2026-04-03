"""
JARVIS-MKIII — session_summarizer.py
Summarizes long sessions into 3-bullet digests stored in ChromaDB.
"""

from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

MIN_INTERACTIONS = 10  # don't summarize very short sessions


async def summarize_session(
    session_id: str,
    interactions: list[dict],
    force: bool = False,
) -> str | None:
    """
    Ask Groq to distill `interactions` into a 3-bullet summary.
    Returns None if the session is too short (unless force=True).
    """
    if not force and len(interactions) < MIN_INTERACTIONS:
        logger.debug(
            "[SUMMARIZER] Session %s skipped — only %d interactions (min %d)",
            session_id, len(interactions), MIN_INTERACTIONS,
        )
        return None

    # Build condensed transcript for the prompt
    lines = []
    for m in interactions[-50:]:  # cap at last 50 to stay within token budget
        role = "Khalid" if m["role"] == "user" else "JARVIS"
        lines.append(f"{role}: {m['content'][:200]}")
    transcript = "\n".join(lines)

    prompt = (
        "Summarize the following JARVIS session in exactly 3 concise bullet points. "
        "Focus on decisions made, topics discussed, and any action items. "
        "Be specific, not generic.\n\n"
        f"SESSION {session_id}:\n{transcript}"
    )

    try:
        from core.vault import Vault
        from config.settings import MODEL_CFG
        from groq import AsyncGroq

        vault = Vault()
        client = AsyncGroq(api_key=vault.get("GROQ_API_KEY"))
        resp = await client.chat.completions.create(
            model=MODEL_CFG.groq_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
        )
        summary = resp.choices[0].message.content.strip()
        logger.info("[SUMMARIZER] Session %s summarized (%d chars).", session_id, len(summary))
        return summary
    except Exception as exc:
        logger.error("[SUMMARIZER] Failed to summarize session %s: %s", session_id, exc)
        return None


def store_session_summary(session_id: str, summary: str) -> None:
    """Persist the summary in ChromaDB with session_summary metadata."""
    try:
        from memory.chroma_store import get_store
        store = get_store()
        doc_id = f"session_summary_{session_id}_{int(datetime.utcnow().timestamp())}"
        store._col.add(
            ids=[doc_id],
            documents=[summary],
            metadatas=[{
                "type": "session_summary",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        )
        logger.info("[SUMMARIZER] Summary stored in ChromaDB for session %s.", session_id)
    except Exception as exc:
        logger.error("[SUMMARIZER] Failed to store summary for session %s: %s", session_id, exc)
