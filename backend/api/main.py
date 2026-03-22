# JARVIS-MKIII backend entry point

"""
JARVIS-MKIII — api/main.py
All backend endpoints in one place.

Endpoints:
  POST /chat              → send a message, get a response
  GET  /health            → health check (alias)
  GET  /status            → health check + version info
  GET  /weather           → live Cairo weather
  GET  /calendar          → current date/time/calendar data
  GET  /forecast          → 5-day forecast
  GET  /memory/{sid}      → inspect session memory
  POST /consolidate       → save to long-term memory
  GET  /tools             → list sandbox tools
  POST /tool/{name}       → run a sandboxed tool
  GET  /apps              → list open applications
  GET  /agents            → list operative agents
  POST /agents/spawn      → spawn a named agent
  DELETE /agents/{id}     → cancel an agent
  WS   /ws/{session_id}   → HUD streaming chat + voice relay
  WS   /ws/hud-voice-bridge → voice orchestrator relay
  WS   /ws/agents         → agent event feed (HUD AgentFeed)
"""

from __future__ import annotations
import asyncio, json, os, uuid, time as _time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

_START_TIME = _time.time()   # track uptime for /diagnostic

from core.router import classify, TaskTier, RoutingDecision
from core.dispatcher import dispatch
from memory.hindsight import memory
from tools.sandbox import sandbox
from api.voice_bridge import voice_router, request_speak
from api.weather_calendar import weather_router
from system.intent_router import parse_intent
from system.app_controller import launch_app, close_app, list_open_apps
from system.desktop_control import (
    take_screenshot, type_text, press_shortcut,
    youtube_control, get_time_date,
)
from system.terminal_controller import (
    execute, smart_install, remove_package, update_system, format_result,
)
from agents.agent_dispatcher import agent_router, dispatcher as agent_dispatcher


# ── Startup / shutdown lifecycle ──────────────────────────────────────────────
async def _daily_analysis_loop() -> None:
    """Run adaptive pattern extraction every 24 hours."""
    while True:
        await asyncio.sleep(86400)
        try:
            from core.adaptive_memory import run_daily_analysis
            await run_daily_analysis()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background monitor agent
    from agents.monitor_agent import monitor
    monitor.start()
    # Start daily adaptive analysis loop
    analysis_task = asyncio.create_task(_daily_analysis_loop())
    # Start proactive intelligence engine
    from core.proactive_engine import engine as proactive_engine
    proactive_engine.start()
    yield
    # Shutdown
    monitor.stop()
    proactive_engine.stop()
    analysis_task.cancel()
    try:
        from system.browser_agent import browser
        await browser.close()
    except Exception:
        pass
    try:
        from mcp.mcp_hub import close_all as mcp_close_all
        await mcp_close_all()
    except Exception:
        pass


app = FastAPI(title="JARVIS-MKIII", version="3.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)     # /ws/hud-voice-bridge + /ws/{session_id}
app.include_router(weather_router)   # /weather + /calendar + /forecast
app.include_router(agent_router)     # /agents + /ws/agents


# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    prompt:        str
    session_id:    Optional[str] = None
    system_prompt: Optional[str] = None
    force_tier:    Optional[str] = None


class ChatResponse(BaseModel):
    response:    str
    session_id:  str
    tier:        str
    tier_reason: str
    confidence:  float


class ConsolidateRequest(BaseModel):
    session_id: str
    summary:    str
    keywords:   list[str]


# ── Mission schemas ────────────────────────────────────────────────────────────
class MissionCreate(BaseModel):
    title:       str
    description: Optional[str] = ""
    priority:    Optional[str] = "medium"


class MissionPatch(BaseModel):
    status: Optional[str] = None
    notes:  Optional[str] = ""


# ── Adaptive feedback schema ───────────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    session_id: str
    feedback:   str   # "response_approved" | "response_failed" | "response_accepted"


# ── Confirmation store ────────────────────────────────────────────────────────
# Maps session_id → {"action": str, "payload": str|None}
_pending: dict[str, dict] = {}

_CONFIRM_WORDS = {
    "yes", "confirm", "proceed", "do it", "yeah", "yep",
    "go ahead", "affirmative", "ok", "okay", "execute",
}
_CANCEL_WORDS = {
    "no", "cancel", "abort", "don't", "never mind",
    "nope", "negative", "stop", "forget it",
}

# Actions that need terminal/package confirmation
_TERMINAL_ACTIONS = {"terminal", "install", "remove", "update"}

# OS operations that need confirmation before execution
_OS_DESTRUCTIVE = {
    "delete":              lambda a: f"Shall I delete {a.get('path', '?')}, sir?",
    "kill_process":        lambda a: f"Shall I terminate '{a.get('name_or_pid', '?')}', sir?",
    "power_shutdown":      lambda a: "Shall I shut down the system, sir?",
    "power_reboot":        lambda a: "Shall I reboot now, sir?",
    "power_sleep":         lambda a: "Shall I suspend the system, sir?",
    "disconnect_interface": lambda a: f"Shall I disconnect interface '{a.get('interface', '?')}', sir?",
}


def _confirmation_question(action: str, payload: str | None) -> str:
    if action == "terminal":
        return f"Shall I run '{payload}', sir?"
    if action == "install":
        return f"Confirm installation of {payload}, sir?"
    if action == "remove":
        return f"Confirm removal of {payload}, sir?"
    if action == "update":
        return "Shall I update all system packages, sir?"
    if action == "os_op":
        try:
            op_data = json.loads(payload)
            fn = _OS_DESTRUCTIVE.get(op_data.get("op", ""))
            if fn:
                return fn(op_data.get("args", {}))
        except Exception:
            pass
    return "Confirm, sir?"


async def _execute_pending(action: str, payload: str | None) -> str:
    """Run the confirmed command and return a TTS-safe sentence."""
    if action == "terminal":
        result = await execute(payload)
    elif action == "install":
        result = await smart_install(payload)
    elif action == "remove":
        result = await remove_package(payload)
    elif action == "update":
        result = await update_system()
    elif action == "os_op":
        try:
            op_data = json.loads(payload)
            return await _run_os_op(op_data)
        except Exception as e:
            return f"That did not go as planned, sir. {e}"
    else:
        return "I'm not sure what to execute, sir."
    return format_result(action, payload, result)


def _quick_response(text: str, session_id: str, tier: str = "voice") -> ChatResponse:
    return ChatResponse(
        response=text,
        session_id=session_id,
        tier=tier,
        tier_reason="system-control",
        confidence=1.0,
    )


# ── OS operation dispatch ─────────────────────────────────────────────────────
async def _run_os_op(op_data: dict) -> str:
    """
    Execute a parsed OS operation dict {"op": str, "args": dict}.
    Returns a TTS-safe response string.
    """
    import system.os_controller as osc
    op   = op_data.get("op", "")
    args = op_data.get("args", {}) or {}

    fn = getattr(osc, op, None)
    if fn is None:
        print(f"[OS] Unknown op: '{op}'")
        return f"I don't recognise that OS operation, sir."

    print(f"[OS] Executing {op}({args})")
    try:
        result = await asyncio.to_thread(fn, **args)
    except Exception as e:
        print(f"[OS] {op} raised exception: {e}")
        return f"That did not go as planned, sir. {e}"

    print(f"[OS] {op} → success={result['success']} result={result['result'][:80]}")
    if result["success"]:
        r = result["result"]
        # For long results (directory listings etc.), summarise for TTS
        if len(r) > 200:
            lines = r.strip().splitlines()
            preview = f"{lines[0]} — {len(lines)} item(s)." if lines else r[:100]
            return f"Done, sir. {preview}"
        return f"Done, sir. {r}"
    else:
        return f"That did not go as planned, sir. {result['error']}"


async def _handle_os_action(action: str, text: str, session_id: str):
    """
    Interpret natural-language OS instruction, check for confirmation requirement,
    and either execute immediately or stage for confirmation.
    Returns (staged: bool, response_text: str).
    Sets _pending[session_id] if destructive.
    """
    from system.os_interpreter import interpret as os_interpret

    print(f"[OS] Interpreting [{action}]: {text[:80]}")
    try:
        op_data = await os_interpret(text)
    except Exception as e:
        print(f"[OS] Interpreter failed: {e}")
        return None, f"I could not parse that OS command, sir. {e}"

    op = op_data.get("op", "")
    print(f"[OS] Resolved op: {op}  args: {op_data.get('args', {})}")

    # Destructive? Stage for confirmation.
    if op in _OS_DESTRUCTIVE:
        _pending[session_id] = {"action": "os_op", "payload": json.dumps(op_data)}
        return True, _confirmation_question("os_op", json.dumps(op_data))

    # Non-destructive: execute immediately
    response = await _run_os_op(op_data)
    return False, response


async def _handle_browser_action(text: str) -> str:
    from system.browser_agent import browser
    import re

    lower = text.lower()

    # Headed mode request
    if "show browser" in lower or "headed" in lower:
        await browser.set_headed(True)
        return "Browser is now in headed mode, sir."

    # URL navigation
    url_match = re.search(r'https?://\S+', text)
    if url_match:
        url = url_match.group()
        result = await browser.open_url(url)
        return f"Done, sir. {result['result']}" if result["success"] else f"That did not go as planned, sir. {result['error']}"

    # Screenshot
    if "screenshot" in lower:
        result = await browser.screenshot()
        return f"Done, sir. {result['result']}" if result["success"] else f"That did not go as planned, sir. {result['error']}"

    # Web search
    query_match = re.search(
        r'(?:search(?:\s+the\s+web)?(?:\s+for)?|google)\s+(.+)', text, re.IGNORECASE
    )
    if query_match:
        query  = query_match.group(1).strip()
        result = await browser.search_web(query)
        if result["success"]:
            lines  = result["result"].split("\n")
            titles = [l for l in lines if l and not l.startswith("   ")][:3]
            return f"Top results for '{query}':\n{chr(10).join(titles)}"
        return f"Search failed, sir. {result['error']}"

    return "I couldn't determine the browser action, sir. Could you be more specific?"


def _extract_type_text(prompt: str) -> str | None:
    """Extract the text to type from a 'type ...' voice command."""
    import re
    # "type the text hello world" / "type 'hello world'" / "type hello world"
    m = re.search(
        r'\btype\s+(?:the\s+)?(?:text\s+|phrase\s+|word\s+|command\s+)?["\']?(.+?)["\']?\s*$',
        prompt, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_shortcut(prompt: str) -> str | None:
    """
    Extract a keyboard shortcut from natural language.
    "press ctrl s"          → "ctrl+s"
    "press ctrl+alt+t"      → "ctrl+alt+t"
    "press f5"              → "f5"
    "press enter"           → "enter"
    "keyboard shortcut ctrl shift p" → "ctrl+shift+p"
    """
    import re
    lo = prompt.lower().strip()

    # Try explicit shortcut after press/hit/hotkey/keyboard shortcut
    m = re.search(
        r'\b(?:press|hit|hotkey|keyboard\s+shortcut)\s+(?:the\s+)?(?:keys?\s+)?(.+)',
        lo, re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip(".,!?")
        # Normalise spaces between tokens to "+"
        # "ctrl s" → "ctrl+s",  "ctrl alt t" → "ctrl+alt+t"
        parts = re.split(r'[+\s]+', raw)
        parts = [p for p in parts if p]
        return "+".join(parts)
    return None


def _extract_youtube_action(prompt: str) -> str:
    """Extract YouTube action keyword from the prompt."""
    import re
    lo = prompt.lower()
    for keyword in ("pause", "play", "mute", "unmute", "fullscreen", "full screen",
                    "next", "previous", "forward", "rewind", "volume up", "volume down",
                    "captions", "subtitles"):
        if keyword in lo:
            return keyword
    return "pause"  # safe default


async def _spawn_agent(agent_name: str, task: str) -> str:
    try:
        agent_id = await agent_dispatcher.spawn(agent_name, task)
        labels = {
            "research": "Research agent",
            "code":     "Code agent",
            "organize": "File operations agent",
            "file":     "File operations agent",
            "autogui":  "Desktop automation agent",
            "vision":   "Vision agent",
            "dev":      "Developer agent",
        }
        label = labels.get(agent_name, f"{agent_name.capitalize()} agent")
        return f"{label} dispatched, sir. Task: {task}. I'll report back when it's complete."
    except ValueError as e:
        return f"That did not go as planned, sir. {e}"


# ── Chat ──────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id  = req.session_id or str(uuid.uuid4())
    memory.init_session(session_id)
    lower_prompt = req.prompt.strip().lower()

    # Notify proactive engine: user is active (resets idle timer, cancels pending TTS)
    try:
        from core.proactive_engine import engine as _pe
        _pe.note_interaction()
    except Exception:
        pass

    # ── 1. Pending confirmation check ─────────────────────────────────────────
    if not req.force_tier and session_id in _pending:
        pending = _pending[session_id]

        if lower_prompt in _CONFIRM_WORDS:
            del _pending[session_id]
            response_text = await _execute_pending(pending["action"], pending["payload"])
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if lower_prompt in _CANCEL_WORDS:
            del _pending[session_id]
            response_text = "Understood, sir. Command cancelled."
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        del _pending[session_id]

    # ── 2. System-control intent detection ────────────────────────────────────
    if not req.force_tier:
        action, payload = await parse_intent(req.prompt)

        # ── App open / close ──────────────────────────────────────────────────
        if action in ("open", "close") and payload:
            response_text = (
                launch_app(payload) if action == "open" else close_app(payload)
            )
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Terminal / package — ask confirmation ─────────────────────────────
        if action in _TERMINAL_ACTIONS:
            _pending[session_id] = {"action": action, "payload": payload}
            response_text = _confirmation_question(action, payload)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── OS control (file / process / network / system_cfg) ────────────────
        if action in ("file", "process", "network", "system_cfg"):
            staged, response_text = await _handle_os_action(action, req.prompt, session_id)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Browser control ───────────────────────────────────────────────────
        if action == "browser":
            response_text = await _handle_browser_action(req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Agent spawning ────────────────────────────────────────────────────
        if action == "research":
            response_text = await _spawn_agent("research", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if action == "code":
            response_text = await _spawn_agent("code", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if action == "organize":
            response_text = await _spawn_agent("file", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if action == "autogui":
            response_text = await _spawn_agent("autogui", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if action == "vision":
            response_text = await _spawn_agent("vision", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        if action == "dev":
            response_text = await _spawn_agent("dev", payload or req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Mission board ─────────────────────────────────────────────────────
        if action == "mission":
            response_text = await _handle_mission_voice(req.prompt, session_id)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Diagnostics ───────────────────────────────────────────────────────
        if action == "diagnostic":
            response_text = await _handle_diagnostic_voice()
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Time / date ───────────────────────────────────────────────────────
        if action == "time_date":
            result = get_time_date()
            response_text = result["result"]
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Desktop screenshot ────────────────────────────────────────────────
        if action == "screenshot":
            result = await asyncio.to_thread(take_screenshot)
            if result["success"]:
                response_text = f"Done, sir. {result['result']}"
            else:
                response_text = f"Screenshot failed, sir. {result.get('error', 'Unknown error')}"
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Type text ─────────────────────────────────────────────────────────
        if action == "type_text":
            text_to_type = _extract_type_text(req.prompt)
            if text_to_type:
                result = await asyncio.to_thread(type_text, text_to_type)
                if result["success"]:
                    response_text = f"Done, sir. {result['result']}"
                else:
                    response_text = f"That did not work, sir. {result.get('error', 'xdotool unavailable')}"
            else:
                response_text = "What would you like me to type, sir?"
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── Press shortcut / key ──────────────────────────────────────────────
        if action == "press_key":
            shortcut = _extract_shortcut(req.prompt)
            if shortcut:
                result = await asyncio.to_thread(press_shortcut, shortcut)
                if result["success"]:
                    response_text = f"Done, sir. {result['result']}"
                else:
                    response_text = f"That did not work, sir. {result.get('error', 'xdotool unavailable')}"
            else:
                response_text = "Which key or shortcut should I press, sir?"
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── YouTube control ───────────────────────────────────────────────────
        if action == "youtube":
            yt_action = _extract_youtube_action(req.prompt)
            result    = await asyncio.to_thread(youtube_control, yt_action)
            if result["success"]:
                response_text = f"Done, sir. {result['result']}"
            else:
                response_text = f"That did not work, sir. {result.get('error', 'xdotool unavailable')}"
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            if session_id != "voice-pipeline":
                await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── MCP: Brave web search ──────────────────────────────────────────────
        if action == "mcp_brave":
            voice_text, display_text = await _handle_mcp_brave(req.prompt)
            memory.record(session_id, "user",      req.prompt,   tier="voice")
            memory.record(session_id, "assistant", display_text, tier="voice")
            await request_speak(voice_text)
            return _quick_response(display_text, session_id)

        # ── MCP: GitHub query ─────────────────────────────────────────────────
        if action == "mcp_github":
            response_text = await _handle_mcp_github(req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            await request_speak(response_text)
            return _quick_response(response_text, session_id)

        # ── MCP: Web fetch ────────────────────────────────────────────────────
        if action == "mcp_fetch":
            response_text = await _handle_mcp_fetch(req.prompt)
            memory.record(session_id, "user",      req.prompt,    tier="voice")
            memory.record(session_id, "assistant", response_text, tier="voice")
            await request_speak(response_text)
            return _quick_response(response_text, session_id)

    # ── 3. Normal LLM chat flow ───────────────────────────────────────────────
    if req.force_tier:
        try:
            tier     = TaskTier(req.force_tier)
            decision = RoutingDecision(tier=tier, reason="forced", confidence=1.0)
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

    # Log interaction for adaptive learning (fire-and-forget, never blocks)
    asyncio.create_task(_log_interaction_bg(
        session_id, req.prompt, response_text,
        getattr(decision, "tier", None) and decision.tier.value, None,
    ))

    # Detect implicit feedback on PREVIOUS exchange
    asyncio.create_task(_check_feedback_bg(session_id, req.prompt))

    if session_id != "voice-pipeline":
        await request_speak(response_text)

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        tier=decision.tier.value,
        tier_reason=decision.reason,
        confidence=decision.confidence,
    )


# ── Utility ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "online"}


@app.get("/status")
async def status():
    return {
        "status":  "online",
        "version": "3.3.0",
        "models": {
            "primary": "llama-3.3-70b-versatile (Groq)",
            "local":   "llama3.2:3b (Ollama)",
        },
        "tools":  len(sandbox.list_tools()),
        "agents": len(agent_dispatcher.get_all()),
        "voice":  "faster-whisper + kokoro-82m (British)",
    }


@app.get("/memory/{session_id}")
async def get_memory(session_id: str):
    return {"session_id": session_id, "short_term": memory.get_context(session_id)}


@app.post("/consolidate")
async def consolidate(req: ConsolidateRequest):
    memory.consolidate(req.session_id, req.summary, req.keywords)
    return {"status": "consolidated"}


@app.get("/apps")
async def get_apps():
    return {"open": list_open_apps()}


@app.get("/tools")
async def list_tools():
    return {"tools": sandbox.list_tools()}


@app.post("/tool/{tool_name}")
async def run_tool(tool_name: str, args: dict):
    result = await sandbox.run(tool_name, args, auto_confirm=False)
    return {"success": result.success, "output": result.output, "error": result.error}


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 1 — MISSION BOARD
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_mission_voice(text: str, session_id: str) -> str:
    """Handle mission-related voice commands, return a TTS-safe string."""
    import re
    from core.mission_board import (
        add_mission, get_today, end_of_day_summary, get_stats,
        complete_mission, defer_mission, update_status,
    )
    lower = text.lower()

    # End of day
    if re.search(r'\bend\s+of\s+day\b', lower) or re.search(r'\bdaily\s+briefing\b', lower):
        result = await asyncio.to_thread(end_of_day_summary)
        return result["briefing"]

    # Show missions
    if re.search(r'\b(what|show)\s+(are\s+)?(my\s+)?(missions|tasks)\b', lower) or \
       re.search(r'\b(task|mission)\s+list\b', lower) or \
       re.search(r'\btoday.s\s+(tasks|missions)\b', lower) or \
       re.search(r'\bmy\s+tasks\b', lower):
        missions = await asyncio.to_thread(get_today)
        if not missions:
            return "No missions logged for today, sir."
        pending   = [m for m in missions if m["status"] == "pending"]
        complete  = [m for m in missions if m["status"] == "complete"]
        in_prog   = [m for m in missions if m["status"] == "in_progress"]
        parts     = [f"You have {len(missions)} missions today, sir."]
        if in_prog:
            parts.append(f"{len(in_prog)} in progress: {in_prog[0]['title']}.")
        if pending:
            titles = ", ".join(m["title"] for m in pending[:3])
            parts.append(f"{len(pending)} pending: {titles}.")
        if complete:
            parts.append(f"{len(complete)} completed.")
        return " ".join(parts)

    # Mission status / stats
    if re.search(r'\bmission\s+status\b', lower):
        stats = await asyncio.to_thread(get_stats)
        rate  = stats["completion_rate"]
        return (
            f"Today: {stats['today_completed']} of {stats['today_total']} missions complete, "
            f"{rate}% completion rate. Streak: {stats['streak_days']} day{'s' if stats['streak_days'] != 1 else ''}, sir."
        )

    # Mark mission complete — "mark X complete / done / finished"
    mark_m = re.search(r'\bmark\s+(.+?)\s+(?:complete|done|finished)\b', text, re.IGNORECASE)
    if mark_m:
        fragment = mark_m.group(1).strip().lower()
        missions = await asyncio.to_thread(get_today)
        active   = [m for m in missions if m["status"] not in ("complete", "deferred")]
        matched  = next(
            (m for m in active
             if fragment in m["title"].lower() or m["title"].lower() in fragment),
            None,
        )
        if matched:
            await asyncio.to_thread(complete_mission, matched["id"])
            return f"Mission complete, sir. '{matched['title']}' marked as done."
        return f"No active mission matching '{fragment}' found, sir."

    # Add / create / new mission — handles all formats:
    #   "add mission: title, priority high"
    #   "add mission title"
    #   "create mission title"
    #   "new mission title"
    add_m = re.search(
        r'\b(?:add|create|new)\s+(?:a\s+)?(?:mission|task)\s*:?\s*(.+)',
        text, re.IGNORECASE,
    )
    if add_m:
        rest = add_m.group(1).strip()
        # Extract priority keyword
        prio_match = re.search(
            r',?\s*priority\s+(critical|high|medium|low)\b', rest, re.IGNORECASE
        )
        priority = prio_match.group(1).lower() if prio_match else (
            "critical" if "critical" in lower else "medium"
        )
        if prio_match:
            rest = rest[:prio_match.start()].strip().rstrip(',').strip()
        title = rest.strip().strip('"\'')
        if title:
            await asyncio.to_thread(add_mission, title, "", priority)
            return f"Mission logged, sir. '{title}' added at {priority} priority."

    # Defer task
    if re.search(r'\bdefer\s+(task|mission)\b', lower):
        missions = await asyncio.to_thread(get_today)
        pending  = [m for m in missions if m["status"] == "pending"]
        if not pending:
            return "No pending missions to defer, sir."
        await asyncio.to_thread(defer_mission, pending[0]["id"])
        return f"Deferred '{pending[0]['title']}' to tomorrow, sir."

    return "Mission board is ready, sir. What would you like to do?"


@app.get("/missions")
async def missions_today():
    from core.mission_board import get_today
    return await asyncio.to_thread(get_today)


@app.get("/missions/all")
async def missions_all(date: Optional[str] = None):
    from core.mission_board import get_all
    return await asyncio.to_thread(get_all, date)


@app.get("/missions/stats")
async def missions_stats():
    from core.mission_board import get_stats
    return await asyncio.to_thread(get_stats)


@app.post("/missions/eod")
async def missions_eod():
    from core.mission_board import end_of_day_summary
    result = await asyncio.to_thread(end_of_day_summary)
    # Speak the briefing
    await request_speak(result["briefing"])
    return result


@app.post("/missions")
async def missions_create(req: MissionCreate):
    from core.mission_board import add_mission
    mission = await asyncio.to_thread(
        add_mission, req.title, req.description or "", req.priority or "medium"
    )
    return mission


@app.patch("/missions/{mission_id}")
async def missions_update(mission_id: str, req: MissionPatch):
    from core.mission_board import update_status, get_mission
    if req.status is None:
        raise HTTPException(400, "status is required")
    mission = await asyncio.to_thread(update_status, mission_id, req.status, req.notes or "")
    if not mission:
        raise HTTPException(404, "Mission not found")
    return mission


@app.delete("/missions/{mission_id}")
async def missions_delete(mission_id: str):
    from core.mission_board import delete_mission
    ok = await asyncio.to_thread(delete_mission, mission_id)
    if not ok:
        raise HTTPException(404, "Mission not found")
    return {"deleted": mission_id}


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 2 — ADAPTIVE LEARNING
# ══════════════════════════════════════════════════════════════════════════════

async def _log_interaction_bg(
    session_id: str, user_input: str, response: str,
    intent: Optional[str], agent: Optional[str],
) -> None:
    """Background task — log interaction, never raises."""
    try:
        from core.adaptive_memory import log_interaction
        await asyncio.to_thread(
            log_interaction, session_id, user_input, response, intent, agent, None
        )
    except Exception:
        pass


async def _check_feedback_bg(session_id: str, current_input: str) -> None:
    """Background task — check if current input is feedback on previous response."""
    try:
        from core.adaptive_memory import (
            detect_feedback, get_last_interaction_id, update_feedback,
            get_last_interaction, log_correction,
        )
        feedback = detect_feedback(current_input)
        if not feedback:
            return
        last_id = await asyncio.to_thread(get_last_interaction_id, session_id)
        if last_id:
            await asyncio.to_thread(update_feedback, last_id, feedback)
            # If failed, log as a correction candidate for lesson extraction
            if feedback == "response_failed":
                last = await asyncio.to_thread(get_last_interaction, session_id)
                if last:
                    from core.adaptive_memory import generate_lesson
                    cid = await asyncio.to_thread(
                        log_correction,
                        last["user_input"],
                        last["jarvis_response"],
                        current_input,
                    )
                    asyncio.create_task(generate_lesson(
                        last["user_input"], last["jarvis_response"],
                        current_input, cid,
                    ))
    except Exception:
        pass


@app.get("/adaptive/profile")
async def adaptive_profile():
    from core.adaptive_memory import load_profile
    return await asyncio.to_thread(load_profile)


@app.get("/adaptive/lessons")
async def adaptive_lessons():
    from core.adaptive_memory import get_recent_lessons
    lessons = await asyncio.to_thread(get_recent_lessons, 10)
    return {"lessons": lessons}


@app.get("/adaptive/stats")
async def adaptive_stats():
    from core.adaptive_memory import get_stats
    return await asyncio.to_thread(get_stats)


@app.post("/adaptive/feedback")
async def adaptive_feedback(req: FeedbackRequest):
    from core.adaptive_memory import get_last_interaction_id, update_feedback
    last_id = await asyncio.to_thread(get_last_interaction_id, req.session_id)
    if not last_id:
        raise HTTPException(404, "No interactions found for session")
    await asyncio.to_thread(update_feedback, last_id, req.feedback)
    return {"updated": last_id, "feedback": req.feedback}


# ── Proactive engine endpoints ─────────────────────────────────────────────────

class _DismissRequest(BaseModel):
    alert_id: str


@app.post("/proactive/dismiss")
async def proactive_dismiss(req: _DismissRequest):
    from core.proactive_engine import engine as _pe
    _pe.dismiss_alert(req.alert_id)
    _pe.note_interaction()   # also resets idle timer
    return {"dismissed": req.alert_id}


@app.get("/proactive/pending")
async def proactive_pending():
    from core.proactive_engine import engine as _pe
    return {"pending": list(_pe._pending_alerts.values())}


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 3 — DIAGNOSTIC
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_diagnostic_voice() -> str:
    """Return a TTS-safe one-paragraph diagnostic summary."""
    try:
        import psutil
        cpu   = psutil.cpu_percent(interval=0.3)
        ram   = psutil.virtual_memory().percent
        parts = [
            "All systems nominal, sir.",
            "Backend online. Voice pipeline active.",
        ]
        running_agents = sum(
            1 for a in agent_dispatcher.get_all()
            if a.get("status") == "running"
        )
        total_agents = 6
        parts.append(
            f"{total_agents - running_agents} of {total_agents} agents on standby."
        )
        parts.append(f"CPU at {round(cpu)}%, memory at {round(ram)}%.")
        return " ".join(parts)
    except Exception:
        return "Diagnostic systems available, sir. Run the full report for details."


# ══════════════════════════════════════════════════════════════════════════════
# MCP HANDLER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def _handle_mcp_brave(prompt: str) -> tuple[str, str]:
    """
    Route a voice search prompt to DuckDuckGo.
    Returns (voice_text, display_text):
      - voice_text  — headline + source only, suitable for TTS
      - display_text — full results with snippets for the HUD chat
    """
    try:
        from mcp.mcp_hub import ddg_raw
        import re

        # Strip common preamble to get the actual query
        query = re.sub(
            r"^(search\s+(the\s+)?(web|internet|online)\s+for|look\s+up|web\s+search\s+for|"
            r"search\s+online\s+for|find\s+(me\s+)?information\s+(on|about)|"
            r"what.s\s+(the\s+)?latest\s+(on|about)|news\s+(on|about)|"
            r"search\s+for\s+news\s+about|latest\s+news\s+(on|about)|brave\s+search\s+for)\s+",
            "", prompt, flags=re.IGNORECASE
        ).strip() or prompt

        is_news = bool(re.search(r"\b(news|latest|headlines|today)\b", prompt, re.IGNORECASE))
        results = await ddg_raw(query, count=3, news=is_news)

        if not results:
            msg = f"I couldn't find anything on {query}, sir."
            return msg, msg

        intro = f"Here's what I found on {query}:"

        # Voice: intro + "Headline, from Source." for each result — no snippets
        voice_parts = [intro]
        for r in results:
            title  = r["title"].strip()
            source = r["source"] or "the web"
            voice_parts.append(f"{title}, from {source}.")
        voice_text = " ".join(voice_parts)

        # Display: numbered bullets with headline / source / one-sentence snippet
        display_lines = [intro + "\n"]
        for i, r in enumerate(results, 1):
            title   = r["title"].strip()
            source  = r["source"] or "unknown source"
            snippet = r["snippet"].strip()

            if snippet:
                sentence_end = snippet.find(". ")
                if 0 < sentence_end < 120:
                    snippet = snippet[: sentence_end + 1]
                elif len(snippet) > 120:
                    snippet = snippet[:117].rstrip() + "..."

            display_lines.append(f"{i}. {title}")
            display_lines.append(f"   Source: {source}")
            if snippet:
                display_lines.append(f"   {snippet}")
            display_lines.append("")

        display_text = "\n".join(display_lines).strip()
        return voice_text, display_text

    except Exception as e:
        msg = f"Web search unavailable: {e}"
        return msg, msg


async def _handle_mcp_github(prompt: str) -> str:
    """Route a voice prompt to GitHub via MCP."""
    try:
        from mcp.mcp_hub import github_commits, github_search_repos, github_list_issues
        import re
        p = prompt.lower()

        # Commit history for a specific repo
        m = re.search(r"commits?\s+(?:for|on|in)\s+([\w/-]+)", p)
        if m:
            parts = m.group(1).split("/")
            owner, repo = (parts[0], parts[1]) if len(parts) >= 2 else ("k", parts[0])
            result = await github_commits(owner, repo)
            return f"Recent commits on {owner}/{repo}: {result}"

        # Issues
        if re.search(r"(open\s+)?issues?", p):
            m2 = re.search(r"issues?\s+(?:for|on|in)\s+([\w/-]+)", p)
            if m2:
                parts = m2.group(1).split("/")
                owner, repo = (parts[0], parts[1]) if len(parts) >= 2 else ("k", parts[0])
                result = await github_list_issues(owner, repo)
                return f"Open issues on {owner}/{repo}: {result}"

        # Search repos
        m3 = re.search(r"(?:search|find|show)\s+(?:repos?|repositories)\s+(?:for|about)?\s+(.+)", p)
        if m3:
            result = await github_search_repos(m3.group(1).strip())
            return f"GitHub repositories: {result}"

        # Default: show my recent commits on JARVIS
        result = await github_commits("k", "JARVIS-MKIII")
        return f"Recent JARVIS-MKIII commits: {result}"
    except Exception as e:
        return f"GitHub access unavailable: {e}"


async def _handle_mcp_fetch(prompt: str) -> str:
    """Fetch a URL from a voice prompt via httpx."""
    try:
        from mcp.mcp_hub import web_fetch
        import re
        m = re.search(r"https?://\S+", prompt)
        if not m:
            return "Please provide a URL to fetch, sir."
        url = m.group(0).rstrip(".,;)")
        result = await web_fetch(url)
        return f"Page content: {result}"
    except Exception as e:
        return f"Web fetch unavailable: {e}"


@app.get("/diagnostic")
async def diagnostic():
    import psutil

    # System metrics
    cpu  = await asyncio.to_thread(psutil.cpu_percent, 0.5)
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # GPU VRAM (nvidia-smi, optional)
    gpu_vram: Optional[int] = None
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(",")
            used, total = int(parts[0]), int(parts[1])
            gpu_vram = round(used / total * 100)
    except Exception:
        pass

    # Vault status
    vault_status = "error"
    try:
        from core.vault import Vault
        v = Vault()
        vault_status = "unlocked" if v._unlocked else "locked"
    except Exception:
        pass

    # Hindsight memory
    hindsight_status = "error"
    try:
        from memory.hindsight import memory as hm
        hindsight_status = "active" if hm else "error"
    except Exception:
        pass

    # Agents
    from agents.monitor_agent import monitor as _monitor_agent
    _all_agents = agent_dispatcher.get_all()  # list[dict]
    agents_status: dict[str, str] = {}
    for name in ("research", "code", "file", "monitor", "autogui", "vision"):
        try:
            if name == "monitor":
                agents_status[name] = "running" if _monitor_agent._running else "idle"
            else:
                running = any(
                    a.get("name", "").lower() == name and a.get("status") == "running"
                    for a in _all_agents
                )
                agents_status[name] = "running" if running else "idle"
        except Exception:
            agents_status[name] = "idle"

    # Sensors (vault key presence + github live check)
    from api.weather_calendar import _github_last_ok
    sensors: dict[str, str] = {"calendar": "connected"}
    sensors["github"] = "connected" if _github_last_ok else "error"
    try:
        from core.vault import Vault
        v = Vault()
        if v._unlocked:
            for key, name in (
                ("GMAIL_CREDENTIALS",   "gmail"),
                ("DISCORD_TOKEN",       "discord"),
            ):
                try:
                    val = v._cache.get(key) or os.environ.get(key)
                    sensors[name] = "connected" if val else "error"
                except Exception:
                    sensors[name] = "error"
        else:
            sensors.setdefault("gmail",   "error")
            sensors.setdefault("discord", "error")
    except Exception:
        sensors.setdefault("gmail",   "error")
        sensors.setdefault("discord", "error")

    # Voice pipeline
    voice_status = "online"
    try:
        from api.voice_bridge import voice_router as _vr  # noqa: F401
    except Exception:
        voice_status = "error"

    uptime = int(_time.time() - _START_TIME)

    return {
        "backend":          "online",
        "voice_pipeline":   voice_status,
        "vault":            vault_status,
        "hindsight_memory": hindsight_status,
        "agents":           agents_status,
        "models": {
            "primary":        "llama-3.3-70b-versatile (Groq)",
            "local_fallback": "llama3.2:3b (Ollama)",
        },
        "sensors": sensors,
        "system": {
            "cpu":      round(cpu),
            "ram":      round(ram.percent),
            "disk":     round(disk.percent),
            "gpu_vram": gpu_vram,
        },
        "uptime":  uptime,
        "version": "3.3.0",
    }
