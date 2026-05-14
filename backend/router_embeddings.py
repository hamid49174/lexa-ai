"""Lexa AI — Embeddings Router (Phase 42)
API endpoints for semantic memory management:
- Reindex all memories with embeddings
- Check reindex status / embedding coverage
- Get embedding provider info
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

router = APIRouter(prefix="/memory/embeddings", tags=["embeddings"])
logger = logging.getLogger("lexa.embeddings.router")

# ── Track background reindex progress ────────────
_reindex_running = False
_reindex_progress: dict = {}


@router.get("/status")
async def embedding_status():
    """Return embedding system status: provider, coverage, cache."""
    from backend.memory import get_embedding_stats
    stats = await asyncio.to_thread(get_embedding_stats)
    stats["reindex_running"] = _reindex_running
    return stats


@router.post("/reindex")
async def reindex_embeddings():
    """Trigger a full reindex of all unembedded memories.

    Runs in a background thread. Returns immediately with status.
    """
    global _reindex_running, _reindex_progress

    if _reindex_running:
        return {"status": "already_running", **_reindex_progress}

    _reindex_running = True
    _reindex_progress = {"status": "running", "newly_indexed": 0}

    async def _run():
        global _reindex_running, _reindex_progress
        try:
            from backend.memory import reindex_embeddings as do_reindex
            result = await asyncio.to_thread(do_reindex)
            _reindex_progress = result
        except Exception as e:
            logger.error(f"Reindex failed: {e}", exc_info=True)
            _reindex_progress = {"status": "error", "error": str(e)}
        finally:
            _reindex_running = False

    asyncio.create_task(_run())
    return {"status": "started", "message": "Reindex gestartet im Hintergrund."}


@router.get("/reindex/status")
async def reindex_status():
    """Check progress of a running reindex operation."""
    return {
        "running": _reindex_running,
        **_reindex_progress,
    }


@router.get("/provider")
async def embedding_provider():
    """Return details about the active embedding provider."""
    try:
        from backend.embeddings import get_embedding_status
        return await asyncio.to_thread(get_embedding_status)
    except ImportError:
        return {"provider": "unavailable", "error": "Embeddings module not installed"}
