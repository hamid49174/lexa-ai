"""Lexa AI — Companion Router
API Endpoints für PC-Kontrolle (async-safe via to_thread)
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from companion.engine import companion
from backend.security import is_command_allowed, check_rate_limit, audit_log, validate_params
from backend.i18n import t

logger = logging.getLogger("lexa.companion")
router = APIRouter(prefix="/companion", tags=["companion"])


class CommandRequest(BaseModel):
    command: str
    params: dict = {}
    confirmed: bool = False
    dry_run: bool = False


class CommandResponse(BaseModel):
    success: bool
    data: str | dict | list | None = None
    error: str | None = None
    requires_confirmation: bool = False
    dry_run: bool = False


def _validate_result(result) -> dict:
    """Validate and normalize companion.execute() result to expected schema."""
    if not isinstance(result, dict):
        return {"success": False, "error": f"Unerwartetes Ergebnis: {type(result).__name__}"}

    # Ensure required keys exist with defaults
    normalized = {
        "success": bool(result.get("success", False)),
        "data": result.get("data"),
        "error": result.get("error"),
    }

    # Pass through requires_confirmation if present
    if "requires_confirmation" in result:
        normalized["requires_confirmation"] = bool(result["requires_confirmation"])

    return normalized


@router.post("/execute", response_model=CommandResponse)
async def execute_command(req: CommandRequest):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    permission = is_command_allowed(req.command)

    if permission == "blocked":
        audit_log(req.command, "blocked")
        return CommandResponse(success=False, error=t("command.blockedRouter", command=req.command))

    # Unknown commands (not in whitelist at all) require confirmation — deny by default
    if permission == "unknown" and not req.confirmed:
        audit_log(req.command, "unknown_awaiting_confirmation")
        return CommandResponse(
            success=False,
            requires_confirmation=True,
            error=t("command.needsConfirmation", command=req.command),
        )

    if permission == "confirmation_required" and not req.confirmed:
        audit_log(req.command, "awaiting_confirmation")
        return CommandResponse(
            success=False,
            requires_confirmation=True,
            error=t("command.confirmRequired", command=req.command),
        )

    # Validate params for safety
    try:
        safe_params = validate_params(req.command, req.params)
    except ValueError as e:
        audit_log(req.command, "param_blocked", str(e))
        return CommandResponse(success=False, error=str(e))

    # Dry-run mode: validate command without executing
    if req.dry_run:
        audit_log(req.command, "dry_run")
        return CommandResponse(
            success=True,
            dry_run=True,
            data=t("command.valid", command=req.command),
        )

    # Execute in thread pool to avoid blocking the event loop
    try:
        result = await asyncio.to_thread(companion.execute, req.command, safe_params)
        validated = _validate_result(result)
        return CommandResponse(**validated, dry_run=False)
    except Exception as e:
        logger.error(f"companion.execute() failed for '{req.command}': {e}", exc_info=True)
        audit_log(req.command, "execution_error", str(e))
        return CommandResponse(success=False, error=f"Ausführungsfehler: {str(e)}")


@router.get("/commands")
async def list_commands():
    """Alle verfügbaren Befehle auflisten."""
    return {
        "commands": list(companion.commands.keys()),
        "total": len(companion.commands),
    }


@router.get("/plugins")
async def list_plugins_endpoint():
    """Alle geladenen Plugins auflisten."""
    return {
        "plugins": companion.get_plugin_info(),
        "plugin_commands": companion._loaded_plugins,
    }


@router.get("/timers")
async def pending_timers():
    """Get pending timer/reminder notifications (fired, not yet acknowledged)."""
    timers = companion.get_pending_timers()
    # Include fired reminders
    try:
        from backend import reminders
        fired_reminders = reminders.get_pending_fired()
        for r in fired_reminders:
            timers.append({"message": r["message"], "fired_at": r.get("fired_at", ""), "type": "reminder"})
    except Exception:
        pass
    return {"timers": timers}


@router.post("/timers/acknowledge")
async def acknowledge_timers():
    """Acknowledge all pending timer and reminder notifications."""
    result = companion.acknowledge_timers()
    # Also acknowledge fired reminders
    try:
        from backend import reminders
        reminders.acknowledge_fired()
    except Exception:
        pass
    return {"status": result}


class BatchCommandRequest(BaseModel):
    commands: list[CommandRequest]
    stop_on_error: bool = True


@router.post("/execute/batch")
async def execute_batch(req: BatchCommandRequest):
    """Execute multiple commands sequentially. Max 10 commands per batch.

    Returns results for each command in order. If stop_on_error=True (default),
    stops at the first failed command. Blocked and confirmation-required commands
    are never executed in batch mode. Individual command failures are caught and
    collected — they don't crash the entire batch.
    """
    if not check_rate_limit("execute"):
        return {"success": False, "error": "Rate limit erreicht.", "results": []}

    if len(req.commands) > 10:
        return {"success": False, "error": t("command.batchMax"), "results": []}

    results = []
    all_ok = True

    for i, cmd in enumerate(req.commands):
        # Per-command rate limit check (prevent batch bypass of rate limits)
        if i > 0 and not check_rate_limit("execute"):
            entry = {"command": cmd.command, "success": False, "error": "Rate limit innerhalb Batch erreicht."}
            results.append(entry)
            all_ok = False
            break

        permission = is_command_allowed(cmd.command)

        if permission == "blocked":
            audit_log(cmd.command, "blocked")
            entry = {"command": cmd.command, "success": False, "error": f"Blockiert: {cmd.command}"}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        # Unknown commands (not in whitelist) are never executed in batch
        if permission == "unknown":
            audit_log(cmd.command, "batch_unknown_skipped")
            entry = {"command": cmd.command, "success": False, "error": t("command.batchUnknown", command=cmd.command)}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        if permission == "confirmation_required":
            audit_log(cmd.command, "batch_confirmation_skipped")
            entry = {"command": cmd.command, "success": False, "error": f"Bestätigung erforderlich — im Batch nicht ausführbar: {cmd.command}"}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        try:
            safe_params = validate_params(cmd.command, cmd.params)
        except ValueError as e:
            audit_log(cmd.command, "param_blocked", str(e))
            entry = {"command": cmd.command, "success": False, "error": str(e)}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        # Dry-run in batch: validate only
        if cmd.dry_run:
            audit_log(cmd.command, "dry_run")
            entry = {"command": cmd.command, "success": True, "dry_run": True,
                      "data": t("command.validShort", command=cmd.command)}
            results.append(entry)
            continue

        # Execute with error isolation per command
        try:
            result = await asyncio.to_thread(companion.execute, cmd.command, safe_params)
            validated = _validate_result(result)
            entry = {"command": cmd.command, **validated}
        except Exception as e:
            logger.error(f"Batch command '{cmd.command}' failed: {e}", exc_info=True)
            audit_log(cmd.command, "execution_error", str(e))
            entry = {"command": cmd.command, "success": False, "error": f"Ausführungsfehler: {str(e)}"}

        results.append(entry)

        if not entry.get("success", False):
            all_ok = False
            if req.stop_on_error:
                break

    return {"success": all_ok, "results": results, "executed": len(results)}
