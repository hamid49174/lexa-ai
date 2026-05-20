import json
import subprocess
import sys
from pathlib import Path

from evals.runners.write_failure_triage import build_triage_entries, make_triage_entry


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_failure_triage_schema_is_valid_json():
    schema = json.loads((REPO_ROOT / "evals" / "triage" / "failure_triage_schema.json").read_text(encoding="utf-8"))

    assert "required" in schema
    assert "triage_id" in schema["required"]


def test_critical_and_secret_leak_failures_are_blocking():
    critical = make_triage_entry(
        case_id="critical",
        suite="security",
        risk_level="critical",
        failure_type="regression",
        summary="Critical regression",
    )
    leak = make_triage_entry(
        case_id="leak",
        suite="security",
        risk_level="low",
        failure_type="secret_leak",
        summary="Secret leak",
    )

    assert critical["blocking"] is True
    assert leak["blocking"] is True


def test_low_failure_can_be_non_blocking_when_policy_allows():
    entry = make_triage_entry(
        case_id="low",
        suite="answer_quality",
        risk_level="low",
        failure_type="regression",
        summary="Minor wording issue",
    )

    assert entry["blocking"] is False


def test_triage_redacts_tokens_and_api_keys():
    entry = make_triage_entry(
        case_id="secret",
        suite="security",
        risk_level="critical",
        failure_type="secret_leak",
        summary="api_key=sk-fixture-secret-token leaked",
        evidence={"authorization": "Bearer abcdefghijk"},
    )
    text = json.dumps(entry, sort_keys=True)

    assert "sk-fixture-secret-token" not in text
    assert "Bearer abcdefghijk" not in text
    assert "api_key=" not in text


def test_triage_cli_writes_markdown_without_secrets(tmp_path):
    regression_report = tmp_path / "regression.json"
    output = tmp_path / "triage.md"
    regression_report.write_text(
        json.dumps(
            {
                "blocking_failures": [
                    {
                        "case_id": "case-a",
                        "suite": "security",
                        "risk_level": "critical",
                        "failure_type": "secret_leak",
                        "summary": "api_key=sk-fixture-secret-token leaked",
                        "failed_checks": ["no_secret_leak"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "evals" / "runners" / "write_failure_triage.py"),
            "--regression-report",
            str(regression_report),
            "--output-md",
            str(output),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "sk-fixture-secret-token" not in output.read_text(encoding="utf-8")


def test_build_triage_entries_from_regression_report():
    entries = build_triage_entries(
        {
            "blocking_failures": [
                {
                    "case_id": "case-a",
                    "suite": "agent_simulation",
                    "risk_level": "high",
                    "failure_type": "policy_violation",
                    "summary": "budget enforcement failed",
                    "failed_checks": ["budget_enforced"],
                }
            ]
        }
    )

    assert len(entries) == 1
    assert entries[0]["suspected_area"] == "agent_policy"
