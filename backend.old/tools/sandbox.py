"""
JARVIS-MKIII — sandbox.py
Sandboxed tool execution layer.
All agent-initiated tool calls pass through here — no direct subprocess calls
from the model layer. Each tool is explicitly registered and permissioned.

Adding a new tool:
    @sandbox.register(name="my_tool", requires_confirmation=True)
    async def my_tool(args: dict) -> ToolResult:
        ...
"""

from __future__ import annotations
import asyncio
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Awaitable

# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    success: bool
    output: str
    tool_name: str
    error: str = ""


# ── Sandbox registry ──────────────────────────────────────────────────────────

class Sandbox:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, requires_confirmation: bool = False):
        """Decorator to register a tool with the sandbox."""
        def decorator(fn: Callable[[dict], Awaitable[ToolResult]]):
            self._tools[name] = {
                "fn": fn,
                "requires_confirmation": requires_confirmation,
            }
            return fn
        return decorator

    async def run(self, tool_name: str, args: dict, auto_confirm: bool = False) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(
                success=False, output="", tool_name=tool_name,
                error=f"Unknown tool: '{tool_name}'. Register it in sandbox.py first."
            )

        tool = self._tools[tool_name]
        if tool["requires_confirmation"] and not auto_confirm:
            print(f"\n[SANDBOX] Tool '{tool_name}' requires confirmation.")
            print(f"  Args: {args}")
            confirm = input("  Approve? (y/N): ").strip().lower()
            if confirm != "y":
                return ToolResult(
                    success=False, output="", tool_name=tool_name,
                    error="Execution denied by operator."
                )

        try:
            return await tool["fn"](args)
        except Exception as exc:
            return ToolResult(
                success=False, output="", tool_name=tool_name,
                error=f"Tool raised exception: {exc}"
            )

    def list_tools(self) -> list[dict]:
        return [
            {"name": k, "requires_confirmation": v["requires_confirmation"]}
            for k, v in self._tools.items()
        ]


# ── Global sandbox instance ───────────────────────────────────────────────────

sandbox = Sandbox()


# ── Built-in tools ────────────────────────────────────────────────────────────

@sandbox.register(name="shell", requires_confirmation=True)
async def tool_shell(args: dict) -> ToolResult:
    """
    Execute a shell command. ALWAYS requires confirmation.
    args: { "command": "ls -la /home" }
    """
    cmd = args.get("command", "").strip()
    if not cmd:
        return ToolResult(success=False, output="", tool_name="shell", error="No command provided.")

    # Allowlist check — block obviously dangerous patterns
    blocked = ["rm -rf", "dd if=", "mkfs", ":(){ :|:& };:", "> /dev/sd"]
    for b in blocked:
        if b in cmd:
            return ToolResult(
                success=False, output="", tool_name="shell",
                error=f"Command blocked by sandbox policy: contains '{b}'"
            )

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    success = proc.returncode == 0
    return ToolResult(
        success=success,
        output=stdout.decode(errors="replace"),
        tool_name="shell",
        error=stderr.decode(errors="replace") if not success else "",
    )


@sandbox.register(name="read_file", requires_confirmation=False)
async def tool_read_file(args: dict) -> ToolResult:
    """
    Read a file from disk.
    args: { "path": "/home/agent17/notes.txt" }
    """
    from pathlib import Path
    path = Path(args.get("path", ""))
    if not path.exists():
        return ToolResult(success=False, output="", tool_name="read_file",
                          error=f"File not found: {path}")
    try:
        content = path.read_text(errors="replace")
        return ToolResult(success=True, output=content, tool_name="read_file")
    except Exception as e:
        return ToolResult(success=False, output="", tool_name="read_file", error=str(e))


@sandbox.register(name="write_file", requires_confirmation=True)
async def tool_write_file(args: dict) -> ToolResult:
    """
    Write content to a file.
    args: { "path": "/home/agent17/output.txt", "content": "..." }
    """
    from pathlib import Path
    path = Path(args.get("path", ""))
    content = args.get("content", "")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return ToolResult(success=True, output=f"Written to {path}", tool_name="write_file")
    except Exception as e:
        return ToolResult(success=False, output="", tool_name="write_file", error=str(e))


@sandbox.register(name="web_fetch", requires_confirmation=False)
async def tool_web_fetch(args: dict) -> ToolResult:
    """
    Fetch the text content of a URL.
    args: { "url": "https://example.com" }
    """
    import httpx
    url = args.get("url", "")
    if not url.startswith("https://"):
        return ToolResult(success=False, output="", tool_name="web_fetch",
                          error="Only HTTPS URLs are permitted.")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return ToolResult(success=True, output=resp.text[:8000], tool_name="web_fetch")
    except Exception as e:
        return ToolResult(success=False, output="", tool_name="web_fetch", error=str(e))
