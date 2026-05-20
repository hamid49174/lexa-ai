import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_performance_budget_doc_contains_conservative_targets():
    doc = (REPO_ROOT / "docs" / "release" / "performance_budgets.md").read_text(encoding="utf-8")

    assert "warn-only" in doc
    assert "Eval Suite" in doc
    assert "Quick Gate" in doc
    assert "Full Gate" in doc
    assert "Electron Startup Health Smoke" in doc
    assert "Packaging" in doc


def test_performance_budget_script_is_warn_only_by_default():
    src = (REPO_ROOT / "scripts" / "check_performance_budgets.ps1").read_text(encoding="utf-8")

    assert "[switch]$Strict" in src
    assert "Write-Warning" in src
    assert "run_eval_suite.py" in src


def test_performance_budget_script_runs():
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "check_performance_budgets.ps1"),
            "-EvalSuiteWarnSeconds",
            "120",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout
    assert "Performance budget smoke completed" in result.stdout
