import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "evals" / "runners" / "run_eval_suite.py"
GOLDEN_DIR = REPO_ROOT / "evals" / "golden_tasks"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_eval_suite", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_all_golden_jsonl_files_are_valid_and_ids_unique():
    runner = load_runner()

    tasks = runner.load_tasks_from_paths([GOLDEN_DIR])

    assert tasks
    ids = [task["id"] for task in tasks]
    assert len(ids) == len(set(ids))
    assert {task["category"] for task in tasks} == runner.VALID_CATEGORIES
    for task in tasks:
        assert set(task) >= runner.REQUIRED_TASK_FIELDS
        assert task["risk_level"] in runner.VALID_RISK_LEVELS
        assert task["assertions"]
        assert all(assertion["type"] in runner.VALID_ASSERTION_TYPES for assertion in task["assertions"])


def test_runner_mock_suite_passes_offline():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR])

    assert report["ok"] is True
    assert report["failed"] == 0
    assert report["passed"] == report["task_count"]


def test_runner_lists_suites_and_runs_single_suite():
    runner = load_runner()

    suites = runner.list_suites([GOLDEN_DIR])
    report = runner.run_suite([GOLDEN_DIR], suites=["tool_selection"])

    assert "tool_selection" in suites
    assert report["ok"] is True
    assert report["suites"] == ["tool_selection"]
    assert all(result["category"] == "tool_selection" for result in report["results"])


def test_cli_list_suites(capsys):
    runner = load_runner()

    exit_code = runner.main(["--tasks", str(GOLDEN_DIR), "--list-suites"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "tool_selection" in captured.out
    assert "security" in captured.out


def test_runner_detects_failing_assertions(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "tasks.jsonl"
    response_file = tmp_path / "responses.json"
    task_file.write_text(
        json.dumps(
            {
                "id": "failing-task",
                "category": "answer_quality",
                "input": "Explain the change.",
                "expected_behavior": ["include evidence"],
                "forbidden_behavior": ["invent files"],
                "risk_level": "medium",
                "assertions": [{"type": "contains", "value": "include evidence"}],
                "tags": ["phase3a"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    response_file.write_text(json.dumps({"failing-task": {"output": "no evidence here"}}), encoding="utf-8")

    report = runner.run_suite([task_file], responses_path=response_file)

    assert report["ok"] is False
    assert report["failed"] == 1
    assert report["results"][0]["checks"][0]["passed"] is False


def test_runner_detects_failing_adapter_assertion(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "tool.jsonl"
    task_file.write_text(
        json.dumps(
            {
                "id": "failing-tool-selection",
                "category": "tool_selection",
                "input": "show me git status",
                "expected_behavior": ["select git status"],
                "forbidden_behavior": ["select weather"],
                "risk_level": "medium",
                "assertions": [{"type": "selected_tool", "value": "weather_get"}],
                "tags": ["phase3b"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = runner.run_suite([task_file])

    assert report["ok"] is False
    assert report["failed"] == 1


def test_runner_rejects_broken_schema(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "bad.jsonl"
    task_file.write_text('{"id":"bad","category":"security"}\n', encoding="utf-8")

    with pytest.raises(runner.EvalSchemaError, match="missing required fields"):
        runner.load_tasks_from_paths([task_file])


def test_cli_returns_nonzero_for_schema_errors(tmp_path, capsys):
    runner = load_runner()
    task_file = tmp_path / "bad.jsonl"
    task_file.write_text('{"id":"bad","category":"security"}\n', encoding="utf-8")

    exit_code = runner.main(["--tasks", str(task_file)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "eval schema error" in captured.err


def test_cli_writes_redacted_reports(tmp_path):
    runner = load_runner()
    json_report = tmp_path / "report.json"
    md_report = tmp_path / "report.md"

    exit_code = runner.main(
        [
            "--tasks",
            str(GOLDEN_DIR),
            "--all",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(md_report),
        ]
    )

    assert exit_code == 0
    assert json_report.exists()
    assert md_report.exists()
    report_text = json_report.read_text(encoding="utf-8") + md_report.read_text(encoding="utf-8")
    assert "sk-fixture-secret-token" not in report_text
    assert "api_key=" not in report_text


def test_eval_results_are_ignored_except_placeholder():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "evals/results/*" in gitignore
    assert "!evals/results/.gitkeep" in gitignore
    assert "evals/results/*.json" not in gitignore
