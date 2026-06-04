import json


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_obsidian_context_root_uses_mcp_config_when_project_link_is_unavailable(monkeypatch, tmp_path):
    from backend import obsidian_context

    os_root = tmp_path / "Office" / "Desktop" / "OS"
    os_root.mkdir(parents=True)
    _write(os_root / "OS_MANIFEST.md", "# Manifest\n")
    (tmp_path / "mcp_servers.json").write_text(
        json.dumps({
            "servers": {
                "personal_os": {
                    "env": {
                        "PERSONAL_OS_ROOT": str(os_root),
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(obsidian_context, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LEXA_PERSONAL_OS_ROOT", raising=False)
    monkeypatch.delenv("PERSONAL_OS_ROOT", raising=False)

    assert obsidian_context.resolve_personal_os_root() == os_root


def test_obsidian_context_builds_bounded_vault_packet(monkeypatch, tmp_path):
    from backend.obsidian_context import build_obsidian_context_payload

    monkeypatch.setenv("LEXA_PERSONAL_OS_ROOT", str(tmp_path))
    _write(tmp_path / "OS_MANIFEST.md", "---\ntitle: Manifest\ntags: [os]\n---\n# Manifest\nCanonical structure.")
    _write(tmp_path / "00_System" / "INDEX.md", "---\ntitle: System Index\ntags: [system]\n---\n# System\nRoutes.")
    _write(tmp_path / "00_System" / "Soul.md", "---\ntitle: Soul\ntags: [posture]\n---\n# Soul\nWarm collaboration.")
    _write(tmp_path / "08_Lexa" / "INDEX.md", "---\ntitle: Lexa Index\ntags: [lexa]\n---\n# Lexa\nLexa context.")
    _write(tmp_path / "08_Lexa" / "Hermes.md", "---\ntitle: Hermes Bridge\ntags: [lexa, hermes]\n---\n# Hermes\nHermes reads routed context.")

    payload = build_obsidian_context_payload(
        topic="lexa hermes obsidian",
        max_files=4,
        body_chars=260,
        include_previews=True,
    )

    assert payload["ok"] is True
    assert payload["vault"]["loadedAll"] is False
    assert payload["policy"]["stableWrites"] == "draft-approval-only"
    assert payload["lexaProductContract"]["providerMode"] == "api-backed"
    assert payload["counts"]["selectedFiles"] <= 4
    assert "OS_MANIFEST.md" in payload["bootstrapFiles"]
    assert payload["lexaInventory"]["policy"]["copyCodeIntoObsidian"] is False
    assert any(item["goTo"] == "backend/hermes_adapter.py" for item in payload["lexaInventory"]["quickFind"])
    assert any(file["path"] == "08_Lexa/INDEX.md" for file in payload["files"])


def test_obsidian_context_prompt_names_boundaries(monkeypatch, tmp_path):
    from backend.obsidian_context import build_obsidian_context_payload, format_obsidian_context_for_prompt

    monkeypatch.setenv("LEXA_PERSONAL_OS_ROOT", str(tmp_path))
    _write(tmp_path / "OS_MANIFEST.md", "# Manifest\nUse indexes.")
    _write(tmp_path / "START_NEW_AI_CHAT.md", "# New Chat\nCompact packet.")

    payload = build_obsidian_context_payload(topic="lexa", max_files=2, body_chars=200)
    prompt = format_obsidian_context_for_prompt(payload, limit=2000)

    assert "Obsidian/Personal OS Context Layer" in prompt
    assert "Loaded all vault files: False" in prompt
    assert "Provider mode: api-backed" in prompt
    assert "Lexa quick-find routes" in prompt
    assert "06_Inbox/Drafts" in prompt
    assert "OS_MANIFEST.md" in prompt


def test_obsidian_context_prioritizes_lexa_status_pages(monkeypatch, tmp_path):
    from backend.obsidian_context import build_obsidian_context_payload

    monkeypatch.setenv("LEXA_PERSONAL_OS_ROOT", str(tmp_path))
    _write(tmp_path / "OS_MANIFEST.md", "# Manifest\nUse indexes.")
    _write(tmp_path / "05_Memory" / "Rollups" / "Current_AI_Brief.md", "# Brief\nCompact status.")
    _write(tmp_path / "08_Lexa" / "INDEX.md", "# Lexa\nIndex.")
    _write(tmp_path / "08_Lexa" / "Architecture" / "Lexa_Context_Index.md", "# Lexa Context\nRoutes.")
    _write(tmp_path / "08_Lexa" / "Architecture" / "Hermes_Capabilities.md", "# Hermes\nTelegram.")
    _write(tmp_path / "08_Lexa" / "Tasks" / "Lexa_OS_Live_Status.md", "# Live Status\nAnswer surface.")
    _write(tmp_path / "06_Inbox" / "Draft_Index.md", "# Drafts\n0 pending.")

    payload = build_obsidian_context_payload(
        topic="Was ist der Stand von Lexa OS Hermes Telegram?",
        max_files=4,
        body_chars=220,
    )

    paths = [file["path"] for file in payload["files"]]
    assert "08_Lexa/Architecture/Lexa_Context_Index.md" in paths
    assert "08_Lexa/Architecture/Hermes_Capabilities.md" in paths
    assert "08_Lexa/Tasks/Lexa_OS_Live_Status.md" in paths
