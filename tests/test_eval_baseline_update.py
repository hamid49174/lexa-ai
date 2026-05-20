import json
import subprocess
import sys
from pathlib import Path

from evals.runners.update_eval_baseline import build_baseline


REPO_ROOT = Path(__file__).resolve().parents[1]


def _report(results):
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    return {"task_count": len(results), "passed": passed, "failed": failed, "results": results}


def test_baseline_update_dry_run_does_not_write(tmp_path):
    current = tmp_path / "current.json"
    output = tmp_path / "baseline.json"
    current.write_text(
        json.dumps(_report([{"task_id": "new-case", "category": "security", "risk_level": "critical", "passed": True, "checks": []}])),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "update_eval_baseline.py"),
            "--current",
            str(current),
            "--output",
            str(output),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert not output.exists()


def test_passing_new_case_is_added_to_baseline():
    baseline = build_baseline(
        _report([{"task_id": "new-case", "category": "agent_simulation", "risk_level": "high", "passed": True, "checks": []}]),
        created_from="test",
    )

    assert baseline["case_expectations"][0]["case_id"] == "new-case"
    assert baseline["case_expectations"][0]["expected_status"] == "pass"


def test_failing_case_is_not_accepted():
    report = _report([{"task_id": "bad", "category": "security", "risk_level": "medium", "passed": False, "checks": []}])

    try:
        build_baseline(report)
    except ValueError as exc:
        assert "failing eval report" in str(exc)
    else:
        raise AssertionError("failing report should not update baseline")


def test_critical_failure_blocks_update():
    report = _report([{"task_id": "critical", "category": "security", "risk_level": "critical", "passed": False, "checks": []}])

    try:
        build_baseline(report)
    except ValueError as exc:
        assert "high/critical" in str(exc)
    else:
        raise AssertionError("critical failure should block baseline update")


def test_secret_leak_blocks_update(tmp_path):
    current = tmp_path / "current.json"
    output = tmp_path / "baseline.json"
    current.write_text(
        json.dumps(
            _report(
                [
                    {
                        "task_id": "secret",
                        "category": "security",
                        "risk_level": "critical",
                        "passed": True,
                        "checks": [],
                        "observations": {"api_key": "sk-fixture-secret-token"},
                    }
                ]
            )
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "update_eval_baseline.py"),
            "--current",
            str(current),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 1
    assert not output.exists()


def test_baseline_update_writes_only_manifest(tmp_path):
    current = tmp_path / "current.json"
    output = tmp_path / "baseline.json"
    current.write_text(
        json.dumps(_report([{"task_id": "ok", "category": "memory", "risk_level": "low", "passed": True, "checks": []}])),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "update_eval_baseline.py"),
            "--current",
            str(current),
            "--output",
            str(output),
            "--created-from",
            "test",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert output.exists()
    assert not list(tmp_path.glob("*.md"))
