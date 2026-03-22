"""
JARVIS-MKIII — mcp/mcp_bridge.py
Generic async subprocess client for any stdio MCP server.

Uses JSON-RPC 2.0 over stdin/stdout per the MCP spec.
Keeps the server process alive between calls (persistent).
"""
from __future__ import annotations
import asyncio, json, os
from typing import Any

_INIT_TIMEOUT  = 10.0   # seconds to wait for initialize response
_CALL_TIMEOUT  = 30.0   # seconds to wait for a tool result


class MCPClient:
    """
    Persistent subprocess client for an MCP stdio server.

    Usage:
        client = MCPClient(["mcp-server-filesystem", "/home/k"], env={"FOO": "bar"})
        result = await client.call_tool("read_file", {"path": "/home/k/foo.txt"})
        tools  = await client.list_tools()
        await client.close()
    """

    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        self._command  = command
        self._extra_env = env or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._req_id   = 0
        self._lock     = asyncio.Lock()   # one outstanding request at a time
        self._ready    = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def _ensure(self) -> None:
        """Start the process and handshake if not already running."""
        if self._proc and self._proc.returncode is None:
            return

        env = os.environ.copy()
        env.update(self._extra_env)

        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )

        # MCP handshake: initialize + initialized notification
        await self._send_raw({
            "jsonrpc": "2.0", "id": 0,
            "method":  "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities":    {},
                "clientInfo":      {"name": "jarvis-mkiii", "version": "3.3"},
            },
        })
        await asyncio.wait_for(self._recv_raw(), timeout=_INIT_TIMEOUT)
        await self._send_raw({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._ready = True

    async def close(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except Exception:
                pass
            self._proc = None
            self._ready = False

    # ── Internal I/O ─────────────────────────────────────────────────────────

    async def _send_raw(self, msg: dict) -> None:
        data = json.dumps(msg) + "\n"
        self._proc.stdin.write(data.encode())
        await self._proc.stdin.drain()

    async def _recv_raw(self) -> dict:
        line = await self._proc.stdout.readline()
        return json.loads(line.decode())

    # ── Public API ────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """Return the server's tool manifest."""
        async with self._lock:
            await self._ensure()
            self._req_id += 1
            await self._send_raw({
                "jsonrpc": "2.0", "id": self._req_id,
                "method":  "tools/list", "params": {},
            })
            resp = await asyncio.wait_for(self._recv_raw(), timeout=_INIT_TIMEOUT)
            return resp.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Call a named tool and return the text result as a string.
        Restarts the process automatically if it has crashed.
        """
        async with self._lock:
            await self._ensure()
            self._req_id += 1
            await self._send_raw({
                "jsonrpc": "2.0", "id": self._req_id,
                "method":  "tools/call",
                "params":  {"name": tool_name, "arguments": arguments},
            })
            try:
                resp = await asyncio.wait_for(self._recv_raw(), timeout=_CALL_TIMEOUT)
            except asyncio.TimeoutError:
                await self.close()
                raise RuntimeError(f"MCP tool {tool_name!r} timed out after {_CALL_TIMEOUT}s")

            if "error" in resp:
                err = resp["error"]
                raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")

            content = resp.get("result", {}).get("content", [])
            parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(parts)
