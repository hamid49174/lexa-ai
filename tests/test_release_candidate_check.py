from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_script_orchestrates_required_gates():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8")

    required = [
        "run_clean_clone_smoke.ps1",
        "check_dependency_repro.ps1",
        "run_quality_gates.ps1",
        "run_eval_regression_gate.ps1",
        "check_risky_artifacts.ps1",
        "electron_startup_health_smoke.js",
        "electron_presence_challenge_smoke.js",
        "run_os_quality_gates.ps1",
        "run_hermes_smoke.ps1",
        "run_website_smoke.ps1",
        "run_paid_license_smoke.ps1",
        "run_packaging_smoke.ps1",
        "run_installer_smoke.ps1",
        "check_performance_budgets.ps1",
        "diff --check",
    ]
    for item in required:
        assert item in src


def test_release_candidate_script_does_not_deploy_or_delete():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8").lower()

    forbidden = [
        "upload-artifact",
        "action-gh-release",
        "npm publish",
        "electron-builder --publish",
        "gh release",
        "deploy",
        "remove-item",
        "git add .",
    ]
    for item in forbidden:
        assert item not in src


def test_release_candidate_script_supports_phase_4b_modes():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8")

    assert 'ValidateSet("LocalFull", "CICore", "Packaging", "Installer", "StrictRC")' in src
    assert 'ValidateSet("InternalRC", "PublicRC", "PublicRelease")' in src
    assert '$Mode -eq "CICore"' in src
    assert '$Mode -eq "Packaging"' in src
    assert '$Mode -eq "Installer"' in src
    assert '$Target -in @("PublicRC", "PublicRelease")' in src
    assert "Quality Gates CI" in src
    assert "Installer Smoke" in src


def test_release_candidate_script_reports_decision_and_warnings():
    src = (REPO_ROOT / "scripts" / "run_release_candidate_check.ps1").read_text(encoding="utf-8")

    assert "Release decision:" in src
    assert "Needs Review" in src
    assert "Blocked" in src
    assert "Ready" in src
    assert "Remote CI is not yet remotely proven" in src
    assert "Installer install/uninstall" in src
    assert "Installer signing status is" in src
    assert "Get-InstallerSigningStatus" in src
    assert "Public Supabase/Stripe config placeholders remain unresolved outside Git" in src
    assert "Stripe.js allowlist/CSP policy needs release-owner approval" in src
    assert "Paid activation smoke with real Supabase/Stripe config is not proven" in src
    assert "run_paid_license_smoke.ps1" in src
    assert "Public artifact policy is not proven on remote CI" in src
    assert "privacy_trace_consent_checklist.md" in src
    assert "checklist exists but is not finalized or approved" in src
    assert "Next actions:" in src
    assert "External prerequisites:" in src
    assert "[CI]" in src
    assert "[Installer]" in src
    assert "[Signing]" in src
    assert "[Website]" in src
    assert "[OS]" in src
    assert "[Privacy]" in src


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
    assert "InternalRC" in checklist
    assert "PublicRC" in checklist
    assert "PublicRelease" in checklist
    assert "PublicRC Blocker Matrix" in checklist
    assert "Phase 5B External Proof Actions" in checklist
    assert "agent-solvable" in checklist
    assert "privacy_trace_consent_checklist.md" in checklist


def test_privacy_trace_consent_checklist_exists_and_is_not_approval():
    text = (REPO_ROOT / "docs" / "release" / "privacy_trace_consent_checklist.md").read_text(encoding="utf-8")

    assert "Privacy and Trace Consent Checklist" in text
    assert "audit.log" in text
    assert "bridge-audit.log" in text
    assert "Agent traces" in text
    assert "Memory DB" in text
    assert "Clipboard history" in text
    assert "PublicRelease remains blocked" in text
    assert "Phase 5B Concrete Decisions Needed" in text
    assert "trace opt-in/opt-out" in text
    assert "does not collect user data" in text
    assert "sk-" not in text


def test_installer_build_script_documents_backend_bundle_order():
    script = (REPO_ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    package = (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    guard = (REPO_ROOT / "frontend" / "scripts" / "ensure-backend-bundle.cjs").read_text(encoding="utf-8")

    assert "build_backend.py" in script
    assert "backend-dist\\lexa-backend" in script
    assert "npm.cmd run build" in script
    assert "prebuild" in package
    assert "ensure-backend-bundle.cjs" in package
    assert "sync-vendor.cjs --check" in package
    assert "backend-dist" in guard
    assert "lexa-backend.exe" in guard
    assert "process.exit(1)" in guard
    assert "scripts\\build_installer.ps1" in readme
    assert "backend-dist\\lexa-backend\\lexa-backend.exe" in readme
    assert "npm run build" in readme and "Backend-Bundle" in readme
