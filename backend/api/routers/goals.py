"""
JARVIS-MKIII — api/routers/goals.py
REST API for the multi-step goal tracker.

  GET  /goals/active  → list all active goals with step progress
  POST /goals/create  → create a new goal with explicit steps
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

goals_router = APIRouter(prefix="/goals", tags=["goals"])
logger = logging.getLogger(__name__)


class GoalCreateRequest(BaseModel):
    title: str
    steps: list[str]


@goals_router.get("/active")
async def list_active_goals():
    """Return all currently active goals with step-level progress."""
    from core.goal_tracker import get_goal_tracker
    gt = get_goal_tracker()
    goals = gt.list_active()
    return {"goals": goals, "count": len(goals)}


@goals_router.post("/create")
async def create_goal(body: GoalCreateRequest):
    """Create a new goal with explicit steps."""
    if not body.steps:
        raise HTTPException(status_code=422, detail="At least one step is required.")
    from core.goal_tracker import get_goal_tracker
    gt = get_goal_tracker()
    try:
        goal = gt.create_goal(title=body.title, steps=body.steps)
    except Exception as exc:
        logger.error("[GOALS] Failed to create goal: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return goal
