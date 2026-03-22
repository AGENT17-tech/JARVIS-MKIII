"""
JARVIS-MKIII — Test Suite
Run with: pytest tests/ -v
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
    d = classify("Plan and architect a multi-step agent system")
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
    assert any("JARVIS" in r.summary for r in results)


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
    assert "Unknown tool" in result.error


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
