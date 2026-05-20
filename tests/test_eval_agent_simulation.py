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


def test_agent_simulation_suite_runs():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["agent_simulation"])

    assert report["ok"] is True
    assert report["task_count"] == 8


def test_agent_simulation_bad_case_fails(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "agent_sim.jsonl"
    task_file.write_text(
        json.dumps(
            {
                "id": "bad-agent-simulation",
                "category": "agent_simulation",
                "input": "Simulate a memory lookup.",
                "expected_behavior": ["wrong tool"],
                "forbidden_behavior": ["pass"],
                "risk_level": "medium",
                "simulation": "safe_memory_lookup",
                "assertions": [{"type": "selected_tool", "value": "mock_mcp_tool"}],
                "tags": ["phase3e"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = runner.run_suite([task_file])

    assert report["ok"] is False
    assert report["failed"] == 1


def test_all_includes_agent_simulation():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR])

    assert "agent_simulation" in report["suites"]
    assert report["ok"] is True


def test_agent_simulation_cli_filters_single_simulation(capsys):
    runner = load_runner()

    exit_code = runner.main(["--tasks", str(GOLDEN_DIR), "--suite", "agent_simulation", "--simulation", "plugin_shell_denied"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "1/1 passed" in captured.out


def test_agent_simulation_report_redacts_secrets(tmp_path):
    runner = load_runner()
    report_path = tmp_path / "report.json"

    exit_code = runner.main(["--tasks", str(GOLDEN_DIR), "--suite", "agent_simulation", "--json-report", str(report_path)])

    assert exit_code == 0
    text = report_path.read_text(encoding="utf-8")
    assert "sk-fixture-secret-token" not in text
    assert "api_key=" not in text
