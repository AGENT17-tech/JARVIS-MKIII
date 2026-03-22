"""
JARVIS-MKIII — core/mission_board.py
Daily Mission Board with SQLite storage.

Missions:  { id, date, title, description, priority, status, created_at, completed_at, notes }
Priorities: critical | high | medium | low
Statuses:   pending | in_progress | complete | deferred
"""
from __future__ import annotations
import sqlite3, uuid, datetime
from pathlib import Path

DB_PATH = Path.home() / "JARVIS_MKIII" / "backend" / "data" / "jarvis.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id           TEXT PRIMARY KEY,
                date         TEXT NOT NULL,
                title        TEXT NOT NULL,
                description  TEXT NOT NULL DEFAULT '',
                priority     TEXT NOT NULL DEFAULT 'medium',
                status       TEXT NOT NULL DEFAULT 'pending',
                created_at   REAL NOT NULL,
                completed_at REAL,
                notes        TEXT NOT NULL DEFAULT ''
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_missions_date ON missions(date)
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS missions_log (
                id         TEXT PRIMARY KEY,
                date       TEXT NOT NULL,
                summary    TEXT NOT NULL,
                completed  INTEGER NOT NULL DEFAULT 0,
                total      INTEGER NOT NULL DEFAULT 0,
                logged_at  REAL NOT NULL
            )
        """)
        c.commit()


_init_db()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _today() -> str:
    return datetime.date.today().isoformat()


def _now() -> float:
    return datetime.datetime.now().timestamp()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_mission(title: str, description: str = "", priority: str = "medium") -> dict:
    mid   = str(uuid.uuid4())[:8]
    today = _today()
    now   = _now()
    with _conn() as c:
        c.execute(
            "INSERT INTO missions (id, date, title, description, priority, status, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (mid, today, title, description, priority, "pending", now),
        )
        c.commit()
    return get_mission(mid)


def get_mission(mid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM missions WHERE id = ?", (mid,)).fetchone()
        return _row_to_dict(row) if row else None


def update_status(mid: str, status: str, notes: str = "") -> dict | None:
    now = _now()
    with _conn() as c:
        if status == "complete":
            c.execute(
                "UPDATE missions SET status=?, notes=?, completed_at=? WHERE id=?",
                (status, notes, now, mid),
            )
        else:
            c.execute(
                "UPDATE missions SET status=?, notes=? WHERE id=?",
                (status, notes, mid),
            )
        c.commit()
    return get_mission(mid)


def complete_mission(mid: str, notes: str = "") -> dict | None:
    return update_status(mid, "complete", notes)


def defer_mission(mid: str) -> dict | None:
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    with _conn() as c:
        c.execute(
            "UPDATE missions SET date=?, status='pending' WHERE id=?",
            (tomorrow, mid),
        )
        c.commit()
    return get_mission(mid)


def delete_mission(mid: str) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM missions WHERE id=?", (mid,))
        c.commit()
        return c.execute("SELECT changes()").fetchone()[0] > 0


# ── Queries ───────────────────────────────────────────────────────────────────

def get_today() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM missions WHERE date=? ORDER BY created_at",
            (_today(),),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_all(date_filter: str | None = None) -> list[dict]:
    with _conn() as c:
        if date_filter:
            rows = c.execute(
                "SELECT * FROM missions WHERE date=? ORDER BY created_at",
                (date_filter,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM missions ORDER BY date DESC, created_at"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]


# ── Statistics ────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    today = _today()
    with _conn() as c:
        rows     = c.execute("SELECT status FROM missions WHERE date=?", (today,)).fetchall()
        statuses = [r["status"] for r in rows]
        total     = len(statuses)
        completed = statuses.count("complete")

        # Daily streak — consecutive days with ≥1 completed mission
        streak = 0
        check  = datetime.date.today()
        while True:
            cnt = c.execute(
                "SELECT COUNT(*) AS n FROM missions WHERE date=? AND status='complete'",
                (check.isoformat(),),
            ).fetchone()["n"]
            if cnt == 0:
                break
            streak += 1
            check -= datetime.timedelta(days=1)

        return {
            "today_total":       total,
            "today_completed":   completed,
            "today_pending":     statuses.count("pending"),
            "today_in_progress": statuses.count("in_progress"),
            "completion_rate":   round(completed / total * 100) if total else 0,
            "streak_days":       streak,
        }


# ── End-of-day summary ────────────────────────────────────────────────────────

def end_of_day_summary() -> dict:
    today    = _today()
    missions = get_today()
    completed = [m for m in missions if m["status"] == "complete"]
    pending   = [m for m in missions if m["status"] == "pending"]
    in_prog   = [m for m in missions if m["status"] == "in_progress"]
    deferred  = [m for m in missions if m["status"] == "deferred"]

    # Write daily log
    log_id = str(uuid.uuid4())[:8]
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO missions_log (id, date, summary, completed, total, logged_at)"
            " VALUES (?,?,?,?,?,?)",
            (log_id, today,
             f"{len(completed)}/{len(missions)} missions completed",
             len(completed), len(missions), _now()),
        )
        c.commit()

    briefing = _build_eod_briefing(completed, pending, in_prog)
    return {
        "date":             today,
        "total":            len(missions),
        "completed":        completed,
        "pending":          pending,
        "in_progress":      in_prog,
        "deferred":         deferred,
        "completion_rate":  round(len(completed) / len(missions) * 100) if missions else 0,
        "briefing":         briefing,
    }


def _build_eod_briefing(completed: list, pending: list, in_prog: list) -> str:
    c, p, ip = len(completed), len(pending), len(in_prog)
    total    = c + p + ip
    if total == 0:
        return "No missions logged for today, sir."

    parts = [f"End of day report, sir. {c} of {total} missions completed."]
    if completed:
        titles = ", ".join(m["title"] for m in completed[:3])
        if c > 3:
            titles += f" and {c - 3} more"
        parts.append(f"Completed: {titles}.")
    if pending:
        titles = ", ".join(m["title"] for m in pending[:2])
        parts.append(f"{p} mission{'s' if p > 1 else ''} pending: {titles}.")
    if in_prog:
        parts.append(f"{ip} still in progress.")
    return " ".join(parts)
