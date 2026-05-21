"""Deterministic Agent Reflection v1 policy.

This layer is intentionally small and policy-based. It runs after registry
schema validation and before action execution, adding a review checkpoint for
risky, write-like, scheduled, or multi-step tool actions.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from backend.security import audit_log

logger = logging.getLogger("lexa.agent_reflection")

RISK_LEVELS = {"low", "medium", "high", "critical"}
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0

_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passphrase|credential|auth|authorization|bearer|private|path|file)",
    re.IGNORECASE,
)
_WRITE_MARKERS = (
    "write",
    "create",
    "update",
    "delete",
    "move",
    "copy",
    "restore",
    "apply",
    "approve",
    "reject",
    "execute",
    "run",
    "start",
    "stop",
    "set",
    "toggle",
    "send",
    "commit",
    "push",
    "pull",
    "clean",
    "shutdown",
    "restart",
    "kill",
)
_READ_ONLY_PREFIXES = (
    "app_list",
    "app_search",
    "archive_list",
    "backup_list",
    "battery_",
    "calendar_search",
    "calendar_today",
    "calendar_week",
    "clipboard_read",
    "disk_analysis",
    "docker_images",
    "docker_logs",
    "docker_ps",
    "docker_stats",
    "email_read",
    "email_search",
    "email_summarize",
    "env_get",
    "env_list",
    "file_info",
    "file_search",
    "folder_size",
    "git_branch_list",
    "git_diff",
    "git_log",
    "git_status",
    "habit_list",
    "hermes_status",
    "installed_apps",
    "log_analyze",
    "memory_search",
    "network_info",
    "note_list",
    "note_read",
    "os_agent_list_tasks",
    "os_agent_status",
    "os_agent_task_status",
    "personal_os_context_pack",
    "personal_os_diagnostics",
    "personal_os_draft_history",
    "personal_os_graph",
    "personal_os_lexa_code_loop",
    "personal_os_list_drafts",
    "personal_os_obsidian_context",
    "personal_os_query",
    "personal_os_raw_inbox_status",
    "personal_os_read_file",
    "personal_os_review_draft",
    "personal_os_view_draft",
    "ping",
    "port_check",
    "process_list",
    "public_ip",
    "reminder_list",
    "routine_list",
    "server_check",
    "service_info",
    "service_list",
    "system_info",
    "system_uptime",
    "time_tracking_report",
    "todo_list",
    "weather_",
    "wifi_status",
    "window_list",
)
_CRITICAL_NAMES = {
    "backup_restore",
    "clean_temp",
    "file_delete",
    "format_disk",
    "mass_delete",
    "os_agent_start_task",
    "process_kill",
    "restart",
    "shutdown",
}


@dataclass
class ReflectionDecision:
    should_execute: bool
    risk_level: str
    confidence: float
    concerns: list[str] = field(default_factory=list)
    safer_alternative: dict[str, Any] | None = None
    requires_confirmation: bool = False
    verification_step: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReflectionContext:
    action_name: str
    params: dict[str, Any]
    permission: str = ""
    source: str = "unknown"
    plan_length: int = 1
    low_confidence: bool = False


def agent_reflection_enabled() -> bool:
    raw = os.getenv("AGENT_REFLECTION_ENABLED", os.getenv("LEXA_AGENT_REFLECTION_ENABLED", "1"))
    return raw.strip().lower() not in _FALSE_VALUES


def infer_reflection_risk(action_name: str, permission: str = "", params: dict[str, Any] | None = None) -> str:
    normalized = (action_name or "").strip().lower()
    params = params or {}
    if not normalized:
        return "critical"
    if normalized in _CRITICAL_NAMES:
        return "critical"
    if permission in {"blocked", "unknown"}:
        return "critical"
    if permission == "confirmation_required":
        return "high"
    if normalized.startswith(("hermes_", "mcp_")) or "mcp" in normalized:
        return "high"
    if normalized.startswith(("os_agent_",)):
        return "high" if any(marker in normalized for marker in _WRITE_MARKERS) else "medium"
    if normalized.startswith("personal_os_"):
        return "high" if _looks_personal_os_write(normalized) else "medium"
    if normalized.startswith(("routine_", "reminder_", "todo_", "habit_", "note_", "memory_")):
        if any(marker in normalized for marker in _WRITE_MARKERS):
            return "medium"
        return "low"
    if any(marker in normalized for marker in _WRITE_MARKERS):
        return "medium"
    if params.get("createReviewDraft") is True:
        return "high"
    return "low"


def should_reflect_action(
    action_name: str,
    params: dict[str, Any] | None = None,
    *,
    permission: str = "",
    plan_length: int = 1,
    low_confidence: bool = False,
) -> bool:
    if not agent_reflection_enabled():
        return False

    normalized = (action_name or "").strip().lower()
    risk = infer_reflection_risk(normalized, permission, params or {})
    if low_confidence:
        return True
    if plan_length > 1:
        return True
    if permission in {"confirmation_required", "unknown", "blocked"}:
        return True
    if risk in {"medium", "high", "critical"}:
        return True
    if normalized.startswith(_READ_ONLY_PREFIXES):
        return False
    return False


def reflect_action(
    action_name: str,
    params: dict[str, Any] | None,
    *,
    permission: str = "",
    source: str = "unknown",
    plan_length: int = 1,
    low_confidence: bool = False,
    decision_factory: Callable[[ReflectionContext], ReflectionDecision | dict[str, Any]] | None = None,
) -> ReflectionDecision | None:
    safe_params = params if isinstance(params, dict) else {}
    context = ReflectionContext(
        action_name=str(action_name or ""),
        params=safe_params,
        permission=str(permission or ""),
        source=str(source or "unknown"),
        plan_length=max(1, int(plan_length or 1)),
        low_confidence=bool(low_confidence),
    )
    if not should_reflect_action(
        context.action_name,
        context.params,
        permission=context.permission,
        plan_length=context.plan_length,
        low_confidence=context.low_confidence,
    ):
        return None

    risk = infer_reflection_risk(context.action_name, context.permission, context.params)
    factory = decision_factory or _policy_reflect_action
    try:
        raw_decision = factory(context)
        decision = _coerce_decision(raw_decision)
    except Exception as exc:
        logger.warning("Agent reflection failed for %s: %s", context.action_name, exc, exc_info=True)
        decision = None

    if decision is None:
        decision = ReflectionDecision(
            should_execute=False,
            risk_level=risk,
            confidence=0.0,
            concerns=["Reflection output was malformed."],
            safer_alternative=_safer_alternative(context.action_name),
            requires_confirmation=context.permission == "confirmation_required" or risk in {"high", "critical"},
            verification_step="Do not execute; request a safer read-only review first.",
            reason="malformed_reflection_failed_closed",
        )

    _audit_reflection(context, decision)
    return decision


def _policy_reflect_action(context: ReflectionContext) -> ReflectionDecision:
    risk = infer_reflection_risk(context.action_name, context.permission, context.params)
    concerns: list[str] = []
    requires_confirmation = context.permission == "confirmation_required" or risk in {"high", "critical"}

    if context.plan_length > 1:
        concerns.append(f"Multi-step plan with {context.plan_length} actions.")
    if context.low_confidence:
        concerns.append("Parsed tool call confidence is low.")
    if requires_confirmation:
        concerns.append("Command policy requires explicit user confirmation.")
    if _has_sensitive_param_keys(context.params):
        concerns.append("Sensitive-looking argument keys are present; values are redacted from logs.")
    if context.action_name.lower().startswith(("routine_", "reminder_")):
        concerns.append("Scheduled/routine actions can run later without the user present.")
    if context.action_name.lower().startswith(("personal_os_", "os_agent_")):
        concerns.append("Personal OS boundary must remain draft/review-first.")

    should_execute = True
    reason = "reflection_passed"
    confidence = {
        "low": 0.95,
        "medium": 0.82,
        "high": 0.68,
        "critical": 0.55,
    }[risk]
    safer_alternative = None

    if context.low_confidence and risk in {"medium", "high", "critical"}:
        should_execute = False
        confidence = 0.2
        safer_alternative = _safer_alternative(context.action_name)
        reason = "low_confidence_risky_action_blocked"
        concerns.append("Risky action was blocked because parsing confidence is low.")
    elif risk == "critical":
        safer_alternative = _safer_alternative(context.action_name)
        concerns.append("Critical action requires a verification step and confirmation before execution.")

    verification_step = _verification_step(context.action_name, risk, should_execute)
    return ReflectionDecision(
        should_execute=should_execute,
        risk_level=risk,
        confidence=confidence,
        concerns=concerns,
        safer_alternative=safer_alternative,
        requires_confirmation=requires_confirmation,
        verification_step=verification_step,
        reason=reason,
    )


def _coerce_decision(raw: ReflectionDecision | dict[str, Any]) -> ReflectionDecision | None:
    if isinstance(raw, ReflectionDecision):
        decision = raw
    elif isinstance(raw, dict):
        try:
            decision = ReflectionDecision(
                should_execute=raw["should_execute"],
                risk_level=raw["risk_level"],
                confidence=raw["confidence"],
                concerns=raw.get("concerns") or [],
                safer_alternative=raw.get("safer_alternative"),
                requires_confirmation=raw.get("requires_confirmation", False),
                verification_step=raw.get("verification_step"),
                reason=raw.get("reason", ""),
            )
        except KeyError:
            return None
    else:
        return None

    if not isinstance(decision.should_execute, bool):
        return None
    if decision.risk_level not in RISK_LEVELS:
        return None
    if not isinstance(decision.confidence, (int, float)):
        return None
    if not (CONFIDENCE_MIN <= float(decision.confidence) <= CONFIDENCE_MAX):
        return None
    if not isinstance(decision.concerns, list) or not all(isinstance(item, str) for item in decision.concerns):
        return None
    if decision.safer_alternative is not None and not isinstance(decision.safer_alternative, dict):
        return None
    if not isinstance(decision.requires_confirmation, bool):
        return None
    if decision.verification_step is not None and not isinstance(decision.verification_step, str):
        return None
    if not isinstance(decision.reason, str):
        return None
    return ReflectionDecision(
        should_execute=decision.should_execute,
        risk_level=decision.risk_level,
        confidence=float(decision.confidence),
        concerns=list(decision.concerns),
        safer_alternative=decision.safer_alternative,
        requires_confirmation=decision.requires_confirmation,
        verification_step=decision.verification_step,
        reason=decision.reason,
    )


def _audit_reflection(context: ReflectionContext, decision: ReflectionDecision) -> None:
    arg_keys = _redacted_arg_keys(context.params)
    detail = (
        f"source={context.source} risk={decision.risk_level} "
        f"execute={decision.should_execute} confidence={decision.confidence:.2f} "
        f"requires_confirmation={decision.requires_confirmation} "
        f"plan_length={context.plan_length} arg_keys={arg_keys} "
        f"reason={decision.reason[:80]}"
    )
    audit_log(context.action_name or "unknown", "agent_reflection", detail)


def _redacted_arg_keys(params: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in sorted(str(k) for k in (params or {}).keys()):
        keys.append("[REDACTED_KEY]" if _SENSITIVE_KEY_RE.search(key) else key)
    return keys


def _has_sensitive_param_keys(params: dict[str, Any]) -> bool:
    for key, value in (params or {}).items():
        if _SENSITIVE_KEY_RE.search(str(key)):
            return True
        if isinstance(value, dict) and _has_sensitive_param_keys(value):
            return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _has_sensitive_param_keys(item):
                    return True
    return False


def _looks_personal_os_write(action_name: str) -> bool:
    return any(marker in action_name for marker in ("write", "apply", "approve", "reject", "raw_submit", "cleanup", "archive", "migrate"))


def _safer_alternative(action_name: str) -> dict[str, Any]:
    normalized = (action_name or "").lower()
    if normalized.startswith("personal_os_") or normalized.startswith("os_agent_"):
        return {
            "mode": "read_only",
            "suggested_action": "personal_os_diagnostics",
            "reason": "Inspect Personal OS status/drafts before any write-like step.",
        }
    if "file" in normalized or normalized in {"backup_restore", "clean_temp"}:
        return {
            "mode": "read_only",
            "suggested_action": "file_info",
            "reason": "Inspect the target before changing or deleting it.",
        }
    if normalized.startswith(("routine_", "reminder_")):
        return {
            "mode": "read_only",
            "suggested_action": "routine_list",
            "reason": "Review existing scheduled actions before changing automation.",
        }
    return {
        "mode": "read_only",
        "suggested_action": "ask_user_to_review_plan",
        "reason": "Review the plan before executing the risky action.",
    }


def _verification_step(action_name: str, risk: str, should_execute: bool) -> str:
    if not should_execute:
        return "Verify by presenting the safer read-only alternative to the user."
    normalized = (action_name or "").lower()
    if risk in {"high", "critical"}:
        return f"After {normalized}, verify status with a read-only check or explicit user confirmation result."
    if normalized.startswith(("routine_", "reminder_")):
        return "Verify the scheduler/routine state with a read-only list/status check."
    return "Verify the action result is successful and does not require follow-up cleanup."
