from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    import backend.router_hermes as router_hermes

    monkeypatch.setattr(router_hermes, "check_rate_limit", lambda bucket: True)
    monkeypatch.setattr(router_hermes, "audit_log", lambda *args, **kwargs: None)

    app = FastAPI()
    app.include_router(router_hermes.router)
    return TestClient(app), router_hermes


def test_hermes_status_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_status", lambda: {
        "status": "ok",
        "available": False,
        "safe_mode": True,
    })

    res = client.get("/hermes/status")

    assert res.status_code == 200
    assert res.json()["safe_mode"] is True


def test_hermes_capabilities_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_capabilities", lambda: {
        "ok": True,
        "healthState": "attention",
        "summary": "Hermes capability map: 5/11 groups ready.",
        "counts": {"ready": 5, "total": 11, "missingLexaSurface": 2},
        "gaps": [{"id": "tool-platform", "state": "attention"}],
        "safeMode": True,
    })

    res = client.get("/hermes/capabilities")

    assert res.status_code == 200
    data = res.json()
    assert data["safeMode"] is True
    assert data["counts"]["missingLexaSurface"] == 2
    assert data["gaps"][0]["id"] == "tool-platform"


def test_hermes_providers_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_provider_status", lambda: {
        "ok": True,
        "healthState": "attention",
        "summary": "Hermes provider setup: primary ready, 0/0 fallback(s) credential-ready.",
        "primary": {"provider": "auto", "effectiveProviderHint": "openai"},
        "fallbacks": [],
        "counts": {"configuredProviders": 1, "fallbacks": 0, "fallbacksReady": 0},
        "setup": {"secretsRedacted": True},
        "safeMode": True,
    })

    res = client.get("/hermes/providers")

    assert res.status_code == 200
    data = res.json()
    assert data["safeMode"] is True
    assert data["primary"]["effectiveProviderHint"] == "openai"
    assert data["setup"]["secretsRedacted"] is True


def test_hermes_media_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_media_status", lambda: {
        "ok": True,
        "healthState": "attention",
        "summary": "Hermes media readiness: 3/5 areas ready.",
        "areas": [{"id": "tts", "provider": "edge", "healthState": "ready"}],
        "counts": {"ready": 3, "total": 5, "attention": 2},
        "setup": {"secretsRedacted": True},
        "safeMode": True,
    })

    res = client.get("/hermes/media")

    assert res.status_code == 200
    data = res.json()
    assert data["safeMode"] is True
    assert data["counts"]["total"] == 5
    assert data["areas"][0]["id"] == "tts"
    assert data["setup"]["secretsRedacted"] is True


def test_hermes_extensions_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_extension_status", lambda: {
        "ok": True,
        "healthState": "attention",
        "summary": "Hermes extension readiness: 3/5 areas ready.",
        "areas": [{"id": "skills", "healthState": "ready"}],
        "counts": {"ready": 3, "total": 5, "enabledPlugins": 1},
        "setup": {"secretsRedacted": True},
        "safeMode": True,
    })

    res = client.get("/hermes/extensions")

    assert res.status_code == 200
    data = res.json()
    assert data["safeMode"] is True
    assert data["counts"]["enabledPlugins"] == 1
    assert data["areas"][0]["id"] == "skills"
    assert data["setup"]["secretsRedacted"] is True


def test_hermes_overview_endpoint_returns_compact_system_packet(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_status", lambda: {
        "health_state": "ready",
        "summary": "Hermes ready",
        "obsidian_context": {"ok": True, "summary": "OS context ok"},
        "personal_os_root": "C:/OS",
    })
    monkeypatch.setattr(router_hermes, "get_hermes_telegram_status", lambda: {"configured": True})
    monkeypatch.setattr(router_hermes, "get_hermes_gateway_autostart_status", lambda: {"enabled": True})
    monkeypatch.setattr(router_hermes, "get_hermes_gateway_log_summary", lambda lines: {
        "status": "ok",
        "health_state": "ok",
        "summary": "Keine Fehler.",
        "counts": {"issues": 0},
    })
    monkeypatch.setattr(router_hermes, "_read_next_work_tasks", lambda hermes: ["Build visible OS/Hermes cockpit"])

    async def fake_drafts(approval, max_drafts, hide_smoke):
        assert approval == "all"
        return {
            "counts": {"pending": 0, "approved": 11, "rejected": 3, "missing": 0, "invalid": 0},
            "drafts": [],
        }

    monkeypatch.setattr(router_hermes, "list_hermes_os_drafts", fake_drafts)
    monkeypatch.setattr(router_hermes, "build_obsidian_context_payload", lambda **kwargs: {
        "ok": True,
        "files": [{
            "title": "Hermes Capabilities",
            "path": "08_Lexa/Architecture/Hermes_Capabilities.md",
            "tags": ["lexa", "hermes"],
        }],
    })
    monkeypatch.setattr(router_hermes, "get_hermes_capabilities", lambda status=None: {
        "healthState": "attention",
        "summary": "Hermes capability map: 6/11 groups ready.",
        "counts": {"ready": 6, "total": 11, "weakLexaSurface": 3, "missingLexaSurface": 2},
        "gaps": [{"id": "tool-platform", "state": "attention", "lexaSurface": "weak"}],
        "providerStatus": {
            "healthState": "attention",
            "primary": {"provider": "auto", "effectiveProviderHint": "openai"},
            "fallbacks": [],
            "counts": {"fallbacks": 0, "fallbacksReady": 0},
        },
        "mediaStatus": {
            "healthState": "attention",
            "summary": "Hermes media readiness: 3/5 areas ready.",
            "counts": {"ready": 3, "total": 5, "attention": 2},
            "areas": [{"id": "tts", "provider": "edge", "healthState": "ready"}],
        },
        "extensionStatus": {
            "healthState": "attention",
            "summary": "Hermes extension readiness: 3/5 areas ready.",
            "counts": {"ready": 3, "total": 5, "enabledPlugins": 1},
            "areas": [{"id": "skills", "healthState": "ready"}],
        },
    })

    res = client.get("/hermes/overview")

    assert res.status_code == 200
    data = res.json()
    assert data["healthState"] == "ready"
    assert data["safeMode"] is True
    assert data["nextAction"] == "Build visible OS/Hermes cockpit"
    assert "/hermes/overview" in data["capabilities"]["backendEndpoints"]
    assert "/hermes/capabilities" in data["capabilities"]["backendEndpoints"]
    assert "/hermes/media" in data["capabilities"]["backendEndpoints"]
    assert "/hermes/extensions" in data["capabilities"]["backendEndpoints"]
    assert "/hermes/telegram/commands/selftest" in data["capabilities"]["backendEndpoints"]
    assert data["capabilities"]["counts"]["missingLexaSurface"] == 2
    assert data["capabilities"]["gaps"][0]["id"] == "tool-platform"
    assert data["providerStatus"]["primary"]["effectiveProviderHint"] == "openai"
    assert data["mediaStatus"]["counts"]["total"] == 5
    assert data["extensionStatus"]["counts"]["enabledPlugins"] == 1
    assert "/lexa_overview" in data["capabilities"]["telegramCommands"]
    assert "Drafts 0 pending, 11 approved, 3 rejected" in data["summary"]
    assert data["contextFiles"][0]["path"] == "08_Lexa/Architecture/Hermes_Capabilities.md"


def test_hermes_run_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)

    def fake_run(message, mode, timeout):
        return {"success": True, "message": message, "mode": mode, "timeout": timeout}

    monkeypatch.setattr(router_hermes, "run_hermes_task", fake_run)

    res = client.post("/hermes/run", json={
        "message": "Improve Lexa",
        "mode": "lexa_improve",
        "timeoutSeconds": 30,
    })

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["mode"] == "lexa_improve"


def test_hermes_context_endpoint_returns_prompt(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    calls = []

    def fake_context(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "vault": {"loadedAll": False}, "files": []}

    monkeypatch.setattr(router_hermes, "build_obsidian_context_payload", fake_context)
    monkeypatch.setattr(router_hermes, "format_obsidian_context_for_prompt", lambda payload: "Obsidian prompt")

    res = client.post("/hermes/context", json={
        "topic": "lexa hermes",
        "maxFiles": 4,
        "bodyChars": 500,
        "includePreviews": False,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["prompt"] == "Obsidian prompt"
    assert calls == [{
        "topic": "lexa hermes",
        "max_files": 4,
        "body_chars": 500,
        "include_previews": False,
    }]


def test_hermes_draft_endpoint_creates_safe_review_draft(monkeypatch):
    client, router_hermes = _client(monkeypatch)

    async def fake_create(req):
        return {
            "success": True,
            "status": "draft",
            "title": req.title or "Draft",
            "targetPath": "05_Memory/Session/example.md",
            "draftPath": "06_Inbox/Drafts/example_update.md",
            "safeMode": True,
        }

    monkeypatch.setattr(router_hermes, "create_hermes_os_draft", fake_create)

    res = client.post("/hermes/draft", json={
        "title": "Remember Hermes context",
        "body": "Hermes should expose status, logs, tasks, context, and drafts.",
    })

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["safeMode"] is True
    assert res.json()["draftPath"].startswith("06_Inbox/Drafts/")


def test_hermes_draft_rejects_draft_directory_target():
    import backend.router_hermes as router_hermes

    try:
        router_hermes._safe_target_path("06_Inbox/Drafts/manual.md", "Manual")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("draft directory target was accepted")


def test_hermes_drafts_endpoint_lists_review_queue(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    seen = []

    async def fake_list(approval, max_drafts, hide_smoke):
        seen.append((approval, max_drafts, hide_smoke))
        return {
            "ok": True,
            "approval": approval,
            "counts": {"pending": 1, "approved": 2, "rejected": 0, "missing": 0},
            "drafts": [{
                "title": "Hermes capability update",
                "path": "06_Inbox/Drafts/hermes.md",
                "approval": "pending",
            }],
            "safeMode": True,
        }

    monkeypatch.setattr(router_hermes, "list_hermes_os_drafts", fake_list)

    res = client.get("/hermes/drafts?approval=pending&maxDrafts=8&hideSmoke=true")

    assert res.status_code == 200
    assert res.json()["safeMode"] is True
    assert res.json()["drafts"][0]["path"].startswith("06_Inbox/Drafts/")
    assert seen == [("pending", 8, True)]


def test_hermes_telegram_status_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_telegram_status", lambda: {
        "status": "ok",
        "configured": False,
        "missing": ["TELEGRAM_BOT_TOKEN"],
    })

    res = client.get("/hermes/telegram/status")

    assert res.status_code == 200
    assert res.json()["missing"] == ["TELEGRAM_BOT_TOKEN"]


def test_hermes_telegram_command_selftest_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    seen = []

    def fake_selftest(include_samples=True):
        seen.append(include_samples)
        return {
            "ok": True,
            "state": "ready",
            "summary": "Lexa Telegram command selftest: 7/7 commands runnable, 7/7 rewrites ok.",
            "commands": [{"command": "lexa-logs", "state": "ok"}],
            "externalSends": False,
            "stableWrites": "none",
        }

    monkeypatch.setattr(router_hermes, "get_hermes_telegram_command_selftest", fake_selftest)

    res = client.get("/hermes/telegram/commands/selftest?includeSamples=false")

    assert res.status_code == 200
    assert res.json()["state"] == "ready"
    assert res.json()["externalSends"] is False
    assert seen == [False]


def test_hermes_gateway_autostart_status_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_gateway_autostart_status", lambda: {
        "status": "ok",
        "supported": True,
        "enabled": False,
        "can_enable": True,
    })

    res = client.get("/hermes/gateway/autostart")

    assert res.status_code == 200
    assert res.json()["can_enable"] is True


def test_hermes_gateway_logs_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "get_hermes_gateway_log_summary", lambda lines: {
        "status": "ok",
        "exists": True,
        "tail_lines": lines,
        "summary": "Keine Fehler.",
    })

    res = client.get("/hermes/gateway/logs?lines=80")

    assert res.status_code == 200
    assert res.json()["tail_lines"] == 80


def test_hermes_gateway_autostart_set_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    seen = []
    monkeypatch.setattr(router_hermes, "set_hermes_gateway_autostart", lambda enabled: {
        "success": True,
        "status": "enabled" if enabled else "disabled",
        "autostart": {"enabled": enabled},
    })
    monkeypatch.setattr(router_hermes, "audit_log", lambda *args, **kwargs: seen.append(args))

    res = client.post("/hermes/gateway/autostart", json={"enabled": True})

    assert res.status_code == 200
    assert res.json()["status"] == "enabled"
    assert seen and seen[0][1] == "gateway_autostart"


def test_hermes_telegram_configure_endpoint_does_not_log_token(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    seen = []
    monkeypatch.setattr(router_hermes, "audit_log", lambda *args, **kwargs: seen.append(args))
    monkeypatch.setattr(router_hermes, "configure_hermes_telegram", lambda token, channel, name: {
        "success": True,
        "status": "configured",
        "token_preview": "1234...abcd",
        "home_channel_configured": bool(channel),
    })

    res = client.post("/hermes/telegram/configure", json={
        "botToken": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc",
        "homeChannel": "987654321",
        "homeChannelName": "Lexa",
    })

    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabc" not in str(seen)


def test_hermes_error_details_redact_paths_tokens_and_license(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    local_path = r"C:\Users\admin\secret.txt"
    telegram_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabc"
    license_key = "LEXA-ABCDE-12345-F00D1-BEEF0"

    def fake_run(message, mode, timeout):
        raise RuntimeError(
            f"failed at {local_path} token=supersecretvalue bot={telegram_token} license={license_key}"
        )

    monkeypatch.setattr(router_hermes, "run_hermes_task", fake_run)

    res = client.post("/hermes/run", json={"message": "status"})

    assert res.status_code == 502
    detail = res.json()["detail"]
    assert "[local-path-redacted]" in detail
    assert "[telegram-token-redacted]" in detail
    assert "[license-redacted]" in detail
    assert local_path not in detail
    assert telegram_token not in detail
    assert license_key not in detail
    assert "supersecretvalue" not in detail


def test_hermes_audit_metadata_does_not_store_user_prompt_text(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    seen = []
    secret_text = "Private Hermes note token=supersecretvalue"
    monkeypatch.setattr(router_hermes, "audit_log", lambda *args, **kwargs: seen.append(args))
    monkeypatch.setattr(router_hermes, "build_obsidian_context_payload", lambda **kwargs: {
        "ok": True,
        "vault": {"loadedAll": False},
        "files": [],
    })
    monkeypatch.setattr(router_hermes, "format_obsidian_context_for_prompt", lambda payload: "prompt")

    context = client.post("/hermes/context", json={"topic": secret_text})

    async def fake_create(req):
        return {"success": True, "status": "draft", "safeMode": True}

    monkeypatch.setattr(router_hermes, "create_hermes_os_draft", fake_create)
    draft = client.post("/hermes/draft", json={"title": secret_text, "body": secret_text})
    monkeypatch.setattr(router_hermes, "improve_lexa_with_hermes", lambda focus, timeout: {
        "success": False,
        "status": "unavailable",
    })
    improve = client.post("/hermes/improve-lexa", json={"focus": secret_text, "timeoutSeconds": 20})

    assert context.status_code == 200
    assert draft.status_code == 200
    assert improve.status_code == 200
    audit_text = str(seen)
    assert "Private Hermes note" not in audit_text
    assert "supersecretvalue" not in audit_text
    assert "topicChars=" in audit_text
    assert "bodyChars=" in audit_text
    assert "focusChars=" in audit_text


def test_hermes_improve_endpoint(monkeypatch):
    client, router_hermes = _client(monkeypatch)
    monkeypatch.setattr(router_hermes, "improve_lexa_with_hermes", lambda focus, timeout: {
        "success": False,
        "status": "unavailable",
        "focus": focus,
        "timeout": timeout,
    })

    res = client.post("/hermes/improve-lexa", json={"focus": "backend", "timeoutSeconds": 20})

    assert res.status_code == 200
    assert res.json()["status"] == "unavailable"
    assert res.json()["focus"] == "backend"
