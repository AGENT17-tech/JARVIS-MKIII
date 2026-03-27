"""
JARVIS-MKIII — api/routers/vision.py
REST endpoints that expose the LLaVA vision engine.

  GET  /vision/status      — check if LLaVA is available in Ollama
  GET  /vision/image       — serve the last screenshot for the HUD
  POST /vision/screenshot  — take a screenshot and analyse it
  POST /vision/analyze     — analyse an uploaded image file
  POST /vision/url         — analyse an image from a URL
"""
from __future__ import annotations
import shutil, tempfile

from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import FileResponse

from vision.vision_engine import analyze_image, analyze_screenshot, analyze_url_image

vision_router = APIRouter()


# ── Status ────────────────────────────────────────────────────────────────────

@vision_router.get("/vision/status")
async def vision_status():
    """Check whether LLaVA is loaded in Ollama."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:11434/api/tags")
            models = r.json().get("models", [])
            llava_available = any("llava" in m.get("name", "") for m in models)
            return {"available": llava_available, "model": "llava:7b"}
    except Exception:
        return {"available": False, "model": "llava:7b"}


# ── Serve last screenshot ─────────────────────────────────────────────────────

@vision_router.get("/vision/image")
async def get_vision_image():
    """Serve /tmp/jarvis_screen.png for the HUD image preview."""
    return FileResponse("/tmp/jarvis_screen.png", media_type="image/png")


# ── Screenshot & analyse ──────────────────────────────────────────────────────

@vision_router.post("/vision/screenshot")
async def vision_screenshot(body: dict = Body(default={})):
    """Take a screenshot and analyse it with LLaVA."""
    prompt = body.get("prompt", "Describe what you see.")
    result = await analyze_screenshot(prompt)
    return {"description": result, "source": "screenshot"}


# ── Upload & analyse ──────────────────────────────────────────────────────────

@vision_router.post("/vision/analyze")
async def vision_analyze_file(
    file:   UploadFile = File(...),
    prompt: str        = "Describe this image.",
):
    """Analyse an uploaded image file with LLaVA."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    result = await analyze_image(tmp_path, prompt)
    return {"description": result, "source": "upload"}


# ── URL & analyse ─────────────────────────────────────────────────────────────

@vision_router.post("/vision/url")
async def vision_url(body: dict = Body(...)):
    """Download an image from a URL and analyse it with LLaVA."""
    url    = body.get("url")
    prompt = body.get("prompt", "Describe this image.")
    if not url:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="url is required")
    result = await analyze_url_image(url, prompt)
    return {"description": result, "source": "url"}
