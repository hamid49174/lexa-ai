"""Lexa AI — FastAPI Backend
Hauptserver auf localhost:8000
"""

import asyncio
import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.ai_engine import chat, chat_stream, get_ai_status, generate_title, set_groq_model, get_groq_model
from backend.router_companion import router as companion_router
from backend.router_voice import router as voice_router
from backend import memory
from backend.security import (
    sanitize_input,
    check_rate_limit,
    is_command_allowed,
    audit_log,
    validate_command_output,
)
from backend.scheduler import start_scheduler, get_scheduler_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("lexa.server")

app = FastAPI(
    title="Lexa AI",
    description="Lokaler KI-Assistent — nur localhost",
    version="0.13.0",
)

# CORS: Nur localhost erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "file://"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Router einbinden
app.include_router(companion_router)
app.include_router(voice_router)

# Conversation history (in-memory, pro Session)
conversation_history: list[dict] = []


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None
    requires_confirmation: bool = False


@app.on_event("startup")
async def startup_event():
    """Start background services."""
    try:
        from companion.engine import companion
        start_scheduler(companion.execute if hasattr(companion, "execute") else None)
        logger.info("Routine-Scheduler gestartet")
    except Exception as e:
        logger.warning(f"Scheduler-Start fehlgeschlagen: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lexa-ai", "version": "0.13.0"}


@app.get("/ai/status")
async def ai_status():
    """Get AI provider status (Groq + Ollama)."""
    return get_ai_status()


@app.get("/scheduler/status")
async def scheduler_status():
    """Get routine scheduler status."""
    return get_scheduler_status()


@app.get("/memory/stats")
async def memory_stats():
    """Get memory database statistics."""
    return memory.get_memory_stats()


@app.get("/memory/notes")
async def list_notes():
    return {"notes": memory.note_list()}


@app.get("/memory/profile")
async def get_profile():
    return {"profile": memory.get_user_profile()}


@app.post("/memory/profile")
async def set_profile(req: Request):
    data = await req.json()
    result = memory.set_profile(data["key"], data["value"])
    return {"status": result}


@app.get("/memory/routines")
async def list_routines():
    return {"routines": memory.routine_list()}


# ── CONVERSATIONS ────────────────────────────────

@app.get("/conversations")
async def list_conversations():
    return {"conversations": memory.conversation_list()}


@app.post("/conversations")
async def create_conversation(req: Request):
    data = await req.json()
    title = data.get("title", "Neuer Chat")
    conv_id = memory.conversation_create(title)
    return {"id": conv_id, "title": title}


@app.get("/conversations/{conv_id}")
async def get_conversation(conv_id: int):
    conv = memory.conversation_get(conv_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    return conv


@app.put("/conversations/{conv_id}")
async def update_conversation(conv_id: int, req: Request):
    data = await req.json()
    title = data.get("title")
    messages = data.get("messages")
    result = memory.conversation_update(conv_id, title=title, messages=messages)
    return {"status": result}


@app.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: int):
    result = memory.conversation_delete(conv_id)
    return {"status": result}


@app.post("/conversations/{conv_id}/load")
async def load_conversation(conv_id: int):
    """Load a conversation's messages as the active chat history."""
    conv = memory.conversation_get(conv_id)
    if not conv:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    conversation_history.clear()
    for msg in conv.get("messages", []):
        conversation_history.append(msg)
    # Keep at most 40 entries
    if len(conversation_history) > 40:
        conversation_history[:] = conversation_history[-40:]
    return {"status": "loaded", "message_count": len(conversation_history)}


# ── SEARCH & EXPORT ─────────────────────────────

@app.get("/search")
async def global_search(q: str = ""):
    """Search across conversations, notes, and memories."""
    if not q.strip():
        return {"conversations": [], "notes": [], "memories": []}
    return memory.global_search(q.strip())


@app.get("/conversations/{conv_id}/export")
async def export_conversation(conv_id: int, fmt: str = "markdown"):
    """Export a conversation as markdown or text."""
    text = memory.conversation_export(conv_id, fmt)
    if text is None:
        return JSONResponse(status_code=404, content={"detail": "Conversation not found"})
    return {"text": text, "format": fmt}


# ── AI TITLE & MODEL SELECTION ──────────────────

@app.post("/ai/title")
async def ai_generate_title(req: ChatRequest):
    """Generate an AI-powered conversation title."""
    title = generate_title(req.message)
    return {"title": title}


@app.get("/ai/models")
async def ai_models():
    """Get available AI models and current selection."""
    return get_groq_model()


@app.post("/ai/models")
async def set_ai_model(req: Request):
    """Set the active Groq model."""
    data = await req.json()
    model_id = data.get("model", "")
    result = set_groq_model(model_id)
    return {"status": result, "current": get_groq_model()}


# ── FILE UPLOAD + ANALYSIS ───────────────────────

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".html",
    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".log", ".sh", ".bat", ".ps1", ".sql", ".env", ".gitignore",
    ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php", ".swift",
}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
MAX_TEXT_CHARS = 8000  # Limit text sent to AI


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

    # Text files
    if ext in TEXT_EXTENSIONS or mime.startswith("text/"):
        result["type"] = "text"
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            if len(text) > MAX_TEXT_CHARS:
                result["content"] = text[:MAX_TEXT_CHARS]
                result["preview"] = f"[Erste {MAX_TEXT_CHARS} Zeichen von {len(text)} gesamt]"
            else:
                result["content"] = text
            result["line_count"] = text.count("\n") + 1
        except Exception as e:
            result["content"] = None
            result["preview"] = f"Fehler beim Lesen: {e}"

    # Images
    elif mime and mime.startswith("image/"):
        result["type"] = "image"
        result["preview"] = f"Bild: {original_name} ({size_kb} KB)"

    # PDF
    elif ext == ".pdf":
        result["type"] = "pdf"
        result["preview"] = f"PDF: {original_name} ({size_kb} KB) — PDF-Textextraktion nicht verfügbar"

    # Other
    else:
        result["type"] = "binary"
        result["preview"] = f"Datei: {original_name} ({size_kb} KB, {mime})"

    return result


@app.post("/chat/file")
async def chat_file_endpoint(
    file: UploadFile = File(...),
    message: str = Form(""),
):
    """Upload a file and analyze it with AI context."""
    if not check_rate_limit():
        return JSONResponse(status_code=429, content={"detail": "Zu viele Anfragen."})

    # Size check
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Datei zu groß (max {MAX_FILE_SIZE // 1024 // 1024} MB)."},
        )

    # Save to temp file
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        file_info = extract_file_content(tmp_path, file.filename or "upload")

        # Build AI prompt with file context
        user_msg = sanitize_input(message) if message else "Analysiere diese Datei."

        if file_info["content"]:
            file_context = (
                f"[Datei: {file_info['filename']} | {file_info['size_kb']} KB | "
                f"{file_info['line_count']} Zeilen | {file_info['extension']}]\n"
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

        # Get AI response
        ai_response = chat(full_prompt, conversation_history)

        # Update history
        conversation_history.append({"role": "user", "content": full_prompt[:2000]})
        conversation_history.append({"role": "assistant", "content": ai_response})
        if len(conversation_history) > 40:
            conversation_history[:] = conversation_history[-40:]

        # Parse for actions
        action = None
        requires_confirmation = False
        reply = ai_response
        try:
            parsed = json.loads(ai_response)
            if isinstance(parsed, dict) and "action" in parsed:
                action_name = parsed["action"]
                validate_command_output(action_name)
                permission = is_command_allowed(action_name)
                if permission == "blocked":
                    action = None
                    reply = f"Befehl blockiert: {action_name}"
                elif permission == "confirmation_required":
                    requires_confirmation = True
                    action = parsed
                    reply = parsed.get("message", ai_response)
                else:
                    action = parsed
                    reply = parsed.get("message", ai_response)
        except (json.JSONDecodeError, TypeError):
            pass

        return {
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


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # Rate Limiting
    if not check_rate_limit():
        audit_log("chat", "rate_limited")
        return JSONResponse(
            status_code=429,
            content={"detail": "Zu viele Anfragen. Bitte kurz warten."},
        )

    # Sanitize Input
    sanitized = sanitize_input(req.message)
    audit_log("chat", "received", f"MSG={sanitized[:100]}")

    # Send to AI
    ai_response = chat(sanitized, conversation_history)

    # Update conversation history (keep last 20 messages)
    conversation_history.append({"role": "user", "content": sanitized})
    conversation_history.append({"role": "assistant", "content": ai_response})
    if len(conversation_history) > 40:
        conversation_history[:] = conversation_history[-40:]

    # Parse AI response for actions
    action = None
    requires_confirmation = False
    reply = ai_response

    try:
        parsed = json.loads(ai_response)
        if isinstance(parsed, dict) and "action" in parsed:
            action_name = parsed["action"]
            validate_command_output(action_name)
            permission = is_command_allowed(action_name)

            if permission == "blocked":
                audit_log(action_name, "blocked")
                reply = f"Dieser Befehl ist aus Sicherheitsgründen blockiert: {action_name}"
                action = None
            elif permission == "confirmation_required":
                requires_confirmation = True
                action = parsed
                reply = parsed.get("message", f"Soll ich '{action_name}' ausführen?")
                audit_log(action_name, "awaiting_confirmation")
            elif permission in ("allowed", "unknown"):
                action = parsed
                reply = parsed.get("message", ai_response)
                audit_log(action_name, "allowed")
            else:
                action = parsed
                reply = parsed.get("message", ai_response)
    except (json.JSONDecodeError, TypeError):
        # Normal text response, no action
        pass

    audit_log("chat", "responded", f"ACTION={'yes' if action else 'no'}")

    return ChatResponse(
        reply=reply,
        action=action,
        requires_confirmation=requires_confirmation,
    )


@app.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Stream AI response via Server-Sent Events."""
    if not check_rate_limit():
        return JSONResponse(
            status_code=429,
            content={"detail": "Zu viele Anfragen. Bitte kurz warten."},
        )

    sanitized = sanitize_input(req.message)
    audit_log("chat_stream", "received", f"MSG={sanitized[:100]}")

    async def event_stream():
        loop = asyncio.get_event_loop()
        gen = chat_stream(sanitized, conversation_history)
        full_text = ""
        _sentinel = object()

        while True:
            chunk = await loop.run_in_executor(
                None, lambda g=gen, s=_sentinel: next(g, s)
            )
            if chunk is _sentinel:
                break
            full_text += chunk
            yield f"data: {json.dumps({'c': chunk})}\n\n"

        # Update conversation history
        conversation_history.append({"role": "user", "content": sanitized})
        conversation_history.append({"role": "assistant", "content": full_text})
        if len(conversation_history) > 40:
            conversation_history[:] = conversation_history[-40:]

        # Parse for actions
        action = None
        requires_confirmation = False
        try:
            parsed = json.loads(full_text)
            if isinstance(parsed, dict) and "action" in parsed:
                action_name = parsed["action"]
                validate_command_output(action_name)
                permission = is_command_allowed(action_name)
                if permission == "blocked":
                    audit_log(action_name, "blocked")
                    action = None
                elif permission == "confirmation_required":
                    requires_confirmation = True
                    action = parsed
                    audit_log(action_name, "awaiting_confirmation")
                elif permission in ("allowed", "unknown"):
                    action = parsed
                    audit_log(action_name, "allowed")
                else:
                    action = parsed
        except (json.JSONDecodeError, TypeError):
            pass

        audit_log("chat_stream", "done", f"LEN={len(full_text)}")
        yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/confirm")
async def confirm_action(req: ChatRequest):
    """User bestätigt eine Aktion die Bestätigung brauchte."""
    audit_log("confirm", "user_confirmed", req.message)
    return {"status": "confirmed", "message": "Aktion wird ausgeführt."}


# ── CLIPBOARD HISTORY ────────────────────────────
clipboard_history: list[dict] = []
MAX_CLIPBOARD_ENTRIES = 50

@app.get("/clipboard/history")
async def get_clipboard_history():
    return {"entries": clipboard_history}

@app.post("/clipboard/add")
async def add_clipboard_entry(req: Request):
    data = await req.json()
    text = data.get("text", "").strip()
    if not text:
        return {"status": "empty"}
    # Avoid duplicates (move to top)
    clipboard_history[:] = [e for e in clipboard_history if e["text"] != text]
    clipboard_history.insert(0, {
        "text": text,
        "timestamp": __import__("datetime").datetime.now().strftime("%H:%M:%S"),
    })
    if len(clipboard_history) > MAX_CLIPBOARD_ENTRIES:
        clipboard_history[:] = clipboard_history[:MAX_CLIPBOARD_ENTRIES]
    return {"status": "added", "count": len(clipboard_history)}

@app.delete("/clipboard/history")
async def clear_clipboard_history():
    clipboard_history.clear()
    return {"status": "cleared"}


# ── QUICK TEXT SNIPPETS ──────────────────────────
@app.get("/snippets")
async def list_snippets():
    return {"snippets": memory.snippet_list()}

@app.post("/snippets")
async def create_snippet(req: Request):
    data = await req.json()
    name = data.get("name", "").strip()
    text = data.get("text", "").strip()
    if not name or not text:
        return JSONResponse(status_code=400, content={"detail": "Name und Text erforderlich"})
    result = memory.snippet_create(name, text)
    return {"status": result}

@app.delete("/snippets/{name}")
async def delete_snippet(name: str):
    result = memory.snippet_delete(name)
    return {"status": result}


@app.get("/history")
async def get_history():
    return {"history": conversation_history}


@app.delete("/history")
async def clear_history():
    conversation_history.clear()
    return {"status": "cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
