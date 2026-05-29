"""Lexa AI — Workflow API Router
REST-Endpoints fuer das Workflow-Automation-System.
Alle Endpoints unter /workflows/*.

WICHTIG: Statische Routen (/templates, /event, /status/engine) muessen
VOR dynamischen Routen (/{workflow_id}) definiert werden, damit FastAPI
sie korrekt matcht und nicht als workflow_id interpretiert.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request

from backend.security import check_rate_limit, audit_log
from backend.shared import parse_json_body
from backend.workflows import get_workflow_engine

logger = logging.getLogger("lexa.router_workflows")

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ══════════════════════════════════════════════════
#  COLLECTION ENDPOINTS (keine {workflow_id})
# ══════════════════════════════════════════════════

@router.get("")
async def list_workflows():
    """Alle Workflows auflisten."""
    engine = get_workflow_engine()
    workflows = await asyncio.to_thread(engine.list_workflows)
    return {
        "status": "ok",
        "count": len(workflows),
        "workflows": workflows,
    }


@router.post("")
async def create_workflow(request: Request):
    """Neuen Workflow erstellen."""
    check_rate_limit("execute")
    data = await parse_json_body(request)

    if not data.get("name"):
        raise HTTPException(status_code=400, detail="Name ist erforderlich.")

    engine = get_workflow_engine()
    result = await asyncio.to_thread(engine.create_workflow, data)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    audit_log("workflow", "created", f"NAME={result.get('name', '')} ID={result.get('id', '')}")
    return {"status": "ok", "workflow": result}


# ══════════════════════════════════════════════════
#  STATISCHE ROUTEN (VOR /{workflow_id} !)
# ══════════════════════════════════════════════════

@router.get("/templates")
async def get_templates():
    """Vordefinierte Workflow-Templates zurueckgeben."""
    from backend.workflow_templates import get_all_templates
    templates = get_all_templates()
    return {
        "status": "ok",
        "count": len(templates),
        "templates": templates,
    }


@router.get("/status/engine")
async def workflow_engine_status():
    """Status der Workflow-Engine abfragen."""
    engine = get_workflow_engine()
    status = await asyncio.to_thread(engine.get_status)
    return {"status": "ok", **status}


@router.post("/event")
async def emit_event(request: Request):
    """Event einspeisen — loest registrierte Event-Workflows aus.
    Body: {"event": "system_start", "data": {...}}
    """
    check_rate_limit("execute")
    body = await parse_json_body(request)

    event_name = body.get("event", "")
    if not event_name:
        raise HTTPException(status_code=400, detail="Event-Name ist erforderlich.")

    event_data = body.get("data", {})
    if not isinstance(event_data, dict):
        event_data = {}

    engine = get_workflow_engine()
    results = await engine.emit_event(event_name, event_data)

    audit_log("workflow", "event", f"EVENT={event_name} TRIGGERED={len(results)}")
    return {
        "status": "ok",
        "event": event_name,
        "triggered_workflows": len(results),
        "results": results,
    }


# ══════════════════════════════════════════════════
#  DYNAMISCHE ROUTEN (/{workflow_id})
# ══════════════════════════════════════════════════

@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Workflow-Details abrufen."""
    engine = get_workflow_engine()
    workflow = await asyncio.to_thread(engine.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden.")
    return {"status": "ok", "workflow": workflow}


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, request: Request):
    """Workflow aktualisieren."""
    check_rate_limit("execute")
    data = await parse_json_body(request)

    engine = get_workflow_engine()
    result = await asyncio.to_thread(engine.update_workflow, workflow_id, data)

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    audit_log("workflow", "updated", f"ID={workflow_id}")
    return {"status": "ok", "workflow": result}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Workflow loeschen."""
    check_rate_limit("execute")
    engine = get_workflow_engine()
    result = await asyncio.to_thread(engine.delete_workflow, workflow_id)

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    audit_log("workflow", "deleted", f"ID={workflow_id}")
    return {"status": "ok", "result": result}


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str):
    """Workflow manuell ausfuehren."""
    check_rate_limit("execute")
    engine = get_workflow_engine()

    # Pruefen ob Workflow existiert
    workflow = await asyncio.to_thread(engine.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden.")

    audit_log("workflow", "manual_run", f"ID={workflow_id} NAME={workflow.get('name', '')}")

    # Workflow ausfuehren (kann laenger dauern)
    result = await engine.run_workflow(workflow_id)

    if isinstance(result, dict) and "error" in result and result.get("status") != "error":
        raise HTTPException(status_code=500, detail=result["error"])

    return {"status": "ok", "result": result}


@router.post("/{workflow_id}/enable")
async def enable_workflow(workflow_id: str):
    """Workflow aktivieren."""
    engine = get_workflow_engine()
    result = await asyncio.to_thread(engine.enable_workflow, workflow_id)

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    audit_log("workflow", "enabled", f"ID={workflow_id}")
    return {"status": "ok", "workflow": result}


@router.post("/{workflow_id}/disable")
async def disable_workflow(workflow_id: str):
    """Workflow deaktivieren."""
    engine = get_workflow_engine()
    result = await asyncio.to_thread(engine.disable_workflow, workflow_id)

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    audit_log("workflow", "disabled", f"ID={workflow_id}")
    return {"status": "ok", "workflow": result}


@router.get("/{workflow_id}/logs")
async def get_workflow_logs(workflow_id: str, limit: int = 50):
    """Ausfuehrungs-Logs eines Workflows abrufen."""
    limit = max(1, min(limit, 200))
    engine = get_workflow_engine()

    # Pruefen ob Workflow existiert
    workflow = await asyncio.to_thread(engine.get_workflow, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden.")

    logs = await asyncio.to_thread(engine.get_workflow_logs, workflow_id, limit)
    return {
        "status": "ok",
        "workflow_id": workflow_id,
        "count": len(logs),
        "logs": logs,
    }
