"""Lexa AI — Conversations Router
Conversation CRUD endpoints: /conversations/*
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from backend.config import MAX_CONVERSATION_TITLE, MAX_CONVERSATION_MESSAGES
from backend.shared import (
    conversation_history,
    _history_lock,
    parse_json_body,
    _trim_history_unlocked,
)
from backend import memory

logger = logging.getLogger("lexa.conversations")

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations():
    return {"status": "ok", "conversations": await asyncio.to_thread(memory.conversation_list)}


@router.post("/conversations")
async def create_conversation(req: Request):
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
    result = await asyncio.to_thread(memory.conversation_update, conv_id, title=title, messages=messages)
    return {"status": result}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    result = await asyncio.to_thread(memory.conversation_delete, conv_id)
    return {"status": result}


@router.post("/conversations/{conv_id}/load")
async def load_conversation(conv_id: int):
    """Load a conversation's messages as the active chat history."""
    conv = await asyncio.to_thread(memory.conversation_get, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    async with _history_lock:
        conversation_history.clear()
        for msg in conv.get("messages", []):
            conversation_history.append(msg)
        _trim_history_unlocked()
    return {"status": "loaded", "message_count": len(conversation_history)}
