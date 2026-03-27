"""
JARVIS-MKIII — memory/rag_memory.py
RAG (Retrieval-Augmented Generation) long-term episodic memory engine.

Uses ChromaDB for persistent vector storage and sentence-transformers
for local CPU embedding. Stores every conversation exchange permanently
and supports semantic recall.
"""
from __future__ import annotations
import json, uuid
from datetime import datetime
from pathlib import Path

DB_PATH    = Path(__file__).parent.parent.parent / "data" / "chromadb"
EMBED_MODEL = "all-MiniLM-L6-v2"  # fast, 384-dim, CPU-only


class RAGMemory:
    def __init__(self):
        DB_PATH.mkdir(parents=True, exist_ok=True)
        import chromadb
        from chromadb.config import Settings
        from sentence_transformers import SentenceTransformer

        self._client = chromadb.PersistentClient(
            path=str(DB_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        self._embedder = SentenceTransformer(EMBED_MODEL)

        self._conversations = self._client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )
        self._missions = self._client.get_or_create_collection(
            name="missions",
            metadata={"hnsw:space": "cosine"},
        )
        self._facts = self._client.get_or_create_collection(
            name="facts",
            metadata={"hnsw:space": "cosine"},
        )
        print("[RAG] Memory engine initialized.")

    # ── Write ──────────────────────────────────────────────────────────────────

    def store_conversation(
        self,
        user_msg: str,
        jarvis_msg: str,
        session_id: str,
        metadata: dict | None = None,
    ) -> None:
        """Permanently store a conversation exchange."""
        doc = f"User: {user_msg}\nJARVIS: {jarvis_msg}"
        embedding = self._embedder.encode(doc).tolist()
        meta = {
            "session_id": session_id,
            "timestamp":  datetime.now().isoformat(),
            "date":       datetime.now().strftime("%Y-%m-%d"),
            "user_msg":   user_msg[:500],
            "jarvis_msg": jarvis_msg[:500],
            **(metadata or {}),
        }
        self._conversations.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            documents=[doc],
            metadatas=[meta],
        )

    def store_fact(
        self,
        fact: str,
        source: str = "conversation",
        tags: list[str] | None = None,
    ) -> None:
        """Store a standalone fact for long-term recall."""
        embedding = self._embedder.encode(fact).tolist()
        self._facts.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            documents=[fact],
            metadatas=[{
                "source":    source,
                "tags":      json.dumps(tags or []),
                "timestamp": datetime.now().isoformat(),
                "date":      datetime.now().strftime("%Y-%m-%d"),
            }],
        )
        print(f"[RAG] Fact stored: {fact[:80]}")

    # ── Read ───────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        n_results: int = 5,
        collection: str = "conversations",
        date_filter: str | None = None,
    ) -> list[dict]:
        """Semantic search across a memory collection."""
        col = self._get_collection(collection)
        count = col.count()
        if count == 0:
            return []

        embedding = self._embedder.encode(query).tolist()
        where = {"date": {"$eq": date_filter}} if date_filter else None

        results = col.query(
            query_embeddings=[embedding],
            n_results=min(n_results, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        for i, doc in enumerate(results["documents"][0]):
            items.append({
                "document":  doc,
                "metadata":  results["metadatas"][0][i],
                "relevance": 1 - results["distances"][0][i],
            })
        return items

    def recall(self, query: str, n_results: int = 5) -> str:
        """Search conversations + facts + missions and merge results."""
        all_results = []

        for collection_name in ("conversations", "facts", "missions"):
            col = self._get_collection(collection_name)
            if col.count() == 0:
                continue
            try:
                embedding = self._embedder.encode(query).tolist()
                results = col.query(
                    query_embeddings=[embedding],
                    n_results=min(n_results, col.count()),
                    include=["documents", "metadatas", "distances"],
                )
                for i, doc in enumerate(results["documents"][0]):
                    relevance = 1 - results["distances"][0][i]
                    if relevance > 0.2:
                        all_results.append({
                            "document":   doc,
                            "metadata":   results["metadatas"][0][i],
                            "relevance":  relevance,
                            "collection": collection_name,
                        })
            except Exception:
                continue

        if not all_results:
            return "No relevant memories found."

        all_results.sort(key=lambda x: x["relevance"], reverse=True)

        context = []
        for r in all_results[:n_results]:
            date = r["metadata"].get("date", "unknown date")
            context.append(f"[{date}] {r['document'][:300]}")

        return "\n\n".join(context) if context else "No sufficiently relevant memories found."

    def get_stats(self) -> dict:
        return {
            "conversations": self._conversations.count(),
            "facts":         self._facts.count(),
            "missions":      self._missions.count(),
            "db_path":       str(DB_PATH),
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _get_collection(self, name: str):
        return {
            "conversations": self._conversations,
            "facts":         self._facts,
            "missions":      self._missions,
        }.get(name, self._conversations)


# ── Singleton ──────────────────────────────────────────────────────────────────
_rag: RAGMemory | None = None


def get_rag() -> RAGMemory:
    global _rag
    if _rag is None:
        _rag = RAGMemory()
    return _rag
