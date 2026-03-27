"""
JARVIS-MKIII — api/routers/whatsapp.py
FastAPI router for the WhatsApp integration.

Endpoints:
  POST /whatsapp/incoming   — Node bridge pushes new messages here
  GET  /whatsapp/status     — bridge connection status
  POST /whatsapp/send       — send a message (contact name or number + text)
  GET  /whatsapp/messages   — last 50 messages from the queue
  GET  /whatsapp/contacts   — proxied from Node bridge
"""

from __future__ import annotations
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from sensors.whatsapp_sensor import whatsapp

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class IncomingMessage(BaseModel):
    from_: str             = None   # 'from' is a reserved Python keyword
    from_name: str         = ""
    body: str              = ""
    timestamp: int         = 0
    is_group: bool         = False
    chat_id: str           = ""

    class Config:
        populate_by_name = True
        extra = "allow"           # accept extra fields from the bridge


class SendRequest(BaseModel):
    contact: str           # name substring, phone number, or full chat_id
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/incoming")
async def incoming(payload: dict):
    """
    Receive a message from the Node bridge and enqueue it.
    Accepts the raw dict so we don't choke on unexpected fields.
    """
    # Normalise 'from' → 'from_name' conflict: bridge sends key 'from'
    msg = dict(payload)
    msg.setdefault("from_name", msg.get("from_name") or msg.get("from", ""))
    msg.setdefault("read", False)
    await whatsapp.push_incoming(msg)
    return {"ok": True}


@router.post("/status")
async def bridge_status(payload: dict):
    """
    Node bridge posts connection status updates here.
    Just ack — the real state is queried live via GET /whatsapp/status.
    """
    return {"ok": True}


@router.get("/status")
async def get_status():
    """Live connection status from the Node bridge."""
    status = await whatsapp.get_status()
    status["unread_count"] = whatsapp.get_unread_count()
    return status


@router.post("/send")
async def send_message(req: SendRequest):
    """
    Send a WhatsApp message.
    'contact' can be a saved contact name, phone number, or raw chat_id (xxx@c.us).
    """
    chat_id = req.contact if req.contact.endswith("@c.us") else None
    if chat_id is None:
        chat_id = await whatsapp.resolve_contact(req.contact)
    if chat_id is None:
        raise HTTPException(404, f"Contact not found: {req.contact!r}")

    result = await whatsapp.send_message(chat_id, req.message)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return {"ok": True, "chat_id": chat_id}


@router.get("/messages")
async def get_messages(limit: int = 50, unread_only: bool = False):
    """Return recent messages from the internal queue."""
    msgs = await whatsapp.poll_incoming(limit=limit, unread_only=unread_only)
    return {"messages": msgs, "total": len(msgs), "unread": whatsapp.get_unread_count()}


@router.get("/contacts")
async def get_contacts():
    """Proxy to the Node bridge /contacts endpoint."""
    contacts = await whatsapp.get_contacts()
    return {"contacts": contacts}
