"""Safely update the commit-friendly eval baseline from a green eval report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.adapters.base import has_secret, redact_secrets  # noqa: E402


def load_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("eval report must be a JSON object")
    if has_secret(payload):
        raise ValueError("eval report contains secret-shaped data")
    safe = redact_secrets(payload)
    if has_secret(safe):
        raise ValueError("eval report contains secret-shaped data")
    return safe


def build_baseline(report: dict[str, Any], *, created_from: str = "manual_green_run") -> dict[str, Any]:
    failed = [result for result in report.get("results", []) if not bool(result.get("passed"))]
    if failed:
        critical_or_high = [
            result
            for result in failed
            if str(result.get("risk_level", "medium")) in {"high", "critical"}
        ]
        if critical_or_high:
            raise ValueError("cannot update baseline from high/critical failing eval report")
        raise ValueError("cannot update baseline from failing eval report")
    results = sorted(report.get("results", []), key=lambda item: str(item.get("task_id")))
    if not results:
        raise ValueError("cannot update baseline from empty eval report")
    totals = Counter(str(result.get("category")) for result in results)
    suites = {
        suite: {
            "expected_total": total,
            "max_failures": 0,
            "critical_failures_allowed": 0,
            "high_failures_allowed": 0,
        }
        for suite, total in sorted(totals.items())
    }
    return {
        "version": 1,
        "created_from": created_from,
        "suites": suites,
        "case_expectations": [
            {
                "case_id": str(result["task_id"]),
                "suite": str(result["category"]),
                "expected_status": "pass",
                "risk_level": str(result.get("risk_level", "medium")),
                "regression_blocking": True,
            }
            for result in results
        ],
    }


def write_baseline(baseline: dict[str, Any], path: str | Path) -> None:
    safe = redact_secrets(baseline)
    if has_secret(safe):
        raise ValueError("baseline contains secret-shaped data")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Lexa eval baseline from a green report.")
    parser.add_argument("--current", required=True, help="Current green eval JSON report.")
    parser.add_argument("--output", required=True, help="Baseline manifest path to write.")
    parser.add_argument("--created-from", default="manual_green_run", help="Baseline provenance label.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print summary without writing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        baseline = build_baseline(load_report(args.current), created_from=args.created_from)
        if args.dry_run:
            print(f"Baseline dry run: {len(baseline['case_expectations'])} cases")
            return 0
        write_baseline(baseline, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"baseline update error: {exc}", file=sys.stderr)
        return 1
    print(f"Baseline updated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
