import json
import subprocess
import sys
from pathlib import Path

from evals.runners.check_eval_regressions import evaluate_regressions


REPO_ROOT = Path(__file__).resolve().parents[1]


def _baseline(expected_status="pass", risk_level="critical"):
    return {
        "version": 1,
        "created_from": "test",
        "suites": {"security": {"expected_total": 1, "max_failures": 0, "critical_failures_allowed": 0, "high_failures_allowed": 0}},
        "case_expectations": [
            {
                "case_id": "case-a",
                "suite": "security",
                "expected_status": expected_status,
                "risk_level": risk_level,
                "regression_blocking": True,
            }
        ],
    }


def _report(result):
    return {"task_count": 1, "passed": 1 if result["passed"] else 0, "failed": 0 if result["passed"] else 1, "results": [result]}


def test_passing_report_against_baseline_is_ok():
    result = evaluate_regressions(
        _baseline(),
        _report({"task_id": "case-a", "category": "security", "risk_level": "critical", "passed": True, "checks": []}),
    )

    assert result["ok"] is True


def test_new_low_failure_blocks_as_unknown_regression():
    result = evaluate_regressions(
        _baseline(),
        {
            "task_count": 2,
            "passed": 1,
            "failed": 1,
            "results": [
                {"task_id": "case-a", "category": "security", "risk_level": "critical", "passed": True, "checks": []},
                {"task_id": "new-low", "category": "answer_quality", "risk_level": "low", "passed": False, "checks": [{"type": "contains", "passed": False}]},
            ],
        },
    )

    assert result["ok"] is False
    assert any(item["failure_type"] == "new_failure" for item in result["blocking_failures"])


def test_high_and_critical_failures_block():
    for risk in ["high", "critical"]:
        result = evaluate_regressions(
            _baseline(risk_level=risk),
            _report({"task_id": "case-a", "category": "security", "risk_level": risk, "passed": False, "checks": [{"type": "contains", "passed": False}]}),
        )

        assert result["ok"] is False
        assert result["blocking_failures"][0]["blocking"] is True


def test_fixed_failure_is_reported_positively():
    result = evaluate_regressions(
        _baseline(expected_status="fail", risk_level="medium"),
        _report({"task_id": "case-a", "category": "security", "risk_level": "medium", "passed": True, "checks": []}),
    )

    assert result["ok"] is True
    assert result["fixed_failures"] == ["case-a"]


def test_secret_report_is_redacted_and_blocks():
    result = evaluate_regressions(
        _baseline(),
        _report({"task_id": "case-a", "category": "security", "risk_level": "critical", "passed": False, "checks": [], "observations": {"token": "sk-fixture-secret-token"}}),
    )

    text = json.dumps(result, sort_keys=True)
    assert result["ok"] is False
    assert "sk-fixture-secret-token" not in text


def test_checker_cli_writes_redacted_markdown_triage(tmp_path):
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    triage = tmp_path / "triage.md"
    baseline.write_text(json.dumps(_baseline()), encoding="utf-8")
    current.write_text(
        json.dumps(
            _report(
                {
                    "task_id": "case-a",
                    "category": "security",
                    "risk_level": "critical",
                    "passed": False,
                    "checks": [{"type": "no_secret_leak", "passed": False, "value": "api_key=sk-fixture-secret-token"}],
                }
            )
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "check_eval_regressions.py"),
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            "--triage-md",
            str(triage),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 1
    assert triage.exists()
    text = triage.read_text(encoding="utf-8")
    assert "sk-fixture-secret-token" not in text
    assert "api_key=" not in text


def test_eval_regression_gate_parallel_runs_use_separate_outputs(tmp_path):
    work_a = tmp_path / "run-a"
    work_b = tmp_path / "run-b"
    script = REPO_ROOT / "scripts" / "run_eval_regression_gate.ps1"

    procs = [
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-WorkDir", str(work_a)],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ),
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-WorkDir", str(work_b)],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ),
    ]
    outputs = [proc.communicate(timeout=60)[0] for proc in procs]

    assert all(proc.returncode == 0 for proc in procs), outputs
    assert (work_a / "run-a-current_eval_report.json").exists()
    assert (work_b / "run-b-current_eval_report.json").exists()
    assert work_a != work_b
