"""
JARVIS-MKIII — api/routers/td.py
FastAPI endpoints for TouchDesigner OSC bridge.
"""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

td_router = APIRouter(prefix="/td", tags=["touchdesigner"])


class OSCSendRequest(BaseModel):
    address: str
    args: list[Any] = []


@td_router.post("/send")
async def td_send(req: OSCSendRequest):
    """Send a custom OSC message to TouchDesigner."""
    from integrations.touchdesigner_bridge import send_event
    send_event(req.address, *req.args)
    return {"status": "sent", "address": req.address, "args": req.args}


@td_router.get("/status")
async def td_status():
    """Return TouchDesigner bridge connection info."""
    from integrations.touchdesigner_bridge import TD_HOST, TD_PORT, is_available
    return {
        "host":      TD_HOST,
        "port":      TD_PORT,
        "available": is_available(),
    }
