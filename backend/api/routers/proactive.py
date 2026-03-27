"""
JARVIS-MKIII — api/routers/proactive.py
Endpoints for the autonomous proactive agent.

GET  /proactive/status   — agent health + counters
GET  /proactive/history  — last 20 alerts fired
POST /proactive/config   — update thresholds + interval
POST /proactive/silence  — suppress alerts for N minutes
POST /proactive/trigger  — manually trigger a scan
"""

from __future__ import annotations
import time
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

proactive_router = APIRouter(prefix="/proactive", tags=["proactive"])


def _agent():
    from agents.proactive_agent import agent as _a
    return _a


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConfigRequest(BaseModel):
    calendar_warn_minutes: int | None = None
    cpu_threshold:         int | None = None
    ram_threshold:         int | None = None
    vram_threshold:        int | None = None
    check_interval:        int | None = None
    mission_stale_hours:   int | None = None


class SilenceRequest(BaseModel):
    duration_minutes: int = 30


class TriggerRequest(BaseModel):
    source: str = "all"   # "all" | "calendar" | "github" | "system" | "weather" | "missions" | "whatsapp"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@proactive_router.get("/status")
async def get_status():
    """Full status of the proactive agent."""
    a   = _agent()
    now = time.time()
    silenced = now < a._silenced_until
    return {
        "running":            a._running,
        "check_interval":     a._config.get("check_interval", 60),
        "alerts_fired_today": a._alerts_fired_today,
        "last_scan":          a._last_scan.isoformat() if a._last_scan else None,
        "silenced":           silenced,
        "silenced_until":     (
            datetime.fromtimestamp(a._silenced_until).isoformat()
            if silenced else None
        ),
        "active_monitors": [
            "calendar", "github", "system_health",
            "weather", "missions", "whatsapp",
        ],
        "config": a._config,
    }


@proactive_router.get("/history")
async def get_history():
    """Last 20 proactive alerts, newest first."""
    a       = _agent()
    history = list(reversed(a._history[-20:]))
    return {"alerts": history, "total": len(a._history)}


@proactive_router.post("/config")
async def update_config(req: ConfigRequest):
    """Persist threshold and interval updates."""
    a       = _agent()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        a.save_config(updates)
    return {"config": a._config}


@proactive_router.post("/silence")
async def silence(req: SilenceRequest):
    """Silence all proactive alerts for the requested duration."""
    a                  = _agent()
    a._silenced_until  = time.time() + req.duration_minutes * 60
    until_dt           = datetime.fromtimestamp(a._silenced_until)
    return {
        "silenced":         True,
        "until":            until_dt.isoformat(),
        "duration_minutes": req.duration_minutes,
    }


@proactive_router.post("/resume")
async def resume():
    """Cancel silence — resume proactive alerts immediately."""
    a                 = _agent()
    a._silenced_until = 0.0
    return {"silenced": False}


@proactive_router.post("/trigger")
async def trigger(req: TriggerRequest):
    """Manually run a scan of one or all sources."""
    import asyncio
    a = _agent()
    asyncio.create_task(a.trigger_scan(req.source))
    return {
        "triggered": req.source,
        "message":   f"Scan triggered for source: {req.source}",
    }
