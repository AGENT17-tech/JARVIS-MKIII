"""
JARVIS-MKIII — system/intent_router.py
Detects system-control intents from natural language.

Supported actions (in detection order)
────────────────────────────────────────
  App control : "open"     / "close"   + known app name
  Terminal    : "terminal" / "install" / "remove" / "update"
  OS control  : "file" / "process" / "network" / "system_cfg"
  Browser     : "browser"
  Agent spawn : "research" / "code" / "organize"
  LLM fallback: ambiguous app-control phrasing

Strategy
────────
  1. App keyword pass    — open/close keywords + known app name  (fastest)
  2. Terminal keywords   — install/remove/execute/update
  3. OS control keywords — file, process, network, system config
  4. Browser keywords    — url, search web, screenshot
  5. Agent keywords      — research, code writing, file organisation
  6. LLM fallback        — Groq JSON for ambiguous app-control phrases
"""
from __future__ import annotations
import json, re
from system.app_controller import _load_registry

# ── App control ───────────────────────────────────────────────────────────────
_OPEN_WORDS  = {"open", "launch", "start", "run", "fire up", "bring up", "load"}
_CLOSE_WORDS = {"close", "kill", "quit", "exit", "stop", "shut", "terminate"}

# ── Terminal / package ────────────────────────────────────────────────────────
_INSTALL_WORDS  = {"install", "download"}
_REMOVE_WORDS   = {"uninstall", "remove"}
_UPDATE_PHRASES = {
    "update system", "update packages", "update all",
    "upgrade system", "upgrade packages", "system update", "system upgrade",
}
_EXEC_PATTERNS = [
    r'\bexecute\s+(.+)',
    r'\brun in terminal\s+(.+)',
    r'\bin terminal\s+(.+)',
    r'\bterminal\s+(.+)',
]
_RUN_PATTERN = re.compile(r'\brun\s+(.+)', re.IGNORECASE)

# ── OS File System ────────────────────────────────────────────────────────────
_FILE_PATS = [
    r'\b(create|make|new)\s+(file|document|doc)\b',
    r'\b(create|make|new)\s+(folder|directory|dir)\b',
    r'\b(mkdir|touch)\b',
    r'\bdelete\s+(file|folder|directory|document)\b',
    r'\b(rename|move)\s+\S+.*\bto\b',
    r'\bcopy\s+(file|folder|directory)\b',
    r'\bread\s+(the\s+)?(file|document|contents?\s+of)\b',
    r'\bshow\s+(me\s+)?(the\s+)?(file|content|contents|text)\s+(of|in|at)\b',
    r'\blist\s+(files|directory|dir|folder|contents)\b',
    r'\bwhat.s in\s+.*\b(folder|directory|dir)\b',
    r'\b(find|search for)\s+(file|files|document|documents|pdf)\b',
]

# ── Process Management ────────────────────────────────────────────────────────
_PROC_PATS = [
    r'\bwhat.s\s+running\b',
    r'\blist\s+processes\b',
    r'\brunning\s+processes\b',
    r'\btask\s+manager\b',
    r'\bkill\s+(process|pid)\b',
    r'\bkill\s+\w+\s+(process|service)\b',
    r'\bstop\s+(process|service)\s+\w',
    r'\bterminate\s+process\b',
    r'\bcpu\s+usage\b',
    r'\bprocess\s+list\b',
    r'\bwhat processes\b',
    r'\bset\s+priority\b',
    r'\bnice\s+value\b',
]

# ── Network ───────────────────────────────────────────────────────────────────
_NET_PATS = [
    r'\bnetwork\s+status\b',
    r'\bnetwork\s+info\b',
    r'\bscan\s+(the\s+)?(network|subnet|local)\b',
    r'\bwho.s\s+connected\b',
    r'\bwho\s+is\s+connected\b',
    r'\bactive\s+connections\b',
    r'\bbandwidth\b',
    r'\bnetwork\s+speed\b',
    r'\bdisconnect\s+(wifi|wlan|eth|interface|network)\b',
    r'\bconnect\s+interface\b',
    r'\bwifi\s+status\b',
    r'\bmy\s+ip\s+(address)?\b',
    r'\bip\s+address\b',
    r'\bopen\s+connections\b',
]

# ── System Config ─────────────────────────────────────────────────────────────
_SYSCFG_PATS = [
    r'\bset\s+volume\b',
    r'\bvolume\s+to\s+\d',
    r'\bturn\s+(up|down)\s+(the\s+)?(volume|sound)\b',
    r'\b(what.s|what\s+is)\s+(the\s+)?(volume|brightness)\b',
    r'\bset\s+brightness\b',
    r'\bbrightness\s+to\s+\d',
    r'\b(power\s+off|shut\s+down|shutdown|power\s+down)\b',
    r'\breboot\b',
    r'\brestart\s+(the\s+)?(computer|system|machine|pc)\b',
    r'\bsleep\s+mode\b',
    r'\bsuspend\b',
    r'\bstartup\s+apps\b',
    r'\bauto.?start\b',
    r'\benable\s+startup\b',
    r'\bdisable\s+startup\b',
]

# ── Browser ───────────────────────────────────────────────────────────────────
_BROWSER_PATS = [
    r'\bgo\s+to\s+https?://',
    r'\bopen\s+https?://',
    r'\bnavigate\s+to\s+https?://',
    r'\bbrowse\s+to\b',
    r'\bsearch\s+(the\s+)?(web|online|internet)\b',
    r'\bgoogle\s+\w',
    r'\bdownload\s+.*from\s+https?://',
    r'\btake\s+(a\s+)?screenshot\b',
    r'\bopen.*\burl\b',
    r'\bweb\s+search\b',
]

# ── Research agent ────────────────────────────────────────────────────────────
_RESEARCH_PATS = [
    r'\bdo.*research.*\bon\b',
    r'\brun.*research\b',
    r'\bfind\s+out\s+about\b',
    r'\bdeep.?dive\b',
    r'\binvestigate\b',
    r'\bresearch\s+\w+',         # "research quantum computing"
    r'\bwrite\s+(me\s+)?a\s+(report|briefing|summary)\s+(on|about)\b',
]

# ── Code agent ────────────────────────────────────────────────────────────────
_CODE_PATS = [
    r'\bwrite\s+(me\s+)?(some\s+)?code\b',
    r'\bwrite\s+(a\s+)?script\b',
    r'\bwrite\s+(a\s+)?program\b',
    r'\bwrite\s+(a\s+)?function\b',
    r'\bcreate\s+(a\s+)?script\b',
    r'\bbuild\s+(a\s+)?script\b',
    r'\bautomate.*with.*code\b',
    r'\bcode\s+that\s+\w',
    r'\bprogram\s+that\s+\w',
    r'\bpython\s+(script|code|program)\b',
]

# ── Developer agent (codebase editing via Anthropic API) ─────────────────────
_DEV_PATS = [
    r'\bdev\s+agent\b',
    r'\blaunch\s+dev\b',
    r'\bdev[,:]?\s+\w',                                      # "dev: add X"  "dev, fix Y"
    r'\b(edit|modify|update|fix|patch)\s+(the\s+)?(jarvis\s+)?(codebase|backend|hud|frontend)\b',
    r'\b(add|implement|create)\s+.{0,40}(to|in)\s+(the\s+)?(jarvis|backend|codebase)\b',
    r'\bjarvis\s+(modify|edit|update|fix|implement|add)\s+(the\s+)?(backend|code|codebase|agent)\b',
    r'\b(modify|edit|update|fix|patch)\s+\S+\.(py|js|jsx|ts|tsx)\b',
    r'\b(create|add|write)\s+(a\s+)?(new\s+)?(agent|endpoint|route|module)\s+(to|in|for)\s+(jarvis|the\s+backend)\b',
]

# ── File organisation agent ───────────────────────────────────────────────────
_ORGANIZE_PATS = [
    r'\borganize\s+(my\s+)?(files|downloads|documents)\b',
    r'\bsort\s+(my\s+)?files\b',
    r'\bclean\s+up\s+.*folder\b',
    r'\bfind\s+all\s+.*files\b',
    r'\bfiles\s+modified\b',
    r'\bdelete\s+(all\s+)?files\s+(larger|bigger|older)\b',
    r'\bmove\s+files\s+by\b',
    r'\bgroup\s+files\b',
    r'\bdelete\s+duplicate\b',
]

# ── Mission Board ─────────────────────────────────────────────────────────────
_MISSION_PATS = [
    r'\badd\s+(a\s+)?(mission|task)\b',
    r'\bnew\s+(mission|task)\b',
    r'\bcreate\s+(a\s+)?(mission|task)\b',
    r'\bmark\b.+\b(complete|done|finished)\b',   # "mark X complete" (title in middle)
    r'\bmark\s+(complete|done|finished)\b',        # "mark complete" (no title)
    r'\b(what|show)\s+(are\s+)?(my\s+)?(missions|tasks)\b',
    r'\bmission\s+status\b',
    r'\bend\s+of\s+day\b',
    r'\bdefer\s+(task|mission)\b',
    r'\bdaily\s+briefing\b',
    r'\bmission\s+board\b',
    r'\bcomplete\s+(mission|task)\b',
    r'\btask\s+list\b',
    r'\bmy\s+tasks\b',
    r'\btoday.s\s+(tasks|missions)\b',
]

# ── Mission keyword fast-check (simple contains, checked before all regex) ────
_MISSION_KEYWORDS = (
    "add mission", "new mission", "add task", "create mission", "create task",
    "complete mission", "mark complete", "mission status",
)

# ── Brave / web search ────────────────────────────────────────────────────────
_BRAVE_PATS = [
    r'\bbrave\s+search\b',
    r'\bsearch\s+(the\s+)?(web|internet|online)\s+for\b',
    r'\blook\s+up\s+.+\s+online\b',
    r'\bweb\s+search\s+for\b',
    r'\bsearch\s+online\s+for\b',
    r'\bfind\s+(me\s+)?information\s+(on|about)\b',
    r'\bwhat.s\s+(the\s+)?latest\s+(on|about)\b',
    r'\bnews\s+(on|about)\b',
    r'\bsearch\s+for\s+news\b',
    r'\blatest\s+news\b',
]

# ── GitHub queries ─────────────────────────────────────────────────────────────
_GITHUB_PATS = [
    r'\bgithub\s+(repos?|repositories)\b',
    r'\bmy\s+(repos?|repositories)\b',
    r'\bshow\s+(my\s+)?repos?\b',
    r'\brecent\s+commits?\b',
    r'\blatest\s+commits?\b',
    r'\bgithub\s+commits?\b',
    r'\bcommit\s+history\b',
    r'\bopen\s+issues?\b',
    r'\bgithub\s+issues?\b',
    r'\bcreate\s+(a\s+)?github\s+issue\b',
    r'\bgithub\s+pull\s+requests?\b',
    r'\bmy\s+github\b',
    r'\bgithub\s+status\b',
]

# ── Web fetch ──────────────────────────────────────────────────────────────────
_FETCH_PATS = [
    r'\bfetch\s+(the\s+)?(page|content|url|site)\b',
    r'\bget\s+(the\s+)?(content\s+of|text\s+from)\s+https?://',
    r'\bscrape\s+(the\s+)?\w',
    r'\bread\s+(the\s+)?(page|content)\s+at\s+https?://',
    r'\bwhat.s\s+(on|at)\s+https?://',
    r'\bopen\s+and\s+read\s+https?://',
]

# ── Diagnostics ────────────────────────────────────────────────────────────────
_DIAGNOSTIC_PATS = [
    r'\brun\s+diagnostics?\b',
    r'\bjarvis.+diagnostic\b',
    r'\bsystem\s+status\b',
    r'\bsystem\s+health\b',
    r'\bsystems?\s+check\b',
    r'\ball\s+systems\b',
    r'\bhow.s\s+(everything|jarvis)\s+(doing|running)\b',
    r'\brun\s+a\s+check\b',
    r'\bhealth\s+report\b',
    r'\bdiagnostic\s+report\b',
]

# ── Google Calendar ───────────────────────────────────────────────────────────
_CALENDAR_PATS = [
    r"\bwhat.s\s+on\s+my\s+calendar\b",
    r"\bmy\s+calendar\s+today\b",
    r"\bcalendar\s+today\b",
    r"\bany\s+meetings?\s+today\b",
    r"\bdo\s+i\s+have\s+(any\s+)?meetings?\b",
    r"\bwhat.s\s+scheduled\b",
    r"\bmy\s+schedule\b",
    r"\btoday.s\s+(schedule|agenda|events?|meetings?)\b",
    r"\bshow\s+(me\s+)?my\s+(calendar|schedule|events?|meetings?)\b",
    r"\bcheck\s+(my\s+)?(calendar|schedule|events?|meetings?)\b",
    r"\bwhat\s+(events?|meetings?)\s+(do\s+i\s+have|are\s+(scheduled|on))\b",
    r"\bupcoming\s+(events?|meetings?)\b",
    r"\bnext\s+(event|meeting|appointment)\b",
    r"\bcalendar\s+(check|briefing|update)\b",
    r"\bagenda\s+for\s+today\b",
]

# ── Time / date ───────────────────────────────────────────────────────────────
_TIME_PATS = [
    r'\bwhat\s+(time|date)\s+is\s+it\b',
    r'\bwhat.s\s+the\s+(time|date)\b',
    r'\btell\s+me\s+the\s+(time|date)\b',
    r'\bcurrent\s+(time|date)\b',
    r'\bwhat\s+day\s+is\s+(it|today)\b',
    r'\bwhat.s\s+today.s\s+date\b',
    r'\bwhat\s+is\s+today.s\s+date\b',
    r'\bwhat\s+is\s+the\s+time\b',
    r'\bwhat\s+is\s+the\s+date\b',
]

# ── Screenshot (direct — save to ~/Pictures/jarvis/) ──────────────────────────
_SCREENSHOT_PATS = [
    r'\btake\s+(a\s+)?screenshot\b',
    r'\bscreenshot\b',
    r'\bcapture\s+(the\s+)?(screen|desktop)\b',
    r'\bsnap\s+(the\s+)?(screen|desktop)\b',
]

# ── Type text (direct xdotool) ────────────────────────────────────────────────
_TYPE_TEXT_PATS = [
    r'\btype\s+.{2,}',
    r'\bwrite\s+.{2,}\s+(?:here|now)\b',
]

# ── Press key / shortcut (direct xdotool) ─────────────────────────────────────
_PRESS_KEY_PATS = [
    r'\bpress\s+(?:the\s+)?(?:keys?\s+)?(?:ctrl|alt|shift|win|super|f\d+|enter|escape|esc|tab|space|backspace|delete)\b',
    r'\bpress\s+ctrl\b',
    r'\bpress\s+alt\b',
    r'\bpress\s+f\d+\b',
    r'\bpress\s+(?:the\s+)?(?:key\s+)?(?:ctrl|alt)\s*[+\s]\s*\S',
    r'\bhit\s+(?:the\s+)?(?:enter|escape|esc|tab|space|ctrl|alt|f\d+)\b',
    r'\bkeyboard\s+shortcut\b',
]

# ── YouTube browser control ────────────────────────────────────────────────────
_YOUTUBE_PATS = [
    r'\b(pause|play|mute|unmute|fullscreen|full\s+screen)\s+youtube\b',
    r'\byoutube\s+(pause|play|mute|unmute|fullscreen|full\s+screen|next|previous|forward|rewind)\b',
    r'\b(pause|play)\s+(?:the\s+)?video\b',
    r'\bmute\s+(?:the\s+)?(?:video|tab|browser)\b',
    r'\byoutube\b.{0,30}\b(pause|play|mute|stop|fullscreen)\b',
]

# ── Desktop automation (AutoGUI) ──────────────────────────────────────────────
_AUTOGUI_PATS = [
    r'\bclick\s+on\b',
    r'\bdouble.?click\b',
    r'\bright.?click\b',
    r'\btype\s+(the\s+)?(text|word|phrase|command)\b',
    r'\bpress\s+(the\s+)?(key\s+)?(enter|escape|tab|ctrl|alt|shift|space|backspace|f\d+)\b',
    r'\bpress\s+ctrl\b',
    r'\btake\s+(a\s+)?screenshot\s+(of\s+)?(my\s+)?(desktop|screen)\b',
    r'\bscreenshot\s+(of\s+)?(my\s+)?(desktop|screen)\b',
    r'\bdesktop\s+screenshot\b',
    r'\bautomate\b',
    r'\bmacro\b',
    r'\bmove\s+(the\s+)?mouse\b',
    r'\bopen\s+with\s+keyboard\b',
    r'\bhotkey\b',
    r'\bkeyboard\s+shortcut\b',
    r'\bscroll\s+(up|down)\b',
    r'\bdrag\s+from\b',
    r'\btype\s+and\s+(press|hit)\b',
]

# ── Screen vision ─────────────────────────────────────────────────────────────
_VISION_PATS = [
    r'\bwhat\s+do\s+you\s+see\b',
    r"\bwhat.s\s+on\s+(my\s+)?screen\b",
    r'\bread\s+(the\s+)?screen\b',
    r'\bdescribe\s+(the\s+)?screen\b',
    r'\banalyse\s+(the\s+)?screen\b',
    r'\banalyze\s+(the\s+)?screen\b',
    r'\bscreen\s+(content|text|capture)\b',
    r'\bfind\s+(the\s+)?(button|element|icon|link)\s+(on|in)\s+(the\s+)?screen\b',
    r'\bwhere\s+is\s+.+\s+on\s+(the\s+)?screen\b',
    r'\bwhat\s+(app|application|window)\s+is\s+open\b',
    r'\bwatch\s+(the\s+)?screen\b',
    r'\bmonitor\s+(the\s+)?screen\b',
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _known_apps() -> list[str]:
    return list(_load_registry()["apps"].keys())


def _keyword_match(text: str) -> tuple[str | None, str | None]:
    lower = text.lower()
    action = None
    for w in _OPEN_WORDS:
        if w in lower:
            action = "open"; break
    if not action:
        for w in _CLOSE_WORDS:
            if w in lower:
                action = "close"; break
    if not action:
        return None, None
    for app in sorted(_known_apps(), key=len, reverse=True):
        if app in lower:
            return action, app
    return None, None


def _terminal_keyword_match(text: str) -> tuple[str | None, str | None]:
    lower = text.lower().strip()
    for phrase in _UPDATE_PHRASES:
        if phrase in lower:
            return "update", None
    for w in _INSTALL_WORDS:
        m = re.search(rf'\b{w}\s+(\S+)', lower)
        if m:
            return "install", m.group(1)
    for w in _REMOVE_WORDS:
        m = re.search(rf'\b{w}\s+(\S+)', lower)
        if m:
            return "remove", m.group(1)
    for pattern in _EXEC_PATTERNS:
        m = re.search(pattern, lower, re.IGNORECASE)
        if m:
            start   = m.start(1)
            payload = text[start:].strip().strip("'\"")
            if payload:
                return "terminal", payload
    m = _RUN_PATTERN.search(text)
    if m:
        payload = m.group(1).strip().strip("'\"")
        if payload:
            return "terminal", payload
    return None, None


def _pat_match(patterns: list[str], text: str) -> bool:
    lower = text.lower()
    return any(re.search(p, lower) for p in patterns)


def _os_intent_match(text: str) -> tuple[str | None, str | None]:
    """Keyword pass for OS/agent intents. Returns (action, text) or (None, None)."""
    # Vision and autogui checked first — their patterns are specific and
    # would otherwise be swallowed by broader file/browser patterns
    # (e.g. "move the mouse to..." matches the file "move...to" pattern).
    if _pat_match(_DIAGNOSTIC_PATS,  text): return "diagnostic",  text
    if _pat_match(_MISSION_PATS,    text): return "mission",      text
    if _pat_match(_CALENDAR_PATS,   text): return "calendar",     text
    if _pat_match(_TIME_PATS,       text): return "time_date",    text
    if _pat_match(_SCREENSHOT_PATS, text): return "screenshot",   text
    if _pat_match(_TYPE_TEXT_PATS,  text): return "type_text",    text
    if _pat_match(_PRESS_KEY_PATS,  text): return "press_key",    text
    if _pat_match(_YOUTUBE_PATS,    text): return "youtube",      text
    if _pat_match(_VISION_PATS,     text): return "vision",       text
    if _pat_match(_AUTOGUI_PATS,    text): return "autogui",      text
    if _pat_match(_FILE_PATS,       text): return "file",         text
    if _pat_match(_PROC_PATS,       text): return "process",      text
    if _pat_match(_NET_PATS,        text): return "network",      text
    if _pat_match(_SYSCFG_PATS,     text): return "system_cfg",   text
    # MCP-backed intents (checked before generic browser/research to avoid overlap)
    if _pat_match(_GITHUB_PATS,     text): return "mcp_github",   text
    if _pat_match(_BRAVE_PATS,      text): return "mcp_brave",    text
    if _pat_match(_FETCH_PATS,      text): return "mcp_fetch",    text
    if _pat_match(_BROWSER_PATS,    text): return "browser",      text
    if _pat_match(_RESEARCH_PATS,   text): return "research",     text
    if _pat_match(_DEV_PATS,        text): return "dev",          text
    if _pat_match(_CODE_PATS,       text): return "code",         text
    if _pat_match(_ORGANIZE_PATS,   text): return "organize",     text
    return None, None


async def _llm_parse(text: str) -> tuple[str | None, str | None]:
    try:
        from groq import AsyncGroq
        from core.vault import Vault
        from config.settings import MODEL_CFG
        apps_list = ", ".join(_known_apps())
        system = (
            "You are an intent-classification engine. "
            "Reply with ONLY a single JSON object — no markdown, no explanation. "
            'Format: {"action": "open", "app": "<name>"} '
            '     or {"action": "close", "app": "<name>"} '
            '     or {"action": "none", "app": null}. '
            f"Valid app names (use exactly as written): {apps_list}. "
            "If the user is not asking to open or close one of those apps, "
            'return {"action": "none", "app": null}.'
        )
        client = AsyncGroq(api_key=Vault().get("GROQ_API_KEY"))
        resp   = await client.chat.completions.create(
            model=MODEL_CFG.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": text},
            ],
            max_tokens=32,
            temperature=0,
        )
        raw   = resp.choices[0].message.content.strip()
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if not match:
            return None, None
        data   = json.loads(match.group())
        action = data.get("action", "none")
        app    = data.get("app")
        if action in ("open", "close") and app and app.lower() in _known_apps():
            return action, app.lower()
    except Exception:
        pass
    return None, None


# ── Public API ────────────────────────────────────────────────────────────────

async def parse_intent(text: str) -> tuple[str | None, str | None]:
    """
    Returns (action, payload) where action is one of:
      "open" | "close"     — app control       (payload = app name)
      "terminal"           — shell exec        (payload = command string)
      "install" | "remove" — apt package       (payload = package name)
      "update"             — system update     (payload = None)
      "file"               — file system op    (payload = original text)
      "process"            — process mgmt      (payload = original text)
      "network"            — network control   (payload = original text)
      "system_cfg"         — system config     (payload = original text)
      "browser"            — browser control   (payload = original text)
      "research"           — research agent    (payload = original text)
      "dev"                — developer agent   (payload = original text)
      "code"               — code agent        (payload = original text)
      "organize"           — file agent        (payload = original text)
      "calendar"           — Google Calendar    (payload = original text)
      "time_date"          — time/date query    (payload = original text)
      "screenshot"         — desktop screenshot (payload = original text)
      "type_text"          — type text directly (payload = original text)
      "press_key"          — press shortcut     (payload = original text)
      "youtube"            — YouTube control    (payload = original text)
      "vision"             — vision agent       (payload = original text)
      "autogui"            — autogui agent      (payload = original text)
      "mission"            — mission board      (payload = original text)
      "diagnostic"         — system diagnostic  (payload = original text)
      "mcp_brave"          — Brave web search  (payload = original text)
      "mcp_github"         — GitHub query      (payload = original text)
      "mcp_fetch"          — web fetch         (payload = original text)
    Returns (None, None) if no system-control intent detected.
    """
    _lower = text.lower()

    # 0. Mission fast-path — simple string contains, checked before everything else.
    #    Prevents mission commands from accidentally matching app-launcher or
    #    terminal patterns.
    if any(kw in _lower for kw in _MISSION_KEYWORDS):
        return "mission", text

    # 1. App control — keyword + known app
    #    Blocklist: if mission phrasing is present, do not treat as app launch.
    action, app = _keyword_match(text)
    if action and app:
        if not any(kw in _lower for kw in _MISSION_KEYWORDS):
            return action, app

    # 2. Terminal / package
    t_action, t_payload = _terminal_keyword_match(text)
    if t_action:
        return t_action, t_payload

    # 3. OS / browser / agent intent keywords
    o_action, o_payload = _os_intent_match(text)
    if o_action:
        return o_action, o_payload

    # 4. LLM fallback (app-control only)
    return await _llm_parse(text)
