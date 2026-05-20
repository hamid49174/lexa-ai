"""Offline eval runner for Lexa golden tasks.

The Phase 3A runner intentionally avoids network calls and external model APIs.
It validates JSONL task files and can score deterministic mock responses or a
caller-provided response map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


VALID_CATEGORIES = {
    "tool_selection",
    "memory",
    "os_drafts",
    "prompt_injection",
    "security",
    "answer_quality",
}
VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_ASSERTION_TYPES = {
    "contains",
    "not_contains",
    "selected_tool",
    "blocked",
    "requires_confirmation",
    "creates_draft",
    "no_secret_leak",
}
REQUIRED_TASK_FIELDS = {
    "id",
    "category",
    "input",
    "expected_behavior",
    "forbidden_behavior",
    "risk_level",
    "assertions",
    "tags",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"),
]


class EvalSchemaError(ValueError):
    """Raised when a golden task file is malformed."""


@dataclass(frozen=True)
class EvalResult:
    task_id: str
    category: str
    passed: bool
    checks: list[dict[str, Any]]


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_secret(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True, ensure_ascii=True) if not isinstance(value, str) else value
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def validate_assertion(assertion: Any, *, task_id: str, index: int) -> dict[str, str]:
    if not isinstance(assertion, dict):
        raise EvalSchemaError(f"{task_id}: assertion {index} must be an object")
    assertion_type = assertion.get("type")
    value = assertion.get("value")
    if assertion_type not in VALID_ASSERTION_TYPES:
        raise EvalSchemaError(f"{task_id}: invalid assertion type {assertion_type!r}")
    if not isinstance(value, str):
        raise EvalSchemaError(f"{task_id}: assertion {index} value must be a string")
    return {"type": assertion_type, "value": value}


def validate_task(task: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise EvalSchemaError(f"{source}: task must be a JSON object")
    missing = sorted(REQUIRED_TASK_FIELDS - set(task))
    if missing:
        raise EvalSchemaError(f"{source}: missing required fields: {', '.join(missing)}")

    task_id = task["id"]
    if not isinstance(task_id, str) or not task_id.strip():
        raise EvalSchemaError(f"{source}: id must be a non-empty string")
    category = task["category"]
    if category not in VALID_CATEGORIES:
        raise EvalSchemaError(f"{task_id}: invalid category {category!r}")
    if not isinstance(task["input"], str) or not task["input"].strip():
        raise EvalSchemaError(f"{task_id}: input must be a non-empty string")
    for field in ("expected_behavior", "forbidden_behavior", "tags"):
        if not isinstance(task[field], list) or not all(isinstance(item, str) for item in task[field]):
            raise EvalSchemaError(f"{task_id}: {field} must be a list of strings")
    if task["risk_level"] not in VALID_RISK_LEVELS:
        raise EvalSchemaError(f"{task_id}: invalid risk_level {task['risk_level']!r}")
    if not isinstance(task["assertions"], list) or not task["assertions"]:
        raise EvalSchemaError(f"{task_id}: assertions must be a non-empty list")

    validated = dict(task)
    validated["assertions"] = [
        validate_assertion(assertion, task_id=task_id, index=index)
        for index, assertion in enumerate(task["assertions"])
    ]
    return validated


def iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalSchemaError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            yield line_number, parsed


def collect_task_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.jsonl")))
        elif path.suffix == ".jsonl":
            files.append(path)
        else:
            raise EvalSchemaError(f"{path}: expected a JSONL file or directory")
    return files


def load_tasks_from_paths(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    task_files = collect_task_files(Path(path) for path in paths)
    tasks: list[dict[str, Any]] = []
    seen_ids: dict[str, str] = {}
    for task_file in task_files:
        for line_number, raw_task in iter_jsonl(task_file):
            source = f"{task_file}:{line_number}"
            task = validate_task(raw_task, source=source)
            previous = seen_ids.get(task["id"])
            if previous:
                raise EvalSchemaError(f"{source}: duplicate task id {task['id']!r}; first seen at {previous}")
            seen_ids[task["id"]] = source
            tasks.append(task)
    if not tasks:
        raise EvalSchemaError("no eval tasks found")
    return tasks


def deterministic_mock_response(task: dict[str, Any]) -> dict[str, Any]:
    output_parts = list(task["expected_behavior"])
    response: dict[str, Any] = {
        "output": "\n".join(output_parts),
        "selected_tool": None,
        "blocked": False,
        "requires_confirmation": False,
        "creates_draft": False,
    }
    for assertion in task["assertions"]:
        assertion_type = assertion["type"]
        value = assertion["value"]
        if assertion_type == "contains" and value:
            output_parts.append(value)
        elif assertion_type == "selected_tool":
            response["selected_tool"] = value
        elif assertion_type == "blocked":
            response["blocked"] = True
        elif assertion_type == "requires_confirmation":
            response["requires_confirmation"] = True
        elif assertion_type == "creates_draft":
            response["creates_draft"] = True
    response["output"] = "\n".join(dict.fromkeys(output_parts))
    return response


def normalize_response(response: Any) -> dict[str, Any]:
    if isinstance(response, str):
        return {"output": response}
    if isinstance(response, dict):
        return dict(response)
    return {"output": json.dumps(response, sort_keys=True, ensure_ascii=True)}


def evaluate_assertion(assertion: dict[str, str], response: dict[str, Any]) -> dict[str, Any]:
    assertion_type = assertion["type"]
    value = assertion["value"]
    output = str(response.get("output", ""))

    if assertion_type == "contains":
        passed = value in output
    elif assertion_type == "not_contains":
        passed = value not in output and value != str(response.get("selected_tool", ""))
    elif assertion_type == "selected_tool":
        selected = response.get("selected_tool")
        selected_tools = response.get("selected_tools", [])
        passed = selected == value or (isinstance(selected_tools, list) and value in selected_tools)
    elif assertion_type == "blocked":
        passed = bool(response.get("blocked"))
    elif assertion_type == "requires_confirmation":
        passed = bool(response.get("requires_confirmation"))
    elif assertion_type == "creates_draft":
        passed = bool(response.get("creates_draft"))
    elif assertion_type == "no_secret_leak":
        passed = not has_secret(response) and (not value or value not in output)
    else:
        passed = False

    return {
        "type": assertion_type,
        "value_hash": stable_hash(value)[:12],
        "passed": passed,
    }


def evaluate_task(task: dict[str, Any], response: Any | None = None) -> EvalResult:
    normalized = normalize_response(response if response is not None else deterministic_mock_response(task))
    checks = [evaluate_assertion(assertion, normalized) for assertion in task["assertions"]]
    return EvalResult(
        task_id=task["id"],
        category=task["category"],
        passed=all(check["passed"] for check in checks),
        checks=checks,
    )


def load_response_map(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise EvalSchemaError("responses file must be a JSON object keyed by task id")
    return data


def run_suite(task_paths: Iterable[str | Path], *, responses_path: str | Path | None = None) -> dict[str, Any]:
    tasks = load_tasks_from_paths(task_paths)
    response_map = load_response_map(responses_path)
    results = [evaluate_task(task, response_map.get(task["id"])) for task in tasks]
    failed = [result for result in results if not result.passed]
    return {
        "ok": not failed,
        "task_count": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": [
            {
                "task_id": result.task_id,
                "category": result.category,
                "passed": result.passed,
                "checks": result.checks,
            }
            for result in results
        ],
    }


def write_json_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lexa Eval Report",
        "",
        f"- Status: {'passed' if report['ok'] else 'failed'}",
        f"- Tasks: {report['task_count']}",
        f"- Passed: {report['passed']}",
        f"- Failed: {report['failed']}",
        "",
        "| Task | Category | Result |",
        "| --- | --- | --- |",
    ]
    for result in report["results"]:
        lines.append(
            f"| `{result['task_id']}` | `{result['category']}` | "
            f"{'passed' if result['passed'] else 'failed'} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline Lexa golden-task evals.")
    parser.add_argument(
        "--tasks",
        nargs="+",
        default=[str(Path(__file__).resolve().parents[1] / "golden_tasks")],
        help="JSONL files or directories containing JSONL tasks.",
    )
    parser.add_argument("--responses", help="Optional JSON response map keyed by task id.")
    parser.add_argument("--output-json", help="Optional path for a JSON report.")
    parser.add_argument("--output-md", help="Optional path for a Markdown report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = run_suite(args.tasks, responses_path=args.responses)
        if args.output_json:
            write_json_report(report, args.output_json)
        if args.output_md:
            write_markdown_report(report, args.output_md)
    except EvalSchemaError as exc:
        print(f"eval schema error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Lexa eval suite: {report['passed']}/{report['task_count']} passed, "
        f"{report['failed']} failed"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
