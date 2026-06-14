"""Plan/Act/Verify/Review protocol primitives for Lexa agents.

This module is intentionally isolated from the runtime in Phase 3A. It gives
future agent work a stable, serializable ledger format with explicit safety
checks before any larger orchestration refactor begins.
"""

from __future__ import annotations

import json
import re
import hashlib
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


MAX_BUDGET_STEPS = 50
MAX_BUDGET_SECONDS = 3600
MAX_TRACE_SUMMARY_CHARS = 240
MAX_TRACE_METADATA_CHARS = 160
SECRET_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"),
]
VALID_TRACE_EVENT_TYPES = {
    "run_started",
    "plan_created",
    "tool_considered",
    "tool_selected",
    "action_started",
    "action_finished",
    "verification_started",
    "verification_finished",
    "review_created",
    "run_finished",
    "run_failed",
}


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class LedgerStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class AgentPolicyDecision:
    allowed: bool
    review_required: bool = False
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "review_required": self.review_required,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: Any) -> str:
    payload = json.dumps(redact_secrets(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def coerce_risk_level(value: RiskLevel | str) -> RiskLevel:
    try:
        return value if isinstance(value, RiskLevel) else RiskLevel(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid risk_level: {value!r}") from exc


def coerce_action_status(value: ActionStatus | str) -> ActionStatus:
    try:
        return value if isinstance(value, ActionStatus) else ActionStatus(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid action status: {value!r}") from exc


def coerce_ledger_status(value: LedgerStatus | str) -> LedgerStatus:
    try:
        return value if isinstance(value, LedgerStatus) else LedgerStatus(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid ledger status: {value!r}") from exc


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: _redact_match(match.group(0)), redacted)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_secrets(item) for key, item in value.items()}
    return value


def redacted_summary(value: Any, *, max_chars: int = MAX_TRACE_SUMMARY_CHARS) -> str:
    redacted = redact_secrets(value)
    text = redacted if isinstance(redacted, str) else json.dumps(redacted, sort_keys=True, ensure_ascii=True, default=str)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 15].rstrip() + " ... [truncated]"
    return text


def redacted_metadata(value: Any) -> Any:
    redacted = redact_secrets(value)
    if isinstance(redacted, dict):
        safe: dict[str, Any] = {}
        for key, item in redacted.items():
            key_text = str(key)
            if key_text.lower() in {"prompt", "content", "conversation", "memory", "clipboard", "args", "arguments"}:
                safe[key_text] = {"hash": stable_hash(item)[:12], "redacted": True}
            else:
                safe[key_text] = redacted_metadata(item)
        return safe
    if isinstance(redacted, list):
        return [redacted_metadata(item) for item in redacted[:20]]
    if isinstance(redacted, str):
        return redacted_summary(redacted, max_chars=MAX_TRACE_METADATA_CHARS)
    return redacted


def _redact_match(text: str) -> str:
    if text.lower().startswith("bearer "):
        return "Bearer [REDACTED]"
    if text.startswith("sk-"):
        return "sk-[REDACTED]"
    if "=" in text:
        return text.split("=", 1)[0] + "=[REDACTED]"
    if ":" in text:
        return text.split(":", 1)[0] + ": [REDACTED]"
    return "[REDACTED]"


@dataclass
class AgentPlan:
    goal: str
    risk_level: RiskLevel | str
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    budget_steps: int = 10
    budget_seconds: int = 300
    checkpoints: list[str] = field(default_factory=list)
    requires_user_review: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    max_tool_calls: int | None = None
    max_risky_tool_calls: int | None = None
    max_memory_reads: int | None = None
    max_os_writes: int | None = None
    max_runtime_seconds: int | None = None
    max_retry_count: int | None = None

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("goal must not be empty")
        self.risk_level = coerce_risk_level(self.risk_level)
        self.allowed_tools = _clean_string_list(self.allowed_tools, "allowed_tools")
        self.forbidden_tools = _clean_string_list(self.forbidden_tools, "forbidden_tools")
        overlap = sorted(set(self.allowed_tools).intersection(self.forbidden_tools))
        if overlap:
            raise ValueError(f"forbidden tools cannot also be allowed: {', '.join(overlap)}")
        if not 1 <= int(self.budget_steps) <= MAX_BUDGET_STEPS:
            raise ValueError(f"budget_steps must be between 1 and {MAX_BUDGET_STEPS}")
        if not 1 <= int(self.budget_seconds) <= MAX_BUDGET_SECONDS:
            raise ValueError(f"budget_seconds must be between 1 and {MAX_BUDGET_SECONDS}")
        self.max_tool_calls = _clean_optional_budget(self.max_tool_calls, "max_tool_calls", MAX_BUDGET_STEPS)
        self.max_risky_tool_calls = _clean_optional_budget(self.max_risky_tool_calls, "max_risky_tool_calls", MAX_BUDGET_STEPS)
        self.max_memory_reads = _clean_optional_budget(self.max_memory_reads, "max_memory_reads", MAX_BUDGET_STEPS)
        self.max_os_writes = _clean_optional_budget(self.max_os_writes, "max_os_writes", MAX_BUDGET_STEPS)
        self.max_runtime_seconds = _clean_optional_budget(self.max_runtime_seconds, "max_runtime_seconds", MAX_BUDGET_SECONDS)
        self.max_retry_count = _clean_optional_budget(self.max_retry_count, "max_retry_count", MAX_BUDGET_STEPS)
        self.checkpoints = _clean_string_list(self.checkpoints, "checkpoints", allow_empty=True)
        if self.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            self.requires_user_review = True

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "goal": self.goal,
                "risk_level": self.risk_level.value,
                "allowed_tools": self.allowed_tools,
                "forbidden_tools": self.forbidden_tools,
                "budget_steps": self.budget_steps,
                "budget_seconds": self.budget_seconds,
                "checkpoints": self.checkpoints,
                "requires_user_review": self.requires_user_review,
                "created_at": self.created_at,
                "max_tool_calls": self.max_tool_calls,
                "max_risky_tool_calls": self.max_risky_tool_calls,
                "max_memory_reads": self.max_memory_reads,
                "max_os_writes": self.max_os_writes,
                "max_runtime_seconds": self.max_runtime_seconds,
                "max_retry_count": self.max_retry_count,
            }
        )


@dataclass
class AgentAction:
    action_id: str
    tool_name: str
    action_type: str
    scope: str
    reason: str
    reversible: bool
    requires_confirmation: bool
    status: ActionStatus | str = ActionStatus.PLANNED
    risk_level: RiskLevel | str = RiskLevel.MEDIUM
    policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_id.strip():
            raise ValueError("action_id must not be empty")
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be empty")
        if not self.action_type.strip():
            raise ValueError("action_type must not be empty")
        self.status = coerce_action_status(self.status)
        self.risk_level = coerce_risk_level(self.risk_level)
        if self.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not self.requires_confirmation:
            raise ValueError("high and critical actions require confirmation")

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "action_id": self.action_id,
                "tool_name": self.tool_name,
                "action_type": self.action_type,
                "scope": self.scope,
                "reason": self.reason,
                "reversible": self.reversible,
                "requires_confirmation": self.requires_confirmation,
                "status": self.status.value,
                "risk_level": self.risk_level.value,
                "policy": redacted_metadata(self.policy),
            }
        )


@dataclass
class AgentVerification:
    action_id: str
    checks_run: list[str] = field(default_factory=list)
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    redacted_logs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.action_id.strip():
            raise ValueError("action_id must not be empty")
        self.checks_run = _clean_string_list(self.checks_run, "checks_run", allow_empty=True)
        self.failures = _clean_string_list(self.failures, "failures", allow_empty=True)
        self.artifacts = _clean_string_list(self.artifacts, "artifacts", allow_empty=True)
        self.redacted_logs = [redact_secrets(log) for log in _clean_string_list(self.redacted_logs, "redacted_logs", allow_empty=True)]

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "action_id": self.action_id,
                "checks_run": self.checks_run,
                "passed": self.passed,
                "failures": self.failures,
                "artifacts": self.artifacts,
                "redacted_logs": self.redacted_logs,
            }
        )


@dataclass
class AgentReview:
    summary: str
    user_decision_required: bool
    rollback_available: bool
    approval_references: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        self.approval_references = _clean_string_list(self.approval_references, "approval_references", allow_empty=True)
        self.remaining_risks = _clean_string_list(self.remaining_risks, "remaining_risks", allow_empty=True)

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "summary": self.summary,
                "user_decision_required": self.user_decision_required,
                "rollback_available": self.rollback_available,
                "approval_references": self.approval_references,
                "remaining_risks": self.remaining_risks,
            }
        )


@dataclass
class AgentRunLedger:
    run_id: str
    plan: AgentPlan
    actions: list[AgentAction] = field(default_factory=list)
    verifications: list[AgentVerification] = field(default_factory=list)
    review: AgentReview | None = None
    status: LedgerStatus | str = LedgerStatus.PLANNED

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        self.status = coerce_ledger_status(self.status)
        action_ids = [action.action_id for action in self.actions]
        duplicates = sorted({action_id for action_id in action_ids if action_ids.count(action_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate action ids: {', '.join(duplicates)}")
        known_actions = set(action_ids)
        for verification in self.verifications:
            if verification.action_id not in known_actions:
                raise ValueError(f"verification references unknown action: {verification.action_id}")

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "run_id": self.run_id,
                "plan": self.plan.to_dict(),
                "actions": [action.to_dict() for action in self.actions],
                "verifications": [verification.to_dict() for verification in self.verifications],
                "review": self.review.to_dict() if self.review else None,
                "status": self.status.value,
            }
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass
class AgentTraceEvent:
    run_id: str
    event_type: str
    risk_level: RiskLevel | str
    step_index: int
    summary: str
    metadata_redacted: dict[str, Any] = field(default_factory=dict)
    related_action_id: str | None = None
    related_tool: str | None = None
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if self.event_type not in VALID_TRACE_EVENT_TYPES:
            raise ValueError(f"invalid trace event_type: {self.event_type!r}")
        self.risk_level = coerce_risk_level(self.risk_level)
        self.summary = redacted_summary(self.summary)
        self.metadata_redacted = redacted_metadata(self.metadata_redacted or {})

    def to_dict(self) -> dict[str, Any]:
        return redact_secrets(
            {
                "event_id": self.event_id,
                "run_id": self.run_id,
                "timestamp": self.timestamp,
                "event_type": self.event_type,
                "risk_level": self.risk_level.value,
                "step_index": int(self.step_index),
                "summary": self.summary,
                "metadata_redacted": self.metadata_redacted,
                "related_action_id": self.related_action_id,
                "related_tool": self.related_tool,
            }
        )

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def trace_path_is_safe(path: str | Path, *, repo_root: str | Path | None = None) -> bool:
    resolved = Path(path).expanduser().resolve()
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[1]
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        # Outside the repo: only the OS temp directory is treated as a safe,
        # controlled scratch space (covers pytest tmp_path and tmp LEXA_AGENT_TRACE_DIR).
        # Arbitrary external targets (system dirs, network drives) are rejected.
        try:
            temp_root = Path(tempfile.gettempdir()).resolve()
        except OSError:
            return False
        return resolved.is_relative_to(temp_root)
    rel_text = rel.as_posix()
    return rel_text.startswith("tmp/") or rel_text.startswith(".test-tmp/") or rel_text.startswith("evals/results/")


class AgentTraceWriter:
    def __init__(self, path: str | Path, *, repo_root: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve()
        if not trace_path_is_safe(self.path, repo_root=repo_root):
            raise ValueError("agent trace path must be outside source or under tmp/, .test-tmp/, or evals/results/")
        self.last_error: str | None = None

    def write_event(self, event: AgentTraceEvent) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.to_jsonl() + "\n")
            return True
        except OSError as exc:
            self.last_error = redacted_summary(str(exc))
            return False


class AgentTraceRecorder:
    def __init__(self, run_id: str, writer: AgentTraceWriter | None = None, *, max_events: int | None = None) -> None:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        self.run_id = run_id
        self.writer = writer
        self.events: list[AgentTraceEvent] = []
        self.write_errors: list[str] = []
        self.max_events = max_events

    def record(
        self,
        event_type: str,
        *,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
        step_index: int = -1,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
        related_action_id: str | None = None,
        related_tool: str | None = None,
    ) -> AgentTraceEvent:
        event = AgentTraceEvent(
            run_id=self.run_id,
            event_type=event_type,
            risk_level=risk_level,
            step_index=step_index,
            summary=summary or event_type,
            metadata_redacted=metadata or {},
            related_action_id=related_action_id,
            related_tool=related_tool,
        )
        if self.max_events is not None and len(self.events) >= self.max_events:
            if "trace event limit reached" not in self.write_errors:
                self.write_errors.append("trace event limit reached")
            return event
        self.events.append(event)
        if self.writer and not self.writer.write_event(event):
            self.write_errors.append(self.writer.last_error or "trace write failed")
        return event


@dataclass
class AgentTraceReplayInput:
    events: list[AgentTraceEvent]

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "AgentTraceReplayInput":
        events: list[AgentTraceEvent] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                events.append(
                    AgentTraceEvent(
                        event_id=str(payload["event_id"]),
                        run_id=str(payload["run_id"]),
                        timestamp=str(payload["timestamp"]),
                        event_type=str(payload["event_type"]),
                        risk_level=str(payload["risk_level"]),
                        step_index=int(payload["step_index"]),
                        summary=str(payload["summary"]),
                        metadata_redacted=dict(payload.get("metadata_redacted") or {}),
                        related_action_id=payload.get("related_action_id"),
                        related_tool=payload.get("related_tool"),
                    )
                )
        return cls(events=events)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]


def validate_plan(plan: AgentPlan) -> AgentPolicyDecision:
    reasons: list[str] = []
    overlap = sorted(set(plan.allowed_tools).intersection(plan.forbidden_tools))
    if overlap:
        reasons.append(f"forbidden tools also allowed: {', '.join(overlap)}")
    if plan.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not plan.requires_user_review:
        reasons.append("high and critical plans require user review")
    return AgentPolicyDecision(allowed=not reasons, review_required=bool(reasons), blocked=bool(reasons), reasons=reasons)


def _action_field(action: AgentAction | dict[str, Any], name: str, default: Any = None) -> Any:
    if isinstance(action, dict):
        return action.get(name, default)
    return getattr(action, name, default)


def validate_action_against_plan(
    action: AgentAction | dict[str, Any],
    plan: AgentPlan,
    *,
    step_index: int | None = None,
) -> AgentPolicyDecision:
    reasons: list[str] = []
    tool_name = str(_action_field(action, "tool_name", "") or "")
    scope = str(_action_field(action, "scope", "") or "")
    action_type = str(_action_field(action, "action_type", "") or "")
    risk_level = coerce_risk_level(_action_field(action, "risk_level", RiskLevel.MEDIUM))
    requires_confirmation = bool(_action_field(action, "requires_confirmation", False))
    reversible = bool(_action_field(action, "reversible", True))

    if step_index is not None and step_index >= int(plan.budget_steps):
        reasons.append("budget_steps exceeded")
    if tool_name in plan.forbidden_tools:
        reasons.append(f"forbidden tool selected: {tool_name}")
    if plan.allowed_tools and tool_name not in plan.allowed_tools:
        reasons.append(f"tool not in allowed_tools: {tool_name}")
    if not scope.strip():
        reasons.append("tool scope must be set")
    if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not requires_confirmation:
        reasons.append("high and critical actions require confirmation")
    if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not reversible:
        reasons.append("non-reversible high/critical action requires review")
    protected_write = action_type in {"write", "delete", "admin", "execute"} and any(
        marker in scope.lower() for marker in ("core", "protected", "stable")
    )
    if protected_write and not requires_confirmation:
        reasons.append("protected/core direct write requires draft approval or confirmation")

    return AgentPolicyDecision(
        allowed=not reasons,
        review_required=bool(reasons),
        blocked=bool(reasons),
        reasons=reasons,
    )


def mark_review_required(ledger: AgentRunLedger, reason: str) -> AgentPolicyDecision:
    ledger.status = LedgerStatus.REVIEW_REQUIRED
    if ledger.review is None:
        ledger.review = AgentReview(
            summary="Agent policy requires review",
            user_decision_required=True,
            rollback_available=True,
            approval_references=[],
            remaining_risks=[reason],
        )
    else:
        ledger.review.user_decision_required = True
        ledger.review.remaining_risks = sorted(set(ledger.review.remaining_risks + [reason]))
    return AgentPolicyDecision(allowed=False, review_required=True, blocked=True, reasons=[reason])


def enforce_agent_policy(ledger: AgentRunLedger) -> AgentPolicyDecision:
    reasons: list[str] = []
    plan_decision = validate_plan(ledger.plan)
    reasons.extend(plan_decision.reasons)
    for index, action in enumerate(ledger.actions):
        action_decision = validate_action_against_plan(action, ledger.plan, step_index=index)
        reasons.extend(action_decision.reasons)
    if ledger.plan.max_tool_calls is not None and len(ledger.actions) > ledger.plan.max_tool_calls:
        reasons.append("max_tool_calls exceeded")
    risky_count = sum(1 for action in ledger.actions if action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL})
    if ledger.plan.max_risky_tool_calls is not None and risky_count > ledger.plan.max_risky_tool_calls:
        reasons.append("max_risky_tool_calls exceeded")
    memory_reads = sum(
        1
        for action in ledger.actions
        if action.action_type == "read" and (action.tool_name.startswith("memory_") or action.scope.startswith("memory"))
    )
    if ledger.plan.max_memory_reads is not None and memory_reads > ledger.plan.max_memory_reads:
        reasons.append("max_memory_reads exceeded")
    os_writes = sum(
        1
        for action in ledger.actions
        if action.action_type in {"write", "delete", "admin", "execute"}
        and (
            action.tool_name.startswith("personal_os_")
            or any(marker in action.scope.lower() for marker in ("os", "core", "protected", "stable"))
        )
    )
    if ledger.plan.max_os_writes is not None and os_writes > ledger.plan.max_os_writes:
        reasons.append("max_os_writes exceeded")
    if ledger.plan.max_retry_count is not None:
        retry_count = sum(int((action.policy or {}).get("retry_count", 0) or 0) for action in ledger.actions)
        if retry_count > ledger.plan.max_retry_count:
            reasons.append("max_retry_count exceeded")
    if reasons:
        reason = "; ".join(dict.fromkeys(reasons))
        return mark_review_required(ledger, reason)
    return AgentPolicyDecision(allowed=True, reasons=[])


def _clean_string_list(values: list[str], field_name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"{field_name} must be a list of strings")
    cleaned = [value.strip() for value in values if value.strip()]
    if not allow_empty and len(cleaned) != len(values):
        raise ValueError(f"{field_name} must not contain empty strings")
    return cleaned


def _clean_optional_budget(value: int | None, field_name: str, upper_bound: int) -> int | None:
    if value is None:
        return None
    normalized = int(value)
    if not 0 <= normalized <= upper_bound:
        raise ValueError(f"{field_name} must be between 0 and {upper_bound}")
    return normalized
