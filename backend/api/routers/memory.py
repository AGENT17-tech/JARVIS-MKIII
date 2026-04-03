"""
JARVIS-MKIII — api/routers/memory.py
Domain-aware memory endpoints backed by ChromaStore.

  GET  /memory/stats                   → total count, per-domain breakdown, timestamps
  GET  /memory/search?q=..&n=..        → semantic search (optional domain filter)
  POST /memory/prune                   → delete entries older than RETENTION_DAYS
  POST /memory/summarize-session       → summarize a session and store in ChromaDB
  DELETE /memory/clear?confirm=true    → wipe jarvis_memory collection
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
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


@memory_router.post("/prune")
async def memory_prune():
    """Delete ChromaDB entries older than RETENTION_DAYS (90). Returns count deleted."""
    try:
        from memory.chroma_store import get_store
        from memory.prune import prune_old_memories, RETENTION_DAYS
        deleted = prune_old_memories(get_store()._col)
        return {"deleted": deleted, "retention_days": RETENTION_DAYS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class _SummarizeRequest(BaseModel):
    session_id: str
    force:      bool = False


@memory_router.post("/summarize-session")
async def summarize_session_endpoint(body: _SummarizeRequest):
    """Summarize a session's conversation and store the digest in ChromaDB."""
    try:
        from memory.hindsight import memory
        from memory.session_summarizer import summarize_session, store_session_summary

        interactions = memory.get_session_interactions(body.session_id, limit=50)
        summary = await summarize_session(body.session_id, interactions, force=body.force)
        if summary is None:
            return {
                "status": "skipped",
                "reason": f"Session has fewer than 10 interactions (use force=true to override)",
                "interaction_count": len(interactions),
            }
        store_session_summary(body.session_id, summary)
        return {"status": "stored", "session_id": body.session_id, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/agent-results")
async def agent_results(limit: int = 20):
    """Return the most recent agent results stored in ChromaDB."""
    try:
        from memory.chroma_store import get_store
        store = get_store()
        # Query with a broad term — filter by type metadata
        raw = store._col.get(
            where={"type": "agent_result"},
            limit=limit,
            include=["documents", "metadatas"],
        )
        docs      = raw.get("documents") or []
        metas     = raw.get("metadatas") or []
        results = [
            {"content": d, "metadata": m}
            for d, m in zip(docs, metas)
        ]
        return {"results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/tool-history")
async def tool_history(limit: int = 50):
    """Return the most recent sandbox tool call audit log."""
    try:
        from memory.hindsight import memory
        rows = memory.get_tool_history(limit=limit)
        return {"calls": rows, "count": len(rows)}
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
