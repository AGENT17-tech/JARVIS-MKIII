"""
JARVIS-MKIII — api/routers/phantom.py
PHANTOM ZERO domain tracking endpoints.

  GET  /phantom/scores    → today's domain scores
  GET  /phantom/weekly    → 7-day trend
  POST /phantom/log       → log an activity
  GET  /phantom/brief     → daily brief addendum
  GET  /phantom/priority  → priority recommendation
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

# Phantom module lives at project root/phantom/ — add to path if needed
_PHANTOM_ROOT = Path(__file__).parent.parent.parent.parent / "phantom"
if str(_PHANTOM_ROOT) not in sys.path:
    sys.path.insert(0, str(_PHANTOM_ROOT.parent))

phantom_router = APIRouter(prefix="/phantom", tags=["phantom"])


class LogRequest(BaseModel):
    domain:        str
    activity_type: str
    value:         float = 1.0
    notes:         Optional[str] = ""


@phantom_router.get("/scores")
async def phantom_scores():
    from phantom.phantom_os import get_phantom
    return get_phantom().get_today_scores()


@phantom_router.get("/weekly")
async def phantom_weekly():
    from phantom.phantom_os import get_phantom
    return get_phantom().get_weekly_trend()


@phantom_router.post("/log", status_code=201)
async def phantom_log(req: LogRequest):
    try:
        from phantom.phantom_os import get_phantom
        get_phantom().log_activity(req.domain, req.activity_type, req.value, req.notes or "")
        return {"status": "logged", "domain": req.domain, "activity_type": req.activity_type, "value": req.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@phantom_router.get("/brief")
async def phantom_brief():
    from phantom.phantom_os import get_phantom
    return {"addendum": get_phantom().generate_daily_brief_addendum()}


@phantom_router.get("/priority")
async def phantom_priority():
    from phantom.phantom_os import get_phantom
    return {"recommendation": get_phantom().get_priority_recommendation()}
