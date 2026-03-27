"""
JARVIS-MKIII — vision/vision_engine.py
Local vision via LLaVA (Ollama) — fast, offline, no API key required.
Falls back gracefully if Ollama is unavailable.
"""
from __future__ import annotations
import base64, os
from pathlib import Path

import httpx

OLLAMA_URL   = "http://localhost:11434/api/generate"
VISION_MODEL = os.getenv("VISION_MODEL", "llava:7b")


async def analyze_image(image_path: str, prompt: str | None = None) -> str:
    """Send an image file to LLaVA and return its description."""
    path = Path(image_path)
    if not path.exists():
        return f"Image not found: {image_path}"

    with open(path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    question = prompt or "Describe what you see in detail."

    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(OLLAMA_URL, json={
            "model":  VISION_MODEL,
            "prompt": question,
            "images": [image_b64],
            "stream": False,
            "options": {"num_gpu": 0},   # CPU inference — GPU VRAM reserved for voice pipeline
        })
        r.raise_for_status()
        data = r.json()
        return data.get("response", "No response from vision model")


async def analyze_screenshot(prompt: str | None = None) -> str:
    """Take a screenshot then analyse it with LLaVA."""
    from tools.computer_control import tool_screenshot_gui
    result = await tool_screenshot_gui({})
    if not result.success:
        return "Screenshot failed — cannot analyse screen."
    description = await analyze_image("/tmp/jarvis_screen.png", prompt)
    try:
        from integrations.touchdesigner_bridge import on_vision_result
        on_vision_result(description)
    except Exception:
        pass
    return description


async def analyze_url_image(url: str, prompt: str | None = None) -> str:
    """Download an image from a URL and analyse it with LLaVA."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        img_path = "/tmp/jarvis_url_image.jpg"
        with open(img_path, "wb") as f:
            f.write(r.content)
    return await analyze_image(img_path, prompt)
