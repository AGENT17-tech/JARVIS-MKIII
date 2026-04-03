"""
JARVIS-MKIII — Test Suite
Run with: pytest backend/tests/ -v  (from repo root, with PYTHONPATH=backend)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# ── Router tests ──────────────────────────────────────────────────────────────

from core.router import classify, TaskTier


def test_router_defaults_to_voice():
    d = classify("What time is it?")
    assert d.tier == TaskTier.VOICE


def test_router_routes_sensitive_to_local():
    d = classify("Store this in the vault and encrypt it")
    assert d.tier == TaskTier.LOCAL


def test_router_routes_reasoning():
    # Short prompt with reasoning keyword but no COMPLEX keywords or word-count threshold
    d = classify("Why does this code fail?")
    assert d.tier == TaskTier.REASONING


def test_router_single_reasoning_keyword():
    d = classify("Can you debug this code?")
    assert d.tier == TaskTier.REASONING


def test_router_local_overrides_reasoning():
    d = classify("Encrypt this sensitive agent plan in the vault")
    assert d.tier == TaskTier.LOCAL


def test_router_confidence_range():
    for prompt in ["hello", "plan a system", "encrypt vault secret"]:
        d = classify(prompt)
        assert 0.0 <= d.confidence <= 1.0


# ── Memory tests ──────────────────────────────────────────────────────────────

from memory.hindsight import HindsightMemory


def test_short_term_records_and_retrieves():
    mem = HindsightMemory()
    mem.init_session("test-session")
    mem.record("test-session", "user", "Hello JARVIS")
    mem.record("test-session", "assistant", "Hello, Agent 17.")
    ctx = mem.get_context("test-session")
    assert len(ctx) == 2
    assert ctx[0]["role"] == "user"
    assert ctx[1]["role"] == "assistant"


def test_short_term_limit_enforced():
    mem = HindsightMemory()
    mem.short._limit = 4
    for i in range(10):
        mem.record("s", "user", f"msg {i}")
    assert len(mem.get_context("s")) == 4


def test_long_term_store_and_retrieve():
    mem = HindsightMemory()
    mem.consolidate("sess-1", "Agent 17 is building JARVIS-MKIII", ["jarvis", "agent17", "build"])
    results = mem.long.retrieve("jarvis build")
    # retrieve() returns raw SQLite rows (tuples): (id, summary, keywords, source_session, timestamp)
    assert any("JARVIS" in r[1] for r in results)


def test_recall_returns_empty_when_no_match():
    mem = HindsightMemory()
    result = mem.recall("zzxyzzyabcdef")
    assert result == ""


def test_recall_returns_context_string():
    mem = HindsightMemory()
    mem.consolidate("sess-2", "Vault uses AES-256-GCM encryption", ["vault", "aes", "encryption"])
    result = mem.recall("vault encryption")
    assert "AES-256" in result or "vault" in result.lower()


# ── Sandbox tests ─────────────────────────────────────────────────────────────

from tools.sandbox import Sandbox, ToolResult


@pytest.mark.asyncio
async def test_sandbox_unknown_tool():
    s = Sandbox()
    result = await s.run("nonexistent_tool", {}, auto_confirm=True)
    assert not result.success
    # Either blocked by whitelist or rejected as unknown — both are valid refusals
    assert result.error, "Should have a non-empty error message"


@pytest.mark.asyncio
async def test_sandbox_read_file_missing():
    from tools.sandbox import sandbox
    result = await sandbox.run("read_file", {"path": "/nonexistent/path.txt"}, auto_confirm=True)
    assert not result.success


@pytest.mark.asyncio
async def test_sandbox_shell_blocked_command():
    from tools.sandbox import sandbox
    result = await sandbox.run("shell", {"command": "rm -rf /"}, auto_confirm=True)
    assert not result.success
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_sandbox_web_fetch_rejects_http():
    from tools.sandbox import sandbox
    result = await sandbox.run("web_fetch", {"url": "http://example.com"}, auto_confirm=True)
    assert not result.success
    assert "HTTPS" in result.error


def test_sandbox_tool_registration():
    s = Sandbox()
    @s.register(name="test_tool", requires_confirmation=False)
    async def my_tool(args): return ToolResult(True, "ok", "test_tool")
    tools = s.list_tools()
    assert any(t["name"] == "test_tool" for t in tools)


# ── Phase 2 tests ─────────────────────────────────────────────────────────────

def test_alert_deduplication():
    """_should_fire() must suppress the same alert type within its cooldown window."""
    from agents.proactive_agent import ProactiveAgent
    import time

    agent = ProactiveAgent()
    # Override cooldown to a large value so second call is definitely suppressed
    agent.ALERT_COOLDOWN = {"test_type": 9999}

    assert agent._should_fire("test_type") is True,  "First call must fire"
    assert agent._should_fire("test_type") is False, "Second call within cooldown must be suppressed"

    # After clearing the last-alert time, it should fire again
    agent._last_alert_times.pop("test_type")
    assert agent._should_fire("test_type") is True, "After reset, must fire again"


@pytest.mark.asyncio
async def test_tool_sandbox_whitelist():
    """Sandbox must block tool names not in ALLOWED_TOOLS."""
    from tools.sandbox import Sandbox, ToolResult
    from config.settings import ALLOWED_TOOLS

    s = Sandbox()

    # Register a harmless tool under an unauthorized name
    @s.register(name="__evil_tool__", requires_confirmation=False)
    async def evil(args): return ToolResult(True, "pwned", "__evil_tool__")

    # The tool is registered but should be blocked by the whitelist
    result = await s.run("__evil_tool__", {}, auto_confirm=True)
    assert not result.success, "Unauthorized tool must be blocked"
    assert "not in the allowed list" in result.error

    # A whitelisted tool that is also registered should pass
    @s.register(name="shell", requires_confirmation=False)
    async def fake_shell(args): return ToolResult(True, "ok", "shell")

    result2 = await s.run("shell", {}, auto_confirm=True)
    assert result2.success, "Whitelisted tool must be allowed"


def test_memory_prune():
    """prune_old_memories() must delete entries with timestamps older than retention window."""
    from datetime import datetime, timedelta
    from memory.prune import prune_old_memories

    # Build a minimal mock collection
    class MockCollection:
        def __init__(self):
            self._deleted = []
            self._entries = {
                "ids": ["id_old_1", "id_old_2"],
                "metadatas": [
                    {"timestamp": (datetime.utcnow() - timedelta(days=100)).isoformat()},
                    {"timestamp": (datetime.utcnow() - timedelta(days=95)).isoformat()},
                ],
            }

        def get(self, where, include):
            # Simulate ChromaDB $lt filter: return entries older than cutoff
            cutoff_str = where["timestamp"]["$lt"]
            cutoff = datetime.fromisoformat(cutoff_str)
            ids = [
                eid for eid, meta in zip(self._entries["ids"], self._entries["metadatas"])
                if datetime.fromisoformat(meta["timestamp"]) < cutoff
            ]
            return {"ids": ids, "metadatas": []}

        def delete(self, ids):
            self._deleted.extend(ids)

    col = MockCollection()
    deleted = prune_old_memories(col, days=90)
    assert deleted == 2, f"Expected 2 deletions, got {deleted}"
    assert "id_old_1" in col._deleted
    assert "id_old_2" in col._deleted


# ── Phase 3 tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_summarizer_skip_short():
    """summarize_session() returns None when interactions < MIN_INTERACTIONS and force=False."""
    from memory.session_summarizer import summarize_session
    interactions = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
    result = await summarize_session("test-sess", interactions, force=False)
    assert result is None, "Should return None for < 10 interactions without force"


@pytest.mark.asyncio
async def test_session_summarizer_force():
    """force=True bypasses the minimum interaction count and attempts summarization."""
    from memory.session_summarizer import summarize_session, MIN_INTERACTIONS
    from unittest.mock import AsyncMock, patch

    interactions = [{"role": "user", "content": f"msg {i}"} for i in range(3)]
    assert len(interactions) < MIN_INTERACTIONS

    # Patch the Groq call so no real API call is made
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "• point 1\n• point 2\n• point 3"

    # AsyncGroq is imported locally inside summarize_session — patch at groq module level
    with patch("groq.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat = MagicMock()
        instance.chat.completions = MagicMock()
        instance.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("core.vault.Vault") as MockVault:
            MockVault.return_value.get.return_value = "fake-key"
            result = await summarize_session("test-sess", interactions, force=True)

    assert result is not None, "force=True must attempt summarization even with < 10 interactions"
    assert "point" in result


def _import_voice_orchestrator():
    """Import VoiceOrchestrator with audio/STT dependencies stubbed out."""
    import sys
    # Stub the heavy native-extension modules so the import chain succeeds in test env
    for mod in ["webrtcvad", "sounddevice", "faster_whisper"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()
    # Stub voice.stt so STTEngine is a no-op
    stt_stub = MagicMock()
    stt_stub.STTEngine = MagicMock
    sys.modules.setdefault("voice.stt", stt_stub)
    # Also stub TTS and wake word
    sys.modules.setdefault("voice.tts", MagicMock(TTSEngine=MagicMock))
    sys.modules.setdefault("voice.wake_word", MagicMock(WakeWordDetector=MagicMock))
    sys.modules.setdefault("voice.news", MagicMock())
    from voice.voice_orchestrator import VoiceOrchestrator
    return VoiceOrchestrator


def test_confidence_gate_low():
    """Low-confidence transcript triggers confirmation request instead of direct dispatch."""
    VoiceOrchestrator = _import_voice_orchestrator()

    spoke = []

    class FakeTTS:
        def speak(self, text): spoke.append(text)

    orch = VoiceOrchestrator.__new__(VoiceOrchestrator)
    orch._tts              = FakeTTS()
    orch._is_speaking      = False
    orch._busy             = False
    orch._awaiting_confirmation = None
    orch._confirm_timer    = None
    orch._hud_ws           = None
    orch._loop             = MagicMock()
    orch._loop.is_running.return_value = False

    with patch("config.settings.STT_CFG",
               MagicMock(confirmation_enabled=True, confidence_threshold=0.95,
                         max_confirmation_wait_s=8)):
        with patch("threading.Timer") as mock_timer:
            mock_timer.return_value.start = lambda: None
            orch._on_transcript("uh yeah", confidence=0.4)

    assert orch._awaiting_confirmation == "uh yeah", "Low confidence must enter confirmation state"
    assert any("Did you say" in s for s in spoke), "Must ask for confirmation via TTS"


def test_confidence_gate_high():
    """High-confidence transcript bypasses confirmation and marks busy for dispatch."""
    VoiceOrchestrator = _import_voice_orchestrator()

    class FakeTTS:
        def speak(self, text): pass

    orch = VoiceOrchestrator.__new__(VoiceOrchestrator)
    orch._tts              = FakeTTS()
    orch._is_speaking      = False
    orch._busy             = False
    orch._awaiting_confirmation = None
    orch._confirm_timer    = None
    orch._hud_ws           = None
    orch._loop             = MagicMock()
    orch._loop.is_running.return_value = False

    with patch("config.settings.STT_CFG",
               MagicMock(confirmation_enabled=True, confidence_threshold=0.75,
                         max_confirmation_wait_s=8)):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            orch._on_transcript("set a timer for 5 minutes", confidence=0.95)

    assert orch._awaiting_confirmation is None, "High confidence must not enter confirmation state"
    assert orch._busy is True, "Must mark busy immediately for dispatch"


@pytest.mark.asyncio
async def test_phantom_monthly_endpoint():
    """GET /phantom/monthly returns required schema fields."""
    from phantom.phantom_os import get_phantom
    result = get_phantom().get_monthly_summary()
    assert result["period"] == "30d"
    assert "domains" in result
    assert "overall_avg" in result
    assert "best_domain" in result
    assert "weakest_domain" in result
    assert "generated_at" in result
    for domain_key in ["engineering", "programming", "combat", "strategy", "neuro"]:
        assert domain_key in result["domains"]
        d = result["domains"][domain_key]
        assert "avg" in d
        assert d["trend"] in ("up", "down", "stable")


@pytest.mark.asyncio
async def test_complex_routing_fallback():
    """When ANTHROPIC_API_KEY is empty, COMPLEX tier falls back to Groq."""
    from core.dispatcher import _call_claude

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Groq fallback response"

    with patch("config.settings.ANTHROPIC_API_KEY", ""):
        with patch("core.dispatcher._call_groq", new_callable=AsyncMock, return_value="Groq fallback response") as mock_groq:
            result = await _call_claude([], "system prompt")
            assert mock_groq.called, "Should fall back to Groq when ANTHROPIC_API_KEY is empty"
            assert result == "Groq fallback response"


@pytest.mark.asyncio
async def test_react_loop_final_answer():
    """ReAct loop returns immediately when LLM emits 'Final Answer:' on first iteration."""
    from core.react_loop import react
    from tools.sandbox import Sandbox

    async def llm_immediate(msgs):
        return "Final Answer: The sky is blue."

    result = await react("Why is the sky blue?", tools=Sandbox(), llm_call=llm_immediate)
    assert result == "The sky is blue."


@pytest.mark.asyncio
async def test_react_loop_max_iterations():
    """ReAct loop exhausts MAX_ITERATIONS when LLM always emits an Action, never Final Answer."""
    from core.react_loop import react, MAX_ITERATIONS
    from tools.sandbox import Sandbox

    call_count = 0

    async def llm_always_acts(msgs):
        nonlocal call_count
        call_count += 1
        # Always return an action (nonexistent file) — loop can never terminate naturally
        return 'Action: read_file[{"path": "/nonexistent/loop_test.txt"}]'

    result = await react("Unsolvable?", tools=Sandbox(), llm_call=llm_always_acts)
    assert call_count == MAX_ITERATIONS, f"Expected {MAX_ITERATIONS} calls, got {call_count}"
    # last_response is always the last action string
    assert "Action:" in result or result  # loop returns last response
