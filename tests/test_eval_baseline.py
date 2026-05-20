import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "evals" / "baselines" / "eval_baseline.json"
GOLDEN_DIR = REPO_ROOT / "evals" / "golden_tasks"
RUNNER_PATH = REPO_ROOT / "evals" / "runners" / "run_eval_suite.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_eval_suite", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_eval_baseline_manifest_is_valid_and_references_golden_cases():
    from evals.runners.check_eval_regressions import validate_baseline

    runner = load_runner()
    tasks = runner.load_tasks_from_paths([GOLDEN_DIR])
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    validate_baseline(baseline, golden_tasks=tasks)
    assert baseline["created_from"] == "phase_3f_green"
    assert len(baseline["case_expectations"]) == len(tasks)


def test_eval_baseline_case_ids_are_unique_and_secret_free():
    from evals.adapters.base import has_secret

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    ids = [item["case_id"] for item in baseline["case_expectations"]]

    assert len(ids) == len(set(ids))
    assert not has_secret(baseline)


def test_eval_baseline_passing_current_report_is_green():
    from evals.runners.check_eval_regressions import evaluate_regressions

    runner = load_runner()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    report = runner.run_suite([GOLDEN_DIR])

    result = evaluate_regressions(baseline, report)

    assert result["ok"] is True
    assert result["blocking_failures"] == []


def test_eval_baseline_detects_missing_case():
    from evals.runners.check_eval_regressions import evaluate_regressions

    baseline = {
        "version": 1,
        "created_from": "test",
        "suites": {"security": {"expected_total": 1, "max_failures": 0, "critical_failures_allowed": 0, "high_failures_allowed": 0}},
        "case_expectations": [
            {"case_id": "missing", "suite": "security", "expected_status": "pass", "risk_level": "critical", "regression_blocking": True}
        ],
    }
    report = {"results": [], "task_count": 0, "passed": 0, "failed": 0}

    result = evaluate_regressions(baseline, report)

    assert result["ok"] is False
    assert result["blocking_failures"][0]["failure_type"] == "missing_case"


def test_eval_baseline_detects_new_failure_and_critical_failure():
    from evals.runners.check_eval_regressions import evaluate_regressions

    baseline = {
        "version": 1,
        "created_from": "test",
        "suites": {},
        "case_expectations": [
            {"case_id": "known", "suite": "security", "expected_status": "pass", "risk_level": "critical", "regression_blocking": True}
        ],
    }
    report = {
        "results": [
            {"task_id": "known", "category": "security", "risk_level": "critical", "passed": False, "checks": [{"type": "blocked", "passed": False}]},
            {"task_id": "new-low", "category": "answer_quality", "risk_level": "low", "passed": False, "checks": [{"type": "contains", "passed": False}]},
        ],
    }

    result = evaluate_regressions(baseline, report)

    assert result["ok"] is False
    assert {item["failure_type"] for item in result["blocking_failures"]} == {"policy_violation", "new_failure"}
