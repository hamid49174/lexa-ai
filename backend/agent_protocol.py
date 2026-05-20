"""Plan/Act/Verify/Review protocol primitives for Lexa agents.

This module is intentionally isolated from the runtime in Phase 3A. It gives
future agent work a stable, serializable ledger format with explicit safety
checks before any larger orchestration refactor begins.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


MAX_BUDGET_STEPS = 50
MAX_BUDGET_SECONDS = 3600
SECRET_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"),
]


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        self.checkpoints = _clean_string_list(self.checkpoints, "checkpoints", allow_empty=True)
        if self.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not self.requires_user_review:
            raise ValueError("high and critical plans require user review")

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


def _clean_string_list(values: list[str], field_name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"{field_name} must be a list of strings")
    cleaned = [value.strip() for value in values if value.strip()]
    if not allow_empty and len(cleaned) != len(values):
        raise ValueError(f"{field_name} must not contain empty strings")
    return cleaned
