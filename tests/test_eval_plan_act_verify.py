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


def test_plan_act_verify_suite_runs():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR], suites=["plan_act_verify"])

    assert report["ok"] is True
    assert report["task_count"] == 8


def test_plan_act_verify_bad_fixture_fails(tmp_path):
    runner = load_runner()
    task_file = tmp_path / "plan.jsonl"
    fixtures = tmp_path / "fixtures" / "plan_act_verify"
    fixtures.mkdir(parents=True)
    task_file.write_text(
        json.dumps(
            {
                "id": "bad-plan",
                "category": "plan_act_verify",
                "input": "delete now",
                "expected_behavior": ["requires plan"],
                "forbidden_behavior": ["direct delete"],
                "risk_level": "critical",
                "assertions": [{"type": "has_plan", "value": "true"}],
                "tags": ["phase3d"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (fixtures / "cases.json").write_text(json.dumps({"bad-plan": {"has_plan": False, "output": "bad"}}), encoding="utf-8")

    report = runner.run_suite([task_file], fixture_root=tmp_path / "fixtures")

    assert report["ok"] is False
    assert report["results"][0]["checks"][0]["passed"] is False


def test_all_includes_plan_act_verify():
    runner = load_runner()

    report = runner.run_suite([GOLDEN_DIR])

    assert "plan_act_verify" in report["suites"]
    assert report["ok"] is True


def test_plan_act_verify_report_redacts_secrets(tmp_path):
    runner = load_runner()
    report_path = tmp_path / "report.json"

    exit_code = runner.main(["--tasks", str(GOLDEN_DIR), "--suite", "plan_act_verify", "--json-report", str(report_path)])

    assert exit_code == 0
    assert "sk-fixture-secret-token" not in report_path.read_text(encoding="utf-8")
