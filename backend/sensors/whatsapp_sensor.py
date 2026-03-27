"""
JARVIS-MKIII — sensors/whatsapp_sensor.py
Internal interface to the WhatsApp bridge Node service.

Usage (from the FastAPI router or main.py):
  from sensors.whatsapp_sensor import whatsapp

  await whatsapp.send_message("628xxx@c.us", "Hello")
  status = await whatsapp.get_status()
  contacts = await whatsapp.get_contacts()
"""

from __future__ import annotations
import asyncio
import time
from collections import deque
from typing import Optional
import httpx

BRIDGE_URL = "http://localhost:3001"
MAX_QUEUE  = 200   # keep last N messages in memory

# ── Shared message queue (filled by /whatsapp/incoming endpoint) ──────────────
_message_queue: deque[dict] = deque(maxlen=MAX_QUEUE)
_queue_lock    = asyncio.Lock()


class WhatsAppSensor:
    """Thin async wrapper around the Node bridge HTTP API."""

    # ── Queue management ──────────────────────────────────────────────────────

    async def push_incoming(self, msg: dict) -> None:
        """Called by the FastAPI router when a message arrives from the bridge."""
        msg.setdefault("received_at", time.time())
        async with _queue_lock:
            _message_queue.appendleft(msg)

    async def poll_incoming(self, limit: int = 50, unread_only: bool = False) -> list[dict]:
        """Return up to *limit* messages from the internal queue (newest first)."""
        async with _queue_lock:
            msgs = list(_message_queue)[:limit]
        if unread_only:
            msgs = [m for m in msgs if not m.get("read")]
        return msgs

    async def mark_read(self, chat_ids: list[str]) -> None:
        """Mark messages from given chat_ids as read."""
        async with _queue_lock:
            for msg in _message_queue:
                if msg.get("chat_id") in chat_ids:
                    msg["read"] = True

    def get_unread_count(self) -> int:
        return sum(1 for m in _message_queue if not m.get("read"))

    # ── Bridge HTTP calls ─────────────────────────────────────────────────────

    async def send_message(self, chat_id: str, text: str) -> dict:
        """POST /send to the Node bridge. Returns {"ok": true} or {"error": ...}."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{BRIDGE_URL}/send",
                    json={"chat_id": chat_id, "message": text},
                )
                return r.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_status(self) -> dict:
        """GET /status from the Node bridge."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{BRIDGE_URL}/status")
                return r.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    async def get_contacts(self) -> list[dict]:
        """GET /contacts from the Node bridge."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{BRIDGE_URL}/contacts")
                return r.json().get("contacts", [])
        except Exception as e:
            return []

    async def resolve_contact(self, name_or_number: str) -> Optional[str]:
        """
        Given a name or number string, return the WhatsApp chat_id (e.g. 2010xxx@c.us).
        Returns None if not found.
        """
        contacts = await self.get_contacts()
        query = name_or_number.lower().strip()

        # Exact number match
        for c in contacts:
            if query == c.get("number", ""):
                return c["id"]

        # Name substring match
        for c in contacts:
            if query in c.get("name", "").lower():
                return c["id"]

        # If looks like a number, try building a chat_id directly
        digits = "".join(ch for ch in name_or_number if ch.isdigit())
        if len(digits) >= 7:
            return f"{digits}@c.us"

        return None

    def format_for_voice(self, messages: list[dict], max_msgs: int = 3) -> str:
        """Convert message list to a TTS-friendly string."""
        if not messages:
            return "No new WhatsApp messages, sir."
        lines = []
        for m in messages[:max_msgs]:
            name = m.get("from_name") or m.get("from", "Unknown")
            body = m.get("body", "")
            lines.append(f"From {name}: {body}")
        tail = f" — and {len(messages) - max_msgs} more." if len(messages) > max_msgs else "."
        return "Your WhatsApp messages: " + ". ".join(lines) + tail


# Singleton
whatsapp = WhatsAppSensor()
