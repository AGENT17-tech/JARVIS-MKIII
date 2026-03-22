# JARVIS-MKIII Intelligence Stack

> Multi-tier AI assistant with autonomous agent capabilities, encrypted secrets, tool sandboxing, and Hindsight memory.

---

## Architecture

```
User Input (voice / text / file)
        │
        ▼
  Intent Router  ──── classifies prompt ────►  Task Tier
        │
   ┌────┴──────────────────────┐
   │                           │                          │
   ▼                           ▼                          ▼
Sonnet 4.6               Opus 4.6                  DeepSeek-R1
(voice / fast)    (planning / agents / code)   (local / air-gapped)
   │                           │                          │
   └───────────┬───────────────┘──────────────────────────┘
               │
               ▼
       Tool Execution Layer
       sandbox.py + vault.py
               │
               ▼
       Hindsight Memory
    (short-term + long-term)
               │
               ▼
     Response → TTS / UI / Action
```

---

## Model Tiers

| Tier | Model | Use Case |
|---|---|---|
| Voice | `claude-sonnet-4-6` | Fast responses, always-on assistant, voice output |
| Reasoning | `claude-opus-4-6` | Planning, code gen, multi-step agents, extended thinking |
| Local | `deepseek-r1` (Ollama) | Offline ops, sensitive data, air-gapped fallback |

---

## Setup

```bash
chmod +x setup.sh && ./setup.sh
```

What the setup script does:
1. Installs Python dependencies
2. Initialises the AES-256 vault and stores your Anthropic API key
3. Installs Ollama and pulls DeepSeek-R1
4. Creates the memory store directory
5. Runs the full test suite

---

## Launch

```bash
# Start the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# In a separate terminal, ensure Ollama is running for local tier
ollama serve
```

---

## API Reference

### `POST /chat`
```json
{
  "prompt": "Plan the MKIII agent orchestration architecture",
  "session_id": "optional-uuid",
  "system_prompt": "optional override",
  "force_tier": "reasoning"
}
```

Response:
```json
{
  "response": "...",
  "session_id": "uuid",
  "tier": "reasoning",
  "tier_reason": "Matched 3 deep-reasoning keyword(s)",
  "confidence": 0.75
}
```

### `WS /ws/{session_id}`
Send:
```json
{ "prompt": "JARVIS, status report." }
```
Receive stream:
```json
{ "type": "routing", "tier": "voice", "reason": "..." }
{ "type": "token", "text": "All systems" }
{ "type": "token", "text": " operational." }
{ "type": "done" }
```

### `GET /status` — health check
### `GET /memory/{session_id}` — inspect session context
### `POST /consolidate` — store long-term memory entry
### `GET /tools` — list sandboxed tools
### `POST /tool/{tool_name}` — execute a sandboxed tool

---

## Vault Usage

```bash
# CLI
python core/vault.py init
python core/vault.py set ANTHROPIC_API_KEY
python core/vault.py list

# From code
from core.vault import Vault
vault = Vault()
api_key = vault.get("ANTHROPIC_API_KEY")
```

---

## Adding Tools

```python
# tools/sandbox.py
@sandbox.register(name="my_tool", requires_confirmation=True)
async def my_tool(args: dict) -> ToolResult:
    # args = whatever the model sends
    return ToolResult(success=True, output="done", tool_name="my_tool")
```

---

## Memory System

The Hindsight memory system operates in two layers:

- **Short-term**: sliding window of the last 20 messages per session (in-memory)
- **Long-term**: SQLite store with keyword retrieval. Relevant past entries are automatically injected into the system prompt.

To consolidate a session exchange into long-term memory:
```bash
curl -X POST http://localhost:8000/consolidate \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "...", "summary": "Designed multi-agent orchestrator", "keywords": ["agent", "orchestrator", "design"]}'
```

---

## Project Structure

```
jarvis-mkiii/
├── api/
│   └── main.py          # FastAPI app — REST + WebSocket
├── core/
│   ├── router.py        # Intent classifier → TaskTier
│   ├── dispatcher.py    # Model API calls (Sonnet / Opus / Ollama)
│   └── vault.py         # AES-256-GCM secrets store
├── memory/
│   └── hindsight.py     # Short-term + long-term memory
├── tools/
│   └── sandbox.py       # Sandboxed tool execution layer
├── config/
│   └── settings.py      # Model + server + memory config
├── tests/
│   └── test_jarvis.py   # Full test suite
├── requirements.txt
├── setup.sh
└── README.md
```

---

## Roadmap (MKIII Phase 2)

- [ ] Vector embeddings via `nomic-embed-text` (Ollama) for semantic memory retrieval
- [ ] Multi-agent orchestration — spawn sub-agents per task domain
- [ ] Voice pipeline — Whisper STT → JARVIS → TTS output
- [ ] Electron UI integration — wire WebSocket to existing MKII frontend
- [ ] Docker Compose deployment for full stack isolation
