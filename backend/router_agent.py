"""Lexa AI — Agent Router (Phase 46: Multi-Step Agent)
SSE-Endpoint fuer mehrstufige Agent-Tasks mit Live-Progress.

Ersetzt Phase 41 agent.py — nutzt jetzt agent_loop.py das chat() direkt aufruft.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import MAX_CHAT_MESSAGE_LENGTH, AGENT_MAX_STEPS, VERSION
from backend.shared import conversation_history, _history_lock
from backend.action_parser import update_history
from backend.security import sanitize_input, check_rate_limit, audit_log
from backend.i18n import t

logger = logging.getLogger("lexa.agent_router")

router = APIRouter(prefix="/agent", tags=["agent"])


# ══════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════

class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)


# ══════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════

@router.post("/run")
async def agent_run(req: AgentRequest):
    """Execute a multi-step agent task with live SSE progress.

    The agent plans and executes multiple tool calls autonomously,
    streaming each step back to the frontend in real-time.

    SSE Events:
    - {"type": "thinking", "message": "..."} — Agent reasoning/plan
    - {"type": "step_start", "step": {...}} — Tool execution starting
    - {"type": "step_done", "step": {...}} — Tool execution completed
    - {"type": "step_blocked", "step": {...}} — Tool needs user confirmation (skipped)
    - {"type": "error", "message": "..."} — Error
    - {"type": "done", "run": {...}} — Agent finished with summary
    """
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    sanitized = sanitize_input(req.message)
    audit_log("agent", "received", f"MSG={sanitized[:100]}")

    # Snapshot conversation history under lock
    async with _history_lock:
        history_snapshot = list(conversation_history)

    async def event_stream():
        from backend.agent_loop import run_agent

        full_summary = ""
        try:
            async for event in run_agent(sanitized, history_snapshot):
                # Track summary for conversation history
                if event.get("type") == "done":
                    run_data = event.get("run", {})
                    full_summary = run_data.get("summary", "")
                elif event.get("type") == "thinking" and not full_summary:
                    full_summary = event.get("message", "")

                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

        except asyncio.CancelledError:
            logger.info("Agent stream cancelled by client")
        except Exception as e:
            logger.exception("Agent stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Save agent interaction to conversation history
            if full_summary:
                try:
                    async with _history_lock:
                        update_history(
                            conversation_history,
                            sanitized,
                            f"[Agent] {full_summary[:2000]}",
                        )
                except Exception as e:
                    logger.error(f"Failed to save agent history: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat")
async def agent_chat_endpoint(req: AgentRequest):
    """Non-streaming agent execution. Collects all steps, returns final result.

    Returns JSON with the agent run summary and all steps.
    Use /agent/run for streaming progress instead.
    """
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    sanitized = sanitize_input(req.message)
    audit_log("agent_chat", "received", f"MSG={sanitized[:100]}")

    async with _history_lock:
        history_snapshot = list(conversation_history)

    from backend.agent_loop import run_agent

    steps = []
    summary = ""
    run_data = {}

    try:
        async for event in run_agent(sanitized, history_snapshot):
            etype = event.get("type", "")
            if etype == "step_done":
                steps.append(event.get("step", {}))
            elif etype == "step_blocked":
                steps.append(event.get("step", {}))
            elif etype == "thinking":
                summary = event.get("message", "")
            elif etype == "done":
                run_data = event.get("run", {})
                summary = run_data.get("summary", summary)
            elif etype == "error":
                summary = event.get("message", "Fehler")
    except Exception as e:
        logger.exception("agent_chat() failed")
        raise HTTPException(status_code=502, detail="Agent-Verarbeitung fehlgeschlagen.")

    # Save to history
    if summary:
        async with _history_lock:
            update_history(
                conversation_history,
                sanitized,
                f"[Agent] {summary[:2000]}",
            )

    return {
        "status": "ok",
        "reply": summary,
        "steps": steps,
        "run": run_data,
    }


@router.get("/status")
async def agent_status():
    """Return agent capabilities and configuration."""
    return {
        "enabled": True,
        "max_steps": AGENT_MAX_STEPS,
        "version": VERSION,
    }
