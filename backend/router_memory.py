"""Lexa AI — Memory Router
Memory endpoints: /memory/*, /clipboard/*, /snippets/*, /history
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from backend.config import (
    MAX_NOTE_TITLE,
    MAX_NOTE_CONTENT,
    MAX_NOTE_CATEGORY,
    MAX_MEMORY_CONTENT,
    MAX_MEMORY_CATEGORY,
    MAX_SNIPPET_NAME,
    MAX_SNIPPET_TEXT,
    MAX_CLIPBOARD_TEXT,
    MAX_PROFILE_KEY,
    MAX_PROFILE_VALUE,
    DEFAULT_CLEANUP_DAYS,
    DEFAULT_CLEANUP_MAX_IMPORTANCE,
    MIN_CLEANUP_DAYS,
    MAX_CLEANUP_DAYS,
    CACHE_MEMORY_STATS_TTL,
)
from backend.shared import (
    conversation_history,
    _history_lock,
    parse_json_body,
    cache_get,
    cache_set,
)
from backend import memory
from backend.i18n import t

logger = logging.getLogger("lexa.memory_router")

router = APIRouter(tags=["memory"])


# ══════════════════════════════════════════════════
#  MEMORY STATS
# ══════════════════════════════════════════════════

@router.get("/memory/stats")
async def memory_stats():
    """Get memory database statistics (cached 10s)."""
    cached = cache_get("memory_stats", ttl=CACHE_MEMORY_STATS_TTL)
    if cached:
        return cached
    result = await asyncio.to_thread(memory.get_memory_stats)
    result["status"] = "ok"
    cache_set("memory_stats", result)
    return result


# ══════════════════════════════════════════════════
#  NOTES
# ══════════════════════════════════════════════════

@router.get("/memory/notes")
async def list_notes():
    return {"status": "ok", "notes": await asyncio.to_thread(memory.note_list)}


@router.get("/memory/notes/{note_id}")
async def get_note(note_id: int):
    """Get full note content by ID."""
    try:
        result = await asyncio.to_thread(memory.note_get_by_id, note_id)
        if result:
            return {"status": "ok", **result} if isinstance(result, dict) else result
        raise HTTPException(status_code=404, detail="Notiz nicht gefunden.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_note error")
        raise HTTPException(status_code=500, detail=t("memory.noteLoadError"))


@router.put("/memory/notes/{note_id}")
async def update_note(note_id: int, req: Request):
    """Update note title and/or content."""
    data = await parse_json_body(req)
    title = str(data.get("title", ""))[:MAX_NOTE_TITLE]
    content = str(data.get("content", ""))[:MAX_NOTE_CONTENT]
    category = str(data.get("category", ""))[:MAX_NOTE_CATEGORY]
    try:
        updated = await asyncio.to_thread(memory.note_update_by_id, note_id, title, content, category)
        if not updated:
            raise HTTPException(status_code=400, detail=t("memory.noteNoChanges"))
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_note error")
        raise HTTPException(status_code=500, detail=t("memory.noteUpdateError"))


# ══════════════════════════════════════════════════
#  MEMORIES
# ══════════════════════════════════════════════════

@router.post("/memory/add")
async def add_memory(req: Request):
    """Save a memory entry directly."""
    data = await parse_json_body(req)
    content = str(data.get("content", ""))[:MAX_MEMORY_CONTENT]
    category = str(data.get("category", "general"))[:MAX_MEMORY_CATEGORY]
    try:
        importance = min(10, max(1, int(data.get("importance", 5))))
    except (ValueError, TypeError):
        importance = 5
    if not content:
        raise HTTPException(status_code=400, detail="content fehlt.")
    result = await asyncio.to_thread(memory.add_memory, content, category, importance)
    return {"status": "ok", "result": result}


@router.get("/memory/profile")
async def get_profile():
    return {"status": "ok", "profile": await asyncio.to_thread(memory.get_user_profile)}


@router.post("/memory/profile")
async def set_profile(req: Request):
    data = await parse_json_body(req)
    key = str(data.get("key", ""))[:MAX_PROFILE_KEY]
    value = str(data.get("value", ""))[:MAX_PROFILE_VALUE]
    if not key:
        raise HTTPException(status_code=400, detail="key fehlt.")
    result = await asyncio.to_thread(memory.set_profile, key, value)
    return {"status": result}


@router.get("/memory/routines")
async def list_routines():
    return {"status": "ok", "routines": await asyncio.to_thread(memory.routine_list)}


@router.post("/memory/cleanup")
async def cleanup_memory(req: Request):
    """Manuell alte/unwichtige Erinnerungen aufräumen."""
    data = await parse_json_body(req)
    try:
        days_old = int(data.get("days_old", DEFAULT_CLEANUP_DAYS))
    except (ValueError, TypeError):
        days_old = DEFAULT_CLEANUP_DAYS
    try:
        max_importance = int(data.get("max_importance", DEFAULT_CLEANUP_MAX_IMPORTANCE))
    except (ValueError, TypeError):
        max_importance = DEFAULT_CLEANUP_MAX_IMPORTANCE
    # Sanity limits
    days_old = max(MIN_CLEANUP_DAYS, min(MAX_CLEANUP_DAYS, days_old))
    max_importance = max(1, min(5, max_importance))
    result = await asyncio.to_thread(memory.memory_cleanup, days_old, max_importance)
    if isinstance(result, dict):
        result["status"] = result.get("status", "ok")
    return result


# ══════════════════════════════════════════════════
#  CLIPBOARD HISTORY
# ══════════════════════════════════════════════════

@router.get("/clipboard/history")
async def get_clipboard_history():
    entries = await asyncio.to_thread(memory.clipboard_list)
    return {"status": "ok", "entries": entries}


@router.post("/clipboard/add")
async def add_clipboard_entry(req: Request):
    data = await parse_json_body(req)
    text = data.get("text", "").strip()[:MAX_CLIPBOARD_TEXT]
    if not text:
        return {"status": "empty"}
    result = await asyncio.to_thread(memory.clipboard_add, text)
    try:
        parts = result.split(":")
        count = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        count = 0
    return {"status": "added", "count": count}


@router.delete("/clipboard/history")
async def clear_clipboard_history():
    await asyncio.to_thread(memory.clipboard_clear)
    return {"status": "cleared"}


# ══════════════════════════════════════════════════
#  QUICK TEXT SNIPPETS
# ══════════════════════════════════════════════════

@router.get("/snippets")
async def list_snippets():
    return {"status": "ok", "snippets": await asyncio.to_thread(memory.snippet_list)}


@router.post("/snippets")
async def create_snippet(req: Request):
    data = await parse_json_body(req)
    name = data.get("name", "").strip()[:MAX_SNIPPET_NAME]
    text = data.get("text", "").strip()[:MAX_SNIPPET_TEXT]
    if not name or not text:
        raise HTTPException(status_code=400, detail="Name und Text erforderlich")
    result = await asyncio.to_thread(memory.snippet_create, name, text)
    return {"status": result}


@router.delete("/snippets/{name}")
async def delete_snippet(name: str):
    result = await asyncio.to_thread(memory.snippet_delete, name)
    return {"status": result}


# ══════════════════════════════════════════════════
#  HISTORY (in-memory conversation history)
# ══════════════════════════════════════════════════

@router.get("/history")
async def get_history():
    return {"status": "ok", "history": conversation_history}


@router.delete("/history")
async def clear_history():
    async with _history_lock:
        conversation_history.clear()
    return {"status": "cleared"}
