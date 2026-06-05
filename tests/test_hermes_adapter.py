import json
import sys


def test_hermes_status_uses_project_local_paths(monkeypatch):
    import backend.hermes_adapter as hermes

    monkeypatch.delenv("LEXA_HERMES_CMD", raising=False)
    monkeypatch.delenv("LEXA_HERMES_RUN_ARGS", raising=False)
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: None)
    monkeypatch.setattr(hermes.shutil, "which", lambda name: None)
    monkeypatch.setattr(hermes, "PERSONAL_OS_ROOT", hermes.PROJECT_ROOT / "personal_os")

    status = hermes.get_hermes_status()

    assert status["status"] == "ok"
    assert status["available"] is False
    assert status["health_state"] == "blocked"
    assert any(check["id"] == "command" and check["state"] == "blocked" for check in status["checks"])
    assert status["safe_mode"] is True
    assert status["workspace_root"].endswith("hermes_workspace")
    assert status["hermes_home"].endswith("hermes_workspace\\.hermes") or status["hermes_home"].endswith("hermes_workspace/.hermes")
    assert status["vendor_root"].endswith("vendor\\hermes-agent") or status["vendor_root"].endswith("vendor/hermes-agent")
    assert status["personal_os_root"].endswith("personal_os")


def test_personal_os_root_falls_back_to_mcp_config_when_project_link_is_unavailable(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    os_root = tmp_path / "Office" / "Desktop" / "OS"
    os_root.mkdir(parents=True)
    (os_root / "OS_MANIFEST.md").write_text("# Manifest\n", encoding="utf-8")
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
    monkeypatch.setattr(hermes, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("LEXA_PERSONAL_OS_ROOT", raising=False)
    monkeypatch.delenv("PERSONAL_OS_ROOT", raising=False)

    assert hermes._resolve_personal_os_root() == os_root


def test_hermes_run_returns_unavailable_without_command(monkeypatch):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: None)

    result = hermes.run_hermes_task("Improve Lexa backend", mode="lexa_improve")

    assert result["success"] is False
    assert result["status"] == "unavailable"
    assert "stable Personal OS memory" in result["prompt_preview"]
    assert "personal_os/06_Inbox/Drafts" in result["prompt_preview"]


def test_hermes_run_uses_configured_template(monkeypatch):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: [sys.executable])
    monkeypatch.setenv("LEXA_HERMES_RUN_ARGS", "-c \"print('hermes-ok')\"")

    result = hermes.run_hermes_task("Status only", timeout=10)

    assert result["success"] is True
    assert result["status"] == "completed"
    assert "hermes-ok" in result["stdout"]


def test_telegram_status_reports_missing_local_config(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: ["hermes.exe"])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)

    status = hermes.get_hermes_telegram_status()

    assert status["installed"] is True
    assert status["configured"] is False
    assert "TELEGRAM_BOT_TOKEN" in status["missing"]
    assert "TELEGRAM_HOME_CHANNEL" in status["missing"]
    assert status["token_preview"] is None


def test_hermes_status_reports_gateway_health(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: ["hermes.exe"])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    hermes.configure_hermes_telegram("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc", "987654321", "Lexa")

    status = hermes.get_hermes_status()

    assert status["available"] is True
    assert status["gateway"]["configured"] is True
    assert status["gateway"]["can_start"] is True
    assert any(check["id"] == "telegram-gateway" and check["state"] == "ok" for check in status["checks"])


def test_gateway_autostart_status_blocks_until_configured(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: None)
    monkeypatch.setattr(hermes.os, "name", "nt")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)

    status = hermes.get_hermes_gateway_autostart_status()

    assert status["supported"] is True
    assert status["enabled"] is False
    assert status["can_enable"] is False
    assert "TELEGRAM_BOT_TOKEN" in status["missing"]


def test_gateway_autostart_enable_writes_and_removes_startup_script(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: [sys.executable])
    monkeypatch.setattr(hermes.os, "name", "nt")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc"
    hermes.configure_hermes_telegram(token, "987654321", "Lexa")

    enabled = hermes.set_hermes_gateway_autostart(True)

    assert enabled["success"] is True
    assert enabled["status"] == "enabled"
    assert enabled["autostart"]["enabled"] is True
    assert enabled["autostart"]["script_current"] is True
    script_path = tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Lexa Hermes Gateway.cmd"
    script = script_path.read_text(encoding="utf-8")
    assert "gateway\" \"run\" \"--replace" in script or 'gateway" "run" "--replace' in script
    assert "HERMES_HOME" in script
    assert token not in script

    disabled = hermes.set_hermes_gateway_autostart(False)

    assert disabled["success"] is True
    assert disabled["status"] == "disabled"
    assert not script_path.exists()


def test_gateway_autostart_status_marks_stale_startup_script(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: [sys.executable])
    monkeypatch.setattr(hermes.os, "name", "nt")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    hermes.configure_hermes_telegram("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc", "987654321", "Lexa")

    script_path = tmp_path / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Lexa Hermes Gateway.cmd"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        "\r\n".join([
            "@echo off",
            "set \"HERMES_HOME=C:\\old\\lexa\\hermes_workspace\\.hermes\"",
            "cd /d \"C:\\old\\lexa\"",
            "\"C:\\old\\lexa\\vendor\\hermes-agent\\venv\\Scripts\\hermes.exe\" \"gateway\" \"run\" \"--replace\"",
            "",
        ]),
        encoding="utf-8",
    )

    status = hermes.get_hermes_gateway_autostart_status()

    assert status["script_exists"] is True
    assert status["enabled"] is False
    assert status["configured"] is False
    assert status["stale"] is True
    assert status["can_enable"] is True
    assert "current Lexa workspace" in status["nextAction"]

    refreshed = hermes.set_hermes_gateway_autostart(True)

    assert refreshed["success"] is True
    assert refreshed["autostart"]["enabled"] is True
    assert refreshed["autostart"]["script_current"] is True
    assert "C:\\old\\lexa" not in script_path.read_text(encoding="utf-8")


def test_gateway_log_summary_reads_bounded_redacted_tail(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    log_path = tmp_path / ".hermes" / "logs" / "gateway.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join([
            "2026-05-19 01:00:00,000 INFO gateway.run: Starting Hermes Gateway...",
            "2026-05-19 01:00:01,000 INFO gateway.run: inbound message: platform=telegram user=1234567890 chat=1234567890 msg='hi'",
            "2026-05-19 01:00:02,000 INFO gateway.run: response ready: platform=telegram chat=1234567890 time=1.0s api_calls=1 response=20 chars",
            "2026-05-19 01:00:03,000 WARNING gateway.run: Unauthorized user: 1234567890 on telegram",
        ]),
        encoding="utf-8",
    )

    summary = hermes.get_hermes_gateway_log_summary(20)

    assert summary["exists"] is True
    assert summary["health_state"] == "attention"
    assert summary["counts"]["inbound_messages"] == 1
    assert summary["counts"]["responses_ready"] == 1
    assert summary["counts"]["issues"] == 1
    assert "1234567890" not in str(summary)


def test_gateway_log_summary_marks_raw_traceback_as_attention(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    log_path = tmp_path / ".hermes" / "logs" / "gateway.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join([
            "Hermes Gateway Starting...",
            "Traceback (most recent call last):",
            "ValueError: startup failed",
        ]),
        encoding="utf-8",
    )

    summary = hermes.get_hermes_gateway_log_summary(20)

    assert summary["health_state"] == "attention"
    assert summary["counts"]["issues"] == 2
    assert "Auffaelligkeiten" in summary["summary"]


def test_telegram_configure_writes_local_env_without_leaking_token(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: ["hermes.exe"])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc"

    result = hermes.configure_hermes_telegram(token, "987654321", "Lexa")

    assert result["success"] is True
    assert result["status"] == "configured"
    assert token not in str(result)
    env_text = (tmp_path / ".hermes" / ".env").read_text(encoding="utf-8")
    assert f'TELEGRAM_BOT_TOKEN="{token}"' in env_text
    assert 'TELEGRAM_HOME_CHANNEL="987654321"' in env_text


def test_telegram_configure_can_add_channel_after_token(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    monkeypatch.setattr(hermes, "_resolve_hermes_command", lambda: ["hermes.exe"])
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_HOME_CHANNEL", raising=False)
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc"
    hermes.configure_hermes_telegram(token, "", "Lexa")

    result = hermes.configure_hermes_telegram("", "987654321", "Lexa")

    assert result["success"] is True
    assert result["status"] == "configured"
    env_text = (tmp_path / ".hermes" / ".env").read_text(encoding="utf-8")
    assert f'TELEGRAM_BOT_TOKEN="{token}"' in env_text
    assert 'TELEGRAM_HOME_CHANNEL="987654321"' in env_text


def test_improve_prompt_mentions_os_draft_boundary():
    import backend.hermes_adapter as hermes

    prompt = hermes.build_hermes_prompt("Improve Lexa", mode="lexa_improve")

    assert "Lexa repo" in prompt
    assert "Deutsch, per du, kurz, produktiv" in prompt
    assert "API-gestuetzt" in prompt
    assert "Do not overwrite stable Personal OS memory" in prompt
    assert "personal_os/06_Inbox/Drafts" in prompt
    assert "Obsidian/Personal OS Context Layer" in prompt


def test_hermes_capabilities_report_model_provider_blocker(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    capabilities = hermes.get_hermes_capabilities({
        "available": True,
        "source_available": True,
        "personal_os_available": True,
        "gateway": {"configured": False},
    })

    assert capabilities["healthState"] == "attention"
    assert capabilities["providerAccess"]["primaryReady"] is False
    assert capabilities["providerAccess"]["secretsRedacted"] is True
    assert "/hermes/capabilities" in capabilities["lexaSurfaces"]["backendEndpoints"]
    assert any(gap["id"] == "agent-runtime" for gap in capabilities["gaps"])
    assert capabilities["counts"]["missingLexaSurface"] >= 1


def test_hermes_capabilities_detect_provider_without_leaking_secret(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    secret = "sk-test-super-secret-value"
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    capabilities = hermes.get_hermes_capabilities({
        "available": True,
        "source_available": True,
        "personal_os_available": True,
        "gateway": {"configured": True},
    })

    assert capabilities["providerAccess"]["primaryReady"] is True
    assert capabilities["providerAccess"]["primary"] == ["openai"]
    assert secret not in str(capabilities)
    assert capabilities["counts"]["primaryProviders"] == 1


def test_hermes_capabilities_parse_export_env_with_invalid_bytes(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / ".env").write_bytes(b"export OPENAI_API_KEY=placeholder-provider-token\xff\n")
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", hermes_home)
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    capabilities = hermes.get_hermes_capabilities({
        "available": True,
        "source_available": True,
        "personal_os_available": True,
        "gateway": {"configured": False},
    })

    assert capabilities["providerAccess"]["primaryReady"] is True
    assert capabilities["providerAccess"]["primary"] == ["openai"]
    assert "placeholder-provider-token" not in str(capabilities)


def test_hermes_provider_status_reads_fallback_chain_without_leaking_secrets(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    secret = "sk-test-provider-secret"
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / ".env").write_text(f'OPENAI_API_KEY="{secret}"\nGEMINI_API_KEY="gemini-secret"\n', encoding="utf-8")
    (hermes_home / "config.yaml").write_text(
        "\n".join([
            "model:",
            "  provider: openai",
            "  default: gpt-4.1",
            "fallback_providers:",
            "  - provider: gemini",
            "    model: gemini-2.5-pro",
            "  - provider: custom",
            "    model: local-agent",
            "    base_url: http://127.0.0.1:1234/v1",
            "fallback_model:",
            "  provider: gemini",
            "  model: gemini-2.5-pro",
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", hermes_home)
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    status = hermes.get_hermes_provider_status({"available": True})

    assert status["healthState"] == "ready"
    assert status["primary"]["provider"] == "openai"
    assert status["counts"]["fallbacks"] == 2
    assert status["counts"]["fallbacksReady"] == 2
    assert status["fallbacks"][0]["providerId"] == "google"
    assert status["fallbacks"][1]["providerId"] == "custom"
    assert secret not in str(status)
    assert "gemini-secret" not in str(status)
    assert status["setup"]["secretsRedacted"] is True


def test_hermes_provider_status_blocks_when_primary_missing(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "model:\n  provider: anthropic\n  default: claude-opus-4.6\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", hermes_home)
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    status = hermes.get_hermes_provider_status({"available": True})

    assert status["healthState"] == "blocked"
    assert status["ok"] is False
    assert status["counts"]["fallbacks"] == 0
    assert "hermes model" in status["nextAction"]


def test_hermes_media_status_reads_config_without_leaking_secrets(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    secret = "fal-secret-value"
    codex_secret = "codex-secret-token"
    (hermes_home / ".env").write_text(
        "\n".join([
            f'FAL_KEY="{secret}"',
            'ELEVENLABS_API_KEY="voice-secret"',
            "",
        ]),
        encoding="utf-8",
    )
    (hermes_home / "auth.json").write_text(
        '{"providers":{"openai-codex":{"tokens":{"access_token":"%s"}}}' % codex_secret,
        encoding="utf-8",
    )
    (hermes_home / "config.yaml").write_text(
        "\n".join([
            "model:",
            "  provider: openai-codex",
            "  default: gpt-5.1-codex",
            "tts:",
            "  provider: elevenlabs",
            "stt:",
            "  provider: local",
            "image_gen:",
            "  provider: fal",
            "  model: fal-ai/flux-2-pro",
            "video_gen:",
            "  provider: fal",
            "  model: fal-ai/veo3.1/text-to-video",
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", hermes_home)
    for keys in hermes._HERMES_PROVIDER_ENV_KEYS.values():
        for key in keys:
            monkeypatch.delenv(key, raising=False)

    status = hermes.get_hermes_media_status({"available": True})

    assert status["safeMode"] is True
    assert status["counts"]["total"] == 5
    assert status["counts"]["ready"] >= 4
    assert status["areas"][0]["id"] == "tts"
    assert any(area["id"] == "image-generation" and area["provider"] == "fal" for area in status["areas"])
    assert secret not in str(status)
    assert codex_secret not in str(status)
    assert status["setup"]["secretsRedacted"] is True


def test_hermes_prompt_injects_bounded_obsidian_context(monkeypatch):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "build_obsidian_context_payload", lambda **kwargs: {
        "ok": True,
        "vault": {"root": "C:/OS", "type": "obsidian-compatible-markdown", "loadedAll": False},
        "policy": {"readMode": "bounded-index-routed", "stableWrites": "draft-approval-only"},
        "counts": {"bootstrapAvailable": 1, "areaIndexes": 2},
        "files": [{"title": "Manifest", "path": "OS_MANIFEST.md", "bodyPreview": "Rules"}],
    })
    monkeypatch.setattr(hermes, "format_obsidian_context_for_prompt", lambda payload, limit=4800: "Obsidian bootstrap for Hermes")

    prompt = hermes.build_hermes_prompt("Use OS context", mode="os_context")

    assert "Obsidian bootstrap for Hermes" in prompt
    assert "Do not overwrite stable Personal OS memory" in prompt


def test_telegram_command_selftest_runs_plugin_without_external_sends(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    plugin_path = tmp_path / ".hermes" / "plugins" / "lexa-status" / "__init__.py"
    plugin_path.parent.mkdir(parents=True)
    plugin_path.write_text("# fake plugin", encoding="utf-8")
    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")

    class FakePlugin:
        def _pre_gateway_dispatch(self, event):
            text = getattr(event, "text", "")
            mapping = {
                "Wie findest du mein OS und Hermes?": "/lexa_overview",
                "Hermes Logs bitte": "/lexa_logs",
                "Welche Hermes Baustellen sind offen?": "/lexa_tasks",
                "Such im OS nach Provider-Fallback": "/lexa_context Such im OS nach Provider-Fallback",
                "Welche Drafts sind offen?": "/lexa_drafts",
                "Erstelle einen Lexa OS Draft: Status merken": "/lexa_draft Erstelle einen Lexa OS Draft: Status merken",
                "Was ist der Stand von Lexa/OS?": "/lexa_status",
            }
            return {"action": "rewrite", "text": mapping[text]}

        def register(self, ctx):
            for command in hermes._LEXA_TELEGRAM_COMMANDS:
                ctx.register_command(command, lambda raw="": "ok")
            ctx.register_hook("pre_gateway_dispatch", self._pre_gateway_dispatch)

        def _plugin_status(self, raw=""):
            return "Lexa/OS Stand:\n- ok"

        def _plugin_overview(self, raw=""):
            return "Lexa/Hermes Overview:\n- ok"

        def _plugin_logs(self, raw=""):
            return "Hermes Gateway Logs:\n- Zustand: ok"

        def _plugin_tasks(self, raw=""):
            return "Lexa Tasks:\n- Test"

        def _plugin_context(self, raw=""):
            return "Lexa Kontext: Hermes Status\n- bounded"

        def _post_json(self, url, payload, timeout=5.0):
            raise AssertionError("selftest must replace draft write with a dry-run")

        def _plugin_draft(self, raw=""):
            result = self._post_json("/hermes/draft", {"title": "Dry", "body": raw})
            return f"Lexa Draft erstellt:\n- Draft: {result['draftPath']}"

        def _plugin_drafts(self, raw=""):
            return "Lexa Drafts:\n- pending=0"

    monkeypatch.setattr(hermes, "_load_lexa_status_plugin", lambda: FakePlugin())

    result = hermes.get_hermes_telegram_command_selftest(include_samples=False)

    assert result["state"] == "ready"
    assert result["ok"] is True
    assert result["externalSends"] is False
    assert result["stableWrites"] == "none"
    assert result["counts"]["commandOk"] == 7
    assert result["counts"]["rewriteOk"] == 7
    draft = next(item for item in result["commands"] if item["command"] == "lexa-draft")
    assert draft["dryRun"] is True
    assert draft["mutates"] is True
    assert "sample" not in draft


def test_telegram_command_selftest_blocks_when_plugin_missing(monkeypatch, tmp_path):
    import backend.hermes_adapter as hermes

    monkeypatch.setattr(hermes, "HERMES_HOME_ROOT", tmp_path / ".hermes")

    result = hermes.get_hermes_telegram_command_selftest()

    assert result["state"] == "blocked"
    assert result["ok"] is False
    assert result["commands"] == []
