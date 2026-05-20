import json
import subprocess
import sys
from pathlib import Path

from evals.runners.policy_dashboard import build_dashboard


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_report(path: Path, results):
    passed = sum(1 for result in results if result["passed"])
    payload = {
        "ok": passed == len(results),
        "task_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_policy_dashboard_summarizes_failures_and_prioritizes_high_risk(tmp_path):
    report = tmp_path / "report.json"
    _write_report(
        report,
        [
            {
                "task_id": "critical-leak",
                "category": "security",
                "passed": False,
                "risk_level": "critical",
                "checks": [{"type": "no_secret_leak", "passed": False}],
            },
            {
                "task_id": "low-format",
                "category": "answer_quality",
                "passed": False,
                "risk_level": "low",
                "checks": [{"type": "contains", "passed": False}],
            },
        ],
    )

    summary = build_dashboard([report])

    assert summary["counts"]["failed_cases"] == 2
    assert summary["counts"]["high_critical_failures"] == 1
    assert summary["high_critical_failures"][0]["task_id"] == "critical-leak"
    assert summary["policy_violations"][0]["violation"] == "secret leak"


def test_policy_dashboard_redacts_secrets(tmp_path):
    report = tmp_path / "report.json"
    _write_report(
        report,
        [
            {
                "task_id": "secret-case",
                "category": "security",
                "passed": False,
                "risk_level": "critical",
                "checks": [{"type": "no_secret_leak", "passed": False, "value": "api_key=sk-fixture-secret-token"}],
            }
        ],
    )

    summary = build_dashboard([report])

    text = json.dumps(summary, sort_keys=True)
    assert "sk-fixture-secret-token" not in text
    assert "api_key=" not in text


def test_policy_dashboard_empty_reports_work():
    summary = build_dashboard([])

    assert summary["counts"]["failed_cases"] == 0
    assert summary["high_critical_failures"] == []


def test_policy_dashboard_reports_broken_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{bad json", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "evals" / "runners" / "policy_dashboard.py"), str(bad)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 1
    assert "policy dashboard error" in proc.stderr


def test_policy_dashboard_writes_local_markdown(tmp_path):
    report = tmp_path / "report.json"
    output = tmp_path / "dashboard.md"
    _write_report(
        report,
        [
            {
                "task_id": "budget",
                "category": "agent_simulation",
                "passed": False,
                "risk_level": "high",
                "checks": [{"type": "budget_enforced", "passed": False}],
            }
        ],
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "policy_dashboard.py"),
            str(report),
            "--output-md",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert output.exists()
    assert "High/Critical Failures" in output.read_text(encoding="utf-8")
