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

from companion.engine import companion
from backend.agent_reflection import reflect_action
from backend.security import (
    audit_error_details,
    audit_log,
    audit_param_keys_details,
    audit_safe_token,
    audit_value_metadata,
    check_action_rate_limit,
    is_command_allowed,
    validate_params,
)
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
        audit_log(action_name, "tool_schema_invalid", audit_error_details(e, source=source))
        return {
            "success": False,
            "error": "Tool-Argumente ungueltig. Aktion wurde nicht ausgefuehrt.",
            "executed": False,
            "requires_confirmation": False,
        }

    # Permission classification is read-only; enforcement happens after reflection.
    permission = is_command_allowed(action_name)

    reflection = reflect_action(
        action_name,
        schema_params,
        permission=permission,
        source=source,
    )
    if reflection is not None and not reflection.should_execute:
        audit_log(
            action_name,
            "reflection_blocked",
            f"source={audit_safe_token(source)} {audit_value_metadata('reason', reflection.reason)}",
        )
        return {
            "success": False,
            "error": "Aktion wurde nach Sicherheitsreflexion nicht ausgefuehrt.",
            "executed": False,
            "requires_confirmation": reflection.requires_confirmation,
            "reflection": reflection.to_dict(),
        }

    if permission == "blocked":
        audit_log(action_name, "blocked", f"source={audit_safe_token(source)}")
        return {"success": False, "error": f"'{action_name}' ist blockiert.", "executed": False, "requires_confirmation": False}

    if permission in ("confirmation_required", "unknown") and not confirmed:
        audit_log(action_name, "awaiting_confirmation", f"source={audit_safe_token(source)}")
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
        audit_log(action_name, "param_blocked", audit_error_details(e, source=source))
        return {"success": False, "error": str(e), "executed": False, "requires_confirmation": False}

    rate_limit = check_action_rate_limit(action_name)
    if not rate_limit.get("allowed", False):
        audit_log(
            action_name,
            "risk_rate_limited",
            f"source={audit_safe_token(source)} used={rate_limit.get('used')} limit={rate_limit.get('limit')}",
        )
        return {
            "success": False,
            "error": "Zu viele riskante Aktionen in kurzer Zeit. Read-only Aktionen bleiben erlaubt.",
            "executed": False,
            "requires_confirmation": False,
            "rate_limited": True,
        }

    # Execute using global singleton
    try:
        result = companion.execute(action_name, safe_params)

        if not isinstance(result, dict):
            result = {"success": False, "error": f"Unerwartetes Ergebnis: {type(result).__name__}"}

        success = bool(result.get("success", False))

        if success:
            audit_log(action_name, "executed", f"source={audit_safe_token(source)} {audit_param_keys_details(safe_params)}")
        else:
            audit_log(action_name, "failed", audit_error_details(result.get("error", ""), source=source))

        return {
            "success": success,
            "data": result.get("data"),
            "error": result.get("error"),
            "executed": True,
            "requires_confirmation": False,
        }

    except Exception as e:
        logger.error(f"Action execution failed: {action_name} — {e}", exc_info=True)
        audit_log(action_name, "execution_error", audit_error_details(e, source=source))
        return {
            "success": False,
            "error": f"Ausführungsfehler: {str(e)}",
            "executed": False,
            "requires_confirmation": False,
        }
