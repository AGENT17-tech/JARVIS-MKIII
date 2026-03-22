"""
JARVIS-MKIII — FastAPI Application (Voice-enabled)
Endpoints:
  POST /chat              → single-turn request/response
  WS   /ws/{session_id}  → HUD streaming session (via voice bridge)
  WS   /ws/hud-voice-bridge → voice orchestrator relay
  GET  /status            → health check + model status
  GET  /memory/{sid}      → inspect session memory
  POST /consolidate       → manually trigger memory consolidation
  GET  /tools             → list registered sandbox tools
  POST /tool/{tool_name}  → execute a sandboxed tool
"""

from __future__ import annotations
import uuid
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from core.router import classify, TaskTier
from core.dispatcher import dispatch
from memory.hindsight import memory
from tools.sandbox import sandbox

app = FastAPI(
    title="JARVIS-MKIII",
    description="Multi-tier AI assistant — Sonnet / Opus / DeepSeek-R1 + Voice",
    version="3.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "app://jarvis"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Voice bridge (HUD ↔ voice orchestrator relay) ─────────────────────────────
from api.voice_bridge import voice_router
app.include_router(voice_router)

from api.weather_calendar import weather_router
app.include_router(weather_router)


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    system_prompt: Optional[str] = None
    force_tier: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tier: str
    tier_reason: str
    confidence: float


class ConsolidateRequest(BaseModel):
    session_id: str
    summary: str
    keywords: list[str]


# ── Chat endpoint ─────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    memory.init_session(session_id)

    if req.force_tier:
        try:
            tier = TaskTier(req.force_tier)
            decision = type("D", (), {"tier": tier, "reason": "forced", "confidence": 1.0})()
        except ValueError:
            raise HTTPException(400, f"Invalid tier: {req.force_tier}")
    else:
        decision = classify(req.prompt)

    recalled = memory.recall(req.prompt)
    system   = "\n\n".join(filter(None, [req.system_prompt or "", recalled]))
    history  = memory.get_context(session_id)

    response_text = await dispatch(
        prompt=req.prompt,
        tier=decision.tier,
        history=history,
        system_prompt=system,
        stream=False,
    )

    memory.record(session_id, "user",      req.prompt,    tier=decision.tier.value)
    memory.record(session_id, "assistant", response_text, tier=decision.tier.value)

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        tier=decision.tier.value,
        tier_reason=decision.reason,
        confidence=decision.confidence,
    )


# ── Utility endpoints ─────────────────────────────────────────────────────────

@app.get("/status")
async def status():
    return {
        "status": "online",
        "version": "3.1.0",
        "models": {
            "voice":     "claude-sonnet-4-6",
            "reasoning": "claude-opus-4-6",
            "local":     "deepseek-r1:7b (ollama)",
        },
        "tools": len(sandbox.list_tools()),
        "voice_pipeline": "faster-whisper + kokoro-82m",
    }


@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    return {
        "session_id": session_id,
        "short_term": memory.get_context(session_id),
    }


@app.post("/consolidate")
async def consolidate(req: ConsolidateRequest):
    memory.consolidate(req.session_id, req.summary, req.keywords)
    return {"status": "consolidated", "session_id": req.session_id}


@app.get("/tools")
async def list_tools():
    return {"tools": sandbox.list_tools()}


@app.post("/tool/{tool_name}")
async def run_tool(tool_name: str, args: dict):
    result = await sandbox.run(tool_name, args, auto_confirm=False)
    return {
        "success": result.success,
        "output":  result.output,
        "error":   result.error,
    }
