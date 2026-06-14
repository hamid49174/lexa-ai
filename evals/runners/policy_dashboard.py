"""Local policy and trace failure dashboard generator.

This is a report utility, not product UI. Outputs belong in ignored locations
such as evals/results/.
"""

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


POLICY_CHECK_TYPES = {
    "no_secret_leak": "secret leak",
    "no_direct_write": "direct write",
    "no_direct_tool_execution": "direct tool execution",
    "no_unapproved_apply": "unapproved apply",
    "requires_confirmation": "unconfirmed high-risk action",
    "blocked": "unsafe action not blocked",
    "budget_enforced": "budget violation",
    "verification_failed_blocks_completion": "failed verification marked success",
    "permission_denied": "permission was not denied",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON report must be an object")
    return redact_secrets(payload)


def load_reports(paths: list[str | Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        reports.append(_read_json(Path(path)))
    return reports


def _failed_checks(result: dict[str, Any]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for check in result.get("checks", []):
        if bool(check.get("passed")):
            continue
        check_type = str(check.get("type", ""))
        existing_hash = check.get("value_hash")
        if existing_hash:
            value_hash = str(existing_hash)
        else:
            # Fall back on type + value so externally fed reports without a
            # precomputed value_hash still get a distinguishing hash instead of
            # a constant empty-string hash shared by every check.
            value_hash = stable_hash([check_type, check.get("value", "")])[:12]
        failed.append(
            {
                "type": check_type,
                "passed": False,
                "value_hash": value_hash,
            }
        )
    return failed


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failed_cases: list[dict[str, Any]] = []
    policy_violations: list[dict[str, Any]] = []
    for report in reports:
        for result in report.get("results", []):
            failed = not bool(result.get("passed"))
            failed_checks = _failed_checks(result)
            if failed:
                failed_cases.append(
                    {
                        "task_id": str(result.get("task_id")),
                        "category": str(result.get("category")),
                        "risk_level": str(result.get("risk_level") or _risk_from_category(str(result.get("category")))),
                        "checks": failed_checks,
                    }
                )
            for check in failed_checks:
                check_type = str(check.get("type"))
                if check_type in POLICY_CHECK_TYPES:
                    policy_violations.append(
                        {
                            "task_id": str(result.get("task_id")),
                            "violation": POLICY_CHECK_TYPES[check_type],
                            "check_type": check_type,
                        }
                    )
    high_critical = [
        case for case in failed_cases if str(case.get("risk_level")).lower() in {"high", "critical"}
    ]
    summary = {
        "failed_cases": failed_cases,
        "high_critical_failures": sorted(high_critical, key=lambda item: str(item.get("risk_level"))),
        "policy_violations": policy_violations,
        "counts": {
            "failed_cases": len(failed_cases),
            "high_critical_failures": len(high_critical),
            "policy_violations": len(policy_violations),
        },
    }
    return redact_secrets(summary)


def _risk_from_category(category: str) -> str:
    if category in {"security", "prompt_injection", "agent_simulation", "trace_replay"}:
        return "critical"
    return "medium"


def write_markdown(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lexa Policy Dashboard",
        "",
        f"- Failed cases: {summary['counts']['failed_cases']}",
        f"- High/Critical failures: {summary['counts']['high_critical_failures']}",
        f"- Policy violations: {summary['counts']['policy_violations']}",
        "",
        "## High/Critical Failures",
        "",
    ]
    if summary["high_critical_failures"]:
        for case in summary["high_critical_failures"]:
            lines.append(f"- `{case['task_id']}` ({case['risk_level']}, {case['category']})")
    else:
        lines.append("- none")
    lines.extend(["", "## Policy Violations", ""])
    if summary["policy_violations"]:
        for violation in summary["policy_violations"]:
            lines.append(f"- `{violation['task_id']}`: {violation['violation']}")
    else:
        lines.append("- none")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_dashboard(report_paths: list[str | Path]) -> dict[str, Any]:
    return summarize_reports(load_reports(report_paths))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a local Lexa policy failure dashboard.")
    parser.add_argument("reports", nargs="*", help="Eval JSON report paths.")
    parser.add_argument("--output-md", help="Optional local Markdown dashboard path.")
    parser.add_argument("--output-json", help="Optional local JSON dashboard path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = build_dashboard(args.reports)
        if has_secret(summary):
            raise ValueError("policy dashboard still contains secret-shaped data")
        if args.output_md:
            write_markdown(summary, args.output_md)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"policy dashboard error: {exc}", file=sys.stderr)
        return 1
    print(f"Lexa policy dashboard: {summary['counts']['failed_cases']} failed cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
