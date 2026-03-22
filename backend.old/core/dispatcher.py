"""
JARVIS-MKIII — Model Dispatcher
Handles the actual API calls to each model tier.
Keeps conversation history formatting, thinking blocks, and error handling
isolated here so the rest of the system never touches raw API calls.
"""

from __future__ import annotations
import httpx
import anthropic
from typing import AsyncGenerator

from config.settings import MODEL_CFG
from core.router import TaskTier
from core.vault import Vault

# ── Lazy client init (avoids vault prompt at import time) ────────────────────

_anthropic_client: anthropic.AsyncAnthropic | None = None
_vault = Vault()


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = __import__("os").environ.get("ANTHROPIC_API_KEY") or _vault.get("ANTHROPIC_API_KEY")
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


# ── Message format helpers ────────────────────────────────────────────────────

def _format_history(history: list[dict]) -> list[dict]:
    """
    Ensure history is in Anthropic message format.
    Strips any JARVIS metadata fields before sending.
    """
    clean = []
    for msg in history:
        if msg.get("role") in ("user", "assistant"):
            clean.append({"role": msg["role"], "content": msg["content"]})
    return clean


# ── Dispatch ─────────────────────────────────────────────────────────────────

async def dispatch(
    prompt: str,
    tier: TaskTier,
    history: list[dict],
    system_prompt: str = "",
    stream: bool = False,
) -> str | AsyncGenerator[str, None]:
    """
    Route to the correct model and return a response string.
    Set stream=True for streaming tokens (used by WebSocket endpoint).
    """
    messages = _format_history(history) + [{"role": "user", "content": prompt}]

    if tier == TaskTier.LOCAL:
        return await _call_local(messages, stream)

    if tier == TaskTier.REASONING:
        return await _call_groq(messages, system_prompt)

    return await _call_groq(messages, system_prompt)


# ── Sonnet 4.6 — voice / fast tier ───────────────────────────────────────────

async def _call_sonnet(
    messages: list[dict],
    system: str,
    stream: bool,
) -> str | AsyncGenerator[str, None]:
    client = _get_anthropic()

    if stream:
        async def _stream_sonnet():
            async with client.messages.stream(
                model=MODEL_CFG.voice_model,
                max_tokens=MODEL_CFG.voice_max_tokens,
                system=system or _default_system("Sonnet"),
                messages=messages,
            ) as s:
                async for text in s.text_stream:
                    yield text
        return _stream_sonnet()

    resp = await client.messages.create(
        model=MODEL_CFG.voice_model,
        max_tokens=MODEL_CFG.voice_max_tokens,
        system=system or _default_system("Sonnet"),
        messages=messages,
    )
    return resp.content[0].text


# ── Opus 4.6 — reasoning / agent tier ────────────────────────────────────────

async def _call_opus(
    messages: list[dict],
    system: str,
    stream: bool,
) -> str | AsyncGenerator[str, None]:
    client = _get_anthropic()

    create_kwargs = dict(
        model=MODEL_CFG.reasoning_model,
        max_tokens=MODEL_CFG.reasoning_max_tokens,
        system=system or _default_system("Opus"),
        messages=messages,
        thinking={
            "type": "enabled",
            "budget_tokens": MODEL_CFG.thinking_budget_tokens,
        },
        betas=["interleaved-thinking-2025-05-14"],
    )

    if stream:
        async def _stream_opus():
            async with client.messages.stream(**create_kwargs) as s:
                async for event in s:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            delta = event.delta
                            if hasattr(delta, "text"):
                                yield delta.text
        return _stream_opus()

    resp = await client.messages.create(**create_kwargs)
    # Extract only text blocks (skip thinking blocks)
    text_parts = [b.text for b in resp.content if b.type == "text"]
    return "\n".join(text_parts)


# ── DeepSeek-R1 — local / air-gapped tier ────────────────────────────────────

async def _call_local(
    messages: list[dict],
    stream: bool,
) -> str | AsyncGenerator[str, None]:
    """
    Calls DeepSeek-R1 via Ollama's REST API.
    Ollama must be running: `ollama serve`
    Model must be pulled:   `ollama pull deepseek-r1`
    """
    url = f"{MODEL_CFG.ollama_host}/api/chat"
    payload = {
        "model": MODEL_CFG.local_model,
        "messages": messages,
        "stream": stream,
    }

    if stream:
        async def _stream_local():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line:
                            import json
                            data = json.loads(line)
                            if chunk := data.get("message", {}).get("content", ""):
                                yield chunk
        return _stream_local()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json={**payload, "stream": False})
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# ── System prompts ────────────────────────────────────────────────────────────


def _default_system(model_name: str) -> str:
    import datetime
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%A, %d %B %Y")
    return (
        f"You are JARVIS, a British AI assistant for Agent 17. "
        f"The current time is {time_str}. Today is {date_str}. "
        f"You are running on the {model_name} tier. "
        "RULES: Max 1-2 sentences. No lists. No explanations unless asked. "
        "Be direct, precise, and British. State facts immediately."
    )

# ── Groq client ───────────────────────────────────────────────────────────────

_groq_client = None

def _get_groq():
    global _groq_client
    if _groq_client is None:
        import os
        from groq import AsyncGroq
        api_key = os.environ.get("GROQ_API_KEY") or _vault.get("GROQ_API_KEY")
        _groq_client = AsyncGroq(api_key=api_key)
    return _groq_client


async def _call_groq(messages: list[dict], system: str) -> str:
    client = _get_groq()
    resp = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system or _default_system("Groq Llama 3.3 70B")}] + messages,
        max_tokens=512,
        temperature=0.7,
    )
    return resp.choices[0].message.content
