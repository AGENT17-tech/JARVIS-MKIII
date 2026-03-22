"""
JARVIS-MKIII — voice_bridge.py
Add this WebSocket endpoint to api/main.py.

It acts as a relay between the voice orchestrator and the HUD:
  voice_orchestrator → WS /ws/hud-voice-bridge → broadcast to all HUD clients

Paste the router into main.py with:
    from api.voice_bridge import voice_router
    app.include_router(voice_router)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

voice_router = APIRouter()

# All active HUD connections
_hud_clients: list[WebSocket] = []

# The voice orchestrator's connection
_voice_ws: WebSocket | None = None


@voice_router.websocket("/ws/hud-voice-bridge")
async def voice_bridge(websocket: WebSocket):
    """
    The voice orchestrator connects here.
    Any message it sends is broadcast to all HUD clients.
    """
    global _voice_ws
    await websocket.accept()
    _voice_ws = websocket
    print("[BRIDGE] Voice orchestrator connected.")
    try:
        async for message in websocket.iter_text():
            # Broadcast to all connected HUD sessions
            dead = []
            for client in _hud_clients:
                try:
                    await client.send_text(message)
                except Exception:
                    dead.append(client)
            for d in dead:
                _hud_clients.remove(d)
    except WebSocketDisconnect:
        print("[BRIDGE] Voice orchestrator disconnected.")
        _voice_ws = None


@voice_router.websocket("/ws/{session_id}")
async def hud_session(websocket: WebSocket, session_id: str):
    """
    HUD clients connect here (replaces the existing /ws/{session_id} in main.py).
    Registered so the bridge can broadcast to them.
    Also handles direct chat messages from the HUD.
    """
    from memory.hindsight import memory
    from core.router import classify
    from core.dispatcher import dispatch
    import json

    await websocket.accept()
    memory.init_session(session_id)
    _hud_clients.append(websocket)
    print(f"[BRIDGE] HUD client connected: {session_id}")

    try:
        async for raw in websocket.iter_text():
            try:
                payload = json.loads(raw)
                prompt = payload.get("prompt", "")
                if not prompt:
                    continue

                decision = classify(prompt)
                recalled = memory.recall(prompt)
                history  = memory.get_context(session_id)

                await websocket.send_json({
                    "type": "routing",
                    "tier": decision.tier.value,
                    "reason": decision.reason,
                })

                full_response = []
                stream = await dispatch(
                    prompt=prompt,
                    tier=decision.tier,
                    history=history,
                    system_prompt=recalled,
                    stream=True,
                )
                async for token in stream:
                    full_response.append(token)
                    await websocket.send_json({"type": "token", "text": token})

                await websocket.send_json({"type": "done"})

                response_text = "".join(full_response)
                memory.record(session_id, "user",      prompt,        tier=decision.tier.value)
                memory.record(session_id, "assistant", response_text, tier=decision.tier.value)

            except Exception as e:
                print(f"[BRIDGE] Error handling HUD message: {e}")

    except WebSocketDisconnect:
        _hud_clients.remove(websocket)
        print(f"[BRIDGE] HUD client disconnected: {session_id}")
