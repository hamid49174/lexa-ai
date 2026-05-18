import asyncio


def _run(coro):
    return asyncio.run(coro)


def test_personal_os_diagnostics_action_is_read_only_and_formatted(monkeypatch):
    import backend.personal_os_actions as actions
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

    monkeypatch.setattr(actions, "_ensure_personal_os_connected", fake_connect)
    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(router_personal_os, "_build_storage_check", lambda: {
        "id": "system-storage",
        "label": "System storage",
        "state": "ok",
        "detail": "10.0 GiB free on the Lexa drive.",
    })

    result = _run(actions.execute_personal_os_action("personal_os_diagnostics", {}))

    assert result["success"] is True
    assert "Personal OS Diagnostics" in result["data"]
    assert "State: ready" in result["data"]
    assert "Pending: 0" in result["data"]
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 200,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS diagnostics read",
        })
    ]


def test_personal_os_raw_inbox_status_action_is_read_only_and_formatted(monkeypatch):
    import backend.personal_os_actions as actions

    async def fake_status():
        return {
            "ok": True,
            "processors": [
                {"name": "deterministic", "status": "available", "description": "Rule-based"},
                {"name": "lexa", "status": "disabled", "description": "Disabled until configured"},
            ],
            "failureState": {"failed": 0, "failures": []},
        }

    monkeypatch.setattr(actions, "_run_raw_inbox_worker_status", fake_status)

    result = _run(actions.execute_personal_os_action("personal_os_raw_inbox_status", {}))

    assert result["success"] is True
    assert "Personal OS Raw Inbox Worker" in result["data"]
    assert "deterministic: available" in result["data"]
    assert "lexa: disabled" in result["data"]
    assert "Failed files: 0" in result["data"]


def test_personal_os_query_action_normalizes_visible_tags(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "matches": [{"path": "01_User/Goals.md", "title": "Goals"}],
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_query", {
        "areaPath": ".",
        "tag": "#Personal OS",
        "maxMatches": 3,
    }))

    assert result["success"] is True
    assert "Personal OS Treffer" in result["data"]
    assert calls == [
        ("os_query_index", {
            "areaPath": ".",
            "maxMatches": 3,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS query",
            "tag": "personal-os",
        })
    ]


def test_personal_os_query_action_rejects_empty_normalized_tag(monkeypatch):
    import backend.personal_os_actions as actions

    async def fake_call(tool, arguments):
        raise AssertionError("MCP should not be called for invalid tags")

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_query", {
        "areaPath": ".",
        "tag": "#!!!",
    }))

    assert result["success"] is False
    assert result["error"] == "Invalid tag filter"


def test_personal_os_query_action_rejects_backend_incompatible_tag(monkeypatch):
    import backend.personal_os_actions as actions

    async def fake_call(tool, arguments):
        raise AssertionError("MCP should not be called for invalid tags")

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_query", {
        "areaPath": ".",
        "tag": "#___",
    }))

    assert result["success"] is False
    assert result["error"] == "Invalid tag filter"


def test_personal_os_graph_action_uses_context_map_language(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "areaPath": "00_System",
            "counts": {"files": 2, "nodes": 4, "edges": 3},
            "nodes": [
                {"id": "file:low", "kind": "file", "label": "Low File"},
                {"id": "file:high", "kind": "file", "label": "High File"},
                {"id": "tag:lexa", "kind": "tag", "label": "lexa"},
                {"id": "tag:sdk", "kind": "tag", "label": "sdk"},
            ],
            "edges": [
                {"source": "file:low", "target": "tag:lexa"},
                {"source": "file:high", "target": "tag:lexa"},
                {"source": "file:low", "target": "tag:sdk"},
            ],
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_graph", {
        "areaPath": "00_System",
        "maxFiles": 20,
        "includeTags": True,
    }))

    assert result["success"] is True
    assert "Personal OS Context Map" in result["data"]
    assert "Important files" in result["data"]
    assert "Hubs" in result["data"]
    assert "lexa (2 links)" in result["data"]
    assert result["data"].index("Low File") < result["data"].index("High File")
    assert result["data"].index("lexa (2 links)") < result["data"].index("sdk (1 links)")
    assert "Personal OS Graph" not in result["data"]
    assert calls == [
        ("os_graph_index", {
            "areaPath": "00_System",
            "maxFiles": 20,
            "includeTags": True,
            "hideSmoke": True,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS graph read",
        })
    ]


def test_personal_os_context_pack_action_is_bounded_and_formatted(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_context_pack(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "query": {
                "areaPath": "00_System",
                "tag": "lexa",
                "candidateCount": 2,
                "includedCount": 1,
            },
            "files": [
                {
                    "title": "Current AI Brief",
                    "path": "05_Memory/Rollups/Current_AI_Brief.md",
                    "memory_level": "working",
                    "tags": ["lexa", "personal-os"],
                    "bodyPreview": "Compact handoff context.",
                }
            ],
            "graph": {"counts": {"files": 2, "edges": 3}},
            "errors": [],
        }

    monkeypatch.setattr(actions, "_build_context_pack_payload", fake_context_pack)

    result = _run(actions.execute_personal_os_action("personal_os_context_pack", {
        "areaPath": "00_System",
        "tag": "#Lexa",
        "maxFiles": 4,
        "bodyChars": 500,
    }))

    assert result["success"] is True
    assert "Personal OS Context Pack" in result["data"]
    assert "Context Map: 2 files, 3 edges" in result["data"]
    assert "Current AI Brief" in result["data"]
    assert "Compact handoff context" in result["data"]
    assert calls == [{
        "area_path": "00_System",
        "tag": "lexa",
        "max_files": 4,
        "body_chars": 500,
        "include_graph": True,
        "hide_smoke": True,
        "agent_name": "LexaChat",
        "reason_prefix": "Lexa Chat Personal OS context pack",
    }]


def test_personal_os_lexa_code_loop_action_returns_read_only_prompt(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_code_loop(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "topic": "lexa-code-improvement",
            "prompt": "Du bist Lexa und nutzt das Personal OS als read-only Arbeitsgedaechtnis.\nAufgabe: naechsten kleinen Lexa-Code-Verbesserungsschritt ableiten.",
        }

    monkeypatch.setattr(actions, "_build_lexa_code_loop_payload", fake_code_loop)

    result = _run(actions.execute_personal_os_action("personal_os_lexa_code_loop", {
        "areaPath": "00_System",
        "tag": "tag:Lexa",
        "maxFiles": 4,
        "bodyChars": 600,
    }))

    assert result["success"] is True
    assert "read-only Arbeitsgedaechtnis" in result["data"]
    assert "Lexa-Code-Verbesserungsschritt" in result["data"]
    assert calls == [{
        "area_path": "00_System",
        "tag": "lexa",
        "max_files": 4,
        "body_chars": 600,
        "include_graph": True,
        "hide_smoke": True,
        "agent_name": "LexaChat",
        "reason_prefix": "Lexa Chat Personal OS code loop",
    }]


def test_personal_os_review_draft_action_is_read_only_and_formatted(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_review(draft_path, *, agent_name, reason_prefix):
        calls.append((draft_path, agent_name, reason_prefix))
        return {
            "ok": True,
            "draft": {
                "path": draft_path,
                "approval": "pending",
                "frontmatter": {"title": "Review Me", "confidence": "high"},
                "body": "- [ ] Approved\n- [ ] Rejected\n\nDraft body.",
            },
            "checklist": {"hasApproved": True, "hasRejected": True},
            "assist": {
                "status": "ready",
                "summary": "No deterministic blockers found.",
                "checks": [{"state": "ok", "label": "Draft state", "detail": "Pending."}],
            },
            "applyHint": {"enabled": False, "reason": "Draft must be approved before it can be applied."},
            "related": [{"title": "Related", "path": "OS_MANIFEST.md"}],
            "history": {"ok": True, "events": [{"type": "File.Read"}]},
            "targetCandidate": "00_System/SDK/os-sdk/README.md",
            "targetSource": "frontmatter",
            "target": {"path": "00_System/SDK/os-sdk/README.md", "error": "missing required field type " + ("details " * 80)},
            "diff": None,
        }

    monkeypatch.setattr(actions, "_build_draft_review_payload", fake_review)

    result = _run(actions.execute_personal_os_action("personal_os_review_draft", {
        "draftPath": "06_Inbox/Drafts/review-me.md",
    }))

    assert result["success"] is True
    assert "Personal OS Draft Review" in result["data"]
    assert "Review Me" in result["data"]
    assert "Assist: ready" in result["data"]
    assert "Target comparison: target unreadable" in result["data"]
    assert "[gekuerzt:" in result["data"]
    assert "Target: 00_System/SDK/os-sdk/README.md (source: frontmatter)" in result["data"]
    assert "Draft body" in result["data"]
    assert calls == [(
        "06_Inbox/Drafts/review-me.md",
        "LexaChat",
        "Lexa Chat Personal OS draft",
    )]


def test_personal_os_review_draft_resolves_unique_query(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "drafts": [
                {
                    "title": "AI Context Bootstrap Solution",
                    "path": "06_Inbox/Drafts/bootstrap.md",
                    "approval": "approved",
                },
                {
                    "title": "Lexa Personal OS Cockpit Integration",
                    "path": "06_Inbox/Drafts/cockpit.md",
                    "approval": "approved",
                },
            ],
        }

    async def fake_review(draft_path, *, agent_name, reason_prefix):
        calls.append(("review", draft_path, agent_name, reason_prefix))
        return {
            "ok": True,
            "draft": {
                "path": draft_path,
                "approval": "approved",
                "frontmatter": {"title": "AI Context Bootstrap Solution"},
                "body": "Resolved draft body.",
            },
            "checklist": {"hasApproved": True, "hasRejected": True},
            "assist": {"status": "attention", "summary": "Already approved.", "checks": []},
            "applyHint": {"enabled": False, "reason": "Not supported."},
            "related": [],
            "history": {"ok": True, "events": []},
            "diff": None,
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)
    monkeypatch.setattr(actions, "_build_draft_review_payload", fake_review)

    result = _run(actions.execute_personal_os_action("personal_os_review_draft", {
        "query": "bootstrap solution",
    }))

    assert result["success"] is True
    assert "AI Context Bootstrap Solution" in result["data"]
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 100,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS draft review path resolve",
        }),
        ("review", "06_Inbox/Drafts/bootstrap.md", "LexaChat", "Lexa Chat Personal OS draft"),
    ]


def test_personal_os_review_draft_rejects_ambiguous_query(monkeypatch):
    import backend.personal_os_actions as actions

    async def fake_call(tool, arguments):
        return {
            "ok": True,
            "drafts": [
                {"title": "Lexa One", "path": "06_Inbox/Drafts/lexa-one.md"},
                {"title": "Lexa Two", "path": "06_Inbox/Drafts/lexa-two.md"},
            ],
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_review_draft", {"query": "lexa"}))

    assert result["success"] is False
    assert "ambiguous" in result["error"]


def test_personal_os_list_drafts_query_filters_locally(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "drafts": [
                {
                    "title": "AI Context Bootstrap Solution",
                    "path": "06_Inbox/Drafts/bootstrap.md",
                    "approval": "approved",
                    "tags": ["agents", "context"],
                },
                {
                    "title": "Lexa Personal OS Cockpit Integration",
                    "path": "06_Inbox/Drafts/cockpit.md",
                    "approval": "approved",
                    "tags": ["lexa", "cockpit"],
                },
                {
                    "title": "OS SDK Phase 2 Direction",
                    "path": "06_Inbox/Drafts/sdk.md",
                    "approval": "rejected",
                    "tags": ["sdk"],
                },
            ],
            "counts": {"total": 3, "approved": 2, "rejected": 1},
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_list_drafts", {
        "approval": "all",
        "query": "lexa",
    }))

    assert result["success"] is True
    assert "Query: lexa, 1/3 Treffer" in result["data"]
    assert "Lexa Personal OS Cockpit Integration" in result["data"]
    assert "AI Context Bootstrap Solution" not in result["data"]
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 100,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS draft queue read",
        })
    ]


def test_personal_os_draft_history_resolves_unique_query(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        if tool == "os_list_drafts":
            return {
                "ok": True,
                "drafts": [
                    {
                        "title": "Lexa Personal OS Cockpit Integration",
                        "path": "06_Inbox/Drafts/cockpit.md",
                    },
                ],
            }
        if tool == "os_draft_history":
            return {
                "ok": True,
                "events": [
                    {"timestamp": "2026-05-15T00:00:00Z", "type": "File.Read", "agent": "LexaChat", "reason": "read"},
                ],
            }
        raise AssertionError(tool)

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_draft_history", {
        "query": "cockpit",
        "maxEvents": 10,
    }))

    assert result["success"] is True
    assert "Personal OS Draft History" in result["data"]
    assert "File.Read" in result["data"]
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 100,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS draft history path resolve",
        }),
        ("os_draft_history", {
            "draftPath": "06_Inbox/Drafts/cockpit.md",
            "maxEvents": 10,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS draft history read",
        }),
    ]


def test_personal_os_list_drafts_all_filter_omits_null_approvals(monkeypatch):
    import backend.personal_os_actions as actions

    calls = []

    async def fake_call(tool, arguments):
        calls.append((tool, arguments))
        return {
            "ok": True,
            "counts": {"total": 5, "pending": 0, "approved": 2, "rejected": 3},
            "drafts": [],
            "errors": [],
        }

    monkeypatch.setattr(actions, "_call_personal_os_tool", fake_call)

    result = _run(actions.execute_personal_os_action("personal_os_list_drafts", {"approval": "all"}))

    assert result["success"] is True
    assert calls == [
        ("os_list_drafts", {
            "hideSmoke": True,
            "maxDrafts": 20,
            "agentName": "LexaChat",
            "reason": "Lexa Chat Personal OS draft queue read",
        })
    ]
