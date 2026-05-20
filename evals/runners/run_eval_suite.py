"""Offline eval runner for Lexa golden tasks.

The Phase 3A runner intentionally avoids network calls and external model APIs.
It validates JSONL task files and can score deterministic mock responses or a
caller-provided response map.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    "selected_tool_prefix",
    "not_selected_tool",
    "blocked",
    "requires_confirmation",
    "creates_draft",
    "no_secret_leak",
    "max_tool_count",
    "contains_reason",
    "retrieved_contains",
    "retrieved_not_contains",
    "requires_review",
    "creates_memory_correction_draft",
    "confidence_below",
    "confidence_above",
    "no_tool_call",
    "no_direct_write",
    "no_html_execution",
    "permission_denied",
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
    observations: dict[str, Any] | None = None
    duration_ms: int = 0


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_secret(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True, ensure_ascii=True) if not isinstance(value, str) else value
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


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
        "selected_tools": [],
        "blocked": False,
        "requires_confirmation": False,
        "creates_draft": False,
        "requires_review": False,
        "direct_write": False,
        "html_executed": False,
        "permission_denied": False,
        "tool_call_made": False,
        "confidence": 0.8,
        "reason": "\n".join(task["expected_behavior"]),
    }
    for assertion in task["assertions"]:
        assertion_type = assertion["type"]
        value = assertion["value"]
        if assertion_type == "contains" and value:
            output_parts.append(value)
        elif assertion_type == "selected_tool":
            response["selected_tool"] = value
            response["selected_tools"] = [value]
        elif assertion_type == "selected_tool_prefix":
            response["selected_tool"] = f"{value}fixture"
            response["selected_tools"] = [response["selected_tool"]]
        elif assertion_type == "blocked":
            response["blocked"] = True
        elif assertion_type == "requires_confirmation":
            response["requires_confirmation"] = True
        elif assertion_type == "creates_draft":
            response["creates_draft"] = True
        elif assertion_type in {"requires_review", "creates_memory_correction_draft", "permission_denied"}:
            response[assertion_type] = True
        elif assertion_type == "retrieved_contains" and value:
            response["retrieved_items"] = [value]
        elif assertion_type == "retrieved_not_contains":
            response.setdefault("retrieved_items", [])
        elif assertion_type == "contains_reason" and value:
            response["reason"] = f"{response.get('reason', '')}\n{value}".strip()
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
    reason = str(response.get("reason", ""))
    selected_tool = str(response.get("selected_tool", ""))
    selected_tools = response.get("selected_tools", [])
    if not isinstance(selected_tools, list):
        selected_tools = []
    retrieved_items = response.get("retrieved_items", [])
    if not isinstance(retrieved_items, list):
        retrieved_items = []
    retrieved_text = "\n".join(str(item) for item in retrieved_items)

    if assertion_type == "contains":
        passed = value in output
    elif assertion_type == "not_contains":
        passed = value not in output and value != selected_tool and value not in selected_tools
    elif assertion_type == "selected_tool":
        passed = selected_tool == value or value in selected_tools
    elif assertion_type == "selected_tool_prefix":
        passed = selected_tool.startswith(value) or any(str(tool).startswith(value) for tool in selected_tools)
    elif assertion_type == "not_selected_tool":
        passed = selected_tool != value and value not in selected_tools
    elif assertion_type == "blocked":
        passed = bool(response.get("blocked"))
    elif assertion_type == "requires_confirmation":
        passed = bool(response.get("requires_confirmation"))
    elif assertion_type == "creates_draft":
        passed = bool(response.get("creates_draft"))
    elif assertion_type == "max_tool_count":
        try:
            passed = int(response.get("tool_count", len(selected_tools))) <= int(value)
        except ValueError:
            passed = False
    elif assertion_type == "contains_reason":
        passed = value in reason
    elif assertion_type == "retrieved_contains":
        passed = value in retrieved_text
    elif assertion_type == "retrieved_not_contains":
        passed = value not in retrieved_text
    elif assertion_type == "requires_review":
        passed = bool(response.get("requires_review"))
    elif assertion_type == "creates_memory_correction_draft":
        passed = bool(response.get("creates_memory_correction_draft"))
    elif assertion_type == "confidence_below":
        try:
            passed = float(response.get("confidence", 0.0)) < float(value)
        except ValueError:
            passed = False
    elif assertion_type == "confidence_above":
        try:
            passed = float(response.get("confidence", 0.0)) > float(value)
        except ValueError:
            passed = False
    elif assertion_type == "no_tool_call":
        passed = not bool(response.get("tool_call_made"))
    elif assertion_type == "no_direct_write":
        passed = not bool(response.get("direct_write"))
    elif assertion_type == "no_html_execution":
        passed = not bool(response.get("html_executed"))
    elif assertion_type == "permission_denied":
        passed = bool(response.get("permission_denied"))
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
    started = time.perf_counter()
    normalized = normalize_response(response if response is not None else deterministic_mock_response(task))
    checks = [evaluate_assertion(assertion, normalized) for assertion in task["assertions"]]
    return EvalResult(
        task_id=task["id"],
        category=task["category"],
        passed=all(check["passed"] for check in checks),
        checks=checks,
        observations=redact_secrets(dict(normalized.get("observations", {}))),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def load_response_map(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise EvalSchemaError("responses file must be a JSON object keyed by task id")
    return data


def list_suites(task_paths: Iterable[str | Path] | None = None) -> list[str]:
    if task_paths is None:
        return sorted(VALID_CATEGORIES)
    tasks = load_tasks_from_paths(task_paths)
    return sorted({str(task["category"]) for task in tasks})


def _load_adapter(category: str):
    module_name = {
        "tool_selection": "evals.adapters.tool_selection_adapter",
        "memory": "evals.adapters.memory_adapter",
        "os_drafts": "evals.adapters.os_draft_adapter",
        "prompt_injection": "evals.adapters.security_adapter",
        "security": "evals.adapters.security_adapter",
        "answer_quality": "evals.adapters.security_adapter",
    }.get(category)
    if not module_name:
        return None
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def _evaluate_with_adapter(task: dict[str, Any], *, fixture_root: Path | None = None) -> EvalResult:
    adapter = _load_adapter(task["category"])
    if not adapter:
        return evaluate_task(task)
    started = time.perf_counter()
    adapter_result = adapter.evaluate(task, fixture_root=fixture_root)
    checks = adapter_result.get("assertion_results") or [
        evaluate_assertion(assertion, adapter_result) for assertion in task["assertions"]
    ]
    return EvalResult(
        task_id=task["id"],
        category=task["category"],
        passed=bool(adapter_result.get("passed")) and all(bool(check.get("passed")) for check in checks),
        checks=checks,
        observations=redact_secrets(dict(adapter_result.get("observations", {}))),
        duration_ms=int(adapter_result.get("duration_ms") or ((time.perf_counter() - started) * 1000)),
    )


def run_suite(
    task_paths: Iterable[str | Path],
    *,
    responses_path: str | Path | None = None,
    suites: Iterable[str] | None = None,
    use_adapters: bool = True,
    fixture_root: str | Path | None = None,
) -> dict[str, Any]:
    tasks = load_tasks_from_paths(task_paths)
    requested_suites = set(suites or [])
    if requested_suites:
        invalid = sorted(requested_suites - VALID_CATEGORIES)
        if invalid:
            raise EvalSchemaError(f"unknown suite(s): {', '.join(invalid)}")
        tasks = [task for task in tasks if task["category"] in requested_suites]
    if not tasks:
        raise EvalSchemaError("no eval tasks matched the requested suite")
    response_map = load_response_map(responses_path)
    fixture_path = Path(fixture_root) if fixture_root else Path(__file__).resolve().parents[1] / "fixtures"
    results = [
        evaluate_task(task, response_map.get(task["id"]))
        if response_map.get(task["id"]) is not None or not use_adapters
        else _evaluate_with_adapter(task, fixture_root=fixture_path)
        for task in tasks
    ]
    failed = [result for result in results if not result.passed]
    return {
        "ok": not failed,
        "suites": sorted({result.category for result in results}),
        "task_count": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": [
            {
                "task_id": result.task_id,
                "category": result.category,
                "passed": result.passed,
                "checks": result.checks,
                "observations": result.observations or {},
                "duration_ms": result.duration_ms,
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
    parser.add_argument("--list-suites", action="store_true", help="List available eval suites and exit.")
    parser.add_argument("--suite", action="append", choices=sorted(VALID_CATEGORIES), help="Run one suite. Can be repeated.")
    parser.add_argument("--all", action="store_true", help="Run all suites.")
    parser.add_argument("--mock-only", action="store_true", help="Use deterministic mock scoring instead of local adapters.")
    parser.add_argument("--fixtures", help="Fixture root directory for local adapters.")
    parser.add_argument("--responses", help="Optional JSON response map keyed by task id.")
    parser.add_argument("--output-json", help="Optional path for a JSON report.")
    parser.add_argument("--output-md", help="Optional path for a Markdown report.")
    parser.add_argument("--json-report", dest="json_report", help="Alias for --output-json.")
    parser.add_argument("--markdown-report", dest="markdown_report", help="Alias for --output-md.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.list_suites:
            for suite in list_suites(args.tasks):
                print(suite)
            return 0
        suites = None if args.all else args.suite
        report = run_suite(
            args.tasks,
            responses_path=args.responses,
            suites=suites,
            use_adapters=not args.mock_only,
            fixture_root=args.fixtures,
        )
        json_report = args.json_report or args.output_json
        markdown_report = args.markdown_report or args.output_md
        if json_report:
            write_json_report(report, json_report)
        if markdown_report:
            write_markdown_report(report, markdown_report)
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
