"""Lexa AI — Unified Action Executor (Phase 40A)

Single entry point for executing actions from ANY source:
- Chat streaming (router_chat.py)
- Chat non-streaming (router_chat.py)
- Voice pipeline (router_voice.py)
- File upload (router_chat.py)

Uses the global companion singleton — never creates new CompanionEngine instances.
Handles permission checks, param validation, audit logging, and execution.
"""

import logging
from typing import Optional

from companion.engine import companion
from backend.security import is_command_allowed, validate_params, audit_log
from backend.tool_registry import ToolSchemaValidationError, validate_tool_arguments

logger = logging.getLogger("lexa.executor")


def execute_action(
    action: dict,
    source: str = "unknown",
    confirmed: bool = False,
) -> dict:
    """Execute an action dict using the global companion singleton.

    Args:
        action: Dict with "action" (str), "params" (dict), optional "message" (str)
        source: Where the action originated (chat, chat_stream, voice, file_upload)
        confirmed: Whether the user already confirmed (for confirmation_required actions)

    Returns:
        {
            "success": bool,
            "data": any | None,
            "error": str | None,
            "executed": bool,          # True if actually executed
            "requires_confirmation": bool,
        }
    """
    action_name = action.get("action", "")
    params = action.get("params", {})

    if not action_name:
        return {"success": False, "error": "Kein Aktionsname.", "executed": False, "requires_confirmation": False}

    try:
        schema_params = validate_tool_arguments(action_name, params)
    except ToolSchemaValidationError as e:
        logger.warning("Rejected invalid action args for %s from %s: %s", action_name, source, e)
        audit_log(action_name, "tool_schema_invalid", f"source={source} error={str(e)[:200]}")
        return {
            "success": False,
            "error": "Tool-Argumente ungueltig. Aktion wurde nicht ausgefuehrt.",
            "executed": False,
            "requires_confirmation": False,
        }

    # Permission check
    permission = is_command_allowed(action_name)

    if permission == "blocked":
        audit_log(action_name, "blocked", f"source={source}")
        return {"success": False, "error": f"'{action_name}' ist blockiert.", "executed": False, "requires_confirmation": False}

    if permission in ("confirmation_required", "unknown") and not confirmed:
        audit_log(action_name, "awaiting_confirmation", f"source={source}")
        return {
            "success": False,
            "error": f"'{action_name}' erfordert Bestätigung.",
            "executed": False,
            "requires_confirmation": True,
        }

    # Validate params
    try:
        safe_params = validate_params(action_name, schema_params)
    except ValueError as e:
        audit_log(action_name, "param_blocked", str(e))
        return {"success": False, "error": str(e), "executed": False, "requires_confirmation": False}

    # Execute using global singleton
    try:
        result = companion.execute(action_name, safe_params)

        if not isinstance(result, dict):
            result = {"success": False, "error": f"Unerwartetes Ergebnis: {type(result).__name__}"}

        success = bool(result.get("success", False))

        if success:
            audit_log(action_name, "executed", f"source={source} params={list(safe_params.keys())}")
        else:
            audit_log(action_name, "failed", f"source={source} error={result.get('error', '')[:100]}")

        return {
            "success": success,
            "data": result.get("data"),
            "error": result.get("error"),
            "executed": True,
            "requires_confirmation": False,
        }

    except Exception as e:
        logger.error(f"Action execution failed: {action_name} — {e}", exc_info=True)
        audit_log(action_name, "execution_error", f"source={source} error={str(e)[:200]}")
        return {
            "success": False,
            "error": f"Ausführungsfehler: {str(e)}",
            "executed": False,
            "requires_confirmation": False,
        }
