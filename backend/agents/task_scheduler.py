"""
JARVIS-MKIII — agents/task_scheduler.py
Persistent task scheduler backed by SQLite + APScheduler.

Supports:
  - One-shot reminders   ("remind me at 3pm")
  - Cron schedules       ("every morning at 7")
  - Interval schedules   ("every 30 minutes")

Tasks survive process restart: all active jobs are reloaded from
data/scheduled_tasks.db on startup.
"""

from __future__ import annotations
import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DB_PATH      = _PROJECT_ROOT / "data" / "scheduled_tasks.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id      TEXT PRIMARY KEY,
    message      TEXT NOT NULL,
    run_at       TEXT,          -- ISO datetime for one-shot tasks
    cron_expr    TEXT,          -- cron expression for recurring tasks
    interval_min INTEGER,       -- interval in minutes for recurring tasks
    task_type    TEXT NOT NULL, -- "once" | "cron" | "interval"
    created_at   TEXT NOT NULL,
    fired_count  INTEGER DEFAULT 0,
    active       INTEGER DEFAULT 1  -- 1=active, 0=cancelled/fired
);
"""


class TaskScheduler:
    """Persistent, restart-safe task scheduler."""

    def __init__(self, scheduler: "AsyncIOScheduler"):
        self._sched  = scheduler
        self._db     = self._init_db()

    # ── DB init ───────────────────────────────────────────────────────────────

    def _init_db(self) -> sqlite3.Connection:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        return conn

    # ── Public API ────────────────────────────────────────────────────────────

    async def schedule_reminder(
        self,
        message:          str,
        run_at:           datetime | None = None,
        cron:             str | None      = None,
        interval_minutes: int | None      = None,
        task_id:          str | None      = None,
    ) -> dict:
        """
        Schedule a reminder. Exactly one of run_at / cron / interval_minutes
        must be provided.

        Returns a descriptor dict:
            {"task_id", "message", "scheduled_for", "type"}
        """
        tid = task_id or str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()

        if run_at is not None:
            task_type  = "once"
            scheduled_for = run_at.isoformat()
            self._sched.add_job(
                self._fire_task,
                trigger="date",
                run_date=run_at,
                args=[tid, message],
                id=tid,
                replace_existing=True,
                misfire_grace_time=300,
            )
        elif cron is not None:
            task_type  = "cron"
            scheduled_for = cron
            parts = cron.split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron expression: {cron!r}")
            minute, hour, day, month, day_of_week = parts
            self._sched.add_job(
                self._fire_task,
                trigger="cron",
                minute=minute, hour=hour, day=day,
                month=month, day_of_week=day_of_week,
                args=[tid, message],
                id=tid,
                replace_existing=True,
            )
        elif interval_minutes is not None:
            task_type  = "interval"
            scheduled_for = f"every {interval_minutes}m"
            self._sched.add_job(
                self._fire_task,
                trigger="interval",
                minutes=interval_minutes,
                args=[tid, message],
                id=tid,
                replace_existing=True,
            )
        else:
            raise ValueError("Must provide run_at, cron, or interval_minutes.")

        # Persist to SQLite
        self._db.execute(
            """INSERT OR REPLACE INTO scheduled_tasks
               (task_id, message, run_at, cron_expr, interval_min, task_type, created_at, active)
               VALUES (?,?,?,?,?,?,?,1)""",
            (tid, message,
             run_at.isoformat() if run_at else None,
             cron, interval_minutes, task_type, now),
        )
        self._db.commit()
        logger.info("[SCHEDULER] Scheduled task %s type=%s for=%s", tid, task_type, scheduled_for)

        return {"task_id": tid, "message": message, "scheduled_for": scheduled_for, "type": task_type}

    async def cancel_task(self, task_id: str) -> bool:
        """Remove a scheduled task by ID. Returns True if found."""
        try:
            self._sched.remove_job(task_id)
        except Exception:
            pass  # job may have already fired
        rows = self._db.execute(
            "UPDATE scheduled_tasks SET active=0 WHERE task_id=? AND active=1",
            (task_id,),
        ).rowcount
        self._db.commit()
        if rows:
            logger.info("[SCHEDULER] Cancelled task %s", task_id)
        return rows > 0

    async def list_tasks(self) -> list[dict]:
        """Return all currently active tasks."""
        rows = self._db.execute(
            """SELECT task_id, message, run_at, cron_expr, interval_min,
                      task_type, created_at, fired_count
               FROM scheduled_tasks WHERE active=1
               ORDER BY created_at DESC"""
        ).fetchall()
        return [
            {
                "task_id":      r[0],
                "message":      r[1],
                "run_at":       r[2],
                "cron":         r[3],
                "interval_min": r[4],
                "type":         r[5],
                "created_at":   r[6],
                "fired_count":  r[7],
            }
            for r in rows
        ]

    # ── Reload on startup ─────────────────────────────────────────────────────

    async def reload_from_db(self) -> int:
        """Re-register all active tasks after a process restart. Returns count."""
        rows = self._db.execute(
            """SELECT task_id, message, run_at, cron_expr, interval_min, task_type
               FROM scheduled_tasks WHERE active=1"""
        ).fetchall()
        reloaded = 0
        for tid, message, run_at_str, cron_expr, interval_min, task_type in rows:
            try:
                if task_type == "once":
                    run_at = datetime.fromisoformat(run_at_str)
                    if run_at <= datetime.now():
                        # Missed — fire immediately then mark inactive
                        asyncio.create_task(self._fire_task(tid, message))
                        continue
                    self._sched.add_job(
                        self._fire_task, trigger="date", run_date=run_at,
                        args=[tid, message], id=tid, replace_existing=True,
                        misfire_grace_time=300,
                    )
                elif task_type == "cron" and cron_expr:
                    parts = cron_expr.split()
                    minute, hour, day, month, dow = parts
                    self._sched.add_job(
                        self._fire_task, trigger="cron",
                        minute=minute, hour=hour, day=day, month=month, day_of_week=dow,
                        args=[tid, message], id=tid, replace_existing=True,
                    )
                elif task_type == "interval" and interval_min:
                    self._sched.add_job(
                        self._fire_task, trigger="interval", minutes=interval_min,
                        args=[tid, message], id=tid, replace_existing=True,
                    )
                reloaded += 1
            except Exception as exc:
                logger.warning("[SCHEDULER] Could not reload task %s: %s", tid, exc)
        logger.info("[SCHEDULER] Reloaded %d active task(s) from DB.", reloaded)
        return reloaded

    # ── Firing ────────────────────────────────────────────────────────────────

    async def _fire_task(self, task_id: str, message: str) -> None:
        """Execute a scheduled task: speak + log + deactivate one-shots."""
        logger.info("[SCHEDULER] Firing task %s: %s", task_id, message[:80])

        # Speak via TTS
        try:
            from api.voice_bridge import request_speak
            await request_speak(message)
        except Exception as exc:
            logger.warning("[SCHEDULER] TTS failed for task %s: %s", task_id, exc)

        # Log to hindsight
        try:
            from memory.hindsight import memory
            memory.record("scheduler", "assistant", f"[Reminder] {message}")
        except Exception:
            pass

        # Update fired_count; deactivate one-shot tasks
        self._db.execute(
            "UPDATE scheduled_tasks SET fired_count=fired_count+1 WHERE task_id=?",
            (task_id,),
        )
        row = self._db.execute(
            "SELECT task_type FROM scheduled_tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row and row[0] == "once":
            self._db.execute(
                "UPDATE scheduled_tasks SET active=0 WHERE task_id=?", (task_id,)
            )
        self._db.commit()


# ── Singleton (initialised by lifespan in main.py) ────────────────────────────
_scheduler_instance: TaskScheduler | None = None


def get_task_scheduler() -> TaskScheduler:
    if _scheduler_instance is None:
        raise RuntimeError("TaskScheduler not initialised. Call init_task_scheduler() first.")
    return _scheduler_instance


def init_task_scheduler(apscheduler_instance) -> TaskScheduler:
    global _scheduler_instance
    _scheduler_instance = TaskScheduler(apscheduler_instance)
    return _scheduler_instance
