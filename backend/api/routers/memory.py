"""
JARVIS-MKIII — api/routers/memory.py
Domain-aware memory endpoints backed by ChromaStore.

  GET  /memory/stats             → total count, per-domain breakdown, timestamps
  GET  /memory/search?q=..&n=.. → semantic search (optional domain filter)
  DELETE /memory/clear?confirm=true → wipe jarvis_memory collection
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

memory_router = APIRouter(prefix="/memory", tags=["memory"])


@memory_router.get("/stats")
async def memory_stats():
    """Return memory statistics: total count, domain breakdown, oldest/newest."""
    try:
        from memory.chroma_store import get_store
        return get_store().get_memory_stats()
    except Exception as e:
        return {"error": str(e), "total": 0, "domains": {}}


@memory_router.get("/search")
async def memory_search(
    q: str = Query(..., description="Natural-language search query"),
    n: int = Query(5, ge=1, le=20, description="Number of results"),
    domain: Optional[str] = Query(None, description="Filter by domain (engineering/combat/strategy/language/general)"),
):
    """Semantic search over jarvis_memory collection."""
    try:
        from memory.chroma_store import get_store
        results = get_store().retrieve_relevant(q, n=n, domain_filter=domain)
        return {
            "query":   q,
            "domain":  domain,
            "results": results,
            "count":   len(results.splitlines()) if results else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.delete("/clear")
async def memory_clear(confirm: bool = Query(False)):
    """
    Wipe all memories from jarvis_memory collection.
    Requires ?confirm=true to prevent accidents.
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass ?confirm=true to confirm deletion.",
        )
    try:
        from memory.chroma_store import get_store
        get_store().clear()
        return {"status": "cleared", "message": "All jarvis_memory entries erased."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
