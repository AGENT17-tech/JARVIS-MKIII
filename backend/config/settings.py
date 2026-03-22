from pydantic import BaseModel

class ModelConfig(BaseModel):
    groq_model:      str = "llama-3.3-70b-versatile"
    local_model:     str = "deepseek-r1:7b"
    groq_max_tokens: int = 512
    local_max_tokens: int = 1024
    ollama_host:     str = "http://localhost:11434"

class ServerConfig(BaseModel):
    host:  str = "0.0.0.0"
    port:  int = 8000
    debug: bool = False

class MemoryConfig(BaseModel):
    short_term_limit: int = 20
    long_term_db:     str = "memory/hindsight.db"

LAT  = 30.0444
LON  = 31.2357
CITY = "Cairo"

MODEL_CFG  = ModelConfig()
SERVER_CFG = ServerConfig()
MEMORY_CFG = MemoryConfig()
