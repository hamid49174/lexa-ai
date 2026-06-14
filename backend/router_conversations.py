"""Lexa AI — Conversations Router
Conversation CRUD endpoints: /conversations/*
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from backend.config import MAX_CONVERSATION_TITLE, MAX_CONVERSATION_MESSAGES
from backend.security import check_rate_limit
from backend.shared import (
    conversation_history,
    _history_lock,
    parse_json_body,
    _trim_history_unlocked,
    set_active_conversation_id,
)
from backend import memory

logger = logging.getLogger("lexa.conversations")

router = APIRouter(tags=["conversations"])


def _normalize_conversation_messages(messages: list) -> list[dict]:
    normalized: list[dict] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise HTTPException(status_code=400, detail=f"messages[{index}] must be an object")
        role = str(message.get("role", "")).strip().lower()
        if role not in {"user", "assistant", "system"}:
            raise HTTPException(status_code=400, detail=f"messages[{index}].role is invalid")
        content = str(message.get("content", "")).strip()
        if not content:
            raise HTTPException(status_code=400, detail=f"messages[{index}].content is required")
        normalized.append({"role": role, "content": content})
    return normalized


@router.get("/conversations")
async def list_conversations():
    return {"status": "ok", "conversations": await asyncio.to_thread(memory.conversation_list)}


@router.post("/conversations")
async def create_conversation(req: Request):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    data = await parse_json_body(req)
    title = str(data.get("title", "Neuer Chat"))[:MAX_CONVERSATION_TITLE]
    conv_id = await asyncio.to_thread(memory.conversation_create, title)
    return {"status": "ok", "id": conv_id, "title": title}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: int):
    conv = await asyncio.to_thread(memory.conversation_get, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if isinstance(conv, dict):
        conv["status"] = "ok"
    return conv


@router.put("/conversations/{conv_id}")
async def update_conversation(conv_id: int, req: Request):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    data = await parse_json_body(req)
    title = data.get("title")
    if title is not None:
        title = str(title)[:MAX_CONVERSATION_TITLE]
    messages = data.get("messages")
    if messages is not None:
        if not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="messages must be a list")
        if len(messages) > MAX_CONVERSATION_MESSAGES:
            raise HTTPException(status_code=400, detail=f"Too many messages (max {MAX_CONVERSATION_MESSAGES})")
        messages = _normalize_conversation_messages(messages)
    is_pinned = data.get("is_pinned")
    if is_pinned is not None:
        is_pinned = bool(is_pinned)
    result = await asyncio.to_thread(
        memory.conversation_update, conv_id, title=title, messages=messages, is_pinned=is_pinned
    )
    return {"status": result}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    result = await asyncio.to_thread(memory.conversation_delete, conv_id)
    return {"status": result}


@router.post("/conversations/{conv_id}/load")
async def load_conversation(conv_id: int):
    """Load a conversation's messages as the active chat history."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    conv = await asyncio.to_thread(memory.conversation_get, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    async with _history_lock:
        conversation_history.clear()
        for msg in conv.get("messages", []):
            conversation_history.append(msg)
        _trim_history_unlocked()
    set_active_conversation_id(conv_id)
    return {"status": "loaded", "message_count": len(conversation_history)}
