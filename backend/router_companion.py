"""Lexa AI — Companion Router
API Endpoints für PC-Kontrolle (async-safe via to_thread)
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from companion.engine import companion
from backend.companion_confirmation import (
    ConfirmationError,
    audit_details as confirmation_audit_details,
    consume_confirmation,
    create_confirmation,
)
from backend.security import (
    audit_error_details,
    audit_log,
    audit_safe_token,
    audit_value_metadata,
    check_action_rate_limit,
    check_rate_limit,
    is_command_allowed,
    read_recent_audit_entries,
    validate_params,
)
from backend.i18n import t
from backend.personal_os_actions import execute_personal_os_action, is_personal_os_action
from backend.agent_reflection import reflect_action
from backend.tool_registry import ToolSchemaValidationError, validate_tool_arguments

logger = logging.getLogger("lexa.companion")
router = APIRouter(prefix="/companion", tags=["companion"])
GENERIC_EXECUTION_ERROR = "Command execution failed. Details were logged locally."
GENERIC_INVALID_TOOL_ARGUMENTS = "Tool arguments are invalid. Action was not executed."


class CommandRequest(BaseModel):
    command: str
    params: dict = {}
    confirmed: bool = False
    dry_run: bool = False
    confirmation_id: str | None = None
    command_hash: str | None = None
    action_scope: str | None = None


class PrepareCommandRequest(BaseModel):
    command: str
    params: dict = {}


class CommandResponse(BaseModel):
    success: bool
    data: str | dict | list | None = None
    error: str | None = None
    requires_confirmation: bool = False
    dry_run: bool = False


def _safe_command_name(command: str) -> str:
    return str(command or "").strip()


def _is_registered_command(command: str) -> bool:
    return is_personal_os_action(command) or command in getattr(companion, "commands", {})


def _permission_scope(permission: str) -> str:
    if permission == "confirmation_required":
        return "confirmation_required"
    if permission == "always_allowed":
        return "always_allowed"
    return str(permission or "unknown")


def _raise_confirmation_error(command: str, exc: ConfirmationError) -> None:
    audit_log(command, "confirmation_denied", f"confirmationCode={audit_safe_token(exc.code)}")
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)})


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


def _validate_registry_params(command: str, params: dict, status: str) -> tuple[dict | None, str | None]:
    try:
        return validate_tool_arguments(command, params), None
    except ToolSchemaValidationError as exc:
        logger.warning("Rejected invalid tool args for %s: %s", command, exc)
        audit_log(command, status, audit_error_details(exc))
        return None, str(exc)


@router.post("/execute/prepare")
async def prepare_command(req: PrepareCommandRequest):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    command = _safe_command_name(req.command)
    permission = is_command_allowed(command)

    if permission == "blocked":
        audit_log(command, "prepare_blocked")
        raise HTTPException(status_code=400, detail={"code": "command_blocked", "message": t("command.blockedRouter", command=command)})
    if permission == "unknown" or not _is_registered_command(command):
        audit_log(command, "prepare_unknown")
        raise HTTPException(status_code=400, detail={"code": "unknown_command", "message": t("command.needsConfirmation", command=command)})

    schema_params, schema_error = _validate_registry_params(command, req.params, "prepare_tool_schema_invalid")
    if schema_error:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_tool_arguments", "message": GENERIC_INVALID_TOOL_ARGUMENTS},
        )

    try:
        safe_params = validate_params(command, schema_params)
    except ValueError as e:
        audit_log(command, "prepare_param_blocked", audit_error_details(e))
        raise HTTPException(status_code=400, detail={"code": "invalid_params", "message": str(e)})

    action_scope = _permission_scope(permission)
    confirmation = create_confirmation(command, safe_params, action_scope)
    audit_log(command, "confirmation_prepared", confirmation_audit_details(confirmation))
    return confirmation


@router.post("/execute", response_model=CommandResponse)
async def execute_command(req: CommandRequest):
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    command = _safe_command_name(req.command)
    permission = is_command_allowed(command)

    if permission == "blocked":
        audit_log(command, "blocked")
        return CommandResponse(success=False, error=t("command.blockedRouter", command=command))

    # Unknown commands (not in whitelist at all) require confirmation — deny by default
    if permission == "unknown" or not _is_registered_command(command):
        audit_log(command, "unknown_blocked")
        raise HTTPException(status_code=400, detail={"code": "unknown_command", "message": t("command.needsConfirmation", command=command)})

    action_scope = _permission_scope(permission)

    schema_params, schema_error = _validate_registry_params(command, req.params, "tool_schema_invalid")
    if schema_error:
        return CommandResponse(success=False, error=GENERIC_INVALID_TOOL_ARGUMENTS)

    reflection = reflect_action(
        command,
        schema_params,
        permission=permission,
        source="companion_execute",
    )
    if reflection is not None and not reflection.should_execute:
        audit_log(
            command,
            "reflection_blocked",
            f"source=companion_execute {audit_value_metadata('reason', reflection.reason)}",
        )
        return CommandResponse(
            success=False,
            error="Action was blocked by safety reflection.",
            requires_confirmation=reflection.requires_confirmation,
        )

    # Validate params for safety
    try:
        safe_params = validate_params(command, schema_params)
    except ValueError as e:
        audit_log(command, "param_blocked", audit_error_details(e, source="companion_execute"))
        return CommandResponse(success=False, error=str(e))

    if permission == "confirmation_required":
        try:
            record = consume_confirmation(
                req.confirmation_id,
                command=command,
                params=safe_params,
                action_scope=req.action_scope or action_scope,
                command_hash=req.command_hash,
            )
            audit_log(command, "confirmation_consumed", confirmation_audit_details(record))
        except ConfirmationError as exc:
            _raise_confirmation_error(command, exc)

    # Dry-run mode: validate command without executing
    if req.dry_run:
        audit_log(command, "dry_run")
        return CommandResponse(
            success=True,
            dry_run=True,
            data=t("command.valid", command=command),
        )

    action_budget = check_action_rate_limit(command)
    if not action_budget.get("allowed", False):
        audit_log(
            command,
            "risk_rate_limited",
            f"source={audit_safe_token('companion_execute')} used={action_budget.get('used')} limit={action_budget.get('limit')}",
        )
        return CommandResponse(
            success=False,
            error="Too many risky actions in a short time. Read-only actions remain available.",
        )

    if is_personal_os_action(command):
        result = await execute_personal_os_action(command, safe_params)
        validated = _validate_result(result)
        return CommandResponse(**validated, dry_run=False)

    # Execute in thread pool to avoid blocking the event loop
    try:
        result = await asyncio.to_thread(companion.execute, command, safe_params)
        validated = _validate_result(result)
        return CommandResponse(**validated, dry_run=False)
    except Exception as e:
        logger.error(f"companion.execute() failed for '{command}': {e}", exc_info=True)
        audit_log(command, "execution_error", audit_error_details(e, source="companion_execute"))
        return CommandResponse(success=False, error=GENERIC_EXECUTION_ERROR)


@router.get("/commands")
async def list_commands():
    """Alle verfügbaren Befehle auflisten."""
    return {
        "commands": list(companion.commands.keys()),
        "total": len(companion.commands),
    }


@router.get("/audit/recent")
async def recent_audit_entries(
    limit: int = Query(30, ge=1, le=100),
    hideNoise: bool = Query(False),
):
    """Read-only recent tool/action audit summary for UI trust surfaces."""
    if not check_rate_limit("audit_read"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return read_recent_audit_entries(limit, hide_noise=hideNoise)


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
    if len(req.commands) > 10:
        return {"success": False, "error": t("command.batchMax"), "results": []}

    results = []
    all_ok = True

    for i, cmd in enumerate(req.commands):
        # Per-command rate limit check (prevent batch bypass of rate limits).
        if not check_rate_limit("execute"):
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

        schema_params, schema_error = _validate_registry_params(
            cmd.command,
            cmd.params,
            "batch_tool_schema_invalid",
        )
        if schema_error:
            entry = {"command": cmd.command, "success": False, "error": GENERIC_INVALID_TOOL_ARGUMENTS}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        reflection = reflect_action(
            cmd.command,
            schema_params,
            permission=permission,
            source="companion_batch",
            plan_length=len(req.commands),
        )
        if reflection is not None and not reflection.should_execute:
            audit_log(
                cmd.command,
                "reflection_blocked",
                f"source=companion_batch {audit_value_metadata('reason', reflection.reason)}",
            )
            entry = {"command": cmd.command, "success": False, "error": "Action was blocked by safety reflection."}
            results.append(entry)
            all_ok = False
            if req.stop_on_error:
                break
            continue

        try:
            safe_params = validate_params(cmd.command, schema_params)
        except ValueError as e:
            audit_log(cmd.command, "param_blocked", audit_error_details(e, source="companion_batch"))
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
            audit_log(cmd.command, "execution_error", audit_error_details(e, source="companion_batch"))
            entry = {"command": cmd.command, "success": False, "error": GENERIC_EXECUTION_ERROR}

        results.append(entry)

        if not entry.get("success", False):
            all_ok = False
            if req.stop_on_error:
                break

    return {"success": all_ok, "results": results, "executed": len(results)}
