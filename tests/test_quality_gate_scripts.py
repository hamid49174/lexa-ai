from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_quality_gates_include_release_script_tests_and_startup_smoke():
    src = read("scripts/run_quality_gates.ps1")

    assert "test_release_candidate_check.py" in src
    assert "test_codex_context_pack.py" in src
    assert "test_quality_gate_scripts.py" in src
    assert "test_performance_budgets.py" in src
    assert "test_risky_artifact_check.py" in src
    assert "test_clean_clone_smoke_script.py" in src
    assert "test_installer_smoke_script.py" in src
    assert "test_fastapi_lifespan.py" in src
    assert "check_risky_artifacts.ps1" in src
    assert "electron_startup_health_smoke.js" in src


def test_quality_gates_support_eval_and_ci_modes():
    src = read("scripts/run_quality_gates.ps1")

    assert 'ValidateSet("Quick", "Full", "Eval", "CI")' in src
    assert 'if ($Mode -eq "Eval")' in src
    assert 'if ($Mode -eq "CI")' in src
    assert "Invoke-EvalRegressionGate" in src
    assert "Invoke-PackagingConfigSmoke" in src
    assert "No .git directory found" in src


def test_github_quality_workflow_is_non_deploying_and_secret_free():
    workflow = read(".github/workflows/quality-gates.yml")

    assert "run_quality_gates.ps1 -Mode CI" in workflow
    assert "run_eval_regression_gate.ps1" in workflow
    assert "check_risky_artifacts.ps1" in workflow
    assert "run_packaging_smoke.ps1" in workflow
    assert "run_clean_clone_smoke.ps1 -DryRun" in workflow
    assert "run_release_candidate_check.ps1 -Mode CICore" in workflow
    assert "run_os_quality_gates.ps1 -AllowMissing" in workflow
    assert "actions/upload-artifact" not in workflow
    assert "softprops/action-gh-release" not in workflow
    assert "secrets." not in workflow


def test_dependency_repro_script_is_read_only():
    src = read("scripts/check_dependency_repro.ps1")

    assert "pip install" not in src
    assert "npm install" not in src
    assert "Remove-Item" not in src
    assert "package-lock.json" in src


def test_packaging_smoke_blocks_forbidden_content_without_cleanup():
    src = read("scripts/run_packaging_smoke.ps1")

    assert "electron-builder.json" in src
    assert "personal_os" in src
    assert "lexa_memory.db" in src
    assert "bridge-audit.log" in src
    assert "npx.cmd --no-install electron-builder" in src
    assert "Remove-Item" not in src


def test_eval_regression_gate_uses_unique_temp_paths():
    src = read("scripts/run_eval_regression_gate.ps1")

    assert "[System.IO.Path]::GetTempPath()" in src
    assert "[guid]::NewGuid()" in src
    assert "$RunId-current_eval_report.json" in src
    assert "current_eval_report.json" in src


def test_os_hermes_and_website_smokes_are_non_destructive():
    for script in [
        "scripts/run_os_quality_gates.ps1",
        "scripts/run_hermes_smoke.ps1",
        "scripts/run_website_smoke.ps1",
    ]:
        src = read(script)
        assert "Remove-Item" not in src
        assert "git add" not in src.lower()


def test_website_smoke_has_target_aware_public_rc_blocking():
    src = read("scripts/run_website_smoke.ps1")

    assert 'ValidateSet("InternalRC", "PublicRC", "PublicRelease")' in src
    assert "Website static-external target without package-based build/lint proof blocks" in src


def test_context_pack_generator_is_non_destructive():
    src = read("scripts/generate_codex_context_pack.ps1")

    assert "personal_os" in src
    assert "evals" in src and "results" in src
    assert "Remove-Item" not in src
