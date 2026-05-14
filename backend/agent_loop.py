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
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_message": self.user_message,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
        }


# ══════════════════════════════════════════════════
#  TOOL EXECUTION (sync, runs in thread pool)
# ══════════════════════════════════════════════════

def _execute_tool(action_name: str, params: dict) -> dict:
    """Execute a single tool call via CompanionEngine.

    Returns: {"success": bool, "data": ..., "error": ...}
    """
    # Validate action name (before any heavy imports)
    if not _ACTION_NAME_PATTERN.match(action_name):
        return {"success": False, "error": f"Ungueltiger Befehl: {action_name}"}

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
        safe_params = validate_params(action_name, params)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    safe_params = _sanitize_params(safe_params)

    # Execute (lazy import to avoid loading companion at module level)
    try:
        from companion.engine import companion
        result = companion.execute(action_name, safe_params)
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
                params = tc.get("arguments", {})

                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except (json.JSONDecodeError, TypeError):
                        params = {}

                step = AgentStep(
                    index=step_count,
                    action=action_name,
                    params=params,
                    status=StepStatus.RUNNING,
                    started_at=time.time(),
                )
                run.steps.append(step)

                yield {"type": "step_start", "step": step.to_dict()}

                # Execute the tool
                try:
                    exec_result = await asyncio.wait_for(
                        asyncio.to_thread(_execute_tool, action_name, params),
                        timeout=AGENT_STEP_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    step.status = StepStatus.FAILED
                    step.error = f"Timeout nach {AGENT_STEP_TIMEOUT}s"
                    step.duration_ms = AGENT_STEP_TIMEOUT * 1000
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
    yield {"type": "done", "run": run.to_dict()}
