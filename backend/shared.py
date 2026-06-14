"""Lexa AI — Shared State
Shared mutable state that needs to be accessible from multiple routers.
Separated from main.py to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from backend.config import MAX_HISTORY, CACHE_MAX_ENTRIES

logger = logging.getLogger("lexa.shared")

# ── Conversation History (in-memory + SQLite persistence) ──
conversation_history: list[dict] = []
_history_lock = asyncio.Lock()

# Tracks which conversation the in-memory history currently reflects. Chat
# endpoints re-sync when the active conversation changes, so context never bleeds
# between different chats (the working history used to be a single global list
# that only reset on explicit switch — not on "new chat").
_active_conversation_id: Optional[int] = None


def get_active_conversation_id() -> Optional[int]:
    return _active_conversation_id


def set_active_conversation_id(conv_id: Optional[int]) -> None:
    """Mark which conversation the in-memory history reflects (e.g. after /load)."""
    global _active_conversation_id
    _active_conversation_id = conv_id


async def ensure_active_conversation(conv_id: Optional[int]) -> None:
    """Make conversation_history reflect conv_id.

    If conv_id differs from the active one, reload that conversation's messages
    from storage (clearing the prior chat's context). No-op when conv_id is None
    (legacy/ad-hoc requests) or already active. A brand-new empty conversation
    therefore starts with a clean history — no bleed from the previous chat.
    """
    global _active_conversation_id
    if conv_id is None or conv_id == _active_conversation_id:
        return
    from backend import memory
    try:
        conv = await asyncio.to_thread(memory.conversation_get, conv_id)
    except Exception as e:
        logger.warning(f"ensure_active_conversation: load failed for {conv_id}: {e}")
        conv = None
    async with _history_lock:
        conversation_history.clear()
        for msg in (conv or {}).get("messages", []) or []:
            if isinstance(msg, dict) and msg.get("content"):
                conversation_history.append(
                    {"role": msg.get("role", "user"), "content": str(msg["content"])}
                )
        _trim_history_unlocked()
        _active_conversation_id = conv_id
    logger.info(
        f"Active conversation synced -> {conv_id} ({len(conversation_history)} msgs)"
    )

# ── Pending Confirmation State ──
# Tracks the last action that requires user confirmation.
# This allows Lexa to understand "bestätige" / "ja" / "mach es" follow-ups.
_pending_confirmation: Optional[dict] = None
_pending_confirmation_ts: float = 0.0
_PENDING_CONFIRMATION_TTL = 300.0  # 5 minutes — after that, forget it


def set_pending_confirmation(action: dict) -> None:
    """Store a pending confirmation action (tool call awaiting user approval)."""
    global _pending_confirmation, _pending_confirmation_ts
    _pending_confirmation = action
    _pending_confirmation_ts = time.time()
    logger.info(f"Pending confirmation set: {action.get('action', '?')}")


def get_pending_confirmation() -> Optional[dict]:
    """Get the pending confirmation action, or None if expired/missing."""
    global _pending_confirmation, _pending_confirmation_ts
    if _pending_confirmation is None:
        return None
    if (time.time() - _pending_confirmation_ts) > _PENDING_CONFIRMATION_TTL:
        _pending_confirmation = None
        _pending_confirmation_ts = 0.0
        return None
    return _pending_confirmation


def clear_pending_confirmation() -> None:
    """Clear the pending confirmation (after execution or denial)."""
    global _pending_confirmation, _pending_confirmation_ts
    _pending_confirmation = None
    _pending_confirmation_ts = 0.0


# ── Simple timestamp-based cache (bounded to prevent memory leaks) ──
_cache: dict[str, dict] = {}


def cache_get(key: str, ttl: float) -> dict | None:
    """Return cached value if within TTL, else None."""
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["value"]
    return None


def cache_set(key: str, value: dict) -> None:
    """Set a cache entry, evicting expired/oldest if cache is full."""
    if len(_cache) >= CACHE_MAX_ENTRIES:
        now = time.time()
        expired = [k for k, v in _cache.items() if (now - v["ts"]) > 60]
        for k in expired:
            del _cache[k]
        # If still too large, clear oldest half
        if len(_cache) >= CACHE_MAX_ENTRIES:
            sorted_keys = sorted(_cache, key=lambda k: _cache[k]["ts"])
            for k in sorted_keys[:len(sorted_keys) // 2]:
                del _cache[k]
    _cache[key] = {"value": value, "ts": time.time()}


# ── Startup time tracking ──
startup_time: float = 0.0


# ── Helpers ──

async def parse_json_body(request) -> dict:
    """Parse JSON body with proper error handling."""
    from fastapi import HTTPException
    try:
        return await request.json()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {e}")


def _trim_history_unlocked() -> None:
    """Trim conversation_history to MAX_HISTORY entries (no lock, call under _history_lock)."""
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]


async def trim_history() -> None:
    """Trim conversation_history to MAX_HISTORY entries (async-safe with lock)."""
    async with _history_lock:
        _trim_history_unlocked()
