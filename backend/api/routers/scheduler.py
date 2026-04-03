"""
JARVIS-MKIII — api/routers/scheduler.py
REST API for the persistent task scheduler.

  POST   /scheduler/add             → schedule a reminder (natural-language "when")
  DELETE /scheduler/cancel/{id}     → cancel a scheduled task
  GET    /scheduler/list            → list all active tasks
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

scheduler_router = APIRouter(prefix="/scheduler", tags=["scheduler"])
logger = logging.getLogger(__name__)


class ScheduleRequest(BaseModel):
    message: str
    when:    str   # natural-language expression


@scheduler_router.post("/add")
async def schedule_add(body: ScheduleRequest):
    """Parse `when` as a natural-language time expression and schedule the reminder."""
    from core.time_parser import parse_time_expression
    from agents.task_scheduler import get_task_scheduler

    parsed = parse_time_expression(body.when)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse time expression: {body.when!r}. "
                   "Try: 'at 3pm', 'in 20 minutes', 'every morning at 7', 'tomorrow at noon'.",
        )

    ts = get_task_scheduler()
    try:
        result = await ts.schedule_reminder(
            message=body.message,
            run_at=parsed.get("run_at"),
            cron=parsed.get("cron"),
            interval_minutes=parsed.get("interval_minutes"),
        )
    except Exception as exc:
        logger.error("[SCHEDULER] Failed to schedule: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return result


@scheduler_router.delete("/cancel/{task_id}")
async def schedule_cancel(task_id: str):
    """Cancel a scheduled task by ID."""
    from agents.task_scheduler import get_task_scheduler
    ts        = get_task_scheduler()
    cancelled = await ts.cancel_task(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


@scheduler_router.get("/list")
async def schedule_list():
    """Return all active scheduled tasks."""
    from agents.task_scheduler import get_task_scheduler
    ts    = get_task_scheduler()
    tasks = await ts.list_tasks()
    return {"tasks": tasks, "count": len(tasks)}
