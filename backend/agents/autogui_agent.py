"""
JARVIS-MKIII — agents/autogui_agent.py
Desktop automation agent — gives JARVIS physical control over the desktop.
Uses PyAutoGUI for mouse/keyboard, xdotool/wmctrl for window focus.
Requires DISPLAY environment variable to be set.
"""
from __future__ import annotations
import asyncio, json, pathlib, subprocess, time
from agents.agent_base import AgentBase

_SCREENSHOT_DIR = pathlib.Path.home() / "JARVIS_MKIII" / "screenshots"

# ── Macro step executor ────────────────────────────────────────────────────────

_STEP_SCHEMA = """
Each step is a dict with an "action" key. Supported actions:
  {"action": "click",        "x": int, "y": int}
  {"action": "double_click", "x": int, "y": int}
  {"action": "right_click",  "x": int, "y": int}
  {"action": "move",         "x": int, "y": int, "duration": float}
  {"action": "type",         "text": str, "interval": float}
  {"action": "press",        "key": str}
  {"action": "hotkey",       "keys": [str, ...]}
  {"action": "scroll",       "x": int, "y": int, "clicks": int}
  {"action": "drag",         "x1": int, "y1": int, "x2": int, "y2": int}
  {"action": "screenshot"}
  {"action": "wait",         "seconds": float}
  {"action": "focus",        "title": str}
"""


class AutoGUIAgent(AgentBase):
    def __init__(self):
        super().__init__("AUTOGUI")

    # ── run_task: parse task via LLM then execute ──────────────────────────────

    async def run_task(self, task: str) -> str:
        import pyautogui
        pyautogui.PAUSE = 0.1  # small safety pause between actions

        await self.push_update(f"Planning automation: {task[:80]}")

        # Use LLM to convert natural language to macro steps
        steps_json = await self._llm(
            prompt=(
                f'Convert this desktop automation task to a JSON array of steps:\n"{task}"\n\n'
                f"Schema:\n{_STEP_SCHEMA}\n\n"
                "Return ONLY a JSON array. No markdown, no explanation."
            ),
            system=(
                "You are a desktop automation planner. "
                "Convert natural language instructions to precise GUI macro steps. "
                "Use realistic screen coordinates (1920x1080 assumed). "
                "Always add a wait step of 0.5s after opening apps or clicking buttons."
            ),
            max_tokens=512,
        )

        # Extract JSON array from response
        import re
        m = re.search(r"\[.*\]", steps_json, re.DOTALL)
        if not m:
            raise ValueError(f"LLM did not return a valid step array: {steps_json[:120]}")

        steps = json.loads(m.group())
        await self.push_update(f"Executing {len(steps)} automation step(s)...")

        result = await self.run_macro(steps)
        return result

    # ── Core action primitives ─────────────────────────────────────────────────

    async def take_screenshot(self) -> str:
        """Capture full desktop screenshot. Returns file path."""
        def _snap():
            import pyautogui
            _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            path = _SCREENSHOT_DIR / f"desktop_{int(time.time())}.png"
            img = pyautogui.screenshot()
            img.save(str(path))
            return str(path)
        return await asyncio.to_thread(_snap)

    async def find_on_screen(self, image_path: str) -> tuple[int, int] | None:
        """Locate an image on screen. Returns (x, y) or None."""
        def _find():
            import pyautogui
            loc = pyautogui.locateOnScreen(image_path, confidence=0.8)
            if loc:
                return pyautogui.center(loc)
            return None
        return await asyncio.to_thread(_find)

    async def click(self, x: int, y: int) -> None:
        await asyncio.to_thread(_pyautogui_call, "click", x, y)

    async def double_click(self, x: int, y: int) -> None:
        await asyncio.to_thread(_pyautogui_call, "doubleClick", x, y)

    async def right_click(self, x: int, y: int) -> None:
        await asyncio.to_thread(_pyautogui_call, "rightClick", x, y)

    async def click_image(self, image_path: str) -> bool:
        """Find image on screen and click it. Returns True if found and clicked."""
        pos = await self.find_on_screen(image_path)
        if pos:
            await self.click(pos[0], pos[1])
            return True
        return False

    async def type_text(self, text: str, interval: float = 0.05) -> None:
        await asyncio.to_thread(_pyautogui_call, "typewrite", text, interval=interval)

    async def press_key(self, key: str) -> None:
        await asyncio.to_thread(_pyautogui_call, "press", key)

    async def hotkey(self, *keys: str) -> None:
        await asyncio.to_thread(_pyautogui_call, "hotkey", *keys)

    async def move_mouse(self, x: int, y: int, duration: float = 0.3) -> None:
        await asyncio.to_thread(_pyautogui_call, "moveTo", x, y, duration=duration)

    async def scroll(self, x: int, y: int, clicks: int) -> None:
        await asyncio.to_thread(_pyautogui_call, "scroll", clicks, x=x, y=y)

    async def drag(
        self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.4
    ) -> None:
        await asyncio.to_thread(
            _pyautogui_call, "drag", end_x - start_x, end_y - start_y,
            duration=duration, button="left"
        )

    async def read_screen(self) -> str:
        """Screenshot + OCR via pytesseract. Returns visible text."""
        def _ocr():
            import pyautogui
            try:
                import pytesseract
                from PIL import Image
                img = pyautogui.screenshot()
                return pytesseract.image_to_string(img)
            except ImportError:
                return "(pytesseract not installed — run: sudo apt install tesseract-ocr && pip install pytesseract)"
        return await asyncio.to_thread(_ocr)

    async def focus_window(self, title: str) -> bool:
        """Bring window matching title to foreground using xdotool."""
        def _focus():
            # Try xdotool first
            try:
                result = subprocess.run(
                    ["xdotool", "search", "--name", title, "windowactivate", "--sync"],
                    capture_output=True, timeout=5,
                )
                return result.returncode == 0
            except FileNotFoundError:
                pass
            # Fallback: wmctrl
            try:
                result = subprocess.run(
                    ["wmctrl", "-a", title],
                    capture_output=True, timeout=5,
                )
                return result.returncode == 0
            except FileNotFoundError:
                return False
        return await asyncio.to_thread(_focus)

    # ── Macro executor ────────────────────────────────────────────────────────

    async def run_macro(self, steps: list[dict]) -> str:
        """
        Execute a sequence of automation steps.
        steps = [
            {"action": "hotkey", "keys": ["ctrl", "alt", "t"]},
            {"action": "wait", "seconds": 1.5},
            {"action": "type", "text": "neofetch"},
            {"action": "press", "key": "enter"},
            {"action": "screenshot"},
        ]
        Returns a summary of what was executed.
        """
        log = []
        for i, step in enumerate(steps):
            action = step.get("action", "").lower()
            try:
                if action == "click":
                    await self.click(int(step["x"]), int(step["y"]))
                    log.append(f"Clicked ({step['x']}, {step['y']})")

                elif action == "double_click":
                    await self.double_click(int(step["x"]), int(step["y"]))
                    log.append(f"Double-clicked ({step['x']}, {step['y']})")

                elif action == "right_click":
                    await self.right_click(int(step["x"]), int(step["y"]))
                    log.append(f"Right-clicked ({step['x']}, {step['y']})")

                elif action == "move":
                    dur = float(step.get("duration", 0.3))
                    await self.move_mouse(int(step["x"]), int(step["y"]), duration=dur)
                    log.append(f"Moved mouse to ({step['x']}, {step['y']})")

                elif action == "type":
                    interval = float(step.get("interval", 0.05))
                    await self.type_text(str(step["text"]), interval=interval)
                    log.append(f"Typed: {str(step['text'])[:40]}")

                elif action == "press":
                    await self.press_key(str(step["key"]))
                    log.append(f"Pressed: {step['key']}")

                elif action == "hotkey":
                    keys = step["keys"]
                    await self.hotkey(*keys)
                    log.append(f"Hotkey: {'+'.join(keys)}")

                elif action == "scroll":
                    await self.scroll(int(step["x"]), int(step["y"]), int(step["clicks"]))
                    log.append(f"Scrolled {step['clicks']} clicks at ({step['x']}, {step['y']})")

                elif action == "drag":
                    await self.drag(
                        int(step["x1"]), int(step["y1"]),
                        int(step["x2"]), int(step["y2"]),
                    )
                    log.append(f"Dragged ({step['x1']},{step['y1']}) → ({step['x2']},{step['y2']})")

                elif action == "screenshot":
                    path = await self.take_screenshot()
                    log.append(f"Screenshot saved: {path}")

                elif action == "wait":
                    secs = float(step.get("seconds", 1.0))
                    await asyncio.sleep(secs)
                    log.append(f"Waited {secs}s")

                elif action == "focus":
                    ok = await self.focus_window(str(step["title"]))
                    log.append(f"Focus '{step['title']}': {'OK' if ok else 'not found'}")

                else:
                    log.append(f"Unknown action skipped: {action}")

                await self.push_update(f"Step {i+1}/{len(steps)}: {log[-1]}")

            except Exception as e:
                log.append(f"Step {i+1} FAILED ({action}): {e}")
                await self.push_update(f"Step {i+1} error: {e}")

        self.summary = f"Automation complete — {len(steps)} step(s) executed."
        return "\n".join(log)


# ── pyautogui thread helper ────────────────────────────────────────────────────

def _pyautogui_call(fn_name: str, *args, **kwargs):
    import pyautogui
    getattr(pyautogui, fn_name)(*args, **kwargs)
