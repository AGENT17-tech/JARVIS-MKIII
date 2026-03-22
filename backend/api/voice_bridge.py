"""
JARVIS-MKIII — voice_bridge.py
WebSocket relay:
  Voice orchestrator → /ws/hud-voice-bridge → broadcasts to all HUD clients
  HUD clients        → /ws/{session_id}     → chat streaming + voice signals

FIX: Added message buffer so HUD clients that connect after the greeting
     was sent still receive it on join (late-join replay).
"""

from __future__ import annotations
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

voice_router  = APIRouter()
_hud_clients: list[WebSocket] = []
_voice_ws:    WebSocket | None = None
_is_speaking: bool             = False


def is_speaking() -> bool:
    """True while the voice orchestrator is playing TTS audio."""
    return _is_speaking


async def broadcast_to_hud(payload: dict) -> None:
    """Send a JSON payload to every connected HUD session WebSocket client."""
    dead = []
    msg  = json.dumps(payload)
    for client in _hud_clients:
        try:
            await client.send_text(msg)
        except Exception:
            dead.append(client)
    for d in dead:
        if d in _hud_clients:
            _hud_clients.remove(d)

# ── Late-join replay buffer ───────────────────────────────────────────────────
# Stores the last N messages from the voice orchestrator.
# New HUD clients receive these immediately on connect so they never miss
# the boot greeting even if they join after it was broadcast.
_REPLAY_LIMIT   = 6
_replay_buffer: list[str] = []


def _buffer(message: str) -> None:
    """Add message to replay buffer, capped at _REPLAY_LIMIT."""
    _replay_buffer.append(message)
    if len(_replay_buffer) > _REPLAY_LIMIT:
        _replay_buffer.pop(0)


async def request_speak(text: str) -> None:
    """Ask the voice orchestrator to speak a given text via TTS."""
    if _voice_ws is not None:
        try:
            await _voice_ws.send_text(f"speak:{text}")
        except Exception:
            pass


@voice_router.websocket("/ws/hud-voice-bridge")
async def voice_bridge(websocket: WebSocket):
    """Voice orchestrator connects here. Messages are buffered and broadcast to all HUD clients."""
    global _voice_ws
    await websocket.accept()

    # Close any stale previous connection before replacing it
    old = _voice_ws
    if old is not None:
        try:
            await old.close()
        except Exception:
            pass

    _voice_ws = websocket
    print("[BRIDGE] Voice orchestrator connected.")
    try:
        async for message in websocket.iter_text():
            # Track TTS speaking state so proactive engine can wait its turn
            global _is_speaking
            if message == "speaking:start":
                _is_speaking = True
            elif message == "speaking:stop":
                _is_speaking = False

            # Buffer every message for late-joining HUD clients
            _buffer(message)

            # Broadcast to all currently connected HUD clients
            dead = []
            for client in _hud_clients:
                try:
                    await client.send_text(message)
                except Exception:
                    dead.append(client)
            for d in dead:
                if d in _hud_clients:
                    _hud_clients.remove(d)
    except WebSocketDisconnect:
        pass
    finally:
        if _voice_ws is websocket:
            _voice_ws = None
        print("[BRIDGE] Voice orchestrator disconnected.")


@voice_router.websocket("/ws/{session_id}")
async def hud_session(websocket: WebSocket, session_id: str):
    """HUD clients connect here for streaming chat + voice signal relay."""
    from memory.hindsight import memory

    await websocket.accept()
    memory.init_session(session_id)

    # Remove any stale client for the same session (React StrictMode reconnects)
    _hud_clients[:] = [c for c in _hud_clients if c is not websocket]
    _hud_clients.append(websocket)
    print(f"[BRIDGE] HUD connected: {session_id}")

    # ── Replay buffered voice messages to this client immediately ─────────────
    # This ensures the greeting and any recent voice events are shown even
    # if the HUD connected after they were originally broadcast.
    if _replay_buffer:
        print(f"[BRIDGE] Replaying {len(_replay_buffer)} buffered message(s) to {session_id}")
        for msg in _replay_buffer:
            try:
                await websocket.send_text(msg)
            except Exception:
                break

    try:
        async for raw in websocket.iter_text():
            try:
                payload = json.loads(raw)
                prompt  = payload.get("prompt", "")
                if not prompt:
                    continue

                # ── Route through the full chat handler (intent routing + LLM) ──
                # Lazy import avoids circular dependency (main.py imports voice_bridge
                # at module level; we import main lazily inside this function body,
                # by which point main is fully loaded).
                from api.main import chat as _chat, ChatRequest as _ChatRequest
                req    = _ChatRequest(prompt=prompt, session_id=session_id)
                result = await _chat(req)

                # chat() already called memory.record() and request_speak() —
                # no need to repeat them here.
                await websocket.send_json({
                    "type":   "routing",
                    "tier":   result.tier,
                    "reason": result.tier_reason,
                })
                await websocket.send_json({"type": "token", "text": result.response})
                await websocket.send_json({"type": "done"})

            except Exception as e:
                print(f"[BRIDGE] Error: {e}")

    except WebSocketDisconnect:
        if websocket in _hud_clients:
            _hud_clients.remove(websocket)
        print(f"[BRIDGE] HUD disconnected: {session_id}")
