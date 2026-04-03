"""
JARVIS-MKIII — mcp/server.py
MCP server that exposes JARVIS tools to Claude Code and other MCP clients.

Runs as a separate process via stdio transport.
Launch with: python backend/mcp/run_mcp.py
"""
from __future__ import annotations
import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)

_BASE = "http://localhost:8000"
_TIMEOUT = 30.0


async def _jarvis(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        fn = getattr(client, method)
        resp = await fn(f"{_BASE}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()


def _build_app():
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        raise ImportError(
            "mcp package not installed. Run: pip install mcp"
        )

    app = Server("jarvis-mkiii")

    @app.list_tools()
    async def list_tools():
        return [
            Tool(
                name="jarvis_chat",
                description="Send a message to JARVIS and get a response",
                inputSchema={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            ),
            Tool(
                name="jarvis_screenshot",
                description="Take a screenshot of the desktop and analyze it with vision AI",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="jarvis_memory_search",
                description="Search JARVIS semantic memory for relevant past context",
                inputSchema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            Tool(
                name="jarvis_run_terminal",
                description="Execute a terminal command via the JARVIS sandbox (sandboxed)",
                inputSchema={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            ),
            Tool(
                name="jarvis_get_phantom_scores",
                description="Get current PHANTOM ZERO self-mastery domain scores",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="jarvis_schedule_reminder",
                description="Schedule a reminder using natural language time expression",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "when":    {"type": "string"},
                    },
                    "required": ["message", "when"],
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "jarvis_chat":
                data = await _jarvis(
                    "post", "/chat",
                    json={"prompt": arguments["message"], "session_id": "mcp"},
                )
                text = data.get("response") or data.get("text") or str(data)
                return [TextContent(type="text", text=text)]

            elif name == "jarvis_screenshot":
                data = await _jarvis("post", "/vision/screenshot", json={})
                text = data.get("analysis") or data.get("result") or str(data)
                return [TextContent(type="text", text=text)]

            elif name == "jarvis_memory_search":
                data = await _jarvis(
                    "get", "/memory/search",
                    params={"q": arguments["query"], "n": 5},
                )
                return [TextContent(type="text", text=json.dumps(data, indent=2))]

            elif name == "jarvis_run_terminal":
                data = await _jarvis(
                    "post", "/tool/shell",
                    json={"command": arguments["command"]},
                )
                text = data.get("output") or data.get("result") or str(data)
                return [TextContent(type="text", text=text)]

            elif name == "jarvis_get_phantom_scores":
                data = await _jarvis("get", "/phantom/scores")
                return [TextContent(type="text", text=json.dumps(data, indent=2))]

            elif name == "jarvis_schedule_reminder":
                data = await _jarvis(
                    "post", "/scheduler/add",
                    json={"message": arguments["message"], "when": arguments["when"]},
                )
                return [TextContent(type="text", text=json.dumps(data, indent=2))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as exc:
            logger.error("[MCP] Tool call %r failed: %s", name, exc)
            return [TextContent(type="text", text=f"Error: {exc}")]

    return app


# Lazily built so imports fail loudly only at runtime
try:
    app = _build_app()
except ImportError:
    app = None  # type: ignore[assignment]
