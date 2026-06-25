import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_electron_builder_metadata_is_ascii_and_not_mojibake():
    config_path = REPO_ROOT / "frontend" / "electron-builder.json"
    text = config_path.read_text(encoding="utf-8")
    config = json.loads(text)

    assert text.isascii()
    assert "Â" not in text
    assert "Ã" not in text
    assert "�" not in text
    assert config["copyright"] == "Copyright (c) 2026 hamid49174"


def test_electron_builder_packages_backend_bundle_and_whitelist():
    config = json.loads((REPO_ROOT / "frontend" / "electron-builder.json").read_text(encoding="utf-8"))
    resources = config["extraResources"]

    assert any(item["from"] == "../backend-dist/lexa-backend" and item["to"] == "backend-dist" for item in resources)
    assert any(item["from"] == "../command_whitelist.json" and item["to"] == "command_whitelist.json" for item in resources)


def test_electron_builder_excludes_backend_runtime_artifacts():
    config = json.loads((REPO_ROOT / "frontend" / "electron-builder.json").read_text(encoding="utf-8"))
    backend_resource = next(item for item in config["extraResources"] if item["from"] == "../backend-dist/lexa-backend")
    filters = backend_resource["filter"]

    assert "!**/audit.log" in filters
    assert "!**/bridge-audit.log" in filters
    assert "!**/lexa_memory.db*" in filters


def test_electron_builder_allows_secure_release_signing_without_forcing_dev_signing():
    config_text = (REPO_ROOT / "frontend" / "electron-builder.json").read_text(encoding="utf-8")
    config = json.loads(config_text)
    win_config = config["win"]

    assert win_config["signAndEditExecutable"] is True
    assert win_config["forceCodeSigning"] is False
    assert ".pfx" not in config_text.lower()
    assert ".p12" not in config_text.lower()
    assert "csc_key_password" not in config_text.lower()


def test_release_workflow_requires_and_verifies_signed_installer():
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "WINDOWS_CSC_LINK" in release_workflow
    assert "WINDOWS_CSC_KEY_PASSWORD" in release_workflow
    assert "Require Windows signing secrets" in release_workflow
    assert "Get-AuthenticodeSignature" in release_workflow
    assert "Status -ne \"Valid\"" in release_workflow
    assert "npm ci" in release_workflow
    assert "actions/upload-artifact" not in ci_workflow
    assert "run_packaging_smoke.ps1 -ArtifactRoot dist" in ci_workflow
