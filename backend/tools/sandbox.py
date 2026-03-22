"""
JARVIS-MKIII — sandbox.py
Safe tool execution layer. All agent tool calls pass through here.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable


@dataclass
class ToolResult:
    success:   bool
    output:    str
    tool_name: str
    error:     str = ""


class Sandbox:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, requires_confirmation: bool = False):
        def decorator(fn: Callable[[dict], Awaitable[ToolResult]]):
            self._tools[name] = {"fn": fn, "requires_confirmation": requires_confirmation}
            return fn
        return decorator

    async def run(self, tool_name: str, args: dict, auto_confirm: bool = False) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(False, "", tool_name, f"Unknown tool: '{tool_name}'")
        tool = self._tools[tool_name]
        if tool["requires_confirmation"] and not auto_confirm:
            confirm = input(f"[SANDBOX] Approve '{tool_name}' with args {args}? (y/N): ").strip().lower()
            if confirm != "y":
                return ToolResult(False, "", tool_name, "Denied by operator.")
        try:
            return await tool["fn"](args)
        except Exception as e:
            return ToolResult(False, "", tool_name, str(e))

    def list_tools(self) -> list[dict]:
        return [{"name": k, "requires_confirmation": v["requires_confirmation"]} for k, v in self._tools.items()]


sandbox = Sandbox()


@sandbox.register(name="shell", requires_confirmation=True)
async def tool_shell(args: dict) -> ToolResult:
    cmd = args.get("command", "").strip()
    if not cmd:
        return ToolResult(False, "", "shell", "No command provided.")
    blocked = ["rm -rf", "dd if=", "mkfs", ":(){ :|:& };:"]
    for b in blocked:
        if b in cmd:
            return ToolResult(False, "", "shell", f"Blocked: '{b}'")
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    success = proc.returncode == 0
    return ToolResult(success, stdout.decode(errors="replace"), "shell",
                      stderr.decode(errors="replace") if not success else "")


@sandbox.register(name="read_file", requires_confirmation=False)
async def tool_read_file(args: dict) -> ToolResult:
    from pathlib import Path
    path = Path(args.get("path", ""))
    if not path.exists():
        return ToolResult(False, "", "read_file", f"File not found: {path}")
    try:
        return ToolResult(True, path.read_text(errors="replace"), "read_file")
    except Exception as e:
        return ToolResult(False, "", "read_file", str(e))


@sandbox.register(name="write_file", requires_confirmation=True)
async def tool_write_file(args: dict) -> ToolResult:
    from pathlib import Path
    path    = Path(args.get("path", ""))
    content = args.get("content", "")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return ToolResult(True, f"Written to {path}", "write_file")
    except Exception as e:
        return ToolResult(False, "", "write_file", str(e))


@sandbox.register(name="web_fetch", requires_confirmation=False)
async def tool_web_fetch(args: dict) -> ToolResult:
    import httpx
    url = args.get("url", "")
    if not url.startswith("https://"):
        return ToolResult(False, "", "web_fetch", "Only HTTPS URLs permitted.")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return ToolResult(True, resp.text[:8000], "web_fetch")
    except Exception as e:
        return ToolResult(False, "", "web_fetch", str(e))
