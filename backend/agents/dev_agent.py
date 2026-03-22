"""
JARVIS-MKIII — agents/dev_agent.py
Autonomous developer agent powered by Groq (llama-3.3-70b-versatile).
Reads, edits, and creates files in the JARVIS-MKIII codebase via tool use.
Triggered by voice intent "dev".
"""
from __future__ import annotations
import asyncio, json, pathlib, subprocess
from agents.agent_base import AgentBase

_JARVIS_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()  # /home/k/JARVIS-MKIII
_MAX_ITER    = 25   # max agentic loop iterations
_RESULT_CAP  = 6000 # max chars returned per tool call (keeps context manageable)
_MAX_TOKENS  = 4096 # higher than the default groq_max_tokens (512) for dev tasks

# ── Tool schemas (OpenAI / Groq function-calling format) ──────────────────────
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full text content of a file in the JARVIS-MKIII codebase. "
                "Always read a file before attempting to edit it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to JARVIS-MKIII root, e.g. backend/api/main.py",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create a new file or completely overwrite an existing file. "
                "Use for new files or full rewrites only. "
                "For small targeted changes use edit_file instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Path relative to JARVIS-MKIII root"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Make a targeted string replacement inside an existing file. "
                "Replaces the FIRST occurrence of old_string with new_string. "
                "old_string must be unique within the file — include enough surrounding "
                "context (e.g. the full function signature or several lines) to ensure uniqueness."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":       {"type": "string", "description": "Path relative to JARVIS-MKIII root"},
                    "old_string": {"type": "string", "description": "Exact, unique string to replace"},
                    "new_string": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List files and subdirectories at a path in the codebase. "
                "Ignores __pycache__, .git, venv, node_modules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to JARVIS-MKIII root. Use '.' for project root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": (
                "Search for a text pattern across the codebase using grep. "
                "Returns matching lines with relative paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (basic regex supported)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search, relative to JARVIS root. Use '.' to search everywhere.",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "Optional glob to restrict files, e.g. '*.py'",
                    },
                },
                "required": ["pattern", "path"],
            },
        },
    },
]

# ── Tool execution (sync, run via asyncio.to_thread) ──────────────────────────

def _safe_path(rel: str) -> pathlib.Path:
    """Resolve a relative path inside JARVIS_ROOT; raise if it would escape."""
    target = (_JARVIS_ROOT / rel).resolve()
    if not str(target).startswith(str(_JARVIS_ROOT)):
        raise PermissionError(f"Path traversal blocked: {rel!r}")
    return target


def _exec_read_file(path: str) -> str:
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: {path!r} does not exist."
    if not p.is_file():
        return f"ERROR: {path!r} is a directory, not a file."
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR reading {path!r}: {e}"


def _exec_write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"ERROR: {e}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        rel = p.relative_to(_JARVIS_ROOT)
        return f"Written {rel} ({len(content):,} chars)."
    except Exception as e:
        return f"ERROR writing {path!r}: {e}"


def _exec_edit_file(path: str, old_string: str, new_string: str) -> str:
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: {path!r} does not exist."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR reading {path!r}: {e}"
    if old_string not in text:
        return f"ERROR: old_string not found in {path!r}. Check for whitespace or encoding differences."
    count = text.count(old_string)
    if count > 1:
        return (
            f"ERROR: old_string appears {count} times in {path!r}. "
            "Include more surrounding context to make it unique."
        )
    try:
        p.write_text(text.replace(old_string, new_string, 1), encoding="utf-8")
        rel = p.relative_to(_JARVIS_ROOT)
        return f"Edited {rel} successfully."
    except Exception as e:
        return f"ERROR writing edit to {path!r}: {e}"


def _exec_list_directory(path: str) -> str:
    _SKIP = {"__pycache__", ".git", "venv", "node_modules", ".cache", ".mypy_cache"}
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: {path!r} does not exist."
    if not p.is_dir():
        return f"ERROR: {path!r} is not a directory."
    lines = []
    for item in sorted(p.iterdir()):
        if item.name in _SKIP or item.name.startswith("."):
            continue
        try:
            rel = item.relative_to(_JARVIS_ROOT)
        except ValueError:
            rel = item
        lines.append(f"{rel}{'/' if item.is_dir() else ''}")
    return "\n".join(lines) if lines else "(empty)"


def _exec_search_codebase(pattern: str, path: str, file_glob: str | None = None) -> str:
    try:
        p = _safe_path(path)
    except PermissionError as e:
        return f"ERROR: {e}"
    glob_flag = f"--include={file_glob}" if file_glob else "--include=*.py"
    cmd = ["grep", "-rn", glob_flag, pattern, str(p)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        if not output:
            return "No matches found."
        lines = []
        for line in output.splitlines()[:150]:
            parts = line.split(":", 2)
            if len(parts) == 3:
                try:
                    rel = pathlib.Path(parts[0]).relative_to(_JARVIS_ROOT)
                    lines.append(f"{rel}:{parts[1]}:{parts[2]}")
                    continue
                except ValueError:
                    pass
            lines.append(line)
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "ERROR: search timed out after 15 s."
    except Exception as e:
        return f"ERROR: {e}"


def _dispatch_tool(name: str, inputs: dict) -> str:
    """Synchronously execute a named tool and return a string result."""
    if name == "read_file":
        return _exec_read_file(inputs["path"])
    if name == "write_file":
        return _exec_write_file(inputs["path"], inputs["content"])
    if name == "edit_file":
        return _exec_edit_file(inputs["path"], inputs["old_string"], inputs["new_string"])
    if name == "list_directory":
        return _exec_list_directory(inputs["path"])
    if name == "search_codebase":
        return _exec_search_codebase(
            inputs["pattern"], inputs["path"], inputs.get("file_glob")
        )
    return f"ERROR: Unknown tool {name!r}"


# ── Agent ─────────────────────────────────────────────────────────────────────

class DevAgent(AgentBase):
    """
    Autonomous developer agent.
    Uses Groq (llama-3.3-70b-versatile) with OpenAI-compatible tool calling
    to read, edit, and create files in the JARVIS-MKIII codebase.
    """

    def __init__(self):
        super().__init__("DEV")

    async def run_task(self, task: str) -> str:
        from groq import AsyncGroq
        from core.vault import Vault
        from config.settings import MODEL_CFG

        client = AsyncGroq(api_key=Vault().get("GROQ_API_KEY"))

        system = (
            "You are JARVIS's internal developer agent. "
            f"The JARVIS-MKIII codebase lives at {_JARVIS_ROOT}. "
            "All tool paths are relative to that root. "
            "Strategy: (1) explore with list_directory/search_codebase to understand context, "
            "(2) read relevant files before editing, "
            "(3) make precise edits with edit_file; use write_file only for new files or full rewrites, "
            "(4) when done, give a short plain-English summary of every change made."
        )

        messages: list[dict] = [
            {"role": "system",  "content": system},
            {"role": "user",    "content": task},
        ]
        files_changed: list[str] = []

        await self.push_update("Dev agent online. Analysing task...")

        for iteration in range(1, _MAX_ITER + 1):
            await self.push_update(f"Reasoning... (step {iteration}/{_MAX_ITER})")

            response = await client.chat.completions.create(
                model=MODEL_CFG.groq_model,
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=_MAX_TOKENS,
                temperature=0.3,
            )

            choice        = response.choices[0]
            msg           = choice.message
            finish_reason = choice.finish_reason

            # Surface any text the model produced before/alongside tool calls
            if msg.content:
                await self.push_update(msg.content[:400])

            # Append assistant turn (serialize tool_calls to plain dicts for history)
            assistant_entry: dict = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id":   tc.id,
                        "type": "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_entry)

            if finish_reason != "tool_calls":
                break

            # Execute each tool call and feed results back
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                await self.push_update(f"→ {tool_name}({_input_summary(tool_input)})")

                raw_result = await asyncio.to_thread(_dispatch_tool, tool_name, tool_input)

                if tool_name in ("write_file", "edit_file"):
                    p = tool_input.get("path", "")
                    if p and p not in files_changed:
                        files_changed.append(p)

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      raw_result[:_RESULT_CAP],
                })

        # Final text is the last assistant message content
        final_text = _extract_final_text(messages)
        changed_str = (
            f" Files changed: {', '.join(files_changed)}." if files_changed else ""
        )
        self.summary = f"Dev task complete, sir.{changed_str}"
        return final_text or f"Dev task complete.{changed_str}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _input_summary(inp: dict) -> str:
    """Compact one-line representation of tool inputs for HUD updates."""
    if "path" in inp:
        p = inp["path"]
        if "content" in inp:
            return f"{p!r} ({len(inp['content']):,} chars)"
        return f"{p!r}"
    if "pattern" in inp:
        return f"pattern={inp['pattern']!r} in {inp.get('path', '.')!r}"
    return str(inp)[:80]


def _extract_final_text(messages: list[dict]) -> str:
    """Walk messages in reverse to find the last non-empty assistant text."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return msg["content"]
    return ""
