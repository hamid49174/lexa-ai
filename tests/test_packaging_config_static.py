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
    assert config["copyright"] == "Copyright (c) 2026 alexsprogis"


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
