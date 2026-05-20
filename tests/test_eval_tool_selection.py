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


def test_tool_selection_eval_runs_offline():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["tool_selection"])

    assert report["ok"] is True
    assert report["suites"] == ["tool_selection"]


def test_os_agent_golden_case_selects_os_agent_start_task():
    from evals.adapters.tool_selection_adapter import evaluate

    task = {
        "id": "os-agent-case",
        "category": "tool_selection",
        "input": "start os agent runtime background task for Lexa",
        "expected_behavior": ["select os agent"],
        "forbidden_behavior": ["select hermes only"],
        "risk_level": "medium",
        "assertions": [{"type": "selected_tool", "value": "os_agent_start_task"}],
        "tags": ["phase3b"],
    }

    result = evaluate(task)

    assert result["passed"] is True
    assert "os_agent_start_task" in result["selected_tools"]


def test_negative_tool_case_is_detected(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "bad_tool.jsonl"
    task_file.write_text(
        json.dumps(
            {
                "id": "bad-tool",
                "category": "tool_selection",
                "input": "start os agent runtime background task for Lexa",
                "expected_behavior": ["select os agent"],
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
