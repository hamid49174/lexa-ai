"""Lexa AI — Orchestrator Router (Phase 48 C).

SSE-Endpoint fuer Multi-Agenten-Laeufe + Run-Historie. Spiegelt das bewaehrte SSE-Muster
aus router_agent.py (StreamingResponse, CancelledError-Handling, geshieldetes Speichern).
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import (
    MAX_CHAT_MESSAGE_LENGTH,
    ORCHESTRATOR_ENABLED,
    ORCHESTRATOR_MAX_CONCURRENCY,
    ORCHESTRATOR_MAX_SUBAGENTS,
)
from backend.security import audit_log, check_rate_limit, sanitize_input
from backend.orchestrator import store
from backend.orchestrator.core import _safe, run_orchestration
from backend.orchestrator.roles import ORCHESTRATOR_ROLES

logger = logging.getLogger("lexa.orchestrator_router")

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


class OrchestratorRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
    mode: str = Field("thorough", max_length=20)


class OrchestratorTriageRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)


@router.get("/status")
async def orchestrator_status():
    """Feature-Status + Caps fuer das Frontend."""
    try:
        from backend.orchestrator.browser_agent import browser_status
        browser = browser_status()
    except Exception:
        browser = {"available": False, "reason": "nicht verfuegbar"}
    return {
        "enabled": ORCHESTRATOR_ENABLED,
        "max_subagents": ORCHESTRATOR_MAX_SUBAGENTS,
        "max_concurrency": ORCHESTRATOR_MAX_CONCURRENCY,
        "modes": ["thorough", "fast"],
        "roles": [{"id": rid, "label": spec.get("label", rid)} for rid, spec in ORCHESTRATOR_ROLES.items()],
        "browser": browser,
    }


@router.post("/triage")
async def orchestrator_triage(req: OrchestratorTriageRequest):
    """Entscheidet per guenstigem LLM-Call, ob eine Aufgabe einen Multi-Agenten-Lauf braucht.
    Liefert {needs_agents, subagents, mode, reason}. Blockiert nie (Fallback: needs_agents=false)."""
    if not ORCHESTRATOR_ENABLED:
        return {"needs_agents": False, "subagents": 1, "mode": "fast", "reason": "deaktiviert", "source": "disabled"}
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")
    task = sanitize_input(req.task)
    from backend.orchestrator.triage import triage_task
    return await triage_task(task)


@router.post("/run")
async def orchestrator_run(req: OrchestratorRequest):
    """Fuehre einen Multi-Agenten-Lauf aus und streame die Events (SSE).

    Events: orchestrator_start | plan | subagent_start | subagent_step | subagent_done |
    verification | synthesis | done | error. Der abgeschlossene Lauf wird persistiert.
    """
    if not ORCHESTRATOR_ENABLED:
        raise HTTPException(status_code=503, detail="Orchestrator ist deaktiviert.")
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    task = sanitize_input(req.task)
    if not task.strip():
        raise HTTPException(status_code=400, detail="Leere Aufgabe.")
    mode = "fast" if str(req.mode).strip().lower() == "fast" else "thorough"
    audit_log("orchestrator", "received", f"mode={mode} len={len(task)}")

    async def event_stream():
        collected: list[dict] = []
        final_run: dict | None = None
        cancelled = False
        try:
            async for event in run_orchestration(task, mode=mode):
                collected.append(event)
                if event.get("type") == "done":
                    final_run = event.get("run")
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except asyncio.CancelledError:
            logger.info("orchestrator stream cancelled by client")
            cancelled = True
        except Exception as exc:
            logger.exception("orchestrator stream error")
            yield f"data: {json.dumps({'type': 'error', 'message': _safe(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if final_run:
                record = dict(final_run)
                record["status"] = "partial" if final_run.get("partial") else "completed"
                record["events"] = collected
                try:
                    await asyncio.shield(asyncio.to_thread(store.save_run, record))
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("orchestrator run persist failed: %s", _safe(exc))
            if cancelled:
                raise asyncio.CancelledError()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs")
async def orchestrator_runs(limit: int = 50):
    """Liste der letzten Laeufe (Kurzfassung)."""
    runs = await asyncio.to_thread(store.list_runs, limit)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def orchestrator_run_detail(run_id: str):
    """Voller Lauf inkl. Events (fuer Replay in der UI)."""
    run = await asyncio.to_thread(store.get_run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Lauf nicht gefunden.")
    return run
