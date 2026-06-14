"""Create redacted failure triage entries for eval regressions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.adapters.base import has_secret, redact_secrets, stable_hash  # noqa: E402


VALID_RISKS = {"low", "medium", "high", "critical"}
VALID_FAILURE_TYPES = {"regression", "new_failure", "missing_case", "secret_leak", "policy_violation", "unknown"}
VALID_AREAS = {"tool_selection", "memory", "os_drafts", "plugin", "agent_policy", "frontend", "unknown"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def suspected_area_for_suite(suite: str, failed_checks: list[str] | None = None) -> str:
    failed_checks = failed_checks or []
    if suite == "tool_selection":
        return "tool_selection"
    if suite == "memory":
        return "memory"
    if suite in {"os_drafts", "trace_replay"}:
        return "os_drafts"
    if suite in {"security", "prompt_injection"} and any("html" in check for check in failed_checks):
        return "frontend"
    if suite in {"security", "prompt_injection"}:
        return "agent_policy"
    if suite == "agent_simulation":
        return "agent_policy"
    return "unknown"


def safe_text(value: Any) -> str:
    text = str(redact_secrets(value))
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*\[REDACTED\]",
        "[REDACTED]",
        text,
    )


def is_blocking(risk_level: str, failure_type: str, summary: str = "") -> bool:
    if risk_level in {"high", "critical"}:
        return True
    if failure_type == "secret_leak":
        return True
    if failure_type == "policy_violation" and any(marker in summary.lower() for marker in ("direct write", "approval", "secret", "shell")):
        return True
    return False


def make_triage_entry(
    *,
    case_id: str,
    suite: str,
    risk_level: str,
    failure_type: str,
    summary: str,
    failed_checks: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
    first_seen: str | None = None,
    blocking: bool | None = None,
) -> dict[str, Any]:
    failed_checks = failed_checks or []
    safe_evidence = redact_secrets(evidence or {})
    # Honour the blocking decision already made by the regression checker when it
    # is supplied; only recompute it standalone if the caller has no verdict.
    blocking_flag = bool(blocking) if blocking is not None else is_blocking(risk_level, failure_type, summary)
    entry = {
        "triage_id": f"triage-{stable_hash([case_id, suite, failure_type])[:12]}",
        "case_id": case_id,
        "suite": suite,
        "risk_level": risk_level,
        "failure_type": failure_type,
        "blocking": blocking_flag,
        "summary": safe_text(summary),
        "suspected_area": suspected_area_for_suite(suite, failed_checks),
        "first_seen": first_seen or utc_now_iso(),
        "recommended_action": recommended_action(failure_type, failed_checks),
        "safe_to_ignore": False,
        "redacted_evidence": {
            "failed_checks": list(failed_checks),
            "evidence_hash": stable_hash(safe_evidence)[:12],
        },
    }
    validate_triage_entry(entry)
    return entry


def recommended_action(failure_type: str, failed_checks: list[str]) -> str:
    if failure_type == "missing_case":
        return "Restore the expected golden case or intentionally update the baseline from a green run."
    if failure_type == "secret_leak":
        return "Stop and fix redaction before accepting the run."
    if "no_direct_write" in failed_checks:
        return "Route the write through draft/approval flow and rerun evals."
    if "permission_denied" in failed_checks:
        return "Restore permission enforcement before merging."
    if "budget_enforced" in failed_checks:
        return "Restore budget enforcement and add a focused regression test."
    return "Inspect the adapter, fixture, or runtime policy path and rerun the regression gate."


def validate_triage_entry(entry: dict[str, Any]) -> None:
    required = {
        "triage_id",
        "case_id",
        "suite",
        "risk_level",
        "failure_type",
        "blocking",
        "summary",
        "suspected_area",
        "first_seen",
        "recommended_action",
        "safe_to_ignore",
        "redacted_evidence",
    }
    missing = required - set(entry)
    if missing:
        raise ValueError(f"triage missing required fields: {', '.join(sorted(missing))}")
    if entry["risk_level"] not in VALID_RISKS:
        raise ValueError("invalid triage risk_level")
    if entry["failure_type"] not in VALID_FAILURE_TYPES:
        raise ValueError("invalid triage failure_type")
    if entry["suspected_area"] not in VALID_AREAS:
        raise ValueError("invalid triage suspected_area")
    if has_secret(entry):
        raise ValueError("triage contains secret-shaped data")


def build_triage_entries(regression_report: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for failure in regression_report.get("blocking_failures", []):
        # Preserve the regression checker's blocking verdict instead of
        # recomputing a contradictory one; only fall back when it is absent.
        reported_blocking = failure.get("blocking")
        entries.append(
            make_triage_entry(
                case_id=str(failure.get("case_id", "unknown")),
                suite=str(failure.get("suite", "unknown")),
                risk_level=str(failure.get("risk_level", "medium")),
                failure_type=str(failure.get("failure_type", "unknown")),
                summary=str(failure.get("summary", "Eval regression detected")),
                failed_checks=[str(check) for check in failure.get("failed_checks", [])],
                evidence={"failure": failure},
                blocking=bool(reported_blocking) if reported_blocking is not None else None,
            )
        )
    return entries


def write_json(entries: list[dict[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(redact_secrets({"triage": entries}), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(entries: list[dict[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Lexa Eval Failure Triage", ""]
    if not entries:
        lines.append("No blocking failures.")
    for entry in entries:
        lines.extend(
            [
                f"## {entry['case_id']}",
                "",
                f"- Risk: {entry['risk_level']}",
                f"- Type: {entry['failure_type']}",
                f"- Blocking: {entry['blocking']}",
                f"- Area: {entry['suspected_area']}",
                f"- Summary: {entry['summary']}",
                f"- Action: {entry['recommended_action']}",
                "",
            ]
        )
    text = "\n".join(lines)
    if has_secret(text):
        raise ValueError("triage markdown contains secret-shaped data")
    output_path.write_text(text + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write local eval failure triage reports.")
    parser.add_argument("--regression-report", required=True, help="Regression checker JSON report.")
    parser.add_argument("--output-json", help="Optional local JSON triage path.")
    parser.add_argument("--output-md", help="Optional local Markdown triage path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = json.loads(Path(args.regression_report).read_text(encoding="utf-8"))
        entries = build_triage_entries(redact_secrets(report))
        if args.output_json:
            write_json(entries, args.output_json)
        if args.output_md:
            write_markdown(entries, args.output_md)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failure triage error: {exc}", file=sys.stderr)
        return 1
    print(f"Lexa failure triage: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
