"""Local trend summaries for Lexa eval reports.

Reports are local artifacts. Tests use temp directories; generated reports under
evals/results/ stay ignored by Git.
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

from evals.adapters.base import has_secret, redact_secrets  # noqa: E402


RISK_WEIGHTS = {"low": 1, "medium": 2, "high": 4, "critical": 8}


def load_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: report must be a JSON object")
    return redact_secrets(payload)


def load_reports(paths: list[str | Path]) -> list[dict[str, Any]]:
    return [load_report(path) for path in paths]


def _failed_ids(report: dict[str, Any]) -> set[str]:
    return {str(result.get("task_id")) for result in report.get("results", []) if not bool(result.get("passed"))}


def risk_penalty(report: dict[str, Any]) -> int:
    penalty = 0
    for result in report.get("results", []):
        if bool(result.get("passed")):
            continue
        risk = str(result.get("risk_level") or _risk_from_checks(result)).lower()
        penalty += RISK_WEIGHTS.get(risk, 2)
    return penalty


def _risk_from_checks(result: dict[str, Any]) -> str:
    category = str(result.get("category", ""))
    if category in {"security", "prompt_injection", "agent_simulation", "trace_replay"}:
        return "critical"
    return "medium"


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    total = int(report.get("task_count") or len(report.get("results", [])))
    passed = int(report.get("passed") or 0)
    failed = int(report.get("failed") or max(0, total - passed))
    penalty = risk_penalty(report)
    max_penalty = max(1, sum(RISK_WEIGHTS.get(str(result.get("risk_level", "medium")).lower(), 2) for result in report.get("results", [])))
    return {
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "failed_ids": sorted(_failed_ids(report)),
        "risk_weighted_penalty": penalty,
        "risk_weighted_score": round(max(0.0, 1.0 - (penalty / max_penalty)), 4),
    }


def compare_reports(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_failed = _failed_ids(previous)
    current_failed = _failed_ids(current)
    current_summary = summarize_report(current)
    current_summary.update(
        {
            "new_failures": sorted(current_failed - previous_failed),
            "fixed_failures": sorted(previous_failed - current_failed),
            "changed_failures": sorted(previous_failed.symmetric_difference(current_failed)),
        }
    )
    return current_summary


def build_trend(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return {
            "total_cases": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "changed_failures": [],
            "new_failures": [],
            "fixed_failures": [],
            "risk_weighted_score": 0.0,
            "risk_weighted_penalty": 0,
        }
    if len(reports) == 1:
        summary = summarize_report(reports[0])
        summary.update({"changed_failures": [], "new_failures": summary["failed_ids"], "fixed_failures": []})
        return summary
    return compare_reports(reports[-2], reports[-1])


def write_markdown(summary: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lexa Eval Trend",
        "",
        f"- Total cases: {summary['total_cases']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Pass rate: {summary['pass_rate']}",
        f"- Risk-weighted score: {summary['risk_weighted_score']}",
        "",
        "## Changes",
        "",
        f"- New failures: {', '.join(summary.get('new_failures', [])) or 'none'}",
        f"- Fixed failures: {', '.join(summary.get('fixed_failures', [])) or 'none'}",
        f"- Changed failures: {', '.join(summary.get('changed_failures', [])) or 'none'}",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare local Lexa eval JSON reports.")
    parser.add_argument("reports", nargs="*", help="Eval JSON report paths in chronological order.")
    parser.add_argument("--output-json", help="Optional local JSON trend summary path.")
    parser.add_argument("--output-md", help="Optional local Markdown trend summary path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = build_trend(load_reports(args.reports))
        safe_summary = redact_secrets(summary)
        if has_secret(safe_summary):
            raise ValueError("trend summary still contains secret-shaped data")
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(safe_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.output_md:
            write_markdown(safe_summary, args.output_md)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"eval trend error: {exc}", file=sys.stderr)
        return 1
    print(f"Lexa eval trend: {safe_summary['passed']}/{safe_summary['total_cases']} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
