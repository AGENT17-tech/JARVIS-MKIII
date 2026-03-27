"""
JARVIS-MKIII — memory/chroma_store.py
Domain-aware ChromaDB memory store.

Stores conversation exchanges with automatic domain tagging and supports
filtered semantic retrieval. Single collection "jarvis_memory" with
metadata-based domain partitioning.
"""
from __future__ import annotations

import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH     = Path(__file__).parent.parent.parent / "data" / "chromadb"
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION  = "jarvis_memory"

# ── Domain keywords ────────────────────────────────────────────────────────────
_DOMAIN_RULES: list[tuple[str, list[str]]] = [
    ("engineering", ["code", "python", "cpp", "javascript", "typescript", "rust",
                     "function", "class", "algorithm", "debug", "compile", "git",
                     "docker", "api", "sql", "script", "programming", "software"]),
    ("combat",      ["combat", "workout", "kickbox", "kickboxing", "fight", "spar",
                     "boxing", "training", "gym", "punch", "kick", "jiu", "muay",
                     "anaconda", "cardio", "strength", "drill"]),
    ("strategy",    ["chess", "strategy", "mission", "plan", "objective", "tactic",
                     "decision", "goal", "deploy", "operation", "project", "roadmap"]),
    ("language",    ["arabic", "language", "italian", "french", "spanish", "grammar",
                     "vocabulary", "translate", "translation", "word", "phrase",
                     "pronunciation", "dialect"]),
]


def _detect_domain(text: str) -> str:
    lower = text.lower()
    for domain, keywords in _DOMAIN_RULES:
        if any(kw in lower for kw in keywords):
            return domain
    return "general"


# ── Store ──────────────────────────────────────────────────────────────────────

class ChromaStore:
    def __init__(self) -> None:
        DB_PATH.mkdir(parents=True, exist_ok=True)
        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer

        self._client = chromadb.PersistentClient(
            path=str(DB_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        self._embedder = SentenceTransformer(EMBED_MODEL)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[ChromaStore] Initialized — {self._col.count()} memories loaded.")

    # ── Write ──────────────────────────────────────────────────────────────────

    def store_memory(
        self,
        user_text: str,
        jarvis_text: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Embed and persist a conversation exchange with domain tagging."""
        combined = f"User: {user_text}\nJARVIS: {jarvis_text}"
        domain   = _detect_domain(user_text + " " + jarvis_text)
        now      = datetime.now()
        meta = {
            "timestamp":  now.isoformat(),
            "date":       now.strftime("%Y-%m-%d"),
            "domain":     domain,
            "user_text":  user_text[:500],
            "jarvis_text": jarvis_text[:500],
            "session_id": (metadata or {}).get("session_id", "unknown"),
        }
        if metadata:
            # Merge extra keys — skip ones already set
            for k, v in metadata.items():
                if k not in meta:
                    meta[k] = str(v)

        embedding = self._embedder.encode(combined).tolist()
        self._col.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            documents=[combined],
            metadatas=[meta],
        )

    # ── Read ───────────────────────────────────────────────────────────────────

    def retrieve_relevant(
        self,
        query: str,
        n: int = 5,
        domain_filter: Optional[str] = None,
    ) -> str:
        """Return top-n semantically similar past exchanges as a formatted string."""
        count = self._col.count()
        if count == 0:
            return ""

        embedding = self._embedder.encode(query).tolist()
        where = {"domain": {"$eq": domain_filter}} if domain_filter else None

        # Clamp n to available documents (per-domain count may be < n)
        try:
            results = self._col.query(
                query_embeddings=[embedding],
                n_results=min(n, count),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return ""

        docs     = results["documents"][0]
        metas    = results["metadatas"][0]
        dists    = results["distances"][0]

        parts: list[str] = []
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
            relevance = 1 - dist
            if relevance < 0.15:       # skip noise
                continue
            user_t   = meta.get("user_text",  doc[:200])
            jarvis_t = meta.get("jarvis_text", "")
            parts.append(f"[MEMORY {i}] User: {user_t} | JARVIS: {jarvis_t}")

        return "\n".join(parts)

    def get_memory_stats(self) -> dict:
        """Return total count, per-domain breakdown, oldest/newest timestamps."""
        total = self._col.count()
        if total == 0:
            return {
                "total":   0,
                "domains": {},
                "oldest":  None,
                "newest":  None,
            }

        # Pull all metadata to compute domain breakdown + timestamps
        all_items = self._col.get(include=["metadatas"])
        metas     = all_items["metadatas"]

        domains: dict[str, int] = {}
        timestamps: list[str]   = []

        for m in metas:
            d = m.get("domain", "general")
            domains[d] = domains.get(d, 0) + 1
            ts = m.get("timestamp")
            if ts:
                timestamps.append(ts)

        timestamps.sort()
        return {
            "total":   total,
            "domains": domains,
            "oldest":  timestamps[0]  if timestamps else None,
            "newest":  timestamps[-1] if timestamps else None,
        }

    def clear(self) -> None:
        """Delete and recreate the jarvis_memory collection."""
        self._client.delete_collection(COLLECTION)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )


# ── Singleton + thread-safe background write ───────────────────────────────────

_store: ChromaStore | None = None
_lock  = threading.Lock()


def get_store() -> ChromaStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = ChromaStore()
    return _store


def store_memory_bg(user_text: str, jarvis_text: str, metadata: Optional[dict] = None) -> None:
    """Fire-and-forget: run store_memory in a daemon thread."""
    def _run():
        try:
            get_store().store_memory(user_text, jarvis_text, metadata)
        except Exception as e:
            print(f"[ChromaStore] Background store failed: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
