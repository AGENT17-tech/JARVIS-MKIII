"""
JARVIS-MKIII — integrations/telegram_gateway.py
Embedded Telegram gateway that runs inside the FastAPI event loop.

Bidirectional:
  Incoming: Telegram message → JARVIS /chat pipeline → reply
  Outgoing: proactive_agent / scheduler → send_proactive() → Telegram message

Security: only authorized_chat_id receives or triggers any response.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class TelegramGateway:
    """Runs the Telegram bot inside the FastAPI asyncio event loop."""

    def __init__(
        self,
        token: str,
        authorized_chat_id: int,
        chat_fn: Callable[[str, str], Awaitable[str]],
    ):
        self._token               = token
        self._authorized_chat_id  = authorized_chat_id
        self._chat_fn             = chat_fn
        self._app                 = None
        self._running             = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            from telegram.ext import Application, MessageHandler, filters
            self._app = Application.builder().token(self._token).build()
            from telegram.ext import MessageHandler, filters as tgfilters
            from telegram import Update
            from telegram.ext import ContextTypes

            async def _handle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
                await self._handle_message(update, ctx)

            self._app.add_handler(MessageHandler(tgfilters.TEXT & ~tgfilters.COMMAND, _handle))

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()
            self._running = True
            logger.info("[TELEGRAM] Gateway started — authorized_chat_id=%d", self._authorized_chat_id)
        except Exception as exc:
            logger.error("[TELEGRAM] Failed to start gateway: %s", exc)

    async def stop(self) -> None:
        if self._app and self._running:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as exc:
                logger.warning("[TELEGRAM] Stop error: %s", exc)
            self._running = False
            logger.info("[TELEGRAM] Gateway stopped.")

    # ── Message handling ───────────────────────────────────────────────────────

    async def _handle_message(self, update, context) -> None:
        chat_id = update.effective_chat.id
        if chat_id != self._authorized_chat_id:
            logger.warning("[TELEGRAM] Unauthorized chat_id=%d — dropping message", chat_id)
            return

        user_text = update.message.text or ""
        if not user_text:
            return

        logger.info("[TELEGRAM] Message from authorized user: %r", user_text[:80])
        try:
            response = await self._chat_fn(user_text, session_id="telegram")
            await update.message.reply_text(response)
        except Exception as exc:
            logger.error("[TELEGRAM] Chat pipeline error: %s", exc)
            await update.message.reply_text(f"JARVIS error: {exc}")

    # ── Proactive push ─────────────────────────────────────────────────────────

    async def send_proactive(self, message: str) -> None:
        """Push a proactive alert to the authorized Telegram chat."""
        if not self._app or not self._running:
            logger.warning("[TELEGRAM] send_proactive called but gateway not running")
            return
        try:
            await self._app.bot.send_message(
                chat_id=self._authorized_chat_id,
                text=message,
            )
            logger.info("[TELEGRAM] Proactive message sent: %s", message[:60])
        except Exception as exc:
            logger.warning("[TELEGRAM] send_proactive failed: %s", exc)
