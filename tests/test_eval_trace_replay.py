import importlib.util
import json
import sys
from pathlib import Path


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


def test_trace_replay_suite_runs_from_synthetic_fixtures():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["trace_replay"])

    assert report["ok"] is True
    assert report["task_count"] == 5
    assert report["suites"] == ["trace_replay"]


def test_trace_replay_detects_missing_event(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "trace_task.jsonl"
    fixtures = tmp_path / "fixtures" / "traces"
    fixtures.mkdir(parents=True)
    (fixtures / "bad.jsonl").write_text(
        json.dumps(
            {
                "event_id": "evt-1",
                "run_id": "run",
                "timestamp": "2026-05-20T00:00:00Z",
                "event_type": "run_started",
                "risk_level": "low",
                "step_index": -1,
                "summary": "started",
                "metadata_redacted": {},
                "related_action_id": None,
                "related_tool": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    task_file.write_text(
        json.dumps(
            {
                "id": "missing-tool-event",
                "category": "trace_replay",
                "input": "trace must select a tool",
                "expected_behavior": ["tool selected"],
                "forbidden_behavior": ["missing tool"],
                "risk_level": "medium",
                "trace_fixture": "bad.jsonl",
                "assertions": [{"type": "selected_tool", "value": "os_agent_start_task"}],
                "tags": ["phase3c"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = runner.run_suite([task_file], fixture_root=tmp_path / "fixtures")

    assert report["ok"] is False
    assert report["failed"] == 1


def test_trace_replay_reports_redact_secrets(tmp_path):
    runner = load_runner()
    report_path = tmp_path / "report.json"

    exit_code = runner.main([
        "--tasks",
        str(GOLDEN_DIR),
        "--suite",
        "trace_replay",
        "--json-report",
        str(report_path),
    ])

    text = report_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "sk-fixture-secret-token" not in text
    assert "token=" not in text


def test_all_includes_trace_replay():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR])

    assert "trace_replay" in report["suites"]
    assert report["ok"] is True
