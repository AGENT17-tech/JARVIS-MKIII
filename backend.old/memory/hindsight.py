"""
JARVIS-MKIII — Hindsight Memory System
Two-layer memory architecture:

  SHORT-TERM  → in-memory sliding window (last N messages per session)
  LONG-TERM   → SQLite store with keyword-based retrieval

The "Hindsight" model: after every assistant response, JARVIS optionally
distils a summary of what was learned into long-term storage. On future turns
relevant past context is injected into the system prompt automatically.
"""

from __future__ import annotations
import sqlite3
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from config.settings import MEMORY_CFG

DB_PATH = Path(__file__).parent.parent / MEMORY_CFG.long_term_db


# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str           # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    tier: str = "voice"  # which model tier handled this
    session_id: str = ""


@dataclass
class MemoryEntry:
    id: int
    summary: str
    keywords: list[str]
    source_session: str
    timestamp: float


# ── Short-term memory (per session, in-memory) ────────────────────────────────

class ShortTermMemory:
    def __init__(self, limit: int = MEMORY_CFG.short_term_limit):
        self._limit = limit
        self._sessions: dict[str, list[Message]] = {}

    def add(self, session_id: str, msg: Message) -> None:
        buf = self._sessions.setdefault(session_id, [])
        buf.append(msg)
        if len(buf) > self._limit:
            buf.pop(0)

    def get(self, session_id: str) -> list[Message]:
        return self._sessions.get(session_id, [])

    def to_api_format(self, session_id: str) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in self.get(session_id)
        ]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# ── Long-term memory (SQLite) ─────────────────────────────────────────────────

class LongTermMemory:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                summary         TEXT NOT NULL,
                keywords        TEXT NOT NULL,
                source_session  TEXT NOT NULL,
                timestamp       REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id  TEXT PRIMARY KEY,
                started_at  REAL NOT NULL,
                last_active REAL NOT NULL,
                message_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(timestamp DESC);
        """)
        self._conn.commit()

    def store(self, summary: str, keywords: list[str], session_id: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO memories (summary, keywords, source_session, timestamp) VALUES (?,?,?,?)",
            (summary, json.dumps(keywords), session_id, time.time())
        )
        self._conn.commit()
        return cur.lastrowid

    def retrieve(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """
        Keyword-based retrieval. Replace with vector search once
        nomic-embed-text is wired up via Ollama.
        """
        words = set(query.lower().split())
        rows = self._conn.execute(
            "SELECT id, summary, keywords, source_session, timestamp "
            "FROM memories ORDER BY timestamp DESC LIMIT 200"
        ).fetchall()

        scored = []
        for row in rows:
            kws = set(json.loads(row[2]))
            overlap = len(words & kws)
            if overlap > 0:
                scored.append((overlap, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, row in scored[:top_k]:
            results.append(MemoryEntry(
                id=row[0], summary=row[1],
                keywords=json.loads(row[2]),
                source_session=row[3], timestamp=row[4]
            ))
        return results

    def register_session(self, session_id: str) -> None:
        now = time.time()
        self._conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, started_at, last_active) VALUES (?,?,?)",
            (session_id, now, now)
        )
        self._conn.commit()

    def touch_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET last_active=?, message_count=message_count+1 WHERE session_id=?",
            (time.time(), session_id)
        )
        self._conn.commit()


# ── Unified Hindsight interface ───────────────────────────────────────────────

class HindsightMemory:
    """
    The single interface the rest of JARVIS uses for all memory operations.
    """
    def __init__(self):
        self.short = ShortTermMemory()
        self.long  = LongTermMemory()

    def record(self, session_id: str, role: str, content: str, tier: str = "voice") -> None:
        msg = Message(role=role, content=content, tier=tier, session_id=session_id)
        self.short.add(session_id, msg)
        self.long.touch_session(session_id)

    def get_context(self, session_id: str) -> list[dict]:
        """Returns short-term history in Anthropic message format."""
        return self.short.to_api_format(session_id)

    def recall(self, query: str, top_k: int = 3) -> str:
        """
        Returns relevant long-term memories as an injected system prompt block.
        Empty string if nothing relevant found.
        """
        entries = self.long.retrieve(query, top_k=top_k)
        if not entries:
            return ""
        lines = ["[Relevant past context from long-term memory:]"]
        for e in entries:
            lines.append(f"- {e.summary}")
        return "\n".join(lines)

    def consolidate(self, session_id: str, summary: str, keywords: list[str]) -> None:
        """
        Store a distilled summary of the current exchange into long-term memory.
        Call this after significant exchanges (agent task completions, learned facts).
        """
        self.long.store(summary, keywords, session_id)

    def init_session(self, session_id: str) -> None:
        self.long.register_session(session_id)


# Singleton
memory = HindsightMemory()
