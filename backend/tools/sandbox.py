"""
JARVIS-MKIII — sandbox.py
Safe tool execution layer. All agent tool calls pass through here.
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


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
        # Whitelist check — reject any tool not in the allowed list
        try:
            from config.settings import ALLOWED_TOOLS
            if tool_name not in ALLOWED_TOOLS:
                logger.warning("[SANDBOX] Blocked unauthorized tool: %s", tool_name)
                return ToolResult(False, "", tool_name,
                                  f"Tool '{tool_name}' is not in the allowed list.")
        except ImportError:
            pass  # settings not available in test context — allow

        if tool_name not in self._tools:
            return ToolResult(False, "", tool_name, f"Unknown tool: '{tool_name}'")
        tool = self._tools[tool_name]
        logger.info("[SANDBOX] Executing tool: %s | args: %s", tool_name, args)
        if tool["requires_confirmation"] and not auto_confirm:
            confirm = input(f"[SANDBOX] Approve '{tool_name}' with args {args}? (y/N): ").strip().lower()
            if confirm != "y":
                return ToolResult(False, "", tool_name, "Denied by operator.")
        import time as _time
        t0 = _time.monotonic()
        try:
            result = await tool["fn"](args)
        except Exception as e:
            result = ToolResult(False, "", tool_name, str(e))
        duration_ms = int((_time.monotonic() - t0) * 1000)
        try:
            from memory.hindsight import memory
            memory.log_tool_call(tool_name, args, result, duration_ms)
        except Exception:
            pass
        return result

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


@sandbox.register(name="summarize", requires_confirmation=False)
async def tool_summarize(args: dict) -> ToolResult:
    """Summarize a block of text via Groq. Accepts 'text' or 'input' key."""
    text = args.get("text") or args.get("input", "")
    if not text:
        return ToolResult(False, "", "summarize", "No text provided.")
    try:
        from core.dispatcher import _call_groq
        prompt = f"Summarize the following in 3 concise bullet points:\n\n{text[:6000]}"
        summary = await _call_groq([{"role": "user", "content": prompt}], "")
        return ToolResult(True, summary, "summarize")
    except Exception as e:
        return ToolResult(False, "", "summarize", str(e))


@sandbox.register(name="vision_analyze", requires_confirmation=False)
async def tool_vision_analyze(args: dict) -> ToolResult:
    """Analyze an image (path or base64) via the vision engine. Accepts 'path' or 'input'."""
    image_path = args.get("path") or args.get("input", "")
    if not image_path:
        return ToolResult(False, "", "vision_analyze", "No image path provided.")
    try:
        from vision.vision_engine import analyze_screenshot
        result = await analyze_screenshot(image_path)
        return ToolResult(True, result, "vision_analyze")
    except Exception as e:
        return ToolResult(False, "", "vision_analyze", str(e))
