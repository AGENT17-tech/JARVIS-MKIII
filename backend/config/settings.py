import os
from pathlib import Path
from pydantic import BaseModel

class ModelConfig(BaseModel):
    groq_model:        str = "llama-3.3-70b-versatile"
    local_model:       str = "llava:7b"          # pinned — must match `ollama pull llava:7b`
    local_model_timeout: int = 30                 # seconds for Ollama request timeout
    groq_max_tokens:   int = 512
    local_max_tokens:  int = 1024
    ollama_host:       str = "http://localhost:11434"
    # Complex routing — routes long/complex prompts to Claude instead of Groq
    complex_routing_enabled: bool = True
    complex_model:           str  = "claude-3-haiku-20240307"
    complex_threshold_words: int  = 50
    complex_keywords:        list = [
        "analyze", "explain in detail", "compare", "write a report",
        "plan", "strategy", "research", "summarize this", "design",
    ]

class ServerConfig(BaseModel):
    host:  str = "0.0.0.0"
    port:  int = 8000
    debug: bool = False

class MemoryConfig(BaseModel):
    short_term_limit: int = 20
    long_term_db:     str = "memory/hindsight.db"

class WakeWordConfig(BaseModel):
    sensitivity:  float = 0.5   # detection threshold (0.0–1.0); lower = more sensitive
    cooldown_ms:  int   = 1500  # ms to ignore re-triggers after a detection

class STTConfig(BaseModel):
    confidence_threshold:    float = 0.75
    confirmation_enabled:    bool  = True
    max_confirmation_wait_s: int   = 8

class BrowserConfig(BaseModel):
    headless:            bool = True
    page_load_timeout_s: int  = 15
    implicit_wait_s:     int  = 5
    driver:              str  = "chrome"

class FSConfig(BaseModel):
    """Hard filesystem boundary — operations outside these paths are blocked."""
    resolve_username: bool = True   # auto-fill {username} from os.getlogin()

    def get_allowed_paths(self) -> list[Path]:
        """Return resolved allowed Path objects. Called at runtime."""
        paths: list[Path] = []
        try:
            username = os.getlogin() if self.resolve_username else os.environ.get("USERNAME", "user")
        except Exception:
            username = os.environ.get("USERNAME", "user")
        project_root = Path(__file__).parent.parent.parent

        candidates = [
            Path(f"C:/Users/{username}"),
            Path("C:/tmp"),
            project_root,
        ]
        for p in candidates:
            try:
                paths.append(p.resolve())
            except Exception:
                pass
        return paths

class SchedulerConfig(BaseModel):
    db_path: str = "data/scheduled_tasks.db"   # relative to project root

class WhatsAppConfig(BaseModel):
    enabled:          bool = True
    bridge_port:      int  = 3001
    session_dir:      str  = "whatsapp/whatsapp_session"
    reconnect_delay_s: int = 5

class TelegramConfig(BaseModel):
    enabled:            bool = False
    bot_token:          str  = ""   # from env TELEGRAM_BOT_TOKEN
    authorized_chat_id: int  = 0    # from env TELEGRAM_CHAT_ID — only this ID gets responses

class MCPConfig(BaseModel):
    enabled: bool = True

class MobileConfig(BaseModel):
    push_enabled:     bool = False
    vapid_public_key: str  = ""   # from vault
    vapid_private_key: str = ""   # from vault
    vapid_email:      str  = ""

# ── Tool names that the sandbox is allowed to execute ─────────────────────────
# Any tool name not in this list will be blocked with a warning.
ALLOWED_TOOLS: list[str] = [
    "shell",
    "read_file",
    "write_file",
    "web_fetch",
    "file_read",
    "file_write",
    "web_scrape",
    "calculate",
    "screenshot",
    "screenshot_gui",
    "run_terminal",
    "open_app",
    "search_web",
    "get_weather",
    "get_calendar",
    "get_github_status",
    "type_text",
    "press_shortcut",
    "youtube_control",
    # Phase 4 pipeline tools
    "summarize",
    "vision_analyze",
    "run_pipeline",
]

# ── Built-in tool pipeline presets ────────────────────────────────────────────
PIPELINES: dict = {
    "research_and_brief": [
        {"tool": "web_scrape",  "args": {},                    "use_previous_output": False},
        {"tool": "summarize",   "args": {},                    "use_previous_output": True},
        {"tool": "speak",       "args": {},                    "use_previous_output": True},
    ],
    "screen_and_analyze": [
        {"tool": "screenshot",      "args": {},                "use_previous_output": False},
        {"tool": "vision_analyze",  "args": {},                "use_previous_output": True},
        {"tool": "speak",           "args": {},                "use_previous_output": True},
    ],
}

LAT  = 30.0444
LON  = 31.2357
CITY = "Cairo"

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

MODEL_CFG     = ModelConfig()
SERVER_CFG    = ServerConfig()
MEMORY_CFG    = MemoryConfig()
WAKE_CFG      = WakeWordConfig()
STT_CFG       = STTConfig()
BROWSER_CFG   = BrowserConfig()
FS_CFG        = FSConfig()
SCHEDULER_CFG = SchedulerConfig()
WHATSAPP_CFG  = WhatsAppConfig()
TELEGRAM_CFG  = TelegramConfig(
    enabled            = os.environ.get("TELEGRAM_BOT_TOKEN", "") != "",
    bot_token          = os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    authorized_chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", "0")),
)
MCP_CFG       = MCPConfig()
MOBILE_CFG    = MobileConfig()
