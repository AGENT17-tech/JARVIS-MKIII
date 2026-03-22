"""
JARVIS-MKIII — agents/agent_dispatcher.py
Central registry for all operative agents.
Manages spawning, status, cancellation, and HUD WebSocket broadcast.

Endpoints added to FastAPI app (included via agent_router):
  GET  /agents              → list all agent states
  POST /agents/spawn        → spawn a named agent
  WS   /ws/agents           → real-time agent event stream to HUD AgentFeed
"""
from __future__ import annotations
import asyncio, json, time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

agent_router = APIRouter()

# ── WS client registry ────────────────────────────────────────────────────────
_ws_clients: list[WebSocket] = []

# ── Agent instance registry ───────────────────────────────────────────────────
# Maps agent_id → agent instance
_agents: dict[str, object] = {}


# ── Broadcast helper ──────────────────────────────────────────────────────────
async def broadcast_event(event: dict) -> None:
    """Push a JSON event to all connected HUD AgentFeed WebSocket clients."""
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


# ── Dispatcher class ──────────────────────────────────────────────────────────
class AgentDispatcher:

    def __init__(self):
        self._hud_clients: set[WebSocket] = set()

    def register_hud_client(self, ws: WebSocket) -> None:
        self._hud_clients.add(ws)

    async def broadcast_event(self, event_type: str, data: dict) -> None:
        """Broadcast an event to all connected HUD WebSocket clients."""
        message = json.dumps({"type": event_type, "data": data})
        disconnected = []
        for client in self._hud_clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            self._hud_clients.discard(client)

    async def spawn(self, agent_name: str, task: str) -> str:
        """
        Create an agent instance by name and start it in a background task.
        Returns the agent_id.
        """
        agent = self._make_agent(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        _agents[agent.agent_id] = agent
        loop = asyncio.get_event_loop()
        task_obj = loop.create_task(agent.run(task), name=f"{agent_name}:{agent.agent_id}")
        agent._task_obj = task_obj
        return agent.agent_id

    def get_status(self, agent_id: str) -> dict | None:
        agent = _agents.get(agent_id)
        return agent.report() if agent else None

    def get_all(self) -> list[dict]:
        return [a.report() for a in _agents.values()]

    def cancel(self, agent_id: str) -> bool:
        agent = _agents.get(agent_id)
        if agent:
            agent.cancel()
            return True
        return False

    @staticmethod
    def _make_agent(name: str):
        name = name.lower()
        if name == "research":
            from agents.research_agent import ResearchAgent
            return ResearchAgent()
        if name == "code":
            from agents.code_agent import CodeAgent
            return CodeAgent()
        if name in ("file", "organize"):
            from agents.file_agent import FileAgent
            return FileAgent()
        if name == "autogui":
            from agents.autogui_agent import AutoGUIAgent
            return AutoGUIAgent()
        if name == "vision":
            from agents.vision_agent import VisionAgent
            return VisionAgent()
        if name == "dev":
            from agents.dev_agent import DevAgent
            return DevAgent()
        return None


dispatcher = AgentDispatcher()


# ── WebSocket endpoint — HUD AgentFeed connects here ─────────────────────────
@agent_router.websocket("/ws/agents")
async def agent_feed_ws(websocket: WebSocket):
    await websocket.accept()
    dispatcher.register_hud_client(websocket)
    print(f"[AGENTS] HUD AgentFeed connected ({len(dispatcher._hud_clients)} clients)")

    # Replay current agent states to new client
    for state in dispatcher.get_all():
        try:
            await websocket.send_json({"type": "agent_event", **state})
        except Exception:
            break

    try:
        async for _ in websocket.iter_text():
            pass   # AgentFeed is read-only; ignore any incoming messages
    except WebSocketDisconnect:
        pass
    finally:
        dispatcher._hud_clients.discard(websocket)
        print(f"[AGENTS] HUD AgentFeed disconnected ({len(dispatcher._hud_clients)} clients)")


# ── REST endpoints ────────────────────────────────────────────────────────────
class SpawnRequest(BaseModel):
    agent: str
    task:  str


@agent_router.get("/agents")
async def list_agents():
    return {"agents": dispatcher.get_all()}


@agent_router.post("/agents/spawn")
async def spawn_agent(req: SpawnRequest):
    try:
        agent_id = await dispatcher.spawn(req.agent, req.task)
        return {"status": "spawned", "agent_id": agent_id}
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@agent_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    state = dispatcher.get_status(agent_id)
    if state is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return state


@agent_router.post("/agents/{agent_id}/cancel")
async def cancel_agent_post(agent_id: str):
    ok = dispatcher.cancel(agent_id)
    return {"cancelled": ok}


@agent_router.delete("/agents/{agent_id}")
async def cancel_agent(agent_id: str):
    ok = dispatcher.cancel(agent_id)
    return {"cancelled": ok}
