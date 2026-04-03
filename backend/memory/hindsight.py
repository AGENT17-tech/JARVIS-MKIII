"""
JARVIS-MKIII — hindsight.py
Two-layer memory:
  SHORT-TERM → in-memory sliding window per session
  LONG-TERM  → SQLite keyword search
"""

from __future__ import annotations
import sqlite3, json, time
from pathlib import Path
from dataclasses import dataclass, field
from config.settings import MEMORY_CFG

DB_PATH = Path(__file__).parent.parent / MEMORY_CFG.long_term_db


@dataclass
class Message:
    role:       str
    content:    str
    timestamp:  float = field(default_factory=time.time)
    tier:       str   = "voice"
    session_id: str   = ""


class ShortTermMemory:
    def __init__(self, limit: int = MEMORY_CFG.short_term_limit):
        self._limit    = limit
        self._sessions: dict[str, list[Message]] = {}

    def add(self, session_id: str, msg: Message) -> None:
        buf = self._sessions.setdefault(session_id, [])
        buf.append(msg)
        if len(buf) > self._limit:
            buf.pop(0)

    def get(self, session_id: str) -> list[Message]:
        return self._sessions.get(session_id, [])

    def to_api_format(self, session_id: str) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.get(session_id)]

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class LongTermMemory:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = __import__("threading").Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                summary        TEXT NOT NULL,
                keywords       TEXT NOT NULL,
                source_session TEXT NOT NULL,
                timestamp      REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id    TEXT PRIMARY KEY,
                started_at    REAL NOT NULL,
                last_active   REAL NOT NULL,
                message_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tool_calls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name   TEXT NOT NULL,
                args        TEXT NOT NULL,
                success     INTEGER NOT NULL,
                output      TEXT NOT NULL,
                error       TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                timestamp   REAL NOT NULL
            );
        """)
        self._conn.commit()

    def store(self, summary: str, keywords: list, session_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO memories (summary, keywords, source_session, timestamp) VALUES (?,?,?,?)",
                (summary, json.dumps(keywords), session_id, time.time())
            )
            self._conn.commit()
            return cur.lastrowid

    def log_tool_call(self, tool_name: str, args: dict, result, duration_ms: int) -> None:
        import json as _json
        with self._lock:
            self._conn.execute(
                "INSERT INTO tool_calls (tool_name, args, success, output, error, duration_ms, timestamp) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    tool_name,
                    _json.dumps(args, default=str),
                    1 if result.success else 0,
                    result.output[:2000],
                    result.error[:500],
                    duration_ms,
                    time.time(),
                ),
            )
            self._conn.commit()

    def get_tool_history(self, limit: int = 50) -> list[dict]:
        import json as _json
        rows = self._conn.execute(
            "SELECT tool_name, args, success, output, error, duration_ms, timestamp "
            "FROM tool_calls ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "tool_name":   r[0],
                "args":        _json.loads(r[1]),
                "success":     bool(r[2]),
                "output":      r[3],
                "error":       r[4],
                "duration_ms": r[5],
                "timestamp":   r[6],
            }
            for r in rows
        ]

    def retrieve(self, query: str, top_k: int = 5) -> list:
        words = set(query.lower().split())
        rows  = self._conn.execute(
            "SELECT id, summary, keywords, source_session, timestamp FROM memories ORDER BY timestamp DESC LIMIT 200"
        ).fetchall()
        scored = []
        for row in rows:
            kws     = set(json.loads(row[2]))
            overlap = len(words & kws)
            if overlap > 0:
                scored.append((overlap, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def register_session(self, session_id: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, started_at, last_active) VALUES (?,?,?)",
                (session_id, now, now)
            )
            self._conn.commit()

    def touch_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET last_active=?, message_count=message_count+1 WHERE session_id=?",
                (time.time(), session_id)
            )
            self._conn.commit()


class HindsightMemory:
    def __init__(self):
        self.short = ShortTermMemory()
        self.long  = LongTermMemory()

    def record(self, session_id: str, role: str, content: str, tier: str = "voice") -> None:
        msg = Message(role=role, content=content, tier=tier, session_id=session_id)
        self.short.add(session_id, msg)
        self.long.touch_session(session_id)

    def get_context(self, session_id: str) -> list[dict]:
        history = self.short.to_api_format(session_id)
        history = [
            msg for msg in history
            if not (
                msg.get("role") == "assistant" and
                any(phrase in msg.get("content", "") for phrase in ["Tony Stark", "Iron Man", "Tony's", "genius billionaire"])
            )
        ]
        return history

    def clear_session(self, session_id: str) -> None:
        if session_id in self.short._sessions:
            self.short._sessions[session_id] = []

    def recall(self, query: str, top_k: int = 3) -> str:
        entries = self.long.retrieve(query, top_k=top_k)
        if not entries:
            return ""
        lines = ["[Relevant past context:]"]
        for e in entries:
            lines.append(f"- {e[1]}")
        return "\n".join(lines)

    def log_tool_call(self, tool_name: str, args: dict, result, duration_ms: int) -> None:
        self.long.log_tool_call(tool_name, args, result, duration_ms)

    def get_tool_history(self, limit: int = 50) -> list[dict]:
        return self.long.get_tool_history(limit=limit)

    def consolidate(self, session_id: str, summary: str, keywords: list) -> None:
        self.long.store(summary, keywords, session_id)

    def init_session(self, session_id: str) -> None:
        self.long.register_session(session_id)

    def get_session_interactions(self, session_id: str, limit: int = 50) -> list[dict]:
        """Return the last `limit` messages for a session in API format."""
        msgs = self.short.get(session_id)[-limit:]
        return [{"role": m.role, "content": m.content} for m in msgs]

    def get_active_sessions(self) -> list[str]:
        """Return all session IDs that have at least one message in short-term memory."""
        return list(self.short._sessions.keys())


memory = HindsightMemory()
