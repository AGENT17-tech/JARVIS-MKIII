"""
JARVIS-MKIII — Configuration
All secrets loaded via vault.py, never from raw env.
"""
from pydantic import BaseModel
from typing import Optional


class ModelConfig(BaseModel):
    voice_model: str = "claude-sonnet-4-6"
    reasoning_model: str = "claude-opus-4-6"
    local_model: str = "llama3.2:3b"

    # Token budgets
    voice_max_tokens: int = 1024
    reasoning_max_tokens: int = 8096
    local_max_tokens: int = 4096

    # Extended thinking budget for Opus (reasoning tier)
    thinking_budget_tokens: int = 3000

    # Ollama host
    ollama_host: str = "http://localhost:11434"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class MemoryConfig(BaseModel):
    short_term_limit: int = 20        # messages kept in active context
    long_term_db: str = "memory/hindsight.db"
    embedding_model: str = "nomic-embed-text"   # local via Ollama
    similarity_threshold: float = 0.75


MODEL_CFG = ModelConfig()
SERVER_CFG = ServerConfig()
MEMORY_CFG = MemoryConfig()
