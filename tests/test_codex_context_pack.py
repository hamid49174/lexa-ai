from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_agents_file_contains_core_safety_rules():
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Do not use `git add .`" in text
    assert "Do not delete files" in text
    assert "Do not commit user data" in text
    assert "personal_os/" in text
    assert "dist-*-build/" in text
    assert ".env.example" in text
    assert "placeholders only" in text
    assert ".netrc" in text
    assert ".npmrc" in text
    assert ".docker/config.json" in text
    assert "credentials.*" in text
    assert "secrets.*" in text
    assert ".ssh/id_rsa" in text
    assert ".keystore" in text
    assert "scripts\\run_quality_gates.ps1 -Mode Quick" in text
    assert "PublicRC" in text


def test_gitignore_covers_signing_artifacts_and_env_placeholder():
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    for pattern in [
        "*.key",
        "*.pem",
        "*.ppk",
        "*.pfx",
        "*.p12",
        "*.pvk",
        "*.cer",
        "*.crt",
        "*.spc",
        "*.jks",
        "*.keystore",
        "*.env",
        ".env.local",
        ".netrc",
        ".npmrc",
        ".pnpmrc",
        ".pypirc",
        ".yarnrc",
        ".yarnrc.yml",
        ".aws/credentials",
        ".aws/config",
        ".azure/accessTokens.json",
        ".azure/azureProfile.json",
        ".config/gcloud/application_default_credentials.json",
        ".docker/config.json",
        ".gcloud/application_default_credentials.json",
        ".kube/config",
        ".ssh/id_dsa",
        ".ssh/id_ecdsa",
        ".ssh/id_ed25519",
        ".ssh/id_rsa",
        "credentials.*",
        "secrets.*",
        "client_secret*.json",
        "service-account*.json",
        "service_account*.json",
        "pip.conf",
        "pip.ini",
    ]:
        assert pattern in text
    assert "!.env.example" in text


def test_repo_hygiene_docs_cover_isolated_build_outputs_and_env_placeholder():
    hygiene = (REPO_ROOT / "docs" / "repo_hygiene.md").read_text(encoding="utf-8")
    dev_testing = (REPO_ROOT / "docs" / "dev-testing.md").read_text(encoding="utf-8")

    for text in [hygiene, dev_testing]:
        assert "dist-*-build/" in text
        assert ".env.example" in text
        assert "placeholders" in text
        assert ".netrc" in text
        assert ".npmrc" in text
        assert ".docker/config.json" in text
        assert "credentials.*" in text
        assert "secrets.*" in text
        assert "client_secret*.json" in text
        assert "service-account*.json" in text
        assert "service_account*.json" in text
        assert ".ssh/id_rsa" in text
        assert "keystore" in text
        assert "Mode Warn" in text
        assert "Mode Strict" in text
    assert "completed with warnings" in dev_testing
    for pattern in [".pfx", ".pvk", ".spc", ".jks", ".keystore", "*.ppk"]:
        assert pattern in hygiene


def test_codex_context_pack_excludes_private_os_content():
    text = (REPO_ROOT / "docs" / "codex_context_pack.md").read_text(encoding="utf-8")

    assert "Current Project State" in text
    assert "Open Release Risks" in text
    assert "Agent/User/External Split" in text
    assert "personal_os/" in text
    assert "Do Not Load Or Commit" in text
    assert "private OS/Obsidian content" in text
    assert "06_Inbox/Drafts/2026-" not in text
    assert "05_Memory/Rollups/" not in text
    assert "sk-" not in text


def test_os_cleanup_inventory_is_category_level_only():
    text = (REPO_ROOT / "docs" / "release" / "os_cleanup_inventory.md").read_text(encoding="utf-8")

    assert "category-level inventory" in text
    assert "does not copy private OS/Obsidian content" in text
    assert "06_Inbox/Drafts/2026-" not in text
    assert "events.jsonl" not in text


def test_context_pack_generator_uses_safe_sources(tmp_path):
    output = tmp_path / "codex_context_pack.md"
    script = REPO_ROOT / "scripts" / "generate_codex_context_pack.ps1"

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OutputPath",
            str(output),
            "-Check",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout
    generated = output.read_text(encoding="utf-8")
    assert "PublicRC/PublicRelease remain blocked" in generated
    assert "public_rc_blocker_matrix.md" in generated
    assert "privacy_trace_consent_checklist.md" in generated
    assert "Agent/User/External Split" in generated
    assert "agent-solvable" in generated
    assert "scripts\\check_remote_ci_readiness.ps1" in generated
    assert "personal_os/" in generated
    assert "06_Inbox/Drafts/2026-" not in generated
    assert "05_Memory/Rollups/" not in generated
    assert "sk-" not in generated


def test_context_pack_generator_excludes_risky_paths():
    src = (REPO_ROOT / "scripts" / "generate_codex_context_pack.ps1").read_text(encoding="utf-8")

    assert "personal_os" in src
    assert "evals" in src and "results" in src
    assert "tmp" in src and "agent_traces" in src
    assert "lexa_memory" in src
    assert "Remove-Item" not in src


def test_agent_context_strategy_uses_allowlisted_sources():
    text = (REPO_ROOT / "docs" / "agent_context_strategy.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in text
    assert "docs/codex_context_pack.md" in text
    assert "personal_os/" in text
    assert "Forbidden Context Inputs" in text
    assert "private OS/Obsidian content" in text


def test_public_rc_blocker_matrix_is_structured_and_non_private():
    text = (REPO_ROOT / "docs" / "release" / "public_rc_blocker_matrix.md").read_text(encoding="utf-8")

    for blocker_id in [
        "PRC-001",
        "PRC-002",
        "PRC-003",
        "PRC-004",
        "PRC-005",
        "PRC-006",
        "PRC-007",
        "PRC-008",
        "PRC-009",
        "PRC-010",
    ]:
        assert blocker_id in text
    assert "InternalRC" in text
    assert "PublicRC" in text
    assert "PublicRelease" in text
    assert "Phase 5A Decisions" in text
    assert "Phase 5B Action Classification" in text
    assert "external infrastructure" in text
    assert "06_Inbox/Drafts/2026-" not in text
    assert "05_Memory/Rollups/" not in text
    assert "sk-" not in text


def test_privacy_context_artifact_is_safe_and_blocking():
    text = (REPO_ROOT / "docs" / "release" / "privacy_trace_consent_checklist.md").read_text(encoding="utf-8")

    assert "PublicRelease Blockers" in text
    assert "Trace sampling" in text
    assert "never committed" in text or "Never commit" in text
    assert "approved" in text
    assert "06_Inbox/Drafts/2026-" not in text
    assert "05_Memory/Rollups/" not in text
    assert "sk-" not in text
