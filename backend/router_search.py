"""Lexa AI — Search Router
Search & export endpoints: /search, /search/fts, /memory/rebuild-fts, /conversations/*/export
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.config import MAX_SEARCH_QUERY, MAX_FTS_QUERY
from backend import memory
from backend.security import check_rate_limit, get_rate_limit_info

logger = logging.getLogger("lexa.search")

router = APIRouter(tags=["search"])

# Serialize FTS rebuilds: concurrent rebuilds on the same SQLite DB cause
# lock contention ("database is locked"). Only one rebuild may run at a time.
_rebuild_lock = asyncio.Lock()


def _rate_limited(endpoint_type: str = "chat") -> HTTPException:
    """Build a 429 HTTPException with standard rate-limit headers."""
    rl = get_rate_limit_info(endpoint_type)
    return HTTPException(
        status_code=429,
        detail="Zu viele Anfragen. Bitte kurz warten.",
        headers={
            "X-RateLimit-Limit": str(rl["limit"]),
            "X-RateLimit-Remaining": "0",
            "Retry-After": "60",
        },
    )


@router.get("/search")
async def global_search(q: str = ""):
    """Search across conversations, notes, and memories."""
    if not check_rate_limit("chat"):
        raise _rate_limited()
    q = q.strip()[:MAX_SEARCH_QUERY]
    if not q:
        return {"status": "ok", "conversations": [], "notes": [], "memories": []}
    result = await asyncio.to_thread(memory.global_search, q)
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@router.get("/search/fts")
async def fts_search(q: str = ""):
    if not check_rate_limit("chat"):
        raise _rate_limited()
    q = q.strip()[:MAX_FTS_QUERY]
    if not q:
        return {"status": "ok", "notes": [], "memories": [], "total": 0}
    result = await asyncio.to_thread(memory.full_text_search, q)
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@router.post("/memory/rebuild-fts")
async def rebuild_fts():
    if not check_rate_limit("chat"):
        raise _rate_limited()
    if _rebuild_lock.locked():
        raise HTTPException(status_code=409, detail="FTS-Rebuild läuft bereits.")
    async with _rebuild_lock:
        return {"status": "ok", "result": await asyncio.to_thread(memory.rebuild_fts)}


@router.get("/conversations/{conv_id}/export")
async def export_conversation(conv_id: int, fmt: str = "markdown"):
    """Export a conversation as markdown or text."""
    if not check_rate_limit("chat"):
        raise _rate_limited()
    if fmt not in ("markdown", "text"):
        fmt = "markdown"
    text = await asyncio.to_thread(memory.conversation_export, conv_id, fmt)
    if text is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "text": text, "format": fmt}
