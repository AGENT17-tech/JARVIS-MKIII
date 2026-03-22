"""
JARVIS-MKIII — system/os_interpreter.py
Maps natural-language OS instructions to specific os_controller operations.

Strategy (fastest-first):
  1. Regex quick-parse — handles the most common commands instantly, no LLM cost.
  2. Groq LLM fallback — only for ambiguous / complex instructions.

Returns {"op": str, "args": dict} or raises ValueError.
"""
from __future__ import annotations
import json, re


# ── Valid op names (must match os_controller exactly) ─────────────────────────
_VALID_OPS = {
    "create_file", "create_directory", "delete", "move", "copy",
    "read_file", "list_directory", "search_files",
    "list_processes", "kill_process", "get_process_info", "set_priority",
    "get_network_status", "scan_local_network", "get_active_connections",
    "monitor_bandwidth", "disconnect_interface", "connect_interface",
    "set_volume", "get_volume", "set_brightness", "get_brightness",
    "power_sleep", "power_reboot", "power_shutdown",
    "list_startup_apps", "enable_startup", "disable_startup",
}


# ── 1. Regex quick-parser ─────────────────────────────────────────────────────

def _quick_parse(text: str) -> dict | None:
    """
    Fast regex pass — returns op_data for the most common commands.
    Returns None if the command is too ambiguous for regex.
    """
    t = text.strip()
    lo = t.lower()

    # ── create directory ──────────────────────────────────────────────────────
    m = re.search(
        r'\b(?:create|make|new|mkdir)\s+(?:a\s+)?(?:folder|directory|dir)\s+'
        r'(?:called\s+|named\s+)?["\']?(\S+?)["\']?'
        r'(?:\s+(?:in|inside|at|under)\s+(.+?))?$',
        lo,
    )
    if m:
        name, loc = m.group(1), m.group(2)
        base = loc.strip().rstrip('/') if loc else '~'
        if base in ('home', 'my home', 'home directory', 'my home directory'):
            base = '~'
        path = f"{base}/{name}"
        print(f"[OS_INTERP] regex → create_directory({path})")
        return {"op": "create_directory", "args": {"path": path}}

    # ── create file ───────────────────────────────────────────────────────────
    m = re.search(
        r'\b(?:create|make|new|touch)\s+(?:a\s+)?(?:file|document)\s+'
        r'(?:called\s+|named\s+)?["\']?(\S+?)["\']?'
        r'(?:\s+(?:in|inside|at|under)\s+(.+?))?$',
        lo,
    )
    if m:
        name, loc = m.group(1), m.group(2)
        base = loc.strip().rstrip('/') if loc else '~'
        if base in ('home', 'my home', 'home directory', 'my home directory'):
            base = '~'
        path = f"{base}/{name}"
        print(f"[OS_INTERP] regex → create_file({path})")
        return {"op": "create_file", "args": {"path": path, "content": ""}}

    # ── process: list (must come before list_directory to avoid false match) ───
    if re.search(r'\b(?:list|show|what.s)\s+(?:running\s+)?processes?\b', lo) or \
       re.search(r'\bwhat\s+processes\b', lo) or \
       re.search(r'\bprocesses?\s+(?:are\s+)?running\b', lo) or \
       re.search(r'\btask\s+manager\b', lo):
        print("[OS_INTERP] regex → list_processes()")
        return {"op": "list_processes", "args": {}}

    # ── list directory ────────────────────────────────────────────────────────
    m = re.search(
        r'\b(?:list|show|ls)\s+(?:the\s+)?(?:contents?\s+of\s+|files?\s+in\s+)?'
        r'(?:the\s+)?([~/\w.\-]+)',
        lo,
    )
    if m:
        path = m.group(1)
        if path in ('home', 'my home', 'home directory'):
            path = '~'
        print(f"[OS_INTERP] regex → list_directory({path})")
        return {"op": "list_directory", "args": {"path": path}}

    # ── read file ─────────────────────────────────────────────────────────────
    m = re.search(r'\b(?:read|show|cat|open)\s+(?:the\s+)?(?:file\s+)?([~/\w.\-]+)', lo)
    if m:
        path = m.group(1)
        print(f"[OS_INTERP] regex → read_file({path})")
        return {"op": "read_file", "args": {"path": path}}

    # ── delete ────────────────────────────────────────────────────────────────
    m = re.search(r'\b(?:delete|remove|rm)\s+(?:the\s+)?(?:file\s+|folder\s+|dir\s+)?([~/\w.\-]+)', lo)
    if m:
        path = m.group(1)
        print(f"[OS_INTERP] regex → delete({path})")
        return {"op": "delete", "args": {"path": path}}

    # ── search files ──────────────────────────────────────────────────────────
    m = re.search(r'\b(?:find|search for)\s+(?:files?\s+)?(?:called\s+|named\s+)?["\']?(\S+?)["\']?'
                  r'(?:\s+in\s+(.+?))?$', lo)
    if m:
        query, root = m.group(1), m.group(2) or '~'
        print(f"[OS_INTERP] regex → search_files({query}, {root})")
        return {"op": "search_files", "args": {"query": query, "root": root}}

    # ── process: kill ─────────────────────────────────────────────────────────
    m = re.search(r'\b(?:kill|terminate|stop)\s+(?:process\s+|pid\s+)?["\']?(\S+?)["\']?\s*(?:process)?$', lo)
    if m:
        target = m.group(1)
        print(f"[OS_INTERP] regex → kill_process({target})")
        return {"op": "kill_process", "args": {"name_or_pid": target}}

    # ── network status ────────────────────────────────────────────────────────
    if re.search(r'\bnetwork\s+(?:status|info|interfaces?|ips?)\b', lo) or \
       re.search(r'\bmy\s+ip\b', lo) or re.search(r'\bip\s+address\b', lo):
        print("[OS_INTERP] regex → get_network_status()")
        return {"op": "get_network_status", "args": {}}

    if re.search(r'\bactive\s+connections?\b', lo) or re.search(r'\bopen\s+connections?\b', lo):
        return {"op": "get_active_connections", "args": {}}

    if re.search(r'\bscan\s+(?:the\s+)?(?:network|subnet|local)\b', lo):
        return {"op": "scan_local_network", "args": {}}

    if re.search(r'\bbandwidth\b', lo) or re.search(r'\bnetwork\s+speed\b', lo):
        return {"op": "monitor_bandwidth", "args": {}}

    # ── volume ────────────────────────────────────────────────────────────────
    m = re.search(r'\b(?:set\s+)?volume\s+(?:to\s+)?(\d+)', lo)
    if m:
        print(f"[OS_INTERP] regex → set_volume({m.group(1)})")
        return {"op": "set_volume", "args": {"percent": int(m.group(1))}}

    if re.search(r'\b(?:what.s|what\s+is|get|check)\s+(?:the\s+)?volume\b', lo):
        return {"op": "get_volume", "args": {}}

    # volume up/down by step
    m = re.search(r'\bturn\s+(?:the\s+)?(?:volume|sound)\s+(up|down)\b', lo)
    if m:
        # Default bump ±15
        pct = 15 if m.group(1) == 'up' else -15
        print(f"[OS_INTERP] regex → set_volume(relative {pct:+d}) → fallback to LLM for actual value")
        # Fall through to LLM for this one — needs current level

    # ── brightness ────────────────────────────────────────────────────────────
    m = re.search(r'\b(?:set\s+)?brightness\s+(?:to\s+)?(\d+)', lo)
    if m:
        print(f"[OS_INTERP] regex → set_brightness({m.group(1)})")
        return {"op": "set_brightness", "args": {"percent": int(m.group(1))}}

    if re.search(r'\b(?:what.s|what\s+is|get|check)\s+(?:the\s+)?brightness\b', lo):
        return {"op": "get_brightness", "args": {}}

    # ── power ─────────────────────────────────────────────────────────────────
    if re.search(r'\b(?:shut\s+down|shutdown|power\s+off|power\s+down)\b', lo):
        print("[OS_INTERP] regex → power_shutdown()")
        return {"op": "power_shutdown", "args": {}}

    if re.search(r'\breboot\b|\brestart\s+(?:the\s+)?(?:computer|system|pc|machine)\b', lo):
        print("[OS_INTERP] regex → power_reboot()")
        return {"op": "power_reboot", "args": {}}

    if re.search(r'\bsleep\s+mode\b|\bsuspend\b', lo):
        print("[OS_INTERP] regex → power_sleep()")
        return {"op": "power_sleep", "args": {}}

    # ── startup apps ─────────────────────────────────────────────────────────
    if re.search(r'\bstartup\s+apps?\b|\bauto.?start\b', lo):
        return {"op": "list_startup_apps", "args": {}}

    return None   # no regex match — fall through to LLM


# ── 2. LLM fallback ───────────────────────────────────────────────────────────

_OPS_DOC = """
FILE: create_file(path,content=""), create_directory(path), delete(path),
      move(src,dest), copy(src,dest), read_file(path), list_directory(path),
      search_files(query, root="~")
PROCESS: list_processes(), kill_process(name_or_pid), get_process_info(name),
         set_priority(pid,nice_value)
NETWORK: get_network_status(), scan_local_network(), get_active_connections(),
         monitor_bandwidth(), disconnect_interface(interface), connect_interface(interface)
SYSTEM: set_volume(percent), get_volume(), set_brightness(percent), get_brightness(),
        power_sleep(), power_reboot(), power_shutdown(),
        list_startup_apps(), enable_startup(service), disable_startup(service)
"""

_SYSTEM_PROMPT = (
    "You are an OS command extractor. Given a natural language instruction, "
    "output ONLY a JSON object: {\"op\": \"<name>\", \"args\": {<key>: <value>}}. "
    "Use ~ for home directory paths. No markdown, no explanation.\n\n"
    "Available operations:\n" + _OPS_DOC
)


async def _llm_parse(text: str) -> dict:
    from groq import AsyncGroq
    from core.vault import Vault
    from config.settings import MODEL_CFG

    print(f"[OS_INTERP] LLM fallback for: {text[:80]}")
    client = AsyncGroq(api_key=Vault().get("GROQ_API_KEY"))
    resp = await client.chat.completions.create(
        model=MODEL_CFG.groq_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": text},
        ],
        max_tokens=128,
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON in LLM response: {raw[:80]}")
    data = json.loads(m.group())
    op   = data.get("op", "")
    args = data.get("args", {}) or {}
    if op not in _VALID_OPS:
        raise ValueError(f"LLM returned unknown op '{op}'")
    print(f"[OS_INTERP] LLM → {op}({args})")
    return {"op": op, "args": args}


# ── Public API ─────────────────────────────────────────────────────────────────

async def interpret(text: str) -> dict:
    """
    Parse a natural-language OS instruction.
    Returns {"op": str, "args": dict} or raises ValueError.
    """
    # Fast path — regex
    result = _quick_parse(text)
    if result:
        return result

    # Slow path — LLM
    return await _llm_parse(text)
