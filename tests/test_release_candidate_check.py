from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_script_orchestrates_required_gates():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8")

    required = [
        "run_quality_gates.ps1",
        "run_eval_regression_gate.ps1",
        "check_risky_artifacts.ps1",
        "electron_startup_health_smoke.js",
        "electron_presence_challenge_smoke.js",
        "run_os_quality_gates.ps1",
        "run_hermes_smoke.ps1",
        "run_website_smoke.ps1",
        "run_packaging_smoke.ps1",
        "check_performance_budgets.ps1",
        "diff --check",
    ]
    for item in required:
        assert item in src


def test_release_candidate_script_does_not_deploy_or_delete():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8").lower()

    forbidden = ["upload-artifact", "action-gh-release", "publish", "deploy", "remove-item", "git add ."]
    for item in forbidden:
        assert item not in src


def test_release_docs_exist_and_cover_decision_states():
    checklist = (REPO_ROOT / "docs" / "release" / "release_candidate_checklist.md").read_text(encoding="utf-8")

    assert "Security Gates" in checklist
    assert "Eval Gates" in checklist
    assert "OS Gates" in checklist
    assert "Hermes Gates" in checklist
    assert "Website Gates" in checklist
    assert "Packaging Gates" in checklist
    assert "Ready" in checklist
    assert "Blocked" in checklist
    assert "Needs Review" in checklist
