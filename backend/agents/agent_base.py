"""
JARVIS-MKIII — agents/agent_base.py
Base class for all JARVIS operative agents.
Each agent runs in its own asyncio task, reports status in real time,
and pushes results to the HUD Agent Feed on completion.
"""
from __future__ import annotations
import asyncio, time, uuid
from abc import ABC, abstractmethod
from typing import Any
import logging



logger = logging.getLogger(__name__)
class AgentStatus:
    IDLE     = "idle"
    RUNNING  = "running"
    COMPLETE = "complete"
    ERROR    = "error"


class AgentBase(ABC):
    """
    Subclass and implement run_task(task: str) → str.
    Call self.push_update(message) during execution to stream progress to HUD.
    """

    def __init__(self, name: str):
        self.name:       str        = name
        self.agent_id:   str        = str(uuid.uuid4())[:8]
        self.status:     str        = AgentStatus.IDLE
        self.task:       str        = ""
        self.result:     str        = ""
        self.summary:    str        = ""
        self.start_time: float | None = None
        self.end_time:   float | None = None
        self._task_obj:  asyncio.Task | None = None

    # ── Abstract ───────────────────────────────────────────────────────────────
    @abstractmethod
    async def run_task(self, task: str) -> str:
        """Do the work. Return the full result string."""
        ...

    def get_voice_summary(self) -> str:
        """Return a short TTS-safe summary. Subclasses may override."""
        return self.summary or self.result[:200]

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    async def run(self, task: str) -> None:
        """Spawn the task coroutine and broadcast updates."""
        self.task       = task
        self.status     = AgentStatus.RUNNING
        self.start_time = time.time()
        await self._broadcast_update()
        try:
            self.result = await self.run_task(task)
            self.status = AgentStatus.COMPLETE
        except asyncio.CancelledError:
            self.status = AgentStatus.ERROR
            self.result = "Cancelled by operator."
            raise
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.result = f"Agent error: {e}"
        finally:
            self.end_time = time.time()
            await self._broadcast_update()
            # Speak summary via TTS
            if self.status == AgentStatus.COMPLETE:
                try:
                    from api.voice_bridge import request_speak
                    await request_speak(self.get_voice_summary())
                except Exception:
                    pass

    def cancel(self):
        if self._task_obj and not self._task_obj.done():
            self._task_obj.cancel()

    # ── Reporting ─────────────────────────────────────────────────────────────
    def report(self) -> dict:
        elapsed = None
        if self.start_time:
            end = self.end_time or time.time()
            elapsed = round(end - self.start_time, 1)
        return {
            "agent_id":   self.agent_id,
            "name":       self.name,
            "status":     self.status,
            "task":       self.task,
            "result":     self.result,
            "summary":    self.summary,
            "elapsed":    elapsed,
            "timestamp":  int(time.time()),
            "severity":   "normal",
        }

    async def push_update(self, message: str):
        """Push a progress message to the HUD mid-task."""
        self.result = message
        await self._broadcast_event("agent_event")

    async def _broadcast_update(self):
        """Broadcast current state. On completion sends agent_update (final signal)."""
        is_terminal = self.status in (AgentStatus.COMPLETE, AgentStatus.ERROR)
        msg_type = "agent_update" if is_terminal else "agent_event"
        await self._broadcast_event(msg_type)

    async def _broadcast_event(self, msg_type: str):
        try:
            from agents.agent_dispatcher import dispatcher
            await dispatcher.broadcast_event(msg_type, self.report())
            logger.info(f"[AGENT:{self.name}] Broadcast {msg_type} status={self.status}")
        except Exception as e:
            logger.error(f"[AGENT:{self.name}] Broadcast failed ({msg_type}): {e}")

    # ── Persistence ───────────────────────────────────────────────────────────
    async def _persist_result(self, agent_type: str, result: str) -> None:
        """Store agent result to ChromaDB for future retrieval."""
        try:
            from memory.chroma_store import get_store
            store = get_store()
            store.add(
                content=result,
                metadata={
                    "type":       "agent_result",
                    "agent_type": agent_type,
                    "agent_id":   self.agent_id,
                    "task":       self.task[:200],
                },
                domain="general",
            )
            logger.info("[AGENT:%s] Result persisted to ChromaDB", self.name)
        except Exception as exc:
            logger.warning("[AGENT:%s] Failed to persist result: %s", self.name, exc)

    # ── LLM helper ────────────────────────────────────────────────────────────
    async def _llm(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        """Dispatch to Groq with JARVIS personality. Used by all subclass agents."""
        from core.dispatcher import dispatch
        from core.router import TaskTier
        from core.personality import JARVIS_SYSTEM_PROMPT
        sys = JARVIS_SYSTEM_PROMPT() + ("\n\n" + system if system else "")
        return await dispatch(
            prompt=prompt,
            tier=TaskTier.REASONING,
            history=[],
            system_prompt=sys,
            stream=False,
        )
