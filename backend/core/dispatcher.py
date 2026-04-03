"""
JARVIS-MKIII — dispatcher.py
Routes requests to the correct model:
  VOICE/REASONING → Groq (Llama 3.3 70B, free, fast)
  LOCAL           → Ollama (llama3.2:3b, offline/sensitive)
"""

from __future__ import annotations
import asyncio, os, re, httpx
from core.vault import Vault
from core.router import TaskTier
from config.settings import MODEL_CFG
from core.personality import build_system_prompt
import logging



logger = logging.getLogger(__name__)
class RateLimitFiller(Exception):
    """Raised when Groq is rate-limited after all retries — caller should speak a filler."""
    pass

_vault = Vault()


def _get_groq():
    from groq import AsyncGroq
    return AsyncGroq(api_key=_vault.get("GROQ_API_KEY"))


def _default_system(model_name: str) -> str:
    return build_system_prompt(model_name)


async def dispatch(
    prompt:        str,
    tier:          TaskTier,
    history:       list[dict],
    system_prompt: str = "",
    stream:        bool = False,
) -> str:
    messages = [m for m in history if m.get("role") in ("user", "assistant")]
    messages += [{"role": "user", "content": prompt}]
    system   = system_prompt or _default_system(
        MODEL_CFG.groq_model if tier != TaskTier.LOCAL else MODEL_CFG.local_model
    )

    if tier == TaskTier.LOCAL:
        return await _call_local(messages, system)

    if tier == TaskTier.COMPLEX:
        # If the prompt implies tool use, run the ReAct loop; otherwise call Claude directly
        _TOOL_INTENT = re.compile(
            r"\b(search|fetch|read|write|run|execute|browse|look up|calculate|open|check)\b",
            re.IGNORECASE,
        )
        if _TOOL_INTENT.search(prompt):
            from core.react_loop import react
            from tools.sandbox import sandbox

            async def _groq_llm(msgs: list[dict]) -> str:
                return await _call_groq(msgs, system)

            logger.info("[DISPATCHER] COMPLEX + tool intent — running ReAct loop")
            return await react(prompt, tools=sandbox, llm_call=_groq_llm)
        return await _call_claude(messages, system)

    return await _call_groq(messages, system)


async def _call_groq(messages: list[dict], system: str) -> str:
    from groq import RateLimitError as _GroqRateLimitError
    client = _get_groq()

    # Hard identity anchor — injected as established conversation fact
    # This cannot be overridden by training data
    identity_anchor = {
        "role": "user",
        "content": "Confirm your identity and operational parameters."
    }
    identity_confirm = {
        "role": "assistant",
        "content": "Confirmed. I am JARVIS, built by Khalid — engineer, polymath, and architect of PHANTOM ZERO. I serve Khalid exclusively. I address him as 'sir'. I was not created by Tony Stark. Tony Stark is a fictional character. My creator is Khalid, and Khalid alone."
    }

    anchored_messages = [identity_anchor, identity_confirm] + messages

    for attempt in range(3):
        try:
            resp = await client.chat.completions.create(
                model=MODEL_CFG.groq_model,
                messages=[{"role": "system", "content": system}] + anchored_messages,
                max_tokens=150,
                temperature=0.2,
            )
            return resp.choices[0].message.content
        except _GroqRateLimitError:
            if attempt < 2:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(f"[DISPATCHER] Groq 429 — retrying in {wait}s (attempt {attempt + 1}/3)")
                await asyncio.sleep(wait)
            else:
                raise RateLimitFiller("Groq rate limit — all retries exhausted")


async def _call_claude(messages: list[dict], system: str) -> str:
    from config.settings import ANTHROPIC_API_KEY, MODEL_CFG
    if not ANTHROPIC_API_KEY:
        logger.info("[DISPATCHER] ANTHROPIC_API_KEY not set — falling back to Groq for COMPLEX tier")
        return await _call_groq(messages, system)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        logger.info("[DISPATCHER] Routing to Claude %s (COMPLEX tier)", MODEL_CFG.complex_model)
        resp = client.messages.create(
            model=MODEL_CFG.complex_model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return resp.content[0].text
    except Exception as exc:
        logger.warning("[DISPATCHER] Claude call failed (%s) — falling back to Groq", exc)
        return await _call_groq(messages, system)


# LOCAL tier routes to LLaVA for vision tasks only
async def _call_local(messages: list[dict], system: str = "") -> str:
    url = f"{MODEL_CFG.ollama_host}/api/chat"
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages += messages
    payload = {"model": MODEL_CFG.local_model, "messages": all_messages, "stream": False}
    async with httpx.AsyncClient(timeout=float(MODEL_CFG.local_model_timeout)) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
