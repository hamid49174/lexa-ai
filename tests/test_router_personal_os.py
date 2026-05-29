"""Tests for the narrow Personal OS integration router."""

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch):
    import backend.router_personal_os as router_personal_os

    monkeypatch.setattr(router_personal_os, "check_rate_limit", lambda *a, **kw: True)
    monkeypatch.setattr(router_personal_os, "audit_log", lambda *a, **kw: None)

    app = FastAPI()
    app.include_router(router_personal_os.router)
    return TestClient(app, raise_server_exceptions=False)


def test_raw_inbox_extract_returns_summary_and_tags(monkeypatch):
    from backend import ai_engine

    monkeypatch.setattr(ai_engine, "_get_selected_model_meta", lambda: {
        "provider": "groq",
        "model": "mock-model",
    })
    monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", lambda messages, selected_model, tools=None: {
        "type": "text",
        "content": '{"summary":"Short raw inbox summary.","tags":["Lexa","raw inbox","unsafe tag!!"]}',
    })
    monkeypatch.setattr(ai_engine, "_save_interaction", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not save chat history")))

    res = _client(monkeypatch).post("/personal-os/raw-inbox/extract", json={
        "sourcePath": "06_Inbox/Raw/example.txt",
        "body": "Raw inbox text",
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["summary"] == "Short raw inbox summary."
    assert data["tags"] == ["lexa", "raw-inbox", "unsafe-tag"]
    assert data["provider"] == "groq"
    assert data["model"] == "mock-model"


def test_raw_inbox_submit_writes_raw_and_runs_worker(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_write(req):
        calls.append(("write", req.title, req.body, req.processor))
        return {
            "path": "06_Inbox/Raw/2026-05-15_test-note.txt",
            "filename": "2026-05-15_test-note.txt",
            "title": req.title,
            "size": len(req.body),
        }

    async def fake_worker(filename, processor):
        calls.append(("worker", filename, processor))
        return {
            "ok": True,
            "processed": 1,
            "drafts": ["06_Inbox/Drafts/test-note_update.md"],
            "failures": [],
        }

    monkeypatch.setattr(router_personal_os, "_write_raw_inbox_file", fake_write)
    monkeypatch.setattr(router_personal_os, "_run_raw_inbox_worker", fake_worker)

    res = _client(monkeypatch).post("/personal-os/raw-inbox/submit", json={
        "title": "Test Note",
        "body": "Raw text for intake",
        "processor": "deterministic",
    })

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["raw"]["path"] == "06_Inbox/Raw/2026-05-15_test-note.txt"
    assert data["drafts"] == ["06_Inbox/Drafts/test-note_update.md"]
    assert calls == [
        ("write", "Test Note", "Raw text for intake", "deterministic"),
        ("worker", "2026-05-15_test-note.txt", "deterministic"),
    ]


def test_raw_inbox_status_returns_worker_processors(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_status():
        return {
            "ok": True,
            "processors": [
                {"name": "deterministic", "status": "available"},
                {"name": "lexa", "status": "disabled", "reason": "set RAW_INBOX_LEXA_ENABLED=1"},
            ],
            "failureState": {"failed": 0, "failures": []},
        }

    monkeypatch.setattr(router_personal_os, "_run_raw_inbox_worker_status", fake_status)

    res = _client(monkeypatch).get("/personal-os/raw-inbox/status")

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["processors"][0]["name"] == "deterministic"
    assert data["processors"][1]["status"] == "disabled"


def test_obsidian_context_endpoint_returns_bounded_payload(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    def fake_context(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "vault": {"loadedAll": False},
            "files": [{"path": "OS_MANIFEST.md"}],
        }

    monkeypatch.setattr(router_personal_os, "build_obsidian_context_payload", fake_context)

    res = _client(monkeypatch).get("/personal-os/obsidian-context?topic=lexa%20hermes&maxFiles=3&bodyChars=400")

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["vault"]["loadedAll"] is False
    assert calls == [{
        "topic": "lexa hermes",
        "max_files": 3,
        "body_chars": 400,
        "include_previews": True,
    }]


def test_obsidian_context_endpoint_uses_shared_chat_topic_when_topic_empty(monkeypatch):
    import backend.router_personal_os as router_personal_os
    from backend.context_bus import clear_shared_context, publish_chat_context

    clear_shared_context()
    publish_chat_context("Projekt Alpha Roadmap Recherche", source="unit")
    calls = []

    def fake_context(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "files": []}

    monkeypatch.setattr(router_personal_os, "build_obsidian_context_payload", fake_context)

    res = _client(monkeypatch).get("/personal-os/obsidian-context?maxFiles=2&bodyChars=300")

    clear_shared_context()
    assert res.status_code == 200
    assert calls[0]["topic"] == "Projekt Alpha Roadmap Recherche"
    assert calls[0]["max_files"] == 2


def test_personal_os_shared_context_endpoint_returns_latest_snapshot(monkeypatch):
    from backend.context_bus import clear_shared_context, publish_chat_context

    clear_shared_context()
    publish_chat_context("Projekt Gamma Kontext", source="unit")

    res = _client(monkeypatch).get("/personal-os/shared-context")

    clear_shared_context()
    assert res.status_code == 200
    data = res.json()
    assert data["fresh"] is True
    assert data["topic"] == "Projekt Gamma Kontext"


def test_personal_os_status_reports_review_tools(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_query_index"},
        ]

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)

    res = _client(monkeypatch).get("/personal-os/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "connected"
    assert data["draft_review"] is True
    assert data["tools_count"] == 3
    assert data["capabilities"]["draftQueue"] is True
    assert data["capabilities"]["reviewPacket"] is False
    assert data["capabilities"]["graph"] is False
    assert data["missing_tools"]["reviewPacket"] == ["os_draft_history", "os_read_file"]


def test_personal_os_status_reloads_mcp_config_when_registry_cache_is_stale(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = {"connect": 0, "load_config": 0}

    class FakeRegistry:
        def get_client(self, name):
            return None

        async def connect(self, name):
            calls["connect"] += 1
            if calls["connect"] == 1:
                raise router_personal_os.MCPError("Unknown MCP server: 'personal_os'")
            return {"name": "personal-os"}

        def load_config(self):
            calls["load_config"] += 1
            return {"personal_os": {"command": "node"}}

        def get_server_tools(self, name):
            return [
                {"name": "os_list_drafts"},
                {"name": "os_view_draft"},
                {"name": "os_read_file"},
                {"name": "os_draft_history"},
                {"name": "os_query_index"},
                {"name": "os_graph_index"},
            ]

    monkeypatch.setattr(router_personal_os, "mcp_registry", FakeRegistry())

    res = _client(monkeypatch).get("/personal-os/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "connected"
    assert data["capabilities"]["reviewPacket"] is True
    assert calls == {"connect": 2, "load_config": 1}


def test_personal_os_tool_call_reconnects_once_when_mcp_connection_is_stale(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = {"ensure": 0, "call": 0, "disconnect": 0, "connect": 0}

    async def fake_ensure():
        calls["ensure"] += 1
        return [{"name": "os_list_drafts"}]

    class FakeRegistry:
        async def call_tool(self, server, tool, arguments):
            calls["call"] += 1
            assert server == "personal_os"
            assert tool == "os_list_drafts"
            assert arguments == {"hideSmoke": True}
            if calls["call"] == 1:
                raise router_personal_os.MCPError("MCP server 'personal_os' is not connected")
            return [{"type": "text", "text": '{"ok":true,"value":42}'}]

        async def disconnect(self, name):
            calls["disconnect"] += 1
            assert name == "personal_os"

        async def connect(self, name):
            calls["connect"] += 1
            assert name == "personal_os"

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_ensure)
    monkeypatch.setattr(router_personal_os, "mcp_registry", FakeRegistry())

    data = asyncio.run(router_personal_os._call_personal_os_tool("os_list_drafts", {"hideSmoke": True}))

    assert data == {"ok": True, "value": 42}
    assert calls == {"ensure": 1, "call": 2, "disconnect": 1, "connect": 1}


def test_personal_os_tool_call_does_not_retry_non_connection_mcp_errors(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = {"ensure": 0, "call": 0, "disconnect": 0, "connect": 0}

    async def fake_ensure():
        calls["ensure"] += 1
        return [{"name": "os_list_drafts"}]

    class FakeRegistry:
        async def call_tool(self, server, tool, arguments):
            calls["call"] += 1
            raise router_personal_os.MCPError("Unknown tool: os_missing_tool")

        async def disconnect(self, name):
            calls["disconnect"] += 1

        async def connect(self, name):
            calls["connect"] += 1

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_ensure)
    monkeypatch.setattr(router_personal_os, "mcp_registry", FakeRegistry())

    try:
        asyncio.run(router_personal_os._call_personal_os_tool("os_missing_tool", {}))
    except router_personal_os.HTTPException as exc:
        assert exc.status_code == 502
        assert "Unknown tool" in exc.detail
    else:
        raise AssertionError("expected HTTPException")

    assert calls == {"ensure": 1, "call": 1, "disconnect": 0, "connect": 0}


def test_personal_os_diagnostics_reports_ready_state(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_read_file"},
            {"name": "os_draft_history"},
            {"name": "os_query_index"},
            {"name": "os_graph_index"},
        ]

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "counts": {"total": 5, "pending": 0, "approved": 2, "rejected": 3, "invalid": 0},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "ok",
        "detail": "10.0 GiB free on the Lexa drive.",
    })

    res = _client(monkeypatch).get("/personal-os/diagnostics")

    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "ready"
    assert data["counts"]["pending"] == 0
    assert data["counts"]["approved"] == 2
    assert data["status"]["capabilities"]["graph"] is True
    assert any(check["id"] == "system-storage" and check["state"] == "ok" for check in data["checks"])
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 200,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS diagnostics queue read",
        })
    ]


def test_personal_os_diagnostics_warns_when_pending_drafts_exist(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_read_file"},
            {"name": "os_draft_history"},
            {"name": "os_query_index"},
            {"name": "os_graph_index"},
        ]

    async def fake_call(tool, arguments):
        return {
            "ok": True,
            "counts": {"total": 2, "pending": 2, "approved": 0, "rejected": 0, "invalid": 0},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "ok",
        "detail": "10.0 GiB free on the Lexa drive.",
    })

    res = _client(monkeypatch).get("/personal-os/diagnostics")

    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "attention"
    assert data["ok"] is True
    assert any(check["id"] == "pending-drafts" and check["state"] == "warn" for check in data["checks"])


def test_storage_check_thresholds(monkeypatch):
    import backend.router_personal_os as router_personal_os

    gib = 1024 * 1024 * 1024
    mib = 1024 * 1024

    def set_free_bytes(free):
        monkeypatch.setattr(router_personal_os.shutil, "disk_usage", lambda path: SimpleNamespace(
            total=10 * gib,
            used=(10 * gib) - free,
            free=free,
        ))

    set_free_bytes(2 * gib)
    ok = router_personal_os._build_storage_check()
    assert ok["state"] == "ok"
    assert ok["detail"].startswith("2.0 GiB free")

    set_free_bytes(512 * mib)
    warn = router_personal_os._build_storage_check()
    assert warn["state"] == "warn"
    assert "Low disk space: 512 MiB free" in warn["detail"]

    set_free_bytes(50 * mib)
    block = router_personal_os._build_storage_check()
    assert block["state"] == "block"
    assert "Only 50 MiB free" in block["detail"]


def test_storage_check_probe_failure_is_warning(monkeypatch):
    import backend.router_personal_os as router_personal_os

    def fail_disk_usage(path):
        raise OSError("disk probe failed")

    monkeypatch.setattr(router_personal_os.shutil, "disk_usage", fail_disk_usage)

    check = router_personal_os._build_storage_check()

    assert check["id"] == "system-storage"
    assert check["state"] == "warn"
    assert "Disk space check unavailable" in check["detail"]


def test_personal_os_diagnostics_warns_on_low_disk_space(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_read_file"},
            {"name": "os_draft_history"},
            {"name": "os_query_index"},
            {"name": "os_graph_index"},
        ]

    async def fake_call(tool, arguments):
        return {
            "ok": True,
            "counts": {"total": 2, "pending": 0, "approved": 1, "rejected": 1, "invalid": 0},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "warn",
        "detail": "Low disk space: 220 MiB free on the Lexa drive.",
    })

    res = _client(monkeypatch).get("/personal-os/diagnostics")

    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "attention"
    assert data["ok"] is True
    assert data["nextAction"] == "Free disk space or avoid write-heavy commands before continuing heavy work."
    assert any(check["id"] == "system-storage" and check["state"] == "warn" for check in data["checks"])


def test_personal_os_diagnostics_blocks_on_critical_disk_space(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_read_file"},
            {"name": "os_draft_history"},
            {"name": "os_query_index"},
            {"name": "os_graph_index"},
        ]

    async def fake_call(tool, arguments):
        return {
            "ok": True,
            "counts": {"total": 2, "pending": 0, "approved": 1, "rejected": 1, "invalid": 0},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "block",
        "detail": "Only 50 MiB free on the Lexa drive.",
    })

    res = _client(monkeypatch).get("/personal-os/diagnostics")

    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "blocked"
    assert data["ok"] is False
    assert data["nextAction"] == "Free disk space before write-heavy Lexa or Personal OS work."
    assert any(check["id"] == "system-storage" and check["state"] == "block" for check in data["checks"])


def test_list_drafts_calls_read_only_mcp_tool(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "counts": {"pending": 1},
            "drafts": [{"path": "06_Inbox/Drafts/example.md", "approval": "pending"}],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/drafts?approval=pending&hideSmoke=true")

    assert res.status_code == 200
    assert res.json()["drafts"][0]["approval"] == "pending"
    assert calls == [
        ("os_list_drafts", {
            "approvals": ["pending"],
            "hideSmoke": True,
            "maxDrafts": 50,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS draft queue read",
        })
    ]


def test_list_drafts_omits_approvals_for_all_filter(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "counts": {"total": 5, "pending": 0, "approved": 2, "rejected": 3},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/drafts?approval=all&hideSmoke=true")

    assert res.status_code == 200
    assert res.json()["counts"]["approved"] == 2
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 50,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS draft queue read",
        })
    ]


def test_view_draft_rejects_path_traversal(monkeypatch):
    res = _client(monkeypatch).get(
        "/personal-os/drafts/view",
        params={"draftPath": "06_Inbox/Drafts/../Core.md"},
    )

    assert res.status_code == 400
    assert "traversal" in res.json()["detail"]


def test_view_draft_validation_error_names_missing_draft_path(monkeypatch):
    res = _client(monkeypatch).get("/personal-os/drafts/view")

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail[0]["loc"] == ["query", "draftPath"]
    assert "required" in detail[0]["msg"].lower()


def test_query_os_index_calls_mcp_tool(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "path": "00_System/INDEX.md",
            "frontmatter": {"title": "System Index"},
            "body": "# System Index",
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/query", params={"areaPath": "00_System"})

    assert res.status_code == 200
    assert res.json()["path"] == "00_System/INDEX.md"
    assert calls == [
        ("os_query_index", {
            "areaPath": "00_System",
            "maxMatches": 50,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS context query",
        })
    ]


def test_query_os_tag_calls_mcp_tool(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "query": {"tag": "lexa"},
            "matches": [{"path": "08_Lexa/INDEX.md", "title": "Lexa"}],
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/query", params={"areaPath": ".", "tag": "#Lexa", "maxMatches": 5})

    assert res.status_code == 200
    assert res.json()["matches"][0]["path"] == "08_Lexa/INDEX.md"
    assert calls == [
        ("os_query_index", {
            "areaPath": ".",
            "maxMatches": 5,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS context query",
            "tag": "lexa",
        })
    ]


def test_query_os_rejects_empty_normalized_tag(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_call(tool, arguments):
        raise AssertionError("MCP should not be called for invalid tags")

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/query", params={"areaPath": ".", "tag": "#!!!"})

    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid tag filter"


def test_query_os_validation_error_names_invalid_max_matches(monkeypatch):
    res = _client(monkeypatch).get(
        "/personal-os/query",
        params={"areaPath": "00_System", "maxMatches": "abc"},
    )

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail[0]["loc"] == ["query", "maxMatches"]
    assert "integer" in detail[0]["msg"].lower()


def test_context_pack_reads_query_matches_files_and_graph(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        if tool == "os_query_index":
            return {
                "ok": True,
                "query": {"tag": "lexa"},
                "matches": [
                    {"path": "00_System/INDEX.md", "title": "System Index"},
                    {"path": "06_Inbox/Drafts/smoke_test_update.md", "title": "Smoke Test Draft"},
                    {"path": "OS_MANIFEST.md", "title": "Manifest"},
                ],
            }
        if tool == "os_read_file":
            return {
                "ok": True,
                "path": arguments["filepath"],
                "frontmatter": {
                    "title": arguments["filepath"],
                    "type": "index",
                    "memory_level": "core",
                    "tags": ["lexa"],
                    "related": [],
                },
                "body": "Context body " * 80,
            }
        if tool == "os_graph_index":
            return {
                "ok": False,
                "areaPath": arguments["areaPath"],
                "counts": {"files": 2, "nodes": 4, "edges": 3, "errors": 1},
                "nodes": [{"kind": "file", "path": "OS_MANIFEST.md", "label": "Manifest"}],
                "edges": [],
                "errors": [{"path": "00_System/Broken.md", "error": "Missing frontmatter fields\nextra detail"}],
            }
        raise AssertionError(tool)

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/context-pack",
        params={"areaPath": "00_System", "tag": "tag:Lexa", "maxFiles": 2, "bodyChars": 200},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["query"]["candidateCount"] == 2
    assert data["query"]["includedCount"] == 2
    assert len(data["files"]) == 2
    assert data["files"][0]["truncated"] is True
    assert data["graph"]["ok"] is False
    assert data["graph"]["counts"]["edges"] == 3
    assert data["graph"]["errors"][0]["path"] == "00_System/Broken.md"
    assert data["graph"]["errors"][0]["error"].startswith("Missing frontmatter fields")
    assert calls[0] == ("os_query_index", {
        "areaPath": "00_System",
        "maxMatches": 12,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS context pack query",
        "tag": "lexa",
    })
    assert calls[1][0] == "os_read_file"
    assert calls[2][0] == "os_read_file"
    assert calls[3] == ("os_graph_index", {
        "areaPath": "00_System",
        "maxFiles": 40,
        "includeTags": True,
        "hideSmoke": True,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS context pack context map summary",
    })


def test_lexa_code_loop_builds_read_only_prompt(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_connect():
        return [
            {"name": "os_list_drafts"},
            {"name": "os_view_draft"},
            {"name": "os_read_file"},
            {"name": "os_draft_history"},
            {"name": "os_query_index"},
            {"name": "os_graph_index"},
        ]

    async def fake_status():
        return {
            "ok": True,
            "processors": [{"name": "deterministic", "status": "available"}],
            "failureState": {"failed": 0, "failures": []},
        }

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        if tool == "os_list_drafts":
            return {
                "ok": True,
                "counts": {"total": 2, "pending": 0, "approved": 1, "rejected": 1, "invalid": 0},
                "drafts": [
                    {"title": "Lexa Personal OS Cockpit Integration", "path": "06_Inbox/Drafts/cockpit.md", "approval": "approved", "tags": ["lexa"]},
                    {"title": "Lexa Follow-up Review", "path": "06_Inbox/Drafts/follow-up.md", "approval": "pending", "tags": ["lexa", "personal-os"]},
                    {"title": "Unrelated", "path": "06_Inbox/Drafts/other.md", "approval": "rejected", "tags": ["other"]},
                ],
            }
        if tool == "os_query_index":
            return {
                "ok": True,
                "matches": [
                    {"title": "Current AI Brief", "path": "05_Memory/Rollups/Current_AI_Brief.md", "memory_level": "working", "tags": ["lexa"]},
                ],
            }
        if tool == "os_read_file":
            return {
                "ok": True,
                "path": arguments["filepath"],
                "frontmatter": {"title": "Current AI Brief", "type": "memory-summary", "memory_level": "working", "tags": ["lexa"]},
                "body": "Lexa cockpit should keep OS writes gated.",
            }
        if tool == "os_graph_index":
            return {
                "ok": False,
                "areaPath": arguments["areaPath"],
                "counts": {"files": 1, "nodes": 2, "edges": 1, "errors": 1},
                "nodes": [],
                "edges": [],
                "errors": [{"path": "00_System/Broken.md", "error": "Missing metadata"}],
            }
        raise AssertionError(tool)

    monkeypatch.setattr(router_personal_os, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(router_personal_os, "_run_raw_inbox_worker_status", fake_status)
    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "ok",
        "detail": "10.0 GiB free on the Lexa drive.",
    })

    res = _client(monkeypatch).get(
        "/personal-os/lexa-code-loop",
        params={"areaPath": "00_System", "tag": "#Lexa", "maxFiles": 1, "bodyChars": 300},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["topic"] == "lexa-code-improvement"
    assert data["diagnostics"]["state"] == "ready"
    assert data["drafts"]["items"][0]["title"] == "Lexa Follow-up Review"
    assert data["drafts"]["items"][1]["title"] == "Lexa Personal OS Cockpit Integration"
    assert len(data["drafts"]["items"]) == 2
    assert "naechsten kleinen Lexa-Code" in data["prompt"]
    assert "Inspiziere das Lexa-Repo lokal" in data["prompt"]
    assert "bestehenden OS-Draft" in data["prompt"]
    assert "Keine billigen Demo-Funktionen" in data["prompt"]
    assert "Stoppe nur, wenn eine menschliche Entscheidung wirklich noetig ist" in data["prompt"]
    assert data["prompt"].index("Lexa Follow-up Review [pending]") < data["prompt"].index("Lexa Personal OS Cockpit Integration [approved]")
    assert "Lexa cockpit should keep OS writes gated" in data["prompt"]
    assert "Context Map Health" in data["prompt"]
    assert "Graph Health" not in data["prompt"]
    assert "00_System/Broken.md" in data["prompt"]
    assert data["contextPack"]["graph"]["errors"][0]["path"] == "00_System/Broken.md"
    assert calls[0] == ("os_list_drafts", {
        "hideSmoke": True,
        "maxDrafts": 200,
        "agentName": "LexaPersonalOS",
        "reason": "Lexa Personal OS code loop draft queue read",
    })
    assert calls[1][0] == "os_query_index"
    assert calls[2][0] == "os_read_file"
    assert calls[3][0] == "os_graph_index"


def test_read_os_file_calls_mcp_tool(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "path": "OS_MANIFEST.md",
            "frontmatter": {"title": "OS Manifest"},
            "body": "# OS Manifest",
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get("/personal-os/files/read", params={"filepath": "OS_MANIFEST.md"})

    assert res.status_code == 200
    assert res.json()["body"] == "# OS Manifest"
    assert calls == [
        ("os_read_file", {
            "filepath": "OS_MANIFEST.md",
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS file read",
        })
    ]


def test_read_os_file_rejects_non_markdown(monkeypatch):
    res = _client(monkeypatch).get("/personal-os/files/read", params={"filepath": "06_Inbox/Raw/example.txt"})

    assert res.status_code == 400
    assert "Markdown" in res.json()["detail"]


def test_review_draft_reads_related_context(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        if tool == "os_view_draft":
            return {
                "ok": True,
                "path": "06_Inbox/Drafts/example.md",
                "approval": "pending",
                "frontmatter": {
                    "title": "Review Me",
                    "confidence": "high",
                    "related": ["OS_MANIFEST.md", "../Secret.md", "06_Inbox/Raw/example.txt"],
                },
                "body": "## Approval\n\n- [ ] Approved\n- [ ] Rejected\n",
            }
        if tool == "os_draft_history":
            return {
                "ok": True,
                "draftPath": arguments["draftPath"],
                "events": [{"type": "File.DraftCreated", "agent": "Test", "timestamp": "2026-05-15T00:00:00Z"}],
                "counts": {"File.DraftCreated": 1},
                "total": 1,
            }
        return {
            "ok": True,
            "path": arguments["filepath"],
            "frontmatter": {"title": "Manifest", "type": "manifest", "memory_level": "core"},
            "body": "# Manifest\nBody",
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/drafts/review",
        params={"draftPath": "06_Inbox/Drafts/example.md"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["checklist"]["hasApproved"] is True
    assert data["checklist"]["hasRejected"] is True
    assert data["reviewHints"]["relatedCount"] == 1
    assert data["reviewHints"]["historyCount"] == 1
    assert data["reviewHints"]["assistStatus"] == "ready"
    assert data["reviewHints"]["canApply"] is False
    assert data["assist"]["status"] == "ready"
    assert data["applyHint"]["enabled"] is False
    assert data["history"]["events"][0]["type"] == "File.DraftCreated"
    assert data["related"][0]["path"] == "OS_MANIFEST.md"
    assert calls[0][0] == "os_view_draft"
    assert calls[1] == (
        "os_read_file",
        {
            "filepath": "OS_MANIFEST.md",
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS draft related context read",
        },
    )


def test_review_draft_infers_sdk_target_and_returns_diff(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_call(tool, arguments):
        if tool == "os_view_draft":
            return {
                "ok": True,
                "path": arguments["draftPath"],
                "approval": "pending",
                "frontmatter": {"title": "System Index Update", "confidence": "high", "related": []},
                "body": "# Draft Body\n",
            }
        if tool == "os_draft_history":
            return {"ok": True, "draftPath": arguments["draftPath"], "events": [], "counts": {}, "total": 0}
        return {
            "ok": True,
            "path": arguments["filepath"],
            "frontmatter": {"title": "System Index", "type": "index", "memory_level": "core"},
            "body": "# Current Body\n",
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/drafts/review",
        params={"draftPath": "06_Inbox/Drafts/2026-05-15T15-57-02-821Z_00_System__INDEX_update.md"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["targetCandidate"] == "00_System/INDEX.md"
    assert data["target"]["path"] == "00_System/INDEX.md"
    assert data["diff"]["changed"] is True
    assert data["assist"]["status"] == "blocked"
    assert any(
        check["label"] == "Approval checklist" and check["state"] == "block"
        for check in data["assist"]["checks"]
    )
    assert any("-# Current Body" in line for line in data["diff"]["lines"])
    assert any("+# Draft Body" in line for line in data["diff"]["lines"])


def test_review_draft_infers_frontmatter_target_without_body_diff(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        if tool == "os_view_draft":
            return {
                "ok": True,
                "path": arguments["draftPath"],
                "approval": "pending",
                "frontmatter": {
                    "title": "OS SDK README Frontmatter Fix",
                    "confidence": "high",
                    "related": [],
                    "target_file": "00_System/SDK/os-sdk/README.md",
                },
                "body": "\n".join([
                    "# Context Update Draft",
                    "",
                    "## Approval",
                    "",
                    "- [ ] Approved",
                    "- [ ] Rejected",
                    "",
                ]),
            }
        if tool == "os_draft_history":
            return {"ok": True, "draftPath": arguments["draftPath"], "events": [], "counts": {}, "total": 0}
        if tool == "os_read_file":
            return {
                "ok": True,
                "path": arguments["filepath"],
                "frontmatter": {"title": "OS SDK README", "type": "resource", "memory_level": "core"},
                "body": "# OS SDK\n",
            }
        raise AssertionError(f"unexpected tool: {tool}")

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/drafts/review",
        params={"draftPath": "06_Inbox/Drafts/2026-05-16_os_sdk_readme_frontmatter_fix_draft.md"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["targetCandidate"] == "00_System/SDK/os-sdk/README.md"
    assert data["targetSource"] == "frontmatter"
    assert data["target"]["path"] == "00_System/SDK/os-sdk/README.md"
    assert data["diff"] is None
    assert data["reviewHints"]["hasTargetComparison"] is False
    assert any(
        check["label"] == "Target comparison"
        and check["state"] == "ok"
        and "draft metadata" in check["detail"]
        for check in data["assist"]["checks"]
    )
    assert any(call == (
        "os_read_file",
        {
            "filepath": "00_System/SDK/os-sdk/README.md",
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS draft target comparison read",
        },
    ) for call in calls)


def test_review_draft_reports_apply_hint_for_supported_approved_import(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_call(tool, arguments):
        if tool == "os_view_draft":
            return {
                "ok": True,
                "path": arguments["draftPath"],
                "approval": "approved",
                "frontmatter": {
                    "title": "Raw Inbox Processing: Example",
                    "confidence": "high",
                    "source": "import",
                    "memory_level": "session",
                    "related": [],
                },
                "body": "\n".join([
                    "## Candidate Destination",
                    "",
                    "`05_Memory/Session/example.md`",
                    "",
                    "## Approval",
                    "",
                    "- [x] Approved",
                    "- [ ] Rejected",
                    "",
                ]),
            }
        if tool == "os_draft_history":
            return {
                "ok": True,
                "draftPath": arguments["draftPath"],
                "events": [{"type": "Draft.Approved", "agent": "Test", "timestamp": "2026-05-15T00:00:00Z"}],
                "counts": {"Draft.Approved": 1},
                "total": 1,
            }
        raise AssertionError(f"unexpected tool: {tool}")

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/drafts/review",
        params={"draftPath": "06_Inbox/Drafts/raw-inbox-example.md"},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["applyHint"]["enabled"] is True
    assert data["applyHint"]["target"] == "05_Memory/Session/example.md"
    assert data["reviewHints"]["canApply"] is True
    assert data["assist"]["status"] == "attention"


def test_graph_os_calls_mcp_tool(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "areaPath": "00_System",
            "nodes": [{"id": "00_System/INDEX.md", "kind": "file"}],
            "edges": [],
            "counts": {"files": 1, "tags": 0, "references": 0, "edges": 0},
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)

    res = _client(monkeypatch).get(
        "/personal-os/graph",
        params={"areaPath": "00_System", "maxFiles": 25, "includeTags": "true", "hideSmoke": "true"},
    )

    assert res.status_code == 200
    assert res.json()["nodes"][0]["id"] == "00_System/INDEX.md"
    assert calls == [
        ("os_graph_index", {
            "areaPath": "00_System",
            "maxFiles": 25,
            "includeTags": True,
            "hideSmoke": True,
            "agentName": "LexaPersonalOS",
            "reason": "Lexa Personal OS graph read",
        })
    ]


def test_graph_os_rejects_path_traversal(monkeypatch):
    res = _client(monkeypatch).get("/personal-os/graph", params={"areaPath": "../OS"})

    assert res.status_code == 400
    assert "traversal" in res.json()["detail"]


def test_draft_decision_uses_sdk_cli_boundary(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_guard(req, draft_path):
        return {"blocked": False, "checks": [], "summary": "ok"}

    async def fake_decision(req):
        calls.append(req)
        return {
            "ok": True,
            "decision": req.decision,
            "file": req.draftPath,
        }

    monkeypatch.setattr(router_personal_os, "_ensure_approval_guard", fake_guard)
    monkeypatch.setattr(router_personal_os, "_run_draft_decision_cli", fake_decision)

    res = _client(monkeypatch).post("/personal-os/drafts/decision", json={
        "draftPath": "06_Inbox/Drafts/example.md",
        "decision": "approve",
        "reason": "Reviewed in UI",
        "agentName": "LexaHumanReview",
    })

    assert res.status_code == 200
    assert res.json()["decision"] == "approve"
    assert calls[0].draftPath == "06_Inbox/Drafts/example.md"


def test_draft_approval_blocks_bad_review_without_force(monkeypatch):
    import backend.router_personal_os as router_personal_os

    async def fake_call(tool, arguments):
        assert tool == "os_view_draft"
        return {
            "ok": True,
            "path": arguments["draftPath"],
            "approval": "pending",
            "frontmatter": {"title": "Broken Draft"},
            "body": "No approval checklist here.",
        }

    async def fake_decision(req):
        raise AssertionError("blocked approval must not reach SDK CLI")

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_run_draft_decision_cli", fake_decision)

    res = _client(monkeypatch).post("/personal-os/drafts/decision", json={
        "draftPath": "06_Inbox/Drafts/example.md",
        "decision": "approve",
        "reason": "Approve anyway",
        "agentName": "LexaHumanReview",
    })

    assert res.status_code == 409
    data = res.json()
    assert "Approval blocked" in data["detail"]["message"]
    assert data["detail"]["guard"]["blocked"] is True


def test_draft_approval_force_bypasses_block_guard(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_call(tool, arguments):
        raise AssertionError("forced approval should not call review guard MCP read")

    async def fake_decision(req):
        calls.append(req)
        return {
            "ok": True,
            "decision": req.decision,
            "force": req.force,
        }

    monkeypatch.setattr(router_personal_os, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_run_draft_decision_cli", fake_decision)

    res = _client(monkeypatch).post("/personal-os/drafts/decision", json={
        "draftPath": "06_Inbox/Drafts/example.md",
        "decision": "approve",
        "reason": "Explicit override after human review",
        "agentName": "LexaHumanReview",
        "force": True,
    })

    assert res.status_code == 200
    assert res.json()["force"] is True
    assert calls[0].force is True


def test_draft_apply_uses_sdk_cli_boundary(monkeypatch):
    import backend.router_personal_os as router_personal_os

    calls = []

    async def fake_apply(req):
        calls.append(req)
        return {
            "ok": True,
            "draft": req.draftPath,
            "target": "05_Memory/Session/example.md",
        }

    monkeypatch.setattr(router_personal_os, "_run_draft_apply_cli", fake_apply)

    res = _client(monkeypatch).post("/personal-os/drafts/apply", json={
        "draftPath": "06_Inbox/Drafts/example.md",
        "reason": "Apply after human review",
        "agentName": "LexaHumanReview",
    })

    assert res.status_code == 200
    assert res.json()["target"] == "05_Memory/Session/example.md"
    assert calls[0].draftPath == "06_Inbox/Drafts/example.md"


def test_draft_apply_rejects_path_traversal(monkeypatch):
    res = _client(monkeypatch).post("/personal-os/drafts/apply", json={
        "draftPath": "06_Inbox/Drafts/../Core.md",
        "reason": "Apply",
        "agentName": "LexaHumanReview",
    })

    assert res.status_code == 400
    assert "traversal" in res.json()["detail"]


def test_raw_inbox_extract_rejects_invalid_model_json(monkeypatch):
    from backend import ai_engine

    monkeypatch.setattr(ai_engine, "_get_selected_model_meta", lambda: {
        "provider": "groq",
        "model": "mock-model",
    })
    monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", lambda messages, selected_model, tools=None: {
        "type": "text",
        "content": "not-json",
    })

    res = _client(monkeypatch).post("/personal-os/raw-inbox/extract", json={
        "sourcePath": "06_Inbox/Raw/example.txt",
        "body": "Raw inbox text",
    })

    assert res.status_code == 502
    assert "valid JSON" in res.json()["detail"]


def test_raw_inbox_extract_rejects_empty_body(monkeypatch):
    res = _client(monkeypatch).post("/personal-os/raw-inbox/extract", json={
        "sourcePath": "06_Inbox/Raw/example.txt",
        "body": "",
    })

    assert res.status_code == 422
