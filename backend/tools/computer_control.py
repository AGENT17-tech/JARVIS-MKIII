"""
JARVIS-MKIII — tools/computer_control.py
PyAutoGUI-based computer automation tools.
Registered automatically into sandbox on import.
"""
from __future__ import annotations
import asyncio, subprocess
from tools.sandbox import sandbox, ToolResult

import os
os.environ.setdefault("DISPLAY", ":0")
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except (ImportError, SystemExit, Exception) as _e:
    print(f"[TOOLS] PyAutoGUI import failed: {_e}")
    PYAUTOGUI_AVAILABLE = False


def _check() -> ToolResult | None:
    if not PYAUTOGUI_AVAILABLE:
        return ToolResult(False, "", "computer_control", "pyautogui not installed.")
    return None


@sandbox.register(name="move_mouse")
async def tool_move_mouse(args: dict) -> ToolResult:
    if err := _check(): return err
    x, y = int(args.get("x", 0)), int(args.get("y", 0))
    await asyncio.to_thread(pyautogui.moveTo, x, y, duration=0.3)
    return ToolResult(True, f"Mouse moved to ({x}, {y})", "move_mouse")


@sandbox.register(name="click")
async def tool_click(args: dict) -> ToolResult:
    if err := _check(): return err
    x, y   = int(args.get("x", 0)), int(args.get("y", 0))
    button = args.get("button", "left")
    await asyncio.to_thread(pyautogui.click, x, y, button=button)
    return ToolResult(True, f"Clicked {button} at ({x}, {y})", "click")


@sandbox.register(name="double_click")
async def tool_double_click(args: dict) -> ToolResult:
    if err := _check(): return err
    x, y = int(args.get("x", 0)), int(args.get("y", 0))
    await asyncio.to_thread(pyautogui.doubleClick, x, y)
    return ToolResult(True, f"Double-clicked at ({x}, {y})", "double_click")


@sandbox.register(name="type_text_gui")
async def tool_type_text_gui(args: dict) -> ToolResult:
    if err := _check(): return err
    text = args.get("text", "")
    await asyncio.to_thread(pyautogui.typewrite, text, interval=0.05)
    return ToolResult(True, f"Typed: {text[:60]}", "type_text_gui")


@sandbox.register(name="press_key_gui")
async def tool_press_key_gui(args: dict) -> ToolResult:
    if err := _check(): return err
    key = args.get("key", "")
    if "+" in key:
        parts = [k.strip() for k in key.split("+")]
        await asyncio.to_thread(pyautogui.hotkey, *parts)
    else:
        await asyncio.to_thread(pyautogui.press, key)
    return ToolResult(True, f"Pressed: {key}", "press_key_gui")


@sandbox.register(name="scroll")
async def tool_scroll(args: dict) -> ToolResult:
    if err := _check(): return err
    x, y   = int(args.get("x", 0)), int(args.get("y", 0))
    amount = int(args.get("amount", 3))
    await asyncio.to_thread(pyautogui.scroll, amount, x=x, y=y)
    return ToolResult(True, f"Scrolled {amount} at ({x}, {y})", "scroll")


@sandbox.register(name="screenshot_gui")
async def tool_screenshot_gui(args: dict) -> ToolResult:
    if err := _check(): return err
    path = "/tmp/jarvis_screen.png"
    img  = await asyncio.to_thread(pyautogui.screenshot)
    img.save(path)
    return ToolResult(True, path, "screenshot_gui")


@sandbox.register(name="find_on_screen")
async def tool_find_on_screen(args: dict) -> ToolResult:
    if err := _check(): return err
    image_path = args.get("image_path", "")
    try:
        loc = await asyncio.to_thread(
            pyautogui.locateCenterOnScreen, image_path, confidence=0.8
        )
        if loc:
            return ToolResult(True, f"{loc.x},{loc.y}", "find_on_screen")
        return ToolResult(False, "", "find_on_screen", "Image not found on screen.")
    except Exception as e:
        return ToolResult(False, "", "find_on_screen", str(e))


@sandbox.register(name="open_application")
async def tool_open_application(args: dict) -> ToolResult:
    name = args.get("name", "").strip()
    if not name:
        return ToolResult(False, "", "open_application", "No application name provided.")
    try:
        await asyncio.create_subprocess_exec(
            "xdg-open", name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return ToolResult(True, f"Launched: {name}", "open_application")
    except Exception:
        try:
            await asyncio.create_subprocess_shell(
                name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return ToolResult(True, f"Launched: {name}", "open_application")
        except Exception as e:
            return ToolResult(False, "", "open_application", str(e))
