"""Lexa AI — Agent Router (Phase 46: Multi-Step Agent)
SSE-Endpoint fuer mehrstufige Agent-Tasks mit Live-Progress.

Ersetzt Phase 41 agent.py — nutzt jetzt agent_loop.py das chat() direkt aufruft.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent_protocol import redacted_summary, stable_hash
from backend.config import MAX_CHAT_MESSAGE_LENGTH, AGENT_MAX_STEPS, AGENT_STEP_TIMEOUT, VERSION
from backend.shared import (
    conversation_history,
    _history_lock,
    get_pending_confirmation,
    clear_pending_confirmation,
)
from backend.action_parser import update_history
from backend.security import sanitize_input, check_rate_limit, audit_log
from backend.agent_loop import (
    AgentRun,
    AgentStep,
    StepStatus,
    _execute_tool,
    _format_system_info_user_summary,
    _format_tool_result,
    _hermes_forced_first_tool,
)

logger = logging.getLogger("lexa.agent_router")

router = APIRouter(prefix="/agent", tags=["agent"])

_AGENT_CONFIRMATION_WORDS = frozenset({
    "ja", "yes", "ok", "okay", "confirm", "mach es", "mach das", "ausfuehren",
    "machen", "los", "klar", "sicher",
})
_AGENT_CANCEL_WORDS = frozenset({
    "nein", "no", "nee", "nope", "abbrechen", "abbruch", "cancel",
    "stop", "stopp", "verwerfen", "nicht ausfuehren",
})
_AGENT_CONFIRMATION_WORDS = frozenset(_AGENT_CONFIRMATION_WORDS | {
    "bestatige", "bestaetige", "bestatigen", "bestaetigen", "bestatige es", "bestaetige es",
    "ausfuhren", "ausfuehren",
})
_AGENT_CANCEL_WORDS = frozenset(_AGENT_CANCEL_WORDS | {"nicht ausfuhren", "nicht ausfuehren"})
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc)/[^\s\"'<>|]+)"
)


# ══════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════

class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
    worker: str = Field("lexa", max_length=20)


def _normalize_agent_worker_text(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .strip()
    )


def _is_hermes_worker_request(text: str) -> bool:
    normalized = _normalize_agent_worker_text(text)
    return bool(
        re.match(r"^/hermes\s+", normalized)
        or re.match(r"^hermes\b", normalized)
        or re.match(r"^(?:lass|lasse|beauftrag|beauftrage|starte|nutze|nimm)\s+hermes\b", normalized)
        or re.match(r"^lexa[\s,]+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes\b", normalized)
    )


def _resolve_agent_worker(worker: str | None, message: str) -> str:
    if (worker or "").strip().lower() == "hermes":
        return "hermes"
    if _is_hermes_worker_request(message):
        return "hermes"
    return "lexa"


def _agent_request_audit_details(worker: str, message: str) -> str:
    text = str(message or "")
    return f"WORKER={worker} messageChars={len(text)} messageHash={stable_hash(text)[:12]}"


def _client_safe_agent_error(value: object, *, max_chars: int = 220) -> str:
    text = redacted_summary(str(value or ""), max_chars=max_chars)
    text = _LOCAL_PATH_RE.sub("[local-path-redacted]", text)
    return text or "Details wurden lokal protokolliert."


def _is_hermes_system_status_request(worker: str, message: str) -> bool:
    return worker == "hermes" and _hermes_forced_first_tool(worker, message) == ("system_info", {})


def _is_short_pending_confirmation_message(text: str) -> bool:
    normalized = _normalize_pending_confirmation_text(text)
    return len(normalized.split()) <= 4 and normalized in _AGENT_CONFIRMATION_WORDS


def _is_short_pending_cancel_message(text: str) -> bool:
    normalized = _normalize_pending_confirmation_text(text)
    return len(normalized.split()) <= 4 and normalized in _AGENT_CANCEL_WORDS


def _normalize_pending_confirmation_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("ß", "ss").replace("ÃŸ", "ss")
    normalized = re.sub(r"\s+", " ", normalized).strip().rstrip("!.?")
    return normalized.strip()


def _agent_pending_guard_reply(message: str) -> str | None:
    pending = get_pending_confirmation()
    if not pending:
        return None
    action_name = str(pending.get("action") or "Aktion")
    if _is_short_pending_cancel_message(message):
        clear_pending_confirmation()
        return f"Freigabe fuer {action_name} verworfen. Ich habe nichts ausgefuehrt."
    if _is_short_pending_confirmation_message(message):
        return (
            f"Freigabe offen fuer {action_name}. Bitte bestaetige im normalen Chat kurz mit 'Ja' "
            "ohne Hermes-/Agent-Prefix, oder schreibe 'Abbrechen'."
        )
    return (
        f"Freigabe offen fuer {action_name}. Ich habe nichts ausgefuehrt. "
        "Antworte kurz mit 'Ja' zum Ausfuehren oder 'Abbrechen' zum Verwerfen."
    )


async def _hermes_system_status_events(user_message: str):
    run = AgentRun(user_message=user_message, worker="hermes")
    step = AgentStep(
        index=0,
        action="system_info",
        params={},
        status=StepStatus.RUNNING,
        started_at=time.time(),
    )
    run.steps.append(step)
    yield {"type": "step_start", "step": step.to_dict()}

    try:
        exec_result = await asyncio.wait_for(
            _execute_tool("system_info", {}, plan_length=1),
            timeout=AGENT_STEP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        exec_result = {"success": False, "error": f"Timeout nach {AGENT_STEP_TIMEOUT}s"}
        step.duration_ms = AGENT_STEP_TIMEOUT * 1000
    else:
        step.duration_ms = (time.time() - step.started_at) * 1000

    if exec_result.get("success"):
        step.status = StepStatus.SUCCESS
        step.result = _format_tool_result("system_info", exec_result)
        run.status = "completed"
        run.summary = _format_system_info_user_summary(exec_result.get("data")) or step.result
    else:
        step.status = StepStatus.FAILED
        step.error = exec_result.get("error", "Systemstatus konnte nicht gelesen werden")
        step.result = _format_tool_result("system_info", exec_result)
        run.status = "failed"
        run.summary = f"Hermes konnte den Systemstatus nicht abrufen: {step.error}"

    yield {"type": "step_done", "step": step.to_dict()}
    run.total_duration_ms = (time.time() - run.started_at) * 1000
    yield {"type": "done", "run": run.to_dict()}


async def _collect_agent_events(event_iter):
    events = []
    async for event in event_iter:
        events.append(event)
    return events


def _agent_events_summary(events: list[dict]) -> tuple[str, list[dict], dict]:
    steps = []
    summary = ""
    run_data = {}
    for event in events:
        etype = event.get("type", "")
        if etype in {"step_done", "step_blocked"}:
            steps.append(event.get("step", {}))
        elif etype == "thinking" and event.get("message"):
            summary = event.get("message", summary)
        elif etype == "done":
            run_data = event.get("run", {}) or {}
            summary = run_data.get("summary", summary)
        elif etype == "error":
            summary = _client_safe_agent_error(event.get("message", "Fehler"))
    return summary, steps, run_data


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
    worker = _resolve_agent_worker(req.worker, sanitized)
    audit_log("agent", "received", _agent_request_audit_details(worker, sanitized))
    pending_guard_reply = _agent_pending_guard_reply(sanitized)
    if pending_guard_reply:
        run = AgentRun(user_message=sanitized, worker=worker)
        run.status = "completed"
        run.summary = pending_guard_reply

        async def pending_guard_stream():
            yield f"data: {json.dumps({'type': 'thinking', 'message': pending_guard_reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'run': run.to_dict()}, ensure_ascii=False, default=str)}\n\n"

        async with _history_lock:
            update_history(
                conversation_history,
                sanitized,
                f"[{'Hermes' if worker == 'hermes' else 'Agent'}] {pending_guard_reply[:2000]}",
            )
        return StreamingResponse(
            pending_guard_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Snapshot conversation history under lock
    async with _history_lock:
        history_snapshot = list(conversation_history)

    async def event_stream():
        from backend.agent_loop import run_agent

        full_summary = ""
        try:
            source = (
                _hermes_system_status_events(sanitized)
                if _is_hermes_system_status_request(worker, sanitized)
                else run_agent(sanitized, history_snapshot, worker=worker)
            )
            async for event in source:
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
            yield f"data: {json.dumps({'type': 'error', 'message': _client_safe_agent_error(e)})}\n\n"
        finally:
            # Save agent interaction to conversation history
            if full_summary:
                try:
                    async with _history_lock:
                        update_history(
                            conversation_history,
                            sanitized,
                            f"[{'Hermes' if worker == 'hermes' else 'Agent'}] {full_summary[:2000]}",
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
    worker = _resolve_agent_worker(req.worker, sanitized)
    audit_log("agent_chat", "received", _agent_request_audit_details(worker, sanitized))
    pending_guard_reply = _agent_pending_guard_reply(sanitized)
    if pending_guard_reply:
        async with _history_lock:
            update_history(
                conversation_history,
                sanitized,
                f"[{'Hermes' if worker == 'hermes' else 'Agent'}] {pending_guard_reply[:2000]}",
            )
        return {
            "status": "ok",
            "reply": pending_guard_reply,
            "steps": [],
            "run": {"status": "completed", "summary": pending_guard_reply, "worker": worker},
            "version": VERSION,
        }

    async with _history_lock:
        history_snapshot = list(conversation_history)

    from backend.agent_loop import run_agent

    try:
        source = (
            _hermes_system_status_events(sanitized)
            if _is_hermes_system_status_request(worker, sanitized)
            else run_agent(sanitized, history_snapshot, worker=worker)
        )
        summary, steps, run_data = _agent_events_summary(await _collect_agent_events(source))
    except Exception:
        logger.exception("agent_chat() failed")
        raise HTTPException(status_code=502, detail="Agent-Verarbeitung fehlgeschlagen.")

    # Save to history
    if summary:
        async with _history_lock:
            update_history(
                conversation_history,
                sanitized,
                f"[{'Hermes' if worker == 'hermes' else 'Agent'}] {summary[:2000]}",
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
        "workers": ["lexa", "hermes"],
    }
