"""Lexa AI — FastAPI Backend
Hauptserver auf localhost:8000
"""

import json
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.ai_engine import chat, get_ai_status
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("lexa.server")

app = FastAPI(
    title="Lexa AI",
    description="Lokaler KI-Assistent — nur localhost",
    version="0.5.0",
)

# CORS: Nur localhost erlauben
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "file://"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lexa-ai", "version": "0.5.0"}


@app.get("/ai/status")
async def ai_status():
    """Get AI provider status (Groq + Ollama)."""
    return get_ai_status()


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


@app.post("/chat/confirm")
async def confirm_action(req: ChatRequest):
    """User bestätigt eine Aktion die Bestätigung brauchte."""
    audit_log("confirm", "user_confirmed", req.message)
    return {"status": "confirmed", "message": "Aktion wird ausgeführt."}


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
