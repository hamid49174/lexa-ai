"""Lexa AI — Search Router
Search & export endpoints: /search, /search/fts, /memory/rebuild-fts, /conversations/*/export
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.config import MAX_SEARCH_QUERY, MAX_FTS_QUERY
from backend import memory

logger = logging.getLogger("lexa.search")

router = APIRouter(tags=["search"])


@router.get("/search")
async def global_search(q: str = ""):
    """Search across conversations, notes, and memories."""
    q = q.strip()[:MAX_SEARCH_QUERY]
    if not q:
        return {"status": "ok", "conversations": [], "notes": [], "memories": []}
    result = await asyncio.to_thread(memory.global_search, q)
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@router.get("/search/fts")
async def fts_search(q: str = ""):
    q = q.strip()[:MAX_FTS_QUERY]
    if not q:
        return {"status": "ok", "notes": [], "memories": [], "total": 0}
    result = await asyncio.to_thread(memory.full_text_search, q)
    if isinstance(result, dict):
        result["status"] = "ok"
    return result


@router.post("/memory/rebuild-fts")
async def rebuild_fts():
    return {"status": "ok", "result": await asyncio.to_thread(memory.rebuild_fts)}


@router.get("/conversations/{conv_id}/export")
async def export_conversation(conv_id: int, fmt: str = "markdown"):
    """Export a conversation as markdown or text."""
    if fmt not in ("markdown", "text"):
        fmt = "markdown"
    text = await asyncio.to_thread(memory.conversation_export, conv_id, fmt)
    if text is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", "text": text, "format": fmt}
