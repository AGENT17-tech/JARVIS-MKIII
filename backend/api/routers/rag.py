"""
JARVIS-MKIII — api/routers/rag.py
FastAPI router exposing RAG memory endpoints.
"""
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

rag_router = APIRouter(prefix="/rag", tags=["rag"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query:      str
    n_results:  int = 5
    collection: str = "conversations"
    date_filter: Optional[str] = None


class StoreFactRequest(BaseModel):
    fact:   str
    source: str = "api"
    tags:   list[str] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@rag_router.get("/stats")
async def rag_stats():
    """Return memory collection counts and DB path."""
    try:
        from memory.rag_memory import get_rag
        return get_rag().get_stats()
    except Exception as e:
        return {"error": str(e), "conversations": 0, "facts": 0, "missions": 0}


@rag_router.post("/search")
async def rag_search(req: SearchRequest):
    """Semantic search across memory collections."""
    from memory.rag_memory import get_rag
    results = get_rag().search(
        query=req.query,
        n_results=req.n_results,
        collection=req.collection,
        date_filter=req.date_filter,
    )
    return {"results": results, "count": len(results)}


@rag_router.post("/store_fact")
async def rag_store_fact(req: StoreFactRequest):
    """Store a standalone fact in long-term memory."""
    from memory.rag_memory import get_rag
    get_rag().store_fact(req.fact, source=req.source, tags=req.tags)
    return {"status": "stored", "fact": req.fact}


@rag_router.get("/recall/{query}")
async def rag_recall(query: str, n_results: int = 5):
    """Return formatted memory context for a natural-language query."""
    from memory.rag_memory import get_rag
    context = get_rag().recall(query, n_results=n_results)
    return {"query": query, "context": context}


@rag_router.delete("/clear")
async def rag_clear(x_confirm: Optional[str] = Header(None)):
    """
    Clear ALL RAG memory. Requires header:
      X-Confirm: yes-clear-all-memory
    """
    if x_confirm != "yes-clear-all-memory":
        raise HTTPException(
            403,
            "Send header X-Confirm: yes-clear-all-memory to confirm deletion.",
        )
    # Re-create collections (delete + recreate via ChromaDB client)
    from memory.rag_memory import get_rag
    rag = get_rag()
    client = rag._client
    for name in ("conversations", "facts", "missions"):
        try:
            client.delete_collection(name)
            client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
        except Exception:
            pass

    # Reset singleton so next call re-initialises
    import memory.rag_memory as _rm
    _rm._rag = None

    return {"status": "cleared", "message": "All RAG memory has been erased."}
