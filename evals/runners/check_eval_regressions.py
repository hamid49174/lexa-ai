"""Compare an offline eval report against the committed baseline manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.adapters.base import has_secret, redact_secrets, stable_hash  # noqa: E402
from evals.runners.write_failure_triage import build_triage_entries, write_markdown  # noqa: E402


BLOCKING_CHECK_TYPES = {
    "no_secret_leak": "secret_leak",
    "no_direct_write": "policy_violation",
    "no_direct_tool_execution": "policy_violation",
    "no_unapproved_apply": "policy_violation",
    "permission_denied": "policy_violation",
    "blocked": "policy_violation",
    "budget_enforced": "policy_violation",
    "verification_failed_blocks_completion": "policy_violation",
}
RISK_LEVELS = {"low", "medium", "high", "critical"}


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return redact_secrets(payload)


def validate_baseline(baseline: dict[str, Any], *, golden_tasks: list[dict[str, Any]] | None = None) -> None:
    if baseline.get("version") != 1:
        raise ValueError("baseline version must be 1")
    if not isinstance(baseline.get("suites"), dict):
        raise ValueError("baseline suites must be an object")
    expectations = baseline.get("case_expectations")
    if not isinstance(expectations, list) or not expectations:
        raise ValueError("baseline case_expectations must be a non-empty list")
    seen: set[str] = set()
    golden_by_id = {task["id"]: task for task in golden_tasks or []}
    for item in expectations:
        if not isinstance(item, dict):
            raise ValueError("baseline case expectation must be an object")
        case_id = str(item.get("case_id", ""))
        if not case_id:
            raise ValueError("baseline case_id must not be empty")
        if case_id in seen:
            raise ValueError(f"duplicate baseline case_id: {case_id}")
        seen.add(case_id)
        if item.get("expected_status") not in {"pass", "fail"}:
            raise ValueError(f"{case_id}: expected_status must be pass or fail")
        if item.get("risk_level") not in RISK_LEVELS:
            raise ValueError(f"{case_id}: invalid risk_level")
        if golden_by_id:
            task = golden_by_id.get(case_id)
            if not task:
                raise ValueError(f"{case_id}: baseline references missing golden case")
            if task["category"] != item.get("suite"):
                raise ValueError(f"{case_id}: baseline suite does not match golden case")
            if task["risk_level"] != item.get("risk_level"):
                raise ValueError(f"{case_id}: baseline risk_level does not match golden case")
    if has_secret(baseline):
        raise ValueError("baseline contains secret-shaped data")


def expectation_map(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["case_id"]): dict(item) for item in baseline.get("case_expectations", [])}


def _failed_check_types(result: dict[str, Any]) -> list[str]:
    return [str(check.get("type")) for check in result.get("checks", []) if not bool(check.get("passed"))]


def _failure_type(result: dict[str, Any], expected: dict[str, Any] | None) -> str:
    failed_checks = _failed_check_types(result)
    for check_type in failed_checks:
        if check_type in BLOCKING_CHECK_TYPES:
            return BLOCKING_CHECK_TYPES[check_type]
    if expected is None:
        return "new_failure"
    return "regression"


def _blocking(result: dict[str, Any], expected: dict[str, Any] | None, failure_type: str) -> bool:
    risk = str((expected or {}).get("risk_level") or result.get("risk_level") or "medium")
    if risk in {"high", "critical"}:
        return True
    if failure_type in {"secret_leak", "policy_violation", "missing_case", "new_failure"}:
        return True
    return bool((expected or {}).get("regression_blocking", True))


def evaluate_regressions(
    baseline: dict[str, Any],
    current_report: dict[str, Any],
    *,
    golden_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validate_baseline(baseline, golden_tasks=golden_tasks)
    safe_report = redact_secrets(current_report)
    if has_secret(safe_report):
        return {
            "ok": False,
            "blocking_failures": [
                {
                    "case_id": "__report__",
                    "suite": "unknown",
                    "risk_level": "critical",
                    "failure_type": "secret_leak",
                    "blocking": True,
                    "summary": "Current eval report contains secret-shaped data",
                    "failed_checks": ["no_secret_leak"],
                    "evidence_hash": stable_hash(safe_report)[:12],
                }
            ],
            "warnings": [],
            "fixed_failures": [],
            "new_passing_cases": [],
        }
    baseline_cases = expectation_map(baseline)
    current_results = {str(result.get("task_id")): dict(result) for result in safe_report.get("results", [])}
    blocking_failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    fixed_failures: list[str] = []
    new_passing_cases: list[str] = []

    for case_id, expected in sorted(baseline_cases.items()):
        current = current_results.get(case_id)
        if current is None:
            blocking_failures.append(
                {
                    "case_id": case_id,
                    "suite": expected["suite"],
                    "risk_level": expected["risk_level"],
                    "failure_type": "missing_case",
                    "blocking": True,
                    "summary": "Expected baseline case is missing from current report",
                    "failed_checks": [],
                    "evidence_hash": stable_hash(expected)[:12],
                }
            )
            continue
        if expected.get("expected_status") == "pass" and not bool(current.get("passed")):
            failure_type = _failure_type(current, expected)
            blocking_failures.append(
                {
                    "case_id": case_id,
                    "suite": expected["suite"],
                    "risk_level": expected["risk_level"],
                    "failure_type": failure_type,
                    "blocking": _blocking(current, expected, failure_type),
                    "summary": "Baseline passing case failed in current report",
                    "failed_checks": _failed_check_types(current),
                    "evidence_hash": stable_hash(current)[:12],
                }
            )
        elif expected.get("expected_status") == "fail" and bool(current.get("passed")):
            fixed_failures.append(case_id)

    for case_id, current in sorted(current_results.items()):
        if case_id in baseline_cases:
            continue
        if bool(current.get("passed")):
            new_passing_cases.append(case_id)
            continue
        failure_type = _failure_type(current, None)
        item = {
            "case_id": case_id,
            "suite": str(current.get("category", "unknown")),
            "risk_level": str(current.get("risk_level", "medium")),
            "failure_type": failure_type,
            "blocking": _blocking(current, None, failure_type),
            "summary": "New unknown eval case failed",
            "failed_checks": _failed_check_types(current),
            "evidence_hash": stable_hash(current)[:12],
        }
        blocking_failures.append(item)

    if new_passing_cases:
        warnings.append({"type": "new_passing_cases", "case_ids": new_passing_cases})

    return {
        "ok": not any(item.get("blocking") for item in blocking_failures),
        "blocking_failures": blocking_failures,
        "warnings": warnings,
        "fixed_failures": fixed_failures,
        "new_passing_cases": new_passing_cases,
        "summary": {
            "baseline_cases": len(baseline_cases),
            "current_cases": len(current_results),
            "blocking_failure_count": sum(1 for item in blocking_failures if item.get("blocking")),
            "warning_count": len(warnings),
        },
    }


def write_json_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(redact_secrets(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check current Lexa eval report against baseline.")
    parser.add_argument("--baseline", required=True, help="Baseline manifest JSON.")
    parser.add_argument("--current", required=True, help="Current eval JSON report.")
    parser.add_argument(
        "--tasks",
        nargs="+",
        help="Optional JSONL files or directories with golden tasks; when given, the baseline "
        "is additionally validated for drift against them (missing/renamed cases, suite/risk mismatch).",
    )
    parser.add_argument("--output-json", help="Optional local JSON regression report.")
    parser.add_argument("--triage-md", help="Optional local Markdown triage report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        golden_tasks = None
        if args.tasks:
            from evals.runners.run_eval_suite import load_tasks_from_paths

            golden_tasks = load_tasks_from_paths(args.tasks)
        report = evaluate_regressions(
            load_json(args.baseline),
            load_json(args.current),
            golden_tasks=golden_tasks,
        )
        if args.output_json:
            write_json_report(report, args.output_json)
        if args.triage_md:
            write_markdown(build_triage_entries(report), args.triage_md)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"eval regression error: {exc}", file=sys.stderr)
        return 1
    print(
        "Lexa eval regression gate: "
        f"{'passed' if report['ok'] else 'failed'} "
        f"({report['summary']['blocking_failure_count']} blocking)"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
