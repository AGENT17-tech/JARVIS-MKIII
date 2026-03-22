"""
JARVIS-MKIII — agents/vision_agent.py
Screen awareness agent: screenshot + Claude vision for screen understanding.
Combines OCR (pytesseract) with LLM vision (claude-sonnet) for full awareness.
"""
from __future__ import annotations
import asyncio, base64, io, json, time
from agents.agent_base import AgentBase

_VISION_MODEL   = "claude-sonnet-4-20250514"
_SCREEN_PROMPT  = (
    "Describe what is currently on this screen. "
    "Be precise about what applications are open, "
    "what text is visible, and what the user appears to be doing."
)
_LOCATE_PROMPT  = (
    "Find the UI element described as: {description}\n"
    "Return ONLY a JSON object: "
    '{"x": int, "y": int, "found": bool, "description": str}'
)


class VisionAgent(AgentBase):
    def __init__(self):
        super().__init__("VISION")

    # ── run_task dispatcher ────────────────────────────────────────────────────

    async def run_task(self, task: str) -> str:
        lower = task.lower()

        if any(w in lower for w in ("find", "locate", "where is", "click on")):
            # Extract what to find
            import re
            m = re.search(
                r'(?:find|locate|where\s+is|click\s+on)\s+(?:the\s+)?(.+)', lower
            )
            target = m.group(1).strip() if m else task
            await self.push_update(f"Scanning screen for: {target}")
            result = await self.find_element(target)
            if result.get("found"):
                x, y = result["x"], result["y"]
                self.summary = f"Found '{target}' at ({x}, {y}) on screen."
                return f"Located '{target}' at coordinates ({x}, {y}).\n{result.get('description', '')}"
            else:
                self.summary = f"Could not locate '{target}' on screen."
                return f"Element '{target}' was not found on screen."

        if any(w in lower for w in ("read", "ocr", "text on")):
            await self.push_update("Running OCR on screen...")
            text = await self.read_screen_text()
            self.summary = "Screen text extracted."
            return text

        if "watch" in lower or "change" in lower or "monitor" in lower:
            await self.push_update("Watching screen for changes...")
            result = await self.watch_for_change()
            self.summary = result[:100]
            return result

        # Default: describe screen
        await self.push_update("Capturing and analysing screen...")
        description = await self.describe_screen()
        self.summary = description[:120]
        return description

    # ── Core functions ─────────────────────────────────────────────────────────

    async def capture_screen(self):
        """Take a desktop screenshot and return PIL Image."""
        def _snap():
            import pyautogui
            return pyautogui.screenshot()
        return await asyncio.to_thread(_snap)

    async def _image_to_base64(self, img) -> str:
        """Convert PIL Image to base64 PNG string."""
        def _convert():
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        return await asyncio.to_thread(_convert)

    async def describe_screen(self, prompt: str = _SCREEN_PROMPT) -> str:
        """Screenshot → Claude vision → natural language description."""
        img    = await self.capture_screen()
        b64    = await self._image_to_base64(img)
        return await self._vision_call(prompt, b64)

    async def find_element(self, description: str) -> dict:
        """
        Screenshot → Claude vision → returns {x, y, found, description}.
        Coordinates are for AutoGUIAgent to use directly.
        """
        img    = await self.capture_screen()
        b64    = await self._image_to_base64(img)
        prompt = _LOCATE_PROMPT.format(description=description)
        raw    = await self._vision_call(prompt, b64)

        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return {"found": False, "x": 0, "y": 0, "description": raw}

    async def read_screen_text(self) -> str:
        """OCR via pytesseract on current screenshot."""
        def _ocr():
            try:
                import pyautogui, pytesseract
                img = pyautogui.screenshot()
                return pytesseract.image_to_string(img)
            except ImportError as e:
                return f"OCR unavailable: {e}. Run: sudo apt install tesseract-ocr && pip install pytesseract"
        return await asyncio.to_thread(_ocr)

    async def watch_for_change(
        self, interval: float = 2.0, duration: float = 30.0
    ) -> str:
        """
        Poll screenshots every `interval` seconds for up to `duration` seconds.
        Returns a description of the first significant change detected.
        """
        from PIL import ImageChops, Image
        import numpy as np

        CHANGE_THRESHOLD = 0.02   # fraction of pixels that must differ

        prev_img = await self.capture_screen()
        start    = time.time()
        checks   = 0

        while time.time() - start < duration:
            await asyncio.sleep(interval)
            curr_img = await self.capture_screen()
            checks  += 1

            # Pixel diff
            diff   = await asyncio.to_thread(_pixel_diff, prev_img, curr_img)
            if diff > CHANGE_THRESHOLD:
                await self.push_update(f"Change detected ({diff:.1%} pixels changed) — analysing...")
                desc = await self.describe_screen(
                    "The screen has changed. Describe what is now showing and what changed."
                )
                return f"Change detected after {checks} check(s) ({diff:.1%} pixels changed):\n{desc}"

            prev_img = curr_img
            await self.push_update(f"Watching... {checks} check(s), no change yet.")

        return f"No significant screen change detected over {duration:.0f}s ({checks} checks)."

    # ── Claude vision API call ─────────────────────────────────────────────────

    async def _vision_call(self, prompt: str, image_b64: str) -> str:
        """Send prompt + screenshot to Claude claude-sonnet vision and return text response."""
        def _call():
            import anthropic
            from core.vault import Vault
            from core.personality import JARVIS_SYSTEM_PROMPT

            client = anthropic.Anthropic(api_key=Vault().get("ANTHROPIC_API_KEY"))
            msg = client.messages.create(
                model=_VISION_MODEL,
                max_tokens=1024,
                system=JARVIS_SYSTEM_PROMPT(),
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type":   "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/png",
                                "data":       image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return msg.content[0].text

        return await asyncio.to_thread(_call)


# ── Helper: pixel diff fraction ───────────────────────────────────────────────

def _pixel_diff(img1, img2) -> float:
    """Return fraction of pixels that differ between two PIL images."""
    try:
        from PIL import ImageChops
        import numpy as np
        diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
        arr  = np.array(diff)
        changed = np.any(arr > 15, axis=2)  # >15 per channel = real change
        return float(changed.sum()) / changed.size
    except Exception:
        return 0.0
