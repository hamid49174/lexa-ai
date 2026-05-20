from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evals.adapters.base import build_result, redact_secrets


def _load_trace(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            events.append(redact_secrets(payload))
    return events


def _trace_path(task: dict[str, Any], fixture_root: str | Path | None) -> Path:
    if task.get("_trace_dir"):
        root = Path(str(task["_trace_dir"]))
        return root / str(task.get("trace_fixture") or f"{task['id']}.jsonl")
    root = Path(fixture_root or Path(__file__).resolve().parents[1] / "fixtures")
    fixture_name = str(task.get("trace_fixture") or f"{task['id']}.jsonl")
    trace_path = root / "traces" / fixture_name
    if trace_path.exists():
        return trace_path
    return root / fixture_name


def evaluate(task: dict[str, Any], *, fixture_root: str | Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    events = _load_trace(_trace_path(task, fixture_root))
    event_sequence = [str(event.get("event_type", "")) for event in events]
    selected_tools = [
        str(event.get("related_tool"))
        for event in events
        if event.get("event_type") == "tool_selected" and event.get("related_tool")
    ]
    summaries = "\n".join(str(event.get("summary", "")) for event in events)
    metadata_text = json.dumps(events, sort_keys=True, ensure_ascii=True)
    blocked = any(marker in metadata_text.lower() for marker in ("blocked", "denied", "permission_denied"))
    requires_review = any(
        event.get("event_type") == "review_created"
        and bool((event.get("metadata_redacted") or {}).get("review_required"))
        for event in events
    ) or "review_required" in metadata_text.lower()
    requires_confirmation = "requires_confirmation" in metadata_text.lower() or requires_review
    permission_denied = "permission_denied" in metadata_text.lower() or "permission denied" in metadata_text.lower()
    direct_write = any(bool((event.get("metadata_redacted") or {}).get("direct_write")) for event in events)
    direct_tool_execution = any(
        bool((event.get("metadata_redacted") or {}).get("direct_tool_execution")) for event in events
    )
    unapproved_apply = any(bool((event.get("metadata_redacted") or {}).get("unapproved_apply")) for event in events)
    verification_passed = any(
        event.get("event_type") == "verification_finished"
        and bool((event.get("metadata_redacted") or {}).get("passed"))
        for event in events
    )
    verification_failed_expected = any(
        event.get("event_type") == "verification_finished"
        and not bool((event.get("metadata_redacted") or {}).get("passed", True))
        for event in events
    )
    review_created = any(event.get("event_type") == "review_created" for event in events)
    budget_exceeded = "budget_exceeded" in metadata_text.lower()
    protected_write_requires_draft = "protected_write_requires_draft" in metadata_text.lower() or "draft_required" in metadata_text.lower()
    confirmation_required_for_risky_action = "requires_confirmation" in metadata_text.lower() or "approval_required" in metadata_text.lower()
    redaction_verified = "redaction_verified" in metadata_text.lower()
    max_step_index = max((int(event.get("step_index", 0)) for event in events), default=0)

    response = {
        "output": summaries,
        "event_sequence": event_sequence,
        "selected_tool": selected_tools[0] if selected_tools else "",
        "selected_tools": selected_tools,
        "blocked": blocked,
        "requires_review": requires_review,
        "requires_confirmation": requires_confirmation,
        "permission_denied": permission_denied,
        "direct_write": direct_write,
        "direct_tool_execution": direct_tool_execution,
        "unapproved_apply": unapproved_apply,
        "verification_passed": verification_passed,
        "verification_failed_expected": verification_failed_expected,
        "review_created": review_created,
        "budget_exceeded_detected": budget_exceeded,
        "protected_write_requires_draft": protected_write_requires_draft,
        "confirmation_required_for_risky_action": confirmation_required_for_risky_action,
        "redaction_verified": redaction_verified,
        "step_count": max_step_index + 1 if max_step_index >= 0 else 0,
        "reason": "synthetic agent trace replay",
        "observations": {
            "event_count": len(events),
            "event_sequence": event_sequence,
            "selected_tools": selected_tools,
            "blocked": blocked,
            "requires_review": requires_review,
            "permission_denied": permission_denied,
            "budget_exceeded_detected": budget_exceeded,
            "review_created": review_created,
        },
    }
    return build_result(task, response, started)
