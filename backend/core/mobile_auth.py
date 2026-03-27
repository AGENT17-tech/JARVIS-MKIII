"""
JARVIS-MKIII — core/mobile_auth.py
Token-based auth middleware for public tunnel access.

Rules:
  - Requests from localhost (127.0.0.1 / ::1) → always allowed
  - Requests via Cloudflare tunnel (non-local origin) → token required
    for protected API endpoints
  - Token supplied via:
      Header:  X-JARVIS-Token: <token>
      Query:   ?token=<token>

Protected paths (non-local only):
  /chat  /vision  /missions  /briefing/run  /proactive  /weather
  /github  /forecast  /tts  /tool

Public paths (always):
  /health  /status  /mobile  /ws/  /tunnel  /calendar
"""
from __future__ import annotations
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MOBILE_TOKEN = os.getenv("MOBILE_ACCESS_TOKEN", "phantom-zero-2026")

_PROTECTED = (
    "/chat", "/vision", "/missions", "/briefing/run",
    "/proactive", "/weather", "/github", "/forecast",
    "/tts", "/tool", "/agents",
)
_PUBLIC = (
    "/health", "/status", "/mobile", "/ws/",
    "/tunnel", "/calendar", "/docs", "/openapi",
)


def _is_local(request: Request) -> bool:
    """True when the request originates from localhost with no proxy headers."""
    host = (request.client.host if request.client else "127.0.0.1")
    forwarded = request.headers.get("X-Forwarded-For", "").strip()
    cf_connecting = request.headers.get("CF-Connecting-IP", "").strip()
    return host in ("127.0.0.1", "::1") and not forwarded and not cf_connecting


def _needs_auth(path: str) -> bool:
    if any(path.startswith(p) for p in _PUBLIC):
        return False
    return any(path.startswith(p) for p in _PROTECTED)


class MobileAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_local(request) or not _needs_auth(request.url.path):
            return await call_next(request)

        token = (
            request.headers.get("X-JARVIS-Token")
            or request.query_params.get("token")
        )
        if token != MOBILE_TOKEN:
            return JSONResponse(
                {"error": "Unauthorized. Valid X-JARVIS-Token required.", "code": 401},
                status_code=401,
            )
        return await call_next(request)
