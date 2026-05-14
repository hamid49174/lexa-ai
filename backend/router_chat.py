"""Lexa AI — Chat Router
Chat endpoints: /chat, /chat/file, /chat/stream, /chat/confirm
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import (
    MAX_HISTORY,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_FILE_SIZE,
    MAX_FILE_SIZE_MB,
    MAX_TEXT_CHARS,
    TEXT_EXTENSIONS,
    BLOCKED_EXTENSIONS,
)
from backend.shared import (
    conversation_history,
    _history_lock,
    set_pending_confirmation,
    get_pending_confirmation,
    clear_pending_confirmation,
)
from backend.ai_engine import chat, chat_stream
from backend.action_parser import process_ai_response, process_chat_result, update_history
from backend.i18n import t
from backend.intent_engine import try_local_intent
from backend.security import (
    sanitize_input,
    check_rate_limit,
    get_rate_limit_info,
    audit_log,
)

# Words that indicate the user is confirming a pending action
_CONFIRMATION_WORDS = frozenset({
    "ja", "yes", "bestätige", "bestätigen", "bestätige es", "confirm",
    "mach es", "mach das", "tu es", "ok", "okay", "klar", "sicher",
    "go", "do it", "los", "ausführen", "machen", "jap", "jep", "yep",
    "jawohl", "genau", "stimmt", "richtig", "bitte", "gerne",
})


def _is_confirmation_message(text: str) -> bool:
    """Check if the user message is a short confirmation of a pending action."""
    normalized = text.strip().lower().rstrip("!.?")
    # Only treat as confirmation if it's short (1-4 words) and matches patterns
    if len(normalized.split()) > 4:
        return False
    return normalized in _CONFIRMATION_WORDS

logger = logging.getLogger("lexa.chat")

router = APIRouter(tags=["chat"])


# ══════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None
    requires_confirmation: bool = False


# ══════════════════════════════════════════════════
#  FILE UPLOAD HELPERS
# ══════════════════════════════════════════════════

def extract_file_content(filepath: Path, original_name: str) -> dict:
    """Extract content and metadata from uploaded file."""
    stat = filepath.stat()
    size_kb = round(stat.st_size / 1024, 1)
    ext = Path(original_name).suffix.lower()
    mime = mimetypes.guess_type(original_name)[0] or "application/octet-stream"

    result = {
        "filename": original_name,
        "size_kb": size_kb,
        "extension": ext,
        "mime": mime,
        "content": None,
        "type": "unknown",
        "preview": None,
    }

    if ext in TEXT_EXTENSIONS or mime.startswith("text/"):
        result["type"] = "text"
        try:
            raw_bytes = filepath.read_bytes()
            text = raw_bytes.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                logger.warning(f"File '{original_name}' contained non-UTF-8 bytes (replaced with replacement char)")
            if len(text) > MAX_TEXT_CHARS:
                result["content"] = text[:MAX_TEXT_CHARS]
                result["preview"] = f"[Erste {MAX_TEXT_CHARS} Zeichen von {len(text)} gesamt]"
            else:
                result["content"] = text
            result["line_count"] = text.count("\n") + 1
        except Exception as e:
            result["content"] = None
            result["preview"] = t("error.readFile", error=str(e))
    elif mime and mime.startswith("image/"):
        result["type"] = "image"
        result["preview"] = f"Bild: {original_name} ({size_kb} KB)"
    elif ext == ".pdf":
        result["type"] = "pdf"
        result["preview"] = f"PDF: {original_name} ({size_kb} KB)"
    else:
        result["type"] = "binary"
        result["preview"] = f"Datei: {original_name} ({size_kb} KB, {mime})"

    return result


# ══════════════════════════════════════════════════
#  CHAT ENDPOINTS
# ══════════════════════════════════════════════════

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Standard chat endpoint (non-streaming)."""
    if not check_rate_limit("chat"):
        audit_log("chat", "rate_limited")
        rl = get_rate_limit_info("chat")
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anfragen. Bitte kurz warten.",
            headers={
                "X-RateLimit-Limit": str(rl["limit"]),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            },
        )

    sanitized = sanitize_input(req.message)
    audit_log("chat", "received", f"MSG={sanitized[:100]}")

    # Fast path: check if this is a confirmation of a pending action
    pending = get_pending_confirmation()
    if pending and _is_confirmation_message(sanitized):
        action_name = pending.get("action", "")
        logger.info(f"User confirmed pending action: {action_name}")
        audit_log("chat", "auto_confirm", f"ACTION={action_name}")
        clear_pending_confirmation()
        reply = f"Alles klar, Chef! Führe {action_name} aus."
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)
        return ChatResponse(reply=reply, action=pending, requires_confirmation=False)

    # Fast path: try local intent recognition first (avoids AI API call)
    local_result = try_local_intent(sanitized)
    if local_result is not None:
        audit_log("chat", "local_intent", f"ACTION={local_result.get('action')}")
        reply_msg = local_result["message"]
        action = None
        requires_confirmation = False

        if local_result["action"] is not None:
            synthetic = json.dumps({
                "action": local_result["action"],
                "params": local_result["params"],
                "message": reply_msg,
            })
            reply_msg, action, requires_confirmation = process_ai_response(
                synthetic, source="chat_local"
            )

        # Track pending confirmation
        if requires_confirmation and action:
            set_pending_confirmation(action)
        elif action and not requires_confirmation:
            clear_pending_confirmation()
            # Execute server-side — user sees real result, not placeholder
            try:
                from backend.action_executor import execute_action
                exec_result = await asyncio.to_thread(
                    execute_action, action, source="chat_local"
                )
                if exec_result.get("success"):
                    data = exec_result.get("data")
                    if data and isinstance(data, str):
                        reply_msg = data
                    elif data and isinstance(data, dict):
                        reply_msg = (
                            data.get("summary")
                            or data.get("message")
                            or data.get("error")
                            or ". ".join(
                                f"{k}: {v}" for k, v in data.items()
                                if v and k not in ("icon", "icon_code", "will_rain", "success")
                            )
                            or reply_msg
                        )
                    action = None  # Already executed
                else:
                    reply_msg = exec_result.get("error", reply_msg)
                    action = None
            except Exception as e:
                logger.error(f"[Intent:Exec] Failed: {e}", exc_info=True)

        async with _history_lock:
            update_history(conversation_history, sanitized, reply_msg, MAX_HISTORY)
        logger.info(f"Local intent resolved: {local_result.get('action', 'direct_reply')}")
        return ChatResponse(reply=reply_msg, action=action, requires_confirmation=requires_confirmation)

    # AI call in thread pool (blocking requests library)
    try:
        async with _history_lock:
            history_snapshot = list(conversation_history)
        ai_result = await asyncio.to_thread(chat, sanitized, history_snapshot)
    except ConnectionError as e:
        logger.error(f"AI connection error: {e}")
        raise HTTPException(status_code=503, detail="AI service unavailable. Please try again later.")
    except Exception as e:
        logger.exception("AI chat() call failed")
        raise HTTPException(status_code=502, detail="KI-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.")

    # Phase 40: process_chat_result handles both tool calls and text
    reply, action, requires_confirmation = process_chat_result(ai_result, source="chat")

    # Track pending confirmation
    if requires_confirmation and action:
        set_pending_confirmation(action)
    elif action:
        clear_pending_confirmation()

    async with _history_lock:
        update_history(conversation_history, sanitized, reply, MAX_HISTORY)

    return ChatResponse(reply=reply, action=action, requires_confirmation=requires_confirmation)


@router.post("/chat/file")
async def chat_file_endpoint(
    file: UploadFile = File(...),
    message: str = Form(""),
):
    """Upload a file and analyze it with AI context."""
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    # Read file in chunks to prevent OOM on large uploads
    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Datei zu groß (max {MAX_FILE_SIZE_MB} MB).",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    # Validate filename — prevent path traversal and suspicious names
    original_filename = file.filename or "upload"
    safe_filename = Path(original_filename).name
    if not safe_filename or safe_filename != original_filename:
        safe_filename = "upload"

    # Block dangerous extensions
    suffix = Path(safe_filename).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        audit_log("chat_file", "blocked_extension", f"EXT={suffix}")
        raise HTTPException(
            status_code=400,
            detail=f"Dateityp '{suffix}' ist nicht erlaubt.",
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_info = extract_file_content(tmp_path, file.filename or "upload")
        user_msg = sanitize_input(message) if message else "Analysiere diese Datei."

        if file_info["content"]:
            file_context = (
                f"[Datei: {file_info['filename']} | {file_info['size_kb']} KB | "
                f"{file_info.get('line_count', '?')} Zeilen | {file_info['extension']}]\n"
                f"```\n{file_info['content']}\n```"
            )
            full_prompt = f"{user_msg}\n\n{file_context}"
        elif file_info["type"] == "image":
            full_prompt = (
                f"{user_msg}\n\n[Bild hochgeladen: {file_info['filename']} "
                f"({file_info['size_kb']} KB, {file_info['mime']})]"
            )
        else:
            full_prompt = (
                f"{user_msg}\n\n[Datei: {file_info['filename']} "
                f"({file_info['size_kb']} KB, {file_info['mime']})]"
            )

        audit_log("chat_file", "received", f"FILE={file_info['filename']}")

        # AI call in thread pool
        try:
            async with _history_lock:
                history_snapshot = list(conversation_history)
            ai_result = await asyncio.to_thread(chat, full_prompt, history_snapshot)
        except ConnectionError as e:
            logger.error(f"AI connection error (file): {e}")
            raise HTTPException(status_code=503, detail="AI service unavailable. Please try again later.")
        except Exception as e:
            logger.exception("AI chat() call failed (file)")
            raise HTTPException(status_code=502, detail="KI-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.")

        # Phase 40: unified processing for tool calls + text
        reply, action, requires_confirmation = process_chat_result(ai_result, source="chat_file")

        async with _history_lock:
            update_history(conversation_history, full_prompt[:2000], reply, MAX_HISTORY)

        return {
            "status": "ok",
            "reply": reply,
            "action": action,
            "requires_confirmation": requires_confirmation,
            "file_info": {
                "filename": file_info["filename"],
                "size_kb": file_info["size_kb"],
                "type": file_info["type"],
                "extension": file_info["extension"],
                "line_count": file_info.get("line_count"),
                "preview": file_info["preview"],
            },
        }
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Stream AI response via Server-Sent Events."""
    if not check_rate_limit("chat"):
        rl = get_rate_limit_info("chat")
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anfragen. Bitte kurz warten.",
            headers={
                "X-RateLimit-Limit": str(rl["limit"]),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            },
        )

    sanitized = sanitize_input(req.message)
    audit_log("chat_stream", "received", f"MSG={sanitized[:100]}")

    # Fast path: check if this is a confirmation of a pending action
    pending = get_pending_confirmation()
    if pending and _is_confirmation_message(sanitized):
        action_name = pending.get("action", "")
        logger.info(f"User confirmed pending action (stream): {action_name}")
        audit_log("chat_stream", "auto_confirm", f"ACTION={action_name}")
        clear_pending_confirmation()
        reply = f"Alles klar, Chef! Führe {action_name} aus."
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)

        async def confirm_stream():
            yield f"data: {json.dumps({'c': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': pending, 'rc': False})}\n\n"

        return StreamingResponse(
            confirm_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Fast path: local intent -> execute server-side, return result immediately
    local_result = try_local_intent(sanitized)
    if local_result is not None:
        audit_log("chat_stream", "local_intent", f"ACTION={local_result.get('action')}")
        reply_msg = local_result["message"]
        action = None
        requires_confirmation = False

        if local_result["action"] is not None:
            synthetic = json.dumps({
                "action": local_result["action"],
                "params": local_result["params"],
                "message": reply_msg,
            })
            reply_msg, action, requires_confirmation = process_ai_response(
                synthetic, source="chat_stream_local"
            )

        # Track pending confirmation
        if requires_confirmation and action:
            set_pending_confirmation(action)
        elif action and not requires_confirmation:
            clear_pending_confirmation()
            # Execute action SERVER-SIDE and return real result
            # This prevents the "Führe X aus" problem — user sees actual result
            try:
                from backend.action_executor import execute_action
                exec_result = await asyncio.to_thread(
                    execute_action, action, source="chat_stream_local"
                )
                if exec_result.get("success"):
                    data = exec_result.get("data")
                    if data and isinstance(data, str):
                        reply_msg = data
                    elif data and isinstance(data, dict):
                        reply_msg = (
                            data.get("summary")
                            or data.get("message")
                            or data.get("error")
                            or ". ".join(
                                f"{k}: {v}" for k, v in data.items()
                                if v and k not in ("icon", "icon_code", "will_rain", "success")
                            )
                            or reply_msg
                        )
                    # Action already executed — don't send it to frontend
                    action = None
                    logger.info(f"[Intent:Exec] {local_result['action']} → {reply_msg[:80]}")
                else:
                    reply_msg = exec_result.get("error", reply_msg)
                    action = None
            except Exception as e:
                logger.error(f"[Intent:Exec] Failed: {e}", exc_info=True)
                # Fall through with original reply_msg + action for frontend

        async with _history_lock:
            update_history(conversation_history, sanitized, reply_msg, MAX_HISTORY)
        logger.info(f"Local intent resolved (stream): {local_result.get('action', 'direct_reply')}")

        async def local_stream():
            yield f"data: {json.dumps({'c': reply_msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation})}\n\n"

        return StreamingResponse(
            local_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Snapshot history under lock before creating the streaming generator
    async with _history_lock:
        history_snapshot = list(conversation_history)

    async def event_stream():
        loop = asyncio.get_running_loop()
        gen = None
        full_text = ""
        _sentinel = object()
        tool_call_result = None  # Phase 40: accumulates tool call dict

        try:
            try:
                gen = chat_stream(sanitized, history_snapshot)
            except Exception as e:
                logger.exception("chat_stream() generator creation failed")
                yield f"data: {json.dumps({'error': 'KI-Service nicht verfügbar.'})}\n\n"
                return

            while True:
                try:
                    chunk = await loop.run_in_executor(
                        None, lambda g=gen, s=_sentinel: next(g, s)
                    )
                except Exception as e:
                    logger.error(f"Stream chunk error: {e}")
                    yield f"data: {json.dumps({'error': t('error.streamError')})}\n\n"
                    break
                if chunk is _sentinel:
                    break

                # Phase 40: stream yields either str chunks or a tool_call dict
                if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    tool_call_result = chunk
                    break
                elif isinstance(chunk, str):
                    full_text += chunk
                    yield f"data: {json.dumps({'c': chunk})}\n\n"

            # Phase 40: Handle tool call from stream
            if tool_call_result is not None:
                from backend.action_parser import process_tool_call
                reply, action, requires_confirmation = process_tool_call(
                    tool_call_result.get("tool_calls", []),
                    ai_message=full_text,  # any text before the tool call
                    source="chat_stream",
                )
                # Track pending confirmation for follow-up messages
                if requires_confirmation and action:
                    set_pending_confirmation(action)
                elif action:
                    clear_pending_confirmation()
                # Store richer context in history so AI remembers what was proposed
                history_reply = reply
                if action and requires_confirmation:
                    action_name = action.get("action", "")
                    params = action.get("params", {})
                    params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
                    history_reply = f"{reply} [Aktion: {action_name}({params_str}) wartet auf Bestätigung]"
                async with _history_lock:
                    update_history(conversation_history, sanitized, history_reply, MAX_HISTORY)
                audit_log("chat_stream", "tool_call", f"ACTION={action.get('action') if action else 'none'}")
                yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation, 'reply': reply})}\n\n"

            # Standard text response
            elif full_text:
                async with _history_lock:
                    update_history(conversation_history, sanitized, full_text, MAX_HISTORY)
                reply, action, requires_confirmation = process_ai_response(full_text, source="chat_stream")

                # Fallback: detect tool calls described as text (happens when fallback model has no tools)
                # e.g. "weather_current(location='Hamburg')" or "Führe weather_current aus"
                if action is None and full_text:
                    import re as _re
                    _tool_patterns = [
                        _re.compile(r'(\w+)\(.*?\)'),  # function_name(args)
                        _re.compile(r"[Ff]ühre\s+['\"]?(\w+)['\"]?\s+aus"),
                        _re.compile(r"[Rr]ufe\s+['\"]?(\w+)['\"]?\s+auf"),
                    ]
                    for pat in _tool_patterns:
                        m = pat.search(full_text)
                        if not m:
                            continue
                        detected_tool = m.group(1)
                        try:
                            from backend.tool_registry import get_tool_names
                            if detected_tool not in get_tool_names():
                                continue
                            logger.warning(f"[ChatStream] AI described tool '{detected_tool}' as text — building synthetic call")
                            # Extract params heuristically from the user message
                            args = {}
                            try:
                                from backend.tool_registry import get_tool
                                schema = get_tool(detected_tool)
                                if schema and "parameters" in schema.get("function", {}):
                                    props = schema["function"]["parameters"].get("properties", {})
                                    words = sanitized.split()
                                    lower_words = sanitized.lower().split()
                                    if "city" in props:
                                        for i, w in enumerate(lower_words):
                                            if w in ("in", "für", "von") and i + 1 < len(words):
                                                args["city"] = " ".join(words[i + 1:])
                                                break
                                    if "name" in props:
                                        for trigger in ("öffne", "starte", "open", "start"):
                                            if trigger in lower_words:
                                                idx = lower_words.index(trigger)
                                                if idx + 1 < len(words):
                                                    args["name"] = " ".join(words[idx + 1:])
                                                break
                                    if "query" in props or "search" in props:
                                        key = "query" if "query" in props else "search"
                                        for trigger in ("suche", "such", "search", "find"):
                                            if trigger in lower_words:
                                                idx = lower_words.index(trigger)
                                                if idx + 1 < len(words):
                                                    args[key] = " ".join(words[idx + 1:])
                                                break
                            except Exception:
                                pass

                            from backend.action_parser import process_tool_call
                            synthetic_tc = [{"id": "fallback", "name": detected_tool, "arguments": args}]
                            reply, action, requires_confirmation = process_tool_call(
                                synthetic_tc, ai_message=full_text, source="chat_stream_fallback"
                            )
                            logger.info(f"[ChatStream] Fallback tool: {detected_tool}({json.dumps(args)})")
                        except ImportError:
                            pass
                        break

                # Track pending confirmation for follow-up messages
                if requires_confirmation and action:
                    set_pending_confirmation(action)
                elif action:
                    clear_pending_confirmation()

                audit_log("chat_stream", "done", f"LEN={len(full_text)}")
                yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled by client (partial LEN={len(full_text)})")
        except Exception as e:
            logger.exception("Unexpected error in event_stream")
            yield f"data: {json.dumps({'error': t('error.internalStream')})}\n\n"
        finally:
            if gen is not None:
                gen.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/confirm-clear")
async def clear_confirm_endpoint():
    """Clear pending confirmation state (called when user clicks confirm/deny button)."""
    clear_pending_confirmation()
    return {"status": "ok"}


# /chat/confirm removed (Phase 40A) — was dead code.
# Confirmation execution happens via /companion/execute with confirmed=true.
