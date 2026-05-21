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
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional

from backend.config import (
    AGENT_MAX_STEPS,
    AGENT_STEP_TIMEOUT,
    MAX_HISTORY,
    TOOL_USE_MAX_TOOLS,
)
from backend.security import is_command_allowed, audit_log, validate_params
from backend.action_parser import _ACTION_NAME_PATTERN, _sanitize_params
from backend.i18n import t

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


async def _execute_tool(action_name: str, params: dict) -> dict:
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

    # Check permission (before any heavy imports)
    permission = is_command_allowed(action_name)

    if permission == "blocked":
        audit_log(action_name, "agent_blocked")
        return {"success": False, "error": f"Befehl '{action_name}' ist blockiert."}

    if permission == "confirmation_required":
        audit_log(action_name, "agent_needs_confirmation")
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


def _format_tool_result(action_name: str, result: dict) -> str:
    """Format tool result as concise string for LLM context."""
    if result.get("success"):
        data = result.get("data", "OK")
        if isinstance(data, dict):
            # Truncate large dicts
            text = json.dumps(data, ensure_ascii=False, default=str)
            if len(text) > 1500:
                text = text[:1500] + "... (gekuerzt)"
            return f"[{action_name}] Erfolgreich: {text}"
        elif isinstance(data, list):
            text = json.dumps(data[:20], ensure_ascii=False, default=str)
            suffix = f" (+{len(data)-20} weitere)" if len(data) > 20 else ""
            return f"[{action_name}] Erfolgreich: {text}{suffix}"
        else:
            text = str(data)
            if len(text) > 1500:
                text = text[:1500] + "..."
            return f"[{action_name}] Erfolgreich: {text}"
    else:
        error = result.get("error", "Unbekannter Fehler")
        return f"[{action_name}] Fehlgeschlagen: {error}"


# ══════════════════════════════════════════════════
#  AGENT LOOP (async generator — yields SSE events)
# ══════════════════════════════════════════════════

async def run_agent(
    user_message: str,
    conversation_history: list[dict],
    *,
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

    run = AgentRun(user_message=user_message)
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
    audit_log("agent", "start", f"RUN={run.id} MSG={user_message[:100]}")

    # Build agent-specific system context
    agent_context = (
        "Du bist im AGENT-MODUS. Du fuehrst mehrstufige Aufgaben aus.\n"
        "REGELN:\n"
        "- Plane ZUERST welche Schritte noetig sind, dann fuehre sie einzeln aus.\n"
        "- Nach jedem Schritt bekommst du das Ergebnis und entscheidest den naechsten.\n"
        "- Wenn du FERTIG bist, antworte mit normalem Text (KEIN Tool Call).\n"
        "- Maximal {max_steps} Schritte pro Aufgabe.\n"
        "- Bei Fehlern: versuche eine Alternative oder erklaere das Problem.\n"
        "- Fasse am Ende zusammen was du getan hast.\n"
    ).format(max_steps=AGENT_MAX_STEPS)

    # Working conversation for the agent (separate from global history)
    agent_messages: list[dict] = []

    # Seed with recent conversation context (last 10 messages)
    recent = conversation_history[-10:] if len(conversation_history) > 10 else list(conversation_history)
    agent_messages.extend(recent)

    # Add the user's request
    agent_messages.append({"role": "user", "content": user_message})

    step_count = 0

    while step_count < AGENT_MAX_STEPS:
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
            for tc in tool_calls:
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
                    exec_result = await asyncio.wait_for(
                        _execute_tool(action_name, params),
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
                    # Tell LLM this step needs confirmation — skip it
                    agent_messages.append({
                        "role": "user",
                        "content": (
                            f"[TOOL ERGEBNIS] {action_name}: Befehl braucht User-Bestaetigung. "
                            f"Ueberspringe diesen Schritt und mache weiter mit dem naechsten."
                        ),
                    })
                    step_count += 1
                    continue

                if exec_result.get("success"):
                    step.status = StepStatus.SUCCESS
                    step.result = _format_tool_result(action_name, exec_result)
                else:
                    step.status = StepStatus.FAILED
                    step.error = exec_result.get("error", "Unbekannter Fehler")
                    step.result = _format_tool_result(action_name, exec_result)

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
