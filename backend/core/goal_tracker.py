"""
JARVIS-MKIII — core/goal_tracker.py
Multi-step goal persistence backed by SQLite.
Goals survive process restart and are displayed on MissionBoard.
"""
from __future__ import annotations
import sqlite3
import uuid
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "goals.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    goal_id    TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    status     TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    done_at    TEXT
);
CREATE TABLE IF NOT EXISTS goal_steps (
    step_id     TEXT PRIMARY KEY,
    goal_id     TEXT NOT NULL REFERENCES goals(goal_id),
    step_num    INTEGER NOT NULL,
    description TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    result      TEXT DEFAULT '',
    started_at  TEXT,
    done_at     TEXT
);
"""


class GoalTracker:
    """Persistent multi-step goal tracker backed by SQLite."""

    def __init__(self):
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def create_goal(self, title: str, steps: list[str]) -> dict:
        """Create a new goal with N steps. Returns the goal dict."""
        gid = str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()
        self._db.execute(
            "INSERT INTO goals (goal_id, title, status, created_at) VALUES (?,?,?,?)",
            (gid, title, "active", now),
        )
        for i, desc in enumerate(steps, 1):
            sid = f"{gid}-s{i}"
            self._db.execute(
                "INSERT INTO goal_steps (step_id, goal_id, step_num, description) VALUES (?,?,?,?)",
                (sid, gid, i, desc),
            )
        self._db.commit()
        logger.info("[GOAL] Created goal %s: %s (%d steps)", gid, title, len(steps))
        return self.get_goal(gid)

    def get_goal(self, goal_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT goal_id, title, status, created_at, done_at FROM goals WHERE goal_id=?",
            (goal_id,),
        ).fetchone()
        if not row:
            return None
        steps = self._db.execute(
            "SELECT step_id, step_num, description, status, result "
            "FROM goal_steps WHERE goal_id=? ORDER BY step_num",
            (goal_id,),
        ).fetchall()
        return {
            "goal_id":    row[0],
            "title":      row[1],
            "status":     row[2],
            "created_at": row[3],
            "done_at":    row[4],
            "steps": [
                {
                    "step_id":     s[0],
                    "step_num":    s[1],
                    "description": s[2],
                    "status":      s[3],
                    "result":      s[4],
                }
                for s in steps
            ],
        }

    def update_step(self, step_id: str, status: str, result: str = "") -> None:
        now = datetime.now().isoformat()
        if status == "running":
            self._db.execute(
                "UPDATE goal_steps SET status=?, started_at=? WHERE step_id=?",
                (status, now, step_id),
            )
        else:
            self._db.execute(
                "UPDATE goal_steps SET status=?, result=?, done_at=? WHERE step_id=?",
                (status, result, now, step_id),
            )
        self._db.commit()

    def complete_goal(self, goal_id: str) -> None:
        now = datetime.now().isoformat()
        self._db.execute(
            "UPDATE goals SET status='complete', done_at=? WHERE goal_id=?",
            (now, goal_id),
        )
        self._db.commit()

    def list_active(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT goal_id FROM goals WHERE status='active' ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for (gid,) in rows:
            g = self.get_goal(gid)
            if g:
                result.append(g)
        return result


_tracker: GoalTracker | None = None


def get_goal_tracker() -> GoalTracker:
    global _tracker
    if _tracker is None:
        _tracker = GoalTracker()
    return _tracker
