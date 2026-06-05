"""Lexa AI — Multi-Step Agent Loop (Phase 46)
Plan-Execute-Reflect Schleife fuer komplexe, mehrstufige Aufgaben.

Der Agent:
1. Bekommt eine User-Anfrage
2. Plant Schritte (via LLM mit Tool-Definitionen)
3. Fuehrt jeden Schritt aus (Tool Call → Companion Execute)
4. Gibt Ergebnis ans LLM zurueck (Reflect)
5. LLM entscheidet: naechster Schritt oder fertig

Sicherheit:
- Max AGENT_MAX_STEPS Schritte pro Task (config.py)
- Timeout pro Schritt (AGENT_STEP_TIMEOUT)
- Blockierte/Bestaetigungs-Befehle pausieren den Loop
- Jeder Schritt wird geloggt (audit_log)
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional

from backend.config import (
    AGENT_MAX_STEPS,
    AGENT_STEP_TIMEOUT,
)
from backend.agent_reflection import reflect_action
from backend.security import is_command_allowed, audit_log, validate_params
from backend.action_parser import _ACTION_NAME_PATTERN, _sanitize_params
logger = logging.getLogger("lexa.agent")
_AGENT_ARGS_MISSING = object()
_TOOL_ARGUMENT_ERROR_REPLY = "Tool-Argumente ungueltig. Aktion wurde nicht ausgefuehrt."


# ══════════════════════════════════════════════════
#  DATA MODELS
# ══════════════════════════════════════════════════

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"           # command is blocked by whitelist
    NEEDS_CONFIRMATION = "needs_confirmation"
    SKIPPED = "skipped"


@dataclass
class AgentStep:
    """Ein einzelner Schritt im Agent Loop."""
    index: int
    action: str = ""
    params: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: float = 0.0
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class AgentRun:
    """Eine komplette Agent-Ausfuehrung."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_message: str = ""
    worker: str = "lexa"
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "running"      # running, completed, failed, paused
    summary: str = ""
    started_at: float = field(default_factory=time.time)
    total_duration_ms: float = 0.0
    ledger: Optional[object] = None

    def to_dict(self) -> dict:
        payload = {
            "id": self.id,
            "user_message": self.user_message,
            "worker": self.worker,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
        }
        if self.ledger is not None:
            payload["ledger"] = (
                self.ledger.to_dict()
                if hasattr(self.ledger, "to_dict")
                else self.ledger
            )
        return payload


def _agent_ledger_enabled() -> bool:
    """Return whether Phase 3B ledger emission is enabled."""
    return os.getenv("LEXA_AGENT_LEDGER", "").strip().lower() in {"1", "true", "yes", "on"}


def _agent_trace_enabled() -> bool:
    """Return whether Phase 3C trace emission is enabled."""
    return os.getenv("LEXA_AGENT_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}


def _agent_trace_sampling_enabled() -> bool:
    """Return whether Phase 3D controlled trace sampling is enabled."""
    return os.getenv("LEXA_AGENT_TRACE_SAMPLING", "").strip().lower() in {"1", "true", "yes", "on"}


def _agent_policy_enforce_enabled() -> bool:
    """Return whether Phase 3C policy enforcement is enabled."""
    return os.getenv("LEXA_AGENT_POLICY_ENFORCE", "").strip().lower() in {"1", "true", "yes", "on"}


def _agent_start_audit_details(run_id: str, worker_name: str, user_message: str) -> str:
    """Return start-audit metadata without writing raw prompts to audit.log."""
    from backend.agent_protocol import stable_hash

    message = str(user_message or "")
    return (
        f"RUN={run_id} WORKER={worker_name} "
        f"messageChars={len(message)} messageHash={stable_hash(message)[:12]}"
    )


def _agent_trace_path(run_id: str) -> Path:
    root = Path(__file__).resolve().parents[1]
    configured = os.getenv("LEXA_AGENT_TRACE_DIR", "").strip()
    trace_dir = Path(configured).expanduser() if configured else root / "evals" / "results" / "traces"
    return trace_dir / f"{run_id}.jsonl"


def _build_agent_trace_recorder(run: AgentRun, *, source: str, synthetic_context: bool):
    from backend.agent_protocol import AgentTraceRecorder, AgentTraceWriter
    from backend.agent_trace_sampling import AgentTraceSamplingPolicy

    policy = AgentTraceSamplingPolicy.from_env()
    if not policy.should_sample(source=source, synthetic_context=synthetic_context):
        return None, policy
    try:
        writer = AgentTraceWriter(policy.safe_output_path(run.id))
        return AgentTraceRecorder(run.id, writer=writer, max_events=policy.max_events_per_run), policy
    except ValueError as exc:
        logger.warning("Agent trace disabled: %s", exc)
        return None, policy


def _record_agent_trace(trace_recorder, trace_policy, event_type: str, **kwargs) -> None:
    if trace_recorder is None:
        return
    try:
        metadata = kwargs.pop("metadata", None) or {}
        summary = kwargs.pop("summary", event_type)
        if trace_policy is not None:
            metadata = trace_policy.sanitize_metadata(metadata)
            summary = trace_policy.sanitize_summary(summary)
        trace_recorder.record(event_type, summary=summary, metadata=metadata, **kwargs)
    except Exception as exc:
        logger.warning("Agent trace event skipped: %s", exc)


def _infer_agent_action_risk(action_name: str, permission: str = "") -> str:
    normalized = (action_name or "").lower()
    critical_names = {
        "backup_restore",
        "shutdown",
        "restart",
        "file_delete",
        "clean_temp",
        "os_agent_start_task",
        "mcpcalltool",
    }
    high_prefixes = (
        "backup_",
        "file_move",
        "file_copy",
        "personal_os_",
        "hermes_",
        "mcp_",
    )
    if normalized in critical_names:
        return "critical"
    if permission == "confirmation_required" or any(normalized.startswith(prefix) for prefix in high_prefixes) or "mcp" in normalized:
        return "high"
    if normalized.startswith(("note_", "memory_", "clipboard_", "todo_")):
        return "medium"
    return "low"


def _build_agent_run_ledger(run: AgentRun):
    from backend.agent_protocol import AgentPlan, AgentRunLedger

    plan = AgentPlan(
        goal=run.user_message,
        risk_level="medium",
        allowed_tools=[],
        forbidden_tools=["shell", "unsafe_direct_write", "mcpCallTool"],
        budget_steps=AGENT_MAX_STEPS,
        budget_seconds=AGENT_MAX_STEPS * AGENT_STEP_TIMEOUT,
        checkpoints=["plan", "act", "verify", "review"],
        requires_user_review=False,
        max_tool_calls=AGENT_MAX_STEPS,
        max_risky_tool_calls=max(1, AGENT_MAX_STEPS // 2),
        max_memory_reads=AGENT_MAX_STEPS,
        max_os_writes=1,
        max_runtime_seconds=AGENT_MAX_STEPS * AGENT_STEP_TIMEOUT,
        max_retry_count=2,
    )
    return AgentRunLedger(run_id=run.id, plan=plan, status="running")


def _append_ledger_action(ledger, *, action_id: str, action_name: str, params: dict, permission: str):
    from backend.agent_protocol import AgentAction, stable_hash

    risk_level = _infer_agent_action_risk(action_name, permission)
    requires_confirmation = permission == "confirmation_required" or risk_level in {"high", "critical"}
    param_keys = sorted((params or {}).keys())
    policy_reason = (
        "confirmation required by command policy"
        if requires_confirmation
        else f"permission={permission or 'unknown'}"
    )
    rejected_tools = (
        [{"tool_name": action_name, "reason": permission}]
        if permission in {"blocked", "unknown"}
        else []
    )
    action = AgentAction(
        action_id=action_id,
        tool_name=action_name or "unknown",
        action_type="execute",
        scope="agent_loop",
        reason=f"Agent requested tool; permission={permission or 'unknown'}; param_keys={param_keys}",
        reversible=risk_level in {"low", "medium"},
        requires_confirmation=requires_confirmation,
        status="planned",
        risk_level=risk_level,
        policy={
            "considered_tools": [action_name] if action_name else [],
            "selected_tool": action_name or "",
            "rejected_tools": rejected_tools,
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "policy_reason": policy_reason,
            "args_hash": stable_hash(params or {})[:12],
            "arg_keys": param_keys,
        },
    )
    ledger.actions.append(action)
    return action


def _append_ledger_verification(ledger, *, action_id: str, step: AgentStep):
    from backend.agent_protocol import AgentVerification

    passed = step.status == StepStatus.SUCCESS
    failures = []
    if step.error:
        failures.append(step.error)
    elif step.status in {StepStatus.FAILED, StepStatus.BLOCKED, StepStatus.NEEDS_CONFIRMATION}:
        failures.append(step.status.value)
    ledger.verifications.append(
        AgentVerification(
            action_id=action_id,
            checks_run=["agent_step_status"],
            passed=passed,
            failures=failures,
            artifacts=[],
            redacted_logs=[step.result or step.error or step.status.value],
        )
    )


def _finalize_agent_ledger(ledger, run: AgentRun) -> None:
    from backend.agent_protocol import AgentReview, coerce_ledger_status

    status_map = {
        "completed": "completed",
        "failed": "failed",
        "paused": "review_required",
    }
    ledger.status = coerce_ledger_status(status_map.get(run.status, "completed"))
    needs_decision = any(
        getattr(action, "requires_confirmation", False)
        for action in getattr(ledger, "actions", [])
    )
    ledger.review = AgentReview(
        summary=run.summary or f"Agent run {run.status}",
        user_decision_required=needs_decision,
        rollback_available=not needs_decision,
        approval_references=[],
        remaining_risks=["confirmation required"] if needs_decision else [],
    )


# ══════════════════════════════════════════════════
#  TOOL EXECUTION (sync, runs in thread pool)
# ══════════════════════════════════════════════════

def _reject_agent_tool_schema(action_name: str, reason: str) -> dict:
    logger.warning(
        "Rejected invalid agent tool call %s: %s",
        action_name,
        reason,
    )
    audit_log(action_name, "agent_tool_schema_invalid", reason[:200])
    return {"success": False, "error": _TOOL_ARGUMENT_ERROR_REPLY}


def _coerce_agent_tool_arguments(raw_params) -> tuple[Optional[dict], Optional[str]]:
    if raw_params is _AGENT_ARGS_MISSING:
        return {}, None
    if isinstance(raw_params, str):
        if not raw_params.strip():
            return {}, None
        try:
            parsed = json.loads(raw_params)
        except (json.JSONDecodeError, TypeError):
            return None, "arguments must be a JSON object"
        if not isinstance(parsed, dict):
            return None, "arguments must be a JSON object"
        return parsed, None
    if not isinstance(raw_params, dict):
        return None, "arguments must be an object"
    return raw_params, None


async def _execute_tool(action_name: str, params: dict, *, plan_length: int = 1, low_confidence: bool = False) -> dict:
    """Execute a single tool call via CompanionEngine or a safe async bridge.

    Returns: {"success": bool, "data": ..., "error": ...}
    """
    # Validate action name (before any heavy imports)
    if not _ACTION_NAME_PATTERN.match(action_name):
        return {"success": False, "error": f"Ungueltiger Befehl: {action_name}"}

    # Fail closed before permission checks or execution. The registry schema is
    # the source of truth for allowed LLM tool arguments.
    try:
        from backend.tool_registry import (
            ToolSchemaValidationError,
            validate_tool_arguments,
        )

        schema_params = validate_tool_arguments(action_name, params)
    except ToolSchemaValidationError as exc:
        return _reject_agent_tool_schema(action_name, str(exc))
    except Exception as exc:
        logger.error(
            "Agent tool schema validation failed unexpectedly for %s: %s",
            action_name,
            exc,
            exc_info=True,
        )
        return _reject_agent_tool_schema(action_name, "schema validation unavailable")

    # Permission classification is read-only; enforcement happens after reflection.
    permission = is_command_allowed(action_name)

    reflection = reflect_action(
        action_name,
        schema_params,
        permission=permission,
        source="agent_loop",
        plan_length=plan_length,
        low_confidence=low_confidence,
    )
    if reflection is not None and not reflection.should_execute:
        audit_log(action_name, "agent_reflection_blocked", f"reason={reflection.reason[:120]}")
        return {
            "success": False,
            "error": "Aktion wurde nach Sicherheitsreflexion nicht ausgefuehrt.",
            "reflection_blocked": True,
            "reflection": reflection.to_dict(),
        }

    if permission == "blocked":
        audit_log(action_name, "agent_blocked")
        return {"success": False, "error": f"Befehl '{action_name}' ist blockiert."}

    if permission == "confirmation_required":
        audit_log(action_name, "agent_needs_confirmation")
        try:
            from backend.shared import set_pending_confirmation

            set_pending_confirmation({"action": action_name, "params": schema_params})
        except Exception as exc:
            logger.debug("Could not store pending agent confirmation for %s: %s", action_name, exc)
        return {
            "success": False,
            "error": f"Befehl '{action_name}' braucht User-Bestaetigung.",
            "needs_confirmation": True,
        }

    if permission == "unknown":
        audit_log(action_name, "agent_unknown_command")
        return {"success": False, "error": f"Unbekannter Befehl: {action_name}"}

    # Validate and sanitize params
    try:
        safe_params = validate_params(action_name, schema_params)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    safe_params = _sanitize_params(safe_params)

    if action_name.startswith("personal_os_"):
        try:
            from backend.personal_os_actions import execute_personal_os_action, is_personal_os_action
            if not is_personal_os_action(action_name):
                return {"success": False, "error": f"Unbekannte Personal OS Aktion: {action_name}"}
            return await execute_personal_os_action(action_name, safe_params)
        except Exception as e:
            logger.error(f"Personal OS tool execution failed: {action_name} - {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # Execute (lazy import to avoid loading companion at module level)
    try:
        from companion.engine import companion
        result = await asyncio.to_thread(companion.execute, action_name, safe_params)
        if not isinstance(result, dict):
            return {"success": False, "error": f"Unerwartetes Ergebnis: {type(result).__name__}"}
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {action_name} — {e}", exc_info=True)
        return {"success": False, "error": str(e)}


_ORIGINAL_EXECUTE_TOOL = _execute_tool
_EXECUTE_TOOL_ACCEPTS_PLAN_LENGTH = "plan_length" in inspect.signature(_execute_tool).parameters


def _callable_accepts_plan_length(fn) -> bool:
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return "plan_length" in parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in parameters.values()
    )


def _execute_tool_supports_plan_length(execute_tool) -> bool:
    if execute_tool is _ORIGINAL_EXECUTE_TOOL:
        return _EXECUTE_TOOL_ACCEPTS_PLAN_LENGTH
    side_effect = getattr(execute_tool, "side_effect", None)
    if side_effect is not None:
        return _callable_accepts_plan_length(side_effect)
    return _callable_accepts_plan_length(execute_tool)


def _format_metric(value, suffix: str = "") -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "unbekannt"
    text = f"{num:.1f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _format_system_info_result(data: dict) -> str:
    useful_keys = {
        "cpu_percent", "cpu_cores", "cpu_freq_mhz",
        "ram_total_gb", "ram_used_gb", "ram_percent",
        "disk_total_gb", "disk_used_gb", "disk_percent",
        "battery_percent", "battery_plugged",
    }
    if not isinstance(data, dict) or not useful_keys.intersection(data):
        return ""

    lines = ["[system_info] Erfolgreich: gueltige Systemdaten."]
    lines.append(
        "CPU: "
        f"{_format_metric(data.get('cpu_percent'), '%')}"
        f" Auslastung, {data.get('cpu_cores') or 'unbekannt'} Kerne"
        f", {_format_metric(data.get('cpu_freq_mhz'), ' MHz')} Takt."
    )
    lines.append(
        "RAM: "
        f"{_format_metric(data.get('ram_used_gb'), ' GB')} von "
        f"{_format_metric(data.get('ram_total_gb'), ' GB')} genutzt "
        f"({_format_metric(data.get('ram_percent'), '%')})."
    )
    lines.append(
        "Speicherplatz: "
        f"{_format_metric(data.get('disk_used_gb'), ' GB')} von "
        f"{_format_metric(data.get('disk_total_gb'), ' GB')} genutzt "
        f"({_format_metric(data.get('disk_percent'), '%')})."
    )
    battery_percent = data.get("battery_percent")
    if battery_percent is not None:
        plugged = data.get("battery_plugged")
        plugged_text = "am Strom" if plugged else "im Akkubetrieb"
        lines.append(f"Batterie: {_format_metric(battery_percent, '%')}, {plugged_text}.")
    else:
        lines.append("Batterie: kein Akku gemeldet oder Desktop-PC.")

    try:
        disk_percent = float(data.get("disk_percent"))
    except (TypeError, ValueError):
        disk_percent = 0
    if disk_percent >= 90:
        lines.append("Hinweis: Speicherplatz ist knapp; vor grossen Downloads/Builds aufraeumen.")

    lines.append("Antworte dem User direkt mit dieser Zusammenfassung, frage nicht nach alternativen Systemabfragen.")
    return " ".join(lines)


def _format_system_info_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    summary = (
        "Ich habe den Systemstatus ueber das echte PC-Tool geprueft. "
        "CPU: "
        f"{_format_metric(data.get('cpu_percent'), '%')} Auslastung"
        f", {data.get('cpu_cores') or 'unbekannt'} Kerne. "
        "RAM: "
        f"{_format_metric(data.get('ram_used_gb'), ' GB')} von "
        f"{_format_metric(data.get('ram_total_gb'), ' GB')} genutzt "
        f"({_format_metric(data.get('ram_percent'), '%')}). "
        "Speicherplatz: "
        f"{_format_metric(data.get('disk_used_gb'), ' GB')} von "
        f"{_format_metric(data.get('disk_total_gb'), ' GB')} genutzt "
        f"({_format_metric(data.get('disk_percent'), '%')})."
    )
    battery_percent = data.get("battery_percent")
    if battery_percent is not None:
        plugged = data.get("battery_plugged")
        plugged_text = "am Strom" if plugged else "im Akkubetrieb"
        summary += f" Batterie: {_format_metric(battery_percent, '%')}, {plugged_text}."

    try:
        disk_percent = float(data.get("disk_percent"))
    except (TypeError, ValueError):
        disk_percent = 0
    if disk_percent >= 90:
        summary += " Hinweis: Der Speicherplatz ist knapp; vor grossen Downloads oder Builds solltest du aufraeumen."
    return summary


def _format_desktop_position_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    try:
        x = int(data.get("x"))
        y = int(data.get("y"))
        width = int(data.get("screen_width"))
        height = int(data.get("screen_height"))
    except (TypeError, ValueError):
        return ""
    return (
        f"Aktuelle Mausposition: X={x}, Y={y}. "
        f"Bildschirmgroesse: {width}x{height}. "
        "Ich habe nichts veraendert."
    )


_UI_ACTIONABLE_TYPES = {
    "Button",
    "CheckBox",
    "ComboBox",
    "DataItem",
    "Edit",
    "Hyperlink",
    "ListItem",
    "MenuItem",
    "RadioButton",
    "SplitButton",
    "TabItem",
    "TreeItem",
}


def _short_visible_label(value: object, fallback: str = "Position", limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _control_center(control: dict) -> tuple[int | None, int | None]:
    if isinstance(control, dict) and control.get("rect_valid") is False:
        return None, None
    rect = control.get("rect") if isinstance(control, dict) else None
    if not isinstance(rect, dict):
        return None, None
    try:
        coords = [float(rect.get(key)) for key in ("left", "top", "right", "bottom")]
        if (
            coords[2] <= coords[0]
            or coords[3] <= coords[1]
            or any(abs(coord) >= 30000 for coord in coords)
        ):
            return None, None
        x = int(round((coords[0] + coords[2]) / 2))
        y = int(round((coords[1] + coords[3]) / 2))
    except (TypeError, ValueError):
        return None, None
    return x, y


def _format_ui_tree_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    if not windows:
        return "Ich konnte kein UIA-Fenster lesen. Ich habe nichts veraendert."
    first_window = windows[0] if isinstance(windows[0], dict) else {}
    title = _short_visible_label(first_window.get("title"), fallback="aktuelles Fenster", limit=100)
    selection = data.get("selection") if isinstance(data.get("selection"), dict) else {}
    prefix = ""
    if selection.get("foreground_excluded"):
        foreground = _short_visible_label(selection.get("foreground_title"), fallback="Lexa", limit=80)
        if selection.get("reason") == "lexa_self_control_guard":
            prefix = f'"{foreground}" war im Vordergrund und wurde als Lexa/Codex-Schutz ignoriert. '
        else:
            prefix = f'"{foreground}" war im Vordergrund, ist aber kein steuerbares App-Fenster. '
    controls: list[dict] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        for control in window.get("controls") or []:
            if isinstance(control, dict) and control.get("control_type") in _UI_ACTIONABLE_TYPES:
                controls.append(control)
    named = []
    for control in controls:
        label = _short_visible_label(control.get("name") or control.get("automation_id"), fallback="")
        if label and label not in named:
            named.append(label)
        if len(named) >= 12:
            break
    if not named:
        return f'{prefix}Analysiert wurde: "{title}". Keine klar klickbaren Controls gefunden. Ich habe nichts veraendert.'
    listed = ", ".join(f'"{item}"' for item in named)
    suffix = f" (+{len(controls) - len(named)} weitere)" if len(controls) > len(named) else ""
    return f'{prefix}Analysiert wurde: "{title}". Klickbare Controls: {listed}{suffix}. Ich habe nichts veraendert.'


def _format_ui_find_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    if not matches:
        return "Ich habe kein passendes Windows-Control gefunden. Ich habe nichts veraendert."
    first = matches[0] if isinstance(matches[0], dict) else {}
    label = _short_visible_label(first.get("name") or first.get("automation_id"), fallback="Control")
    control_type = _short_visible_label(first.get("control_type"), fallback="Control", limit=40)
    window = _short_visible_label(first.get("window_title"), fallback="aktuelles Fenster", limit=100)
    x, y = _control_center(first)
    position = f" bei X={x}, Y={y}" if x is not None and y is not None else ""
    extra = f" Es gibt {len(matches)} Treffer." if len(matches) > 1 else ""
    return f'Gefunden: "{label}" ({control_type}) im Fenster "{window}"{position}.{extra} Ich habe nichts veraendert.'


def _format_hermes_desktop_task_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    summary = str(data.get("summary") or "").strip()
    if summary:
        return summary
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    lines = [str(step.get("summary") or "").strip() for step in steps if isinstance(step, dict) and step.get("summary")]
    return " ".join(line for line in lines if line)


def _format_screen_read_text_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict):
        return ""
    text = re.sub(r"\s+", " ", str(payload.get("text") or "").strip())
    method = str(payload.get("method") or payload.get("provider") or payload.get("engine") or "ocr")
    prefix = "Bildschirmtext per UIA gelesen." if method == "uia_text" else "Bildschirmtext gelesen."
    if text:
        return f"{prefix} Textanfang: {text[:300]}"
    if data.get("success") is False and data.get("error"):
        return f"Bildschirmtext konnte nicht gelesen werden: {str(data.get('error'))[:180]}"
    return f"{prefix} Kein Text erkannt."


def _format_desktop_engine_status_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    providers = data.get("providers") if isinstance(data.get("providers"), list) else []
    active: list[str] = []
    optional_missing: list[str] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = _short_visible_label(provider.get("id"), fallback="provider", limit=40)
        if provider.get("active"):
            active.append(provider_id.upper() if provider_id in {"uia", "ocr"} else provider_id)
        elif provider.get("optional") and not provider.get("available"):
            optional_missing.append(provider_id)
    active_text = ", ".join(active) if active else "keine aktiven Provider erkannt"
    optional_text = f" Optionale Provider noch nicht aktiv: {', '.join(optional_missing)}." if optional_missing else ""
    return f"Desktop-Engine bereit. Aktive Provider: {active_text}.{optional_text} Mutierende Aktionen bleiben hinter Lexa-Freigabe."


def _format_desktop_engine_observe_user_summary(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    titles = summary.get("window_titles") if isinstance(summary.get("window_titles"), list) else []
    title = _short_visible_label(titles[0] if titles else data.get("window"), fallback="aktuelles Fenster", limit=100)
    controls = int(summary.get("control_count") or 0)
    text_preview = _short_visible_label(summary.get("text_preview"), fallback="", limit=220)
    errors = data.get("errors") if isinstance(data.get("errors"), dict) else {}
    error_bits = [str(value).strip() for value in errors.values() if str(value or "").strip()]
    if controls or text_preview:
        text_part = f" Textanfang: {text_preview}" if text_preview else ""
        return f'Desktop-Engine hat "{title}" beobachtet: {controls} Controls erkannt.{text_part} Ich habe nichts veraendert.'
    if error_bits:
        return f'Desktop-Engine konnte "{title}" nicht voll beobachten: {error_bits[0][:180]}. Ich habe nichts veraendert.'
    return f'Desktop-Engine hat "{title}" beobachtet, aber keine Controls oder lesbaren Texte erkannt. Ich habe nichts veraendert.'


def _hermes_screen_text_needs_llm_followup(user_message: str) -> bool:
    text = _normalize_agent_text(user_message)
    return any(term in text for term in (
        "sag mir",
        "sage mir",
        "welchen",
        "welche",
        "was soll",
        "was wuerdest",
        "was wurdest",
        "naechstes",
        "nachstes",
        "entscheide",
        "empfiehl",
    ))


def _format_tool_result(action_name: str, result: dict) -> str:
    """Format tool result as concise string for LLM context."""
    if result.get("success"):
        data = result.get("data", "OK")
        if action_name == "system_info":
            formatted_system = _format_system_info_result(data)
            if formatted_system:
                return formatted_system
        if isinstance(data, dict):
            # Truncate large dicts
            text = json.dumps(data, ensure_ascii=False, default=str)
            if len(text) > 1500:
                text = text[:1500] + "... (gekuerzt)"
            return f"[{action_name}] Erfolgreich: {text}"
        elif isinstance(data, list):
            text = json.dumps(data[:20], ensure_ascii=False, default=str)
            suffix = f" (+{len(data) - 20} weitere)" if len(data) > 20 else ""
            return f"[{action_name}] Erfolgreich: {text}{suffix}"
        else:
            text = str(data)
            if len(text) > 1500:
                text = text[:1500] + "..."
            return f"[{action_name}] Erfolgreich: {text}"
    else:
        error = result.get("error", "Unbekannter Fehler")
        return f"[{action_name}] Fehlgeschlagen: {error}"


def _build_step_reflection_message(action_name: str, exec_result: dict, remaining_steps: int) -> str:
    status = "erfolgreich" if exec_result.get("success") else "fehlgeschlagen"
    formatted = _format_tool_result(action_name, exec_result)
    return (
        "[AGENT MINI-REFLEXION]\n"
        f"Der gerade ausgefuehrte Schritt '{action_name}' war {status}.\n"
        f"Ergebnis: {formatted}\n"
        f"Im urspruenglichen Tool-Batch warten noch {remaining_steps} Schritt(e).\n"
        "Pruefe vor dem naechsten Tool-Call kurz: Liefert dieses Ergebnis genug Information "
        "fuer den naechsten Schritt? Wenn nein, passe den Plan an, hole fehlende Information "
        "oder frage den User. Fuehre den naechsten Tool-Call nur aus, wenn er nach diesem "
        "Zwischenergebnis weiterhin sinnvoll und sicher ist."
    )


def _agent_tool_call_signature(action_name: str, params: dict | None) -> str:
    try:
        payload = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        payload = str(params or {})
    return f"{action_name}:{payload}"


def _build_tool_self_correction_message(action_name: str, params: dict | None, exec_result: dict) -> str:
    formatted = _format_tool_result(action_name, exec_result)
    try:
        args_text = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        args_text = str(params or {})
    return (
        f"[TOOL ERGEBNIS] {formatted}\n"
        "[AGENT SELF-CORRECTION]\n"
        f"Der letzte Tool-Call '{action_name}' mit Argumenten {args_text} ist fehlgeschlagen. "
        "Du darfst denselben Tool-Call mit denselben Argumenten nicht direkt wiederholen. "
        "Analysiere den Fehler, korrigiere die Argumente, nutze ein anderes Tool oder erklaere "
        "dem User klar, warum der Schritt nicht moeglich ist."
    )


def _normalize_agent_worker(worker: str | None) -> str:
    return "hermes" if str(worker or "").strip().lower() == "hermes" else "lexa"


def _normalize_agent_text(value: str) -> str:
    text = str(value or "")
    for source, target in {
        "ä": "ae",
        "Ä": "ae",
        "ö": "oe",
        "Ö": "oe",
        "ü": "ue",
        "Ü": "ue",
        "ß": "ss",
        "ẞ": "ss",
    }.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return (
        text
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        .replace("Ã¤", "ae").replace("Ã¶", "oe").replace("Ã¼", "ue").replace("ÃŸ", "ss")
        .replace("Ã„", "ae").replace("Ã–", "oe").replace("Ãœ", "ue")
    )


def _clean_hermes_ui_target(value: str) -> str:
    target = str(value or "").strip(" ._-")
    target = re.split(
        r"\b(?:ich\s+)?(?:bestaetige|bestatige|bestaetigen|bestatigen|confirm|confirmed|freigabe)\b(?:\s+es|\s+das)?",
        target,
        maxsplit=1,
    )[0]
    target = re.split(
        r"\b(?:im|in|am|auf)\s+(?:aktuellen|aktiven|sichtbaren)?\s*(?:fenster|bildschirm|screen)\b",
        target,
        maxsplit=1,
    )[0]
    target = re.split(r"\b(?:aendere|andere|veraendere|verandere)\s+nichts\b", target, maxsplit=1)[0]
    target = re.split(r"\b(?:und|aber)\b", target, maxsplit=1)[0]
    target = re.split(r"[,.;:!?]", target, maxsplit=1)[0]
    target = re.sub(r"\b(?:button|btn|knopf|taste)\b", "", target)
    return target.strip(" ._-")


def _extract_hermes_window_hint(value: str) -> str:
    text = str(value or "").strip()
    known_app_window = r"notepad|editor|discord|spotify|chrome|brave|code|vscode|explorer|whatsapp|telegram|edge|firefox|obsidian"
    patterns = (
        r"\b(?:im|in|ins)\s+(?:fenster|window|app)\s+(?P<window>.+?)(?=\s+(?:und|aber|durch|aus|vor)\b|[,.;!?]|$)",
        r"\b(?:das|den|die|dem)?\s*(?:fenster|window|app)(?!\s+(?:und|aber|mit|per)\b)\s+(?P<window>.+?)(?=\s+(?:mit|und|aber|per|durch|aus|vor)\b|[,.;!?]|$)",
        rf"\b(?:in|bei|aus|von)\s+(?P<window>{known_app_window})(?=\s|[,.;!?]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        window = re.sub(r"\s+", " ", match.group("window").strip(" .,:;!?"))
        if _normalize_agent_text(window) in {
            "aktuelles fenster",
            "aktuellen fenster",
            "aktives fenster",
            "aktiven fenster",
            "aktuelles window",
        }:
            continue
        if _normalize_agent_text(window).startswith(("und ", "aber ", "mit ", "per ")):
            continue
        if window:
            return window[:80]
    return ""


def _hermes_forced_first_tool(worker: str, user_message: str) -> tuple[str, dict] | None:
    if worker != "hermes":
        return None
    text = _normalize_agent_text(user_message)
    desktop_engine_terms = (
        "desktop-engine",
        "desktop engine",
        "desktopengine",
        "desktop_engine",
        "hermes engine",
    )
    if any(term in text for term in desktop_engine_terms):
        if any(term in text for term in ("status", "provider", "providers", "bereit", "ready")):
            return ("desktop_engine_status", {})
        if any(term in text for term in ("beobachte", "beobachten", "observe", "analysiere", "analysieren", "scanne", "scan")):
            params = {"include_text": True, "max_depth": 3, "max_controls": 80}
            window = _extract_hermes_window_hint(user_message)
            if window:
                params["window"] = window
            return ("desktop_engine_observe", params)

    system_terms = (
        "systemstatus", "system status", "system-info", "system info",
        "pc status", "pc-status", "status vom system",
    )
    metric_terms = (
        "cpu", "ram", "arbeitsspeicher", "speicherplatz", "speicher", "disk",
        "platte", "festplatte", "auslastung",
    )
    asks_status = any(term in text for term in system_terms)
    asks_metrics = sum(1 for term in metric_terms if term in text) >= 2
    if asks_status or asks_metrics:
        return ("system_info", {})

    position_terms = (
        "mausposition", "maus position", "cursor", "zeiger",
        "bildschirmgro", "bildschirm gro", "screen size", "screen resolution",
        "aufloesung", "auflosung",
    )
    if any(term in text for term in position_terms):
        return ("desktop_position", {})

    screen_text_terms = (
        "bildschirmtext", "bildschirm text", "text auf dem bildschirm",
        "fenstertext", "lies den fenstertext", "lese den fenstertext",
        "lies den bildschirm", "lese den bildschirm", "ocr", "screen text",
        "lies mir den text", "lese mir den text", "lies mir bitte den text",
        "lese mir bitte den text", "lies den text vor", "lese den text vor",
        "lies den text", "lese den text", "lies bitte den text", "lese bitte den text",
        "lies kurz den text", "lese kurz den text", "lies mal den text", "lese mal den text",
        "zeig mir den text", "zeige mir den text", "zeig den text", "zeige den text",
        "was steht", "read screen", "read the screen", "read text",
    )
    if any(term in text for term in screen_text_terms):
        params = {}
        window = _extract_hermes_window_hint(user_message)
        if window:
            params["window"] = window
        return ("screen_read_text", params)

    ui_tree_terms = (
        "echte windows controls", "windows controls", "ui controls", "echte controls",
        "klickbare buttons", "klickbare controls", "buttons im aktuellen fenster",
        "controls im aktuellen fenster", "was siehst du", "was sieht", "was erkennst",
        "was ist auf dem bildschirm", "was ist offen",
    )
    if any(term in text for term in ui_tree_terms):
        params = {"max_depth": 3, "max_controls": 80}
        window = _extract_hermes_window_hint(user_message)
        if window:
            params["window"] = window
        return ("ui_tree", params)

    ui_find_match = re.search(
        r"\b(?:finde|such(?:e)?|suche|zeige|pruefe|prufe)\b"
        r".{0,40}?\b(?:button|btn|knopf|taste|control|element)\b"
        r"\s+(?P<target>[a-z0-9][a-z0-9 ._-]{1,80})",
        text,
    )
    if ui_find_match:
        target = _clean_hermes_ui_target(ui_find_match.group("target"))
        if target:
            params = {"text": target}
            if any(word in text for word in ("button", "btn", "knopf", "taste")):
                params["control_type"] = "Button"
            return ("ui_find", params)

    click_match = re.search(
        r"\b(?:klick(?:e|en)?|kilck(?:e|en)?|klcik(?:e|en)?|klcick(?:e|en)?|click|drueck(?:e|en)?|druck(?:e|en)?)\b"
        r"(?:\s+(?:bitte|mal|kurz))?"
        r"(?:\s+(?:auf|den|die|das|einen|eine|einem|einer|irgend\s+einen|irgendeinen|anderen|andere))*"
        r"\s+(?P<target>[a-z0-9][a-z0-9 ._-]{1,80})",
        text,
    )
    if click_match:
        target = _clean_hermes_ui_target(click_match.group("target"))
        if target:
            return ("ui_click", {"text": target})

    return None


def _hermes_desktop_controller_required(worker: str, user_message: str) -> bool:
    if worker != "hermes":
        return False
    text = _normalize_agent_text(user_message)
    if any(term in text for term in (
        "systemstatus", "system status", "system-info", "system info",
        "pc status", "pc-status", "status vom system",
    )):
        return False
    metric_terms = (
        "cpu", "ram", "arbeitsspeicher", "speicherplatz", "speicher", "disk",
        "platte", "festplatte", "auslastung",
    )
    if sum(1 for term in metric_terms if term in text) >= 2:
        return False
    try:
        from companion.hermes_desktop import (
            classify_desktop_instruction,
            is_multi_step_desktop_prompt,
            split_hermes_desktop_instructions,
        )

        if is_multi_step_desktop_prompt(user_message):
            return True
        for instruction in split_hermes_desktop_instructions(user_message):
            kind = classify_desktop_instruction(instruction)
            if kind in {"find", "type", "hotkey", "scroll", "wait"}:
                return True
            if kind == "click" and _extract_hermes_window_hint(instruction):
                return True
        return False
    except Exception as exc:
        logger.debug("Hermes desktop controller precheck failed: %s", exc)
        return False


def _build_agent_context(worker: str) -> str:
    base = (
        "Du bist im AGENT-MODUS. Du fuehrst mehrstufige Aufgaben aus.\n"
        "REGELN:\n"
        "- Plane ZUERST welche Schritte noetig sind, dann fuehre sie einzeln aus.\n"
        "- Nach jedem Schritt bekommst du das Ergebnis und entscheidest den naechsten.\n"
        "- Wenn du FERTIG bist, antworte mit normalem Text (KEIN Tool Call).\n"
        "- Maximal {max_steps} Schritte pro Aufgabe.\n"
        "- Bei Fehlern: versuche eine Alternative oder erklaere das Problem.\n"
        "- Fasse am Ende zusammen was du getan hast.\n"
    ).format(max_steps=AGENT_MAX_STEPS)
    if worker != "hermes":
        return base
    return (
        base
        + "\nHERMES-WORKER-MODUS:\n"
        "- Du bist Hermes, der PC-Worker hinter Lexa. Lexa ist Chat-, Kontroll- und Sicherheits-Schicht.\n"
        "- Der User schreibt Befehle in Lexa; Lexa delegiert sie an dich. Entferne gedanklich Prefixe wie 'Hermes' oder 'Lexa sag Hermes'.\n"
        "- Nutze ausschliesslich die bereitgestellten Lexa-Tools fuer PC-Aktionen. Keine rohen Shell-/PowerShell-Befehle erfinden.\n"
        "- Apps oeffnest du mit app_open, Ordner legst du mit folder_create an, neue Text-/Code-Dateien schreibst du mit file_write.\n"
        "- file_write erstellt nur neue Dateien; wenn eine Datei existiert, melde das statt zu ueberschreiben.\n"
        "- Fuer echte Desktop-Steuerung: orientiere dich zuerst mit desktop_engine_observe oder ui_tree/ui_find fuer echte Windows-Controls; nutze screen_read_text/OCR nur als Fallback.\n"
        "- Wenn der User mehrere Desktop-Schritte, Scrollen, Tippen, Hotkeys oder Warten in einem Desktop-Auftrag nennt, nutze hermes_desktop_task: es beobachtet/sucht read-only, nutzt OCR als Fallback und bereitet riskante Aktionen fuer Lexa-Freigabe vor.\n"
        "- Fuer Klicks auf sichtbare Buttons nutze bevorzugt ui_click statt desktop_click_text. Danach darfst du kontrolliert desktop_move, desktop_click, desktop_type, desktop_hotkey, desktop_scroll und desktop_wait nutzen.\n"
        "- Wenn mehrere passende Controls gefunden werden, frage nach statt zu raten. Halte nach jeder mutierenden Aktion an und beobachte neu.\n"
        "- Vor Klicks, Tippen und Hotkeys muss klar sein, welches Fenster/Feld aktiv ist. Wenn nicht klar: erst schauen oder nachfragen.\n"
        "- Erfinde keine Systemwerte und keine UI-Zustaende. Wenn ein Sicht-/PC-Tool fehlschlaegt, melde das statt zu raten.\n"
        "- Riskante oder bestaetigungspflichtige Aktionen werden angehalten; sage dann klar, welche Bestaetigung fehlt.\n"
    )


# ══════════════════════════════════════════════════
#  AGENT LOOP (async generator — yields SSE events)
# ══════════════════════════════════════════════════

async def run_agent(
    user_message: str,
    conversation_history: list[dict],
    *,
    worker: str = "lexa",
    trace_source: str = "runtime",
    synthetic_context: bool = False,
) -> AsyncGenerator[dict, None]:
    """Run the multi-step agent loop.

    Yields SSE-compatible event dicts:
    - {"type": "plan", "message": "..."} — Agent erklaert seinen Plan
    - {"type": "step_start", "step": {...}} — Schritt startet
    - {"type": "step_done", "step": {...}} — Schritt fertig
    - {"type": "step_blocked", "step": {...}} — Schritt braucht Bestaetigung
    - {"type": "thinking", "message": "..."} — Agent denkt nach (Reflect)
    - {"type": "done", "run": {...}} — Alles fertig
    - {"type": "error", "message": "..."} — Fehler
    """
    from backend.ai_engine import chat

    worker_name = _normalize_agent_worker(worker)
    run = AgentRun(user_message=user_message, worker=worker_name)
    if _agent_ledger_enabled():
        run.ledger = _build_agent_run_ledger(run)
    trace_recorder = None
    trace_policy = None
    if _agent_trace_enabled() and _agent_trace_sampling_enabled():
        trace_recorder, trace_policy = _build_agent_trace_recorder(
            run,
            source=trace_source,
            synthetic_context=synthetic_context,
        )
    if trace_recorder is not None:
        from backend.agent_protocol import stable_hash

        _record_agent_trace(
            trace_recorder,
            trace_policy,
            "run_started",
            risk_level="medium",
            step_index=-1,
            summary="Agent run started",
            metadata={
                "message_hash": stable_hash(user_message)[:12],
                "history_count": len(conversation_history),
                "trace_source": trace_source,
                "synthetic_context": synthetic_context,
            },
        )
        if run.ledger is not None:
            _record_agent_trace(
                trace_recorder,
                trace_policy,
                "plan_created",
                risk_level=run.ledger.plan.risk_level,
                step_index=-1,
                summary="Agent ledger plan created",
                metadata={
                    "budget_steps": run.ledger.plan.budget_steps,
                    "budget_seconds": run.ledger.plan.budget_seconds,
                    "forbidden_tools": run.ledger.plan.forbidden_tools,
                },
            )
    audit_log("agent", "start", _agent_start_audit_details(run.id, worker_name, user_message))

    # Build agent-specific system context
    agent_context = _build_agent_context(worker_name)

    # Working conversation for the agent (separate from global history)
    agent_messages: list[dict] = []

    # Seed with recent conversation context (last 10 messages)
    recent = conversation_history[-10:] if len(conversation_history) > 10 else list(conversation_history)
    agent_messages.extend(recent)

    # Add the user's request
    agent_messages.append({"role": "user", "content": user_message})

    step_count = 0
    failed_tool_attempts: dict[str, int] = {}
    forced_first_tool = (
        ("hermes_desktop_task", {"message": user_message})
        if _hermes_desktop_controller_required(worker_name, user_message)
        else _hermes_forced_first_tool(worker_name, user_message)
    )
    forced_direct_summary = ""
    if forced_first_tool is not None:
        action_name, params = forced_first_tool
        step = AgentStep(
            index=step_count,
            action=action_name,
            params=params,
            status=StepStatus.RUNNING,
            started_at=time.time(),
        )
        run.steps.append(step)
        ledger_action_id = f"step-{step_count}"
        permission_for_step = is_command_allowed(action_name)
        forced_step_blocked = False
        if run.ledger is not None:
            _append_ledger_action(
                run.ledger,
                action_id=ledger_action_id,
                action_name=action_name,
                params=params,
                permission=permission_for_step,
            )
            if _agent_policy_enforce_enabled():
                from backend.agent_protocol import validate_action_against_plan

                decision = validate_action_against_plan(run.ledger.actions[-1], run.ledger.plan, step_index=step_count)
                if not decision.allowed:
                    step.status = StepStatus.BLOCKED
                    step.error = "Agent policy review required: " + "; ".join(decision.reasons)
                    step.duration_ms = (time.time() - step.started_at) * 1000
                    _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                    yield {"type": "step_blocked", "step": step.to_dict()}
                    agent_messages.append({
                        "role": "user",
                        "content": f"[TOOL ERGEBNIS] {action_name}: Agent policy requires review.",
                    })
                    forced_step_blocked = True
                    step_count += 1
        if not forced_step_blocked:
            yield {"type": "step_start", "step": step.to_dict()}
            try:
                execute_kwargs = {}
                execute_tool = _execute_tool
                if _execute_tool_supports_plan_length(execute_tool):
                    execute_kwargs["plan_length"] = 1
                exec_result = await asyncio.wait_for(
                    execute_tool(action_name, params, **execute_kwargs),
                    timeout=AGENT_STEP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                exec_result = {"success": False, "error": f"Timeout nach {AGENT_STEP_TIMEOUT}s"}
                step.duration_ms = AGENT_STEP_TIMEOUT * 1000
            else:
                step.duration_ms = (time.time() - step.started_at) * 1000

            if exec_result.get("needs_confirmation"):
                step.status = StepStatus.NEEDS_CONFIRMATION
                step.error = exec_result.get("error", "Bestaetigung noetig")
                step.result = _format_tool_result(action_name, exec_result)
                if run.ledger is not None:
                    _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                yield {"type": "step_blocked", "step": step.to_dict()}
                run.status = "completed"
                run.summary = (
                    f"Bestaetigung noetig fuer {action_name}. "
                    "Antworte kurz mit 'ja', wenn Lexa diese vorbereitete Aktion wirklich ausfuehren soll."
                )
                agent_messages.append({
                    "role": "user",
                    "content": f"[TOOL ERGEBNIS] {step.result}",
                })
            else:
                if exec_result.get("success"):
                    step.status = StepStatus.SUCCESS
                else:
                    step.status = StepStatus.FAILED
                    step.error = exec_result.get("error", "Unbekannter Fehler")
                step.result = _format_tool_result(action_name, exec_result)
                if run.ledger is not None:
                    _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                yield {"type": "step_done", "step": step.to_dict()}
                agent_messages.append({
                    "role": "user",
                    "content": f"[TOOL ERGEBNIS] {step.result}",
                })
                if action_name == "desktop_position" and exec_result.get("success"):
                    forced_direct_summary = _format_desktop_position_user_summary(exec_result.get("data", {}))
                elif action_name == "desktop_engine_status" and exec_result.get("success"):
                    forced_direct_summary = _format_desktop_engine_status_user_summary(exec_result.get("data", {}))
                elif action_name == "desktop_engine_observe" and exec_result.get("success"):
                    forced_direct_summary = _format_desktop_engine_observe_user_summary(exec_result.get("data", {}))
                elif action_name == "ui_tree" and exec_result.get("success"):
                    forced_direct_summary = _format_ui_tree_user_summary(exec_result.get("data", {}))
                elif action_name == "ui_find" and exec_result.get("success"):
                    forced_direct_summary = _format_ui_find_user_summary(exec_result.get("data", {}))
                elif action_name == "hermes_desktop_task" and exec_result.get("success"):
                    forced_direct_summary = _format_hermes_desktop_task_user_summary(exec_result.get("data", {}))
                elif (
                    action_name == "screen_read_text"
                    and exec_result.get("success")
                    and not _hermes_screen_text_needs_llm_followup(user_message)
                ):
                    forced_direct_summary = _format_screen_read_text_user_summary(exec_result.get("data", {}))
            step_count += 1

    if forced_direct_summary:
        run.status = "completed"
        run.summary = forced_direct_summary
        yield {"type": "thinking", "message": forced_direct_summary}

    while run.status == "running" and step_count < AGENT_MAX_STEPS:
        # Call LLM with tools
        # First call: user_message goes through normal _build_messages path
        # Subsequent calls: user_message=None, last msg is already in agent_messages
        try:
            msg = user_message if step_count == 0 else None
            result = await asyncio.to_thread(
                chat,
                msg,
                agent_messages,
                system_extra=agent_context,
            )
        except Exception as e:
            logger.error(f"Agent LLM call failed: {e}", exc_info=True)
            run.status = "failed"
            run.summary = f"KI-Fehler: {e}"
            if trace_recorder is not None:
                _record_agent_trace(
                    trace_recorder,
                    trace_policy,
                    "run_failed",
                    risk_level="high",
                    step_index=step_count,
                    summary="Agent LLM call failed",
                    metadata={"error": str(e)},
                )
            yield {"type": "error", "message": f"KI-Fehler: {e}"}
            break

        result_type = result.get("type", "text")

        # ── Text response = Agent is done ──
        if result_type == "text":
            content = result.get("content", "")
            run.status = "completed"
            run.summary = content
            run.total_duration_ms = (time.time() - run.started_at) * 1000

            # Add to agent messages for context
            agent_messages.append({"role": "assistant", "content": content})

            yield {"type": "thinking", "message": content}
            audit_log("agent", "completed", f"RUN={run.id} STEPS={step_count}")
            break

        # ── Tool call = Execute next step ──
        if result_type == "tool_call":
            tool_calls = result.get("tool_calls", [])
            ai_content = result.get("content", "")

            if ai_content:
                yield {"type": "thinking", "message": ai_content}
                agent_messages.append({"role": "assistant", "content": ai_content})

            if not tool_calls:
                # LLM returned tool_call type but no actual calls — treat as done
                run.status = "completed"
                run.summary = ai_content or "Fertig."
                break

            # Process each tool call in this turn
            for call_index, tc in enumerate(tool_calls):
                if step_count >= AGENT_MAX_STEPS:
                    yield {
                        "type": "error",
                        "message": f"Maximum {AGENT_MAX_STEPS} Schritte erreicht.",
                    }
                    run.status = "completed"
                    run.summary = f"Abgebrochen nach {AGENT_MAX_STEPS} Schritten."
                    break

                action_name = tc.get("name", "")
                params, argument_error = _coerce_agent_tool_arguments(
                    tc.get("arguments", _AGENT_ARGS_MISSING)
                )

                if argument_error:
                    logger.warning(
                        "Rejected invalid agent tool call %s: %s",
                        action_name,
                        argument_error,
                    )
                    audit_log(action_name, "agent_tool_schema_invalid", argument_error[:200])
                    step = AgentStep(
                        index=step_count,
                        action=action_name,
                        params={},
                        status=StepStatus.FAILED,
                        error=_TOOL_ARGUMENT_ERROR_REPLY,
                        started_at=time.time(),
                    )
                    step.duration_ms = (time.time() - step.started_at) * 1000
                    run.steps.append(step)
                    yield {"type": "step_done", "step": step.to_dict()}
                    agent_messages.append({
                        "role": "user",
                        "content": f"[TOOL ERGEBNIS] {action_name}: {_TOOL_ARGUMENT_ERROR_REPLY}",
                    })
                    step_count += 1
                    continue

                step = AgentStep(
                    index=step_count,
                    action=action_name,
                    params=params,
                    status=StepStatus.RUNNING,
                    started_at=time.time(),
                )
                run.steps.append(step)
                ledger_action_id = f"step-{step_count}"
                permission_for_step = is_command_allowed(action_name)
                if trace_recorder is not None:
                    _record_agent_trace(
                        trace_recorder,
                        trace_policy,
                        "tool_considered",
                        risk_level=_infer_agent_action_risk(action_name, permission_for_step),
                        step_index=step_count,
                        summary="Agent considered tool",
                        metadata={"tool_name": action_name, "permission": permission_for_step, "arg_keys": sorted((params or {}).keys())},
                        related_action_id=ledger_action_id,
                        related_tool=action_name,
                    )
                    _record_agent_trace(
                        trace_recorder,
                        trace_policy,
                        "tool_selected",
                        risk_level=_infer_agent_action_risk(action_name, permission_for_step),
                        step_index=step_count,
                        summary="Agent selected tool",
                        metadata={"tool_name": action_name, "permission": permission_for_step},
                        related_action_id=ledger_action_id,
                        related_tool=action_name,
                    )
                if run.ledger is not None:
                    _append_ledger_action(
                        run.ledger,
                        action_id=ledger_action_id,
                        action_name=action_name,
                        params=params,
                        permission=permission_for_step,
                    )

                    if _agent_policy_enforce_enabled():
                        from backend.agent_protocol import validate_action_against_plan

                        decision = validate_action_against_plan(run.ledger.actions[-1], run.ledger.plan, step_index=step_count)
                        if not decision.allowed:
                            step.status = StepStatus.BLOCKED
                            step.error = "Agent policy review required: " + "; ".join(decision.reasons)
                            if trace_recorder is not None:
                                _record_agent_trace(
                                    trace_recorder,
                                    trace_policy,
                                    "action_finished",
                                    risk_level=run.ledger.actions[-1].risk_level,
                                    step_index=step_count,
                                    summary="Agent policy blocked action",
                                    metadata={"reasons": decision.reasons},
                                    related_action_id=ledger_action_id,
                                    related_tool=action_name,
                                )
                            _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                            yield {"type": "step_blocked", "step": step.to_dict()}
                            agent_messages.append({
                                "role": "user",
                                "content": f"[TOOL ERGEBNIS] {action_name}: Agent policy requires review.",
                            })
                            step_count += 1
                            continue

                yield {"type": "step_start", "step": step.to_dict()}
                if trace_recorder is not None:
                    _record_agent_trace(
                        trace_recorder,
                        trace_policy,
                        "action_started",
                        risk_level=_infer_agent_action_risk(action_name, permission_for_step),
                        step_index=step_count,
                        summary="Agent action started",
                        metadata={"tool_name": action_name, "arg_keys": sorted((params or {}).keys())},
                        related_action_id=ledger_action_id,
                        related_tool=action_name,
                    )

                # Execute the tool
                try:
                    execute_kwargs = {}
                    execute_tool = _execute_tool
                    if _execute_tool_supports_plan_length(execute_tool):
                        execute_kwargs["plan_length"] = len(tool_calls)
                    exec_result = await asyncio.wait_for(
                        execute_tool(action_name, params, **execute_kwargs),
                        timeout=AGENT_STEP_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    step.status = StepStatus.FAILED
                    step.error = f"Timeout nach {AGENT_STEP_TIMEOUT}s"
                    step.duration_ms = AGENT_STEP_TIMEOUT * 1000
                    if run.ledger is not None:
                        if trace_recorder is not None:
                            _record_agent_trace(
                                trace_recorder,
                                trace_policy,
                                "verification_started",
                                risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                                step_index=step_count,
                                summary="Agent verification started",
                                metadata={"check": "agent_step_status"},
                                related_action_id=ledger_action_id,
                                related_tool=action_name,
                            )
                        _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                        if trace_recorder is not None:
                            _record_agent_trace(
                                trace_recorder,
                                trace_policy,
                                "verification_finished",
                                risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                                step_index=step_count,
                                summary="Agent verification finished",
                                metadata={"passed": False, "status": step.status.value},
                                related_action_id=ledger_action_id,
                                related_tool=action_name,
                            )
                    if trace_recorder is not None:
                        _record_agent_trace(
                            trace_recorder,
                            trace_policy,
                            "action_finished",
                            risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                            step_index=step_count,
                            summary="Agent action timed out",
                            metadata={"status": step.status.value},
                            related_action_id=ledger_action_id,
                            related_tool=action_name,
                        )
                    yield {"type": "step_done", "step": step.to_dict()}
                    # Tell LLM about the timeout
                    agent_messages.append({
                        "role": "user",
                        "content": f"[TOOL ERGEBNIS] {action_name}: Timeout nach {AGENT_STEP_TIMEOUT}s",
                    })
                    step_count += 1
                    continue

                step.duration_ms = (time.time() - step.started_at) * 1000

                # Handle blocked/confirmation commands
                if exec_result.get("needs_confirmation"):
                    step.status = StepStatus.NEEDS_CONFIRMATION
                    step.error = exec_result.get("error", "Bestaetigung noetig")
                    if run.ledger is not None:
                        if trace_recorder is not None:
                            _record_agent_trace(
                                trace_recorder,
                                trace_policy,
                                "verification_started",
                                risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                                step_index=step_count,
                                summary="Agent verification started",
                                metadata={"check": "agent_step_status"},
                                related_action_id=ledger_action_id,
                                related_tool=action_name,
                            )
                        _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                        if trace_recorder is not None:
                            _record_agent_trace(
                                trace_recorder,
                                trace_policy,
                                "verification_finished",
                                risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                                step_index=step_count,
                                summary="Agent verification finished",
                                metadata={"passed": False, "status": step.status.value},
                                related_action_id=ledger_action_id,
                                related_tool=action_name,
                            )
                    if trace_recorder is not None:
                        _record_agent_trace(
                            trace_recorder,
                            trace_policy,
                            "action_finished",
                            risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                            step_index=step_count,
                            summary="Agent action needs confirmation",
                            metadata={"status": step.status.value},
                            related_action_id=ledger_action_id,
                            related_tool=action_name,
                        )
                    yield {"type": "step_blocked", "step": step.to_dict()}
                    run.status = "completed"
                    run.summary = (
                        f"Bestaetigung noetig fuer {action_name}. "
                        "Antworte kurz mit 'ja', wenn Lexa diese vorbereitete Aktion wirklich ausfuehren soll."
                    )
                    # Tell LLM this step needs confirmation — skip it
                    agent_messages.append({
                        "role": "user",
                        "content": (
                            f"[TOOL ERGEBNIS] {action_name}: Befehl braucht User-Bestaetigung. "
                            f"Der Schritt wurde nicht ausgefuehrt."
                        ),
                    })
                    step_count += 1
                    break

                repeat_failure_count = 0
                if exec_result.get("success"):
                    step.status = StepStatus.SUCCESS
                    step.result = _format_tool_result(action_name, exec_result)
                else:
                    step.status = StepStatus.FAILED
                    step.error = exec_result.get("error", "Unbekannter Fehler")
                    step.result = _format_tool_result(action_name, exec_result)
                    failure_signature = _agent_tool_call_signature(action_name, params)
                    repeat_failure_count = failed_tool_attempts.get(failure_signature, 0) + 1
                    failed_tool_attempts[failure_signature] = repeat_failure_count
                    if repeat_failure_count >= 2:
                        step.error = (
                            f"{step.error} "
                            "(identischer Tool-Call ist zweimal fehlgeschlagen; Agent-Loop abgebrochen)"
                        )
                        step.result = _format_tool_result(action_name, {**exec_result, "error": step.error})

                yield {"type": "step_done", "step": step.to_dict()}
                if run.ledger is not None:
                    if trace_recorder is not None:
                        _record_agent_trace(
                            trace_recorder,
                            trace_policy,
                            "verification_started",
                            risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                            step_index=step_count,
                            summary="Agent verification started",
                            metadata={"check": "agent_step_status"},
                            related_action_id=ledger_action_id,
                            related_tool=action_name,
                        )
                    _append_ledger_verification(run.ledger, action_id=ledger_action_id, step=step)
                    if trace_recorder is not None:
                        _record_agent_trace(
                            trace_recorder,
                            trace_policy,
                            "verification_finished",
                            risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                            step_index=step_count,
                            summary="Agent verification finished",
                            metadata={"passed": step.status == StepStatus.SUCCESS, "status": step.status.value},
                            related_action_id=ledger_action_id,
                            related_tool=action_name,
                        )
                if trace_recorder is not None:
                    _record_agent_trace(
                        trace_recorder,
                        trace_policy,
                        "action_finished",
                        risk_level=_infer_agent_action_risk(action_name, is_command_allowed(action_name)),
                        step_index=step_count,
                        summary="Agent action finished",
                        metadata={"status": step.status.value, "success": bool(exec_result.get("success"))},
                        related_action_id=ledger_action_id,
                        related_tool=action_name,
                    )

                # Feed result back to LLM for the next iteration
                if step.status == StepStatus.FAILED:
                    agent_messages.append({
                        "role": "user",
                        "content": _build_tool_self_correction_message(action_name, params, exec_result),
                    })
                    if repeat_failure_count >= 2:
                        run.status = "failed"
                        run.summary = (
                            f"Abgebrochen: '{action_name}' ist zweimal mit denselben Argumenten fehlgeschlagen."
                        )
                else:
                    formatted = _format_tool_result(action_name, exec_result)
                    agent_messages.append({
                        "role": "user",
                        "content": f"[TOOL ERGEBNIS] {formatted}",
                    })

                audit_log(
                    "agent",
                    "step_done",
                    f"RUN={run.id} STEP={step_count} ACTION={action_name} "
                    f"OK={exec_result.get('success')} DUR={step.duration_ms:.0f}ms",
                )
                step_count += 1
                if run.status == "failed":
                    break
                remaining_in_batch = len(tool_calls) - call_index - 1
                if remaining_in_batch > 0 and step_count < AGENT_MAX_STEPS:
                    agent_messages.append({
                        "role": "user",
                        "content": _build_step_reflection_message(action_name, exec_result, remaining_in_batch),
                    })
                    break

            if run.status == "failed":
                break

            # If we hit max steps inside the for loop, break outer while
            if step_count >= AGENT_MAX_STEPS:
                run.status = "completed"
                run.total_duration_ms = (time.time() - run.started_at) * 1000
                if not run.summary:
                    run.summary = f"Aufgabe nach {step_count} Schritten abgeschlossen."
                break

            continue

        # ── Error from LLM ──
        if result_type == "error":
            error_msg = result.get("content", "Unbekannter KI-Fehler")
            run.status = "failed"
            run.summary = error_msg
            yield {"type": "error", "message": error_msg}
            break

    # Final event
    run.total_duration_ms = (time.time() - run.started_at) * 1000
    if run.status == "running":
        run.status = "completed"
    if run.ledger is not None:
        _finalize_agent_ledger(run.ledger, run)
        if _agent_policy_enforce_enabled():
            from backend.agent_protocol import enforce_agent_policy

            enforce_agent_policy(run.ledger)
        if trace_recorder is not None:
            _record_agent_trace(
                trace_recorder,
                trace_policy,
                "review_created",
                risk_level=run.ledger.plan.risk_level,
                step_index=step_count,
                summary="Agent review created",
                metadata={"status": run.ledger.status.value, "review_required": bool(run.ledger.review and run.ledger.review.user_decision_required)},
            )
    if trace_recorder is not None:
        _record_agent_trace(
            trace_recorder,
            trace_policy,
            "run_finished" if run.status != "failed" else "run_failed",
            risk_level="medium",
            step_index=step_count,
            summary=f"Agent run {run.status}",
            metadata={"status": run.status, "steps": len(run.steps), "trace_write_errors": trace_recorder.write_errors},
        )
    yield {"type": "done", "run": run.to_dict()}
