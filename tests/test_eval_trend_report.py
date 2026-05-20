import json
import subprocess
import sys
from pathlib import Path

from evals.runners.eval_trend_report import build_trend, load_report, risk_penalty


REPO_ROOT = Path(__file__).resolve().parents[1]


def _report(results):
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    return {
        "ok": failed == 0,
        "task_count": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def test_trend_report_detects_new_and_fixed_failures():
    previous = _report(
        [
            {"task_id": "old-fail", "category": "security", "passed": False, "risk_level": "high"},
            {"task_id": "stable-pass", "category": "memory", "passed": True, "risk_level": "low"},
        ]
    )
    current = _report(
        [
            {"task_id": "old-fail", "category": "security", "passed": True, "risk_level": "high"},
            {"task_id": "new-fail", "category": "agent_simulation", "passed": False, "risk_level": "critical"},
        ]
    )

    trend = build_trend([previous, current])

    assert trend["new_failures"] == ["new-fail"]
    assert trend["fixed_failures"] == ["old-fail"]
    assert set(trend["changed_failures"]) == {"new-fail", "old-fail"}


def test_risk_weighted_score_counts_critical_more_than_low():
    low_report = _report([{"task_id": "low", "category": "memory", "passed": False, "risk_level": "low"}])
    critical_report = _report([{"task_id": "critical", "category": "security", "passed": False, "risk_level": "critical"}])

    assert risk_penalty(critical_report) > risk_penalty(low_report)


def test_reports_with_secrets_are_redacted(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            _report(
                [
                    {
                        "task_id": "secret",
                        "category": "security",
                        "passed": False,
                        "risk_level": "critical",
                        "observations": {"token": "sk-fixture-secret-token"},
                    }
                ]
            )
        ),
        encoding="utf-8",
    )

    loaded = load_report(report)

    assert "sk-fixture-secret-token" not in json.dumps(loaded)
    assert "sk-[REDACTED]" in json.dumps(loaded)


def test_trend_cli_uses_tempdir_outputs(tmp_path):
    previous = tmp_path / "previous.json"
    current = tmp_path / "current.json"
    output_json = tmp_path / "trend.json"
    output_md = tmp_path / "trend.md"
    previous.write_text(json.dumps(_report([])), encoding="utf-8")
    current.write_text(json.dumps(_report([{"task_id": "pass", "category": "memory", "passed": True, "risk_level": "low"}])), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "eval_trend_report.py"),
            str(previous),
            str(current),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert output_json.exists()
    assert output_md.exists()
    assert "Lexa Eval Trend" in output_md.read_text(encoding="utf-8")


def test_result_artifacts_remain_ignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "evals/results/*" in gitignore
    assert "!evals/results/.gitkeep" in gitignore
