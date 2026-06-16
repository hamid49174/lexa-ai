"""Tests fuer die echte Coding-Bruecke des Orchestrators (Phase 49 #4/J).

Der read-only code-Sub-Agent darf ZUSAETZLICH zu den lokalen git_*-Tools ueber den
bestehenden mcp_chat_bridge lesend aufs Dateisystem zugreifen — aber NUR die exakt
allowlisteten read-only mcp_filesystem_*-Tools, und nur wenn der Server verbunden ist.
Alles mit injizierten/monkeypatchten Fakes — keine echten MCP-Subprozesse.
"""
import asyncio

import backend.orchestrator.core as core
import backend.orchestrator.roles as roles
from backend.orchestrator.core import _PLANNER_PERSONA, _SYNTH_PERSONA, run_orchestration


# ── roles: Allowlist + Gate ──────────────────────────────────────────────────
def test_role_mcp_read_allowlist():
    code_reads = roles.role_mcp_read_tool_names("code")
    assert "mcp_filesystem_read_text_file" in code_reads
    assert len(code_reads) == 8
    # andere Rollen bekommen KEINE MCP-Reads
    assert roles.role_mcp_read_tool_names("research") == ()
    assert roles.role_mcp_read_tool_names("planning") == ()


def test_is_mcp_read_tool_only_reads():
    assert roles.is_mcp_read_tool("mcp_filesystem_read_text_file") is True
    assert roles.is_mcp_read_tool("mcp_filesystem_directory_tree") is True
    # Schreib-/Fremd-Tools sind NICHT read-only
    assert roles.is_mcp_read_tool("mcp_filesystem_write_file") is False
    assert roles.is_mcp_read_tool("mcp_git_commit") is False
    assert roles.is_mcp_read_tool("") is False


def test_is_role_tool_allowed_mcp_reads():
    assert roles.is_role_tool_allowed("code", "mcp_filesystem_read_text_file") is True
    assert roles.is_role_tool_allowed("code", "mcp_filesystem_search_files") is True
    # code darf KEINE MCP-Schreibtools
    assert roles.is_role_tool_allowed("code", "mcp_filesystem_write_file") is False
    assert roles.is_role_tool_allowed("code", "mcp_git_commit") is False
    # research darf gar keine MCP-Reads
    assert roles.is_role_tool_allowed("research", "mcp_filesystem_read_text_file") is False
    # lokale git-Tools bleiben erlaubt
    assert roles.is_role_tool_allowed("code", "git_status") is True


# ── role_tool_defs: MCP-Defs nur wenn verbunden + allowlistet ────────────────
def _fake_mcp_tool(name):
    return {"type": "function", "function": {"name": name, "description": "x", "parameters": {"type": "object"}}}


def test_role_tool_defs_appends_connected_mcp_reads(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    monkeypatch.setattr(bridge, "mcp_chat_tools", lambda: [
        _fake_mcp_tool("mcp_filesystem_read_text_file"),   # allowlistet -> rein
        _fake_mcp_tool("mcp_filesystem_write_file"),        # Schreibtool -> raus
        _fake_mcp_tool("mcp_git_commit"),                   # nicht allowlistet -> raus
    ])
    names = [t["function"]["name"] for t in roles.role_tool_defs("code")]
    assert "mcp_filesystem_read_text_file" in names
    assert "mcp_filesystem_write_file" not in names
    assert "mcp_git_commit" not in names
    # lokale Tools weiterhin da
    assert "git_status" in names and "file_search" in names


def test_role_tool_defs_no_mcp_for_research(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    monkeypatch.setattr(bridge, "mcp_chat_tools", lambda: [_fake_mcp_tool("mcp_filesystem_read_text_file")])
    names = [t["function"]["name"] for t in roles.role_tool_defs("research")]
    assert not any(n.startswith("mcp_") for n in names)


def test_role_tool_defs_graceful_when_bridge_unavailable(monkeypatch):
    import backend.mcp_chat_bridge as bridge

    def boom():
        raise RuntimeError("MCP aus")

    monkeypatch.setattr(bridge, "mcp_chat_tools", boom)
    # darf nicht werfen — degradiert auf lokale Tools
    names = [t["function"]["name"] for t in roles.role_tool_defs("code")]
    assert "git_status" in names
    assert not any(n.startswith("mcp_") for n in names)


# ── Executor: read routet, write wird abgelehnt ──────────────────────────────
def test_execute_mcp_read_routes_read_tool(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    calls = []

    async def fake_exec(name, params):
        calls.append((name, params))
        return {"success": True, "data": {"content": "datei-inhalt"}}

    monkeypatch.setattr(bridge, "execute_mcp_action", fake_exec)
    res = asyncio.run(core._execute_mcp_read("mcp_filesystem_read_text_file", {"path": "x.py"}))
    assert res["success"] is True
    assert calls == [("mcp_filesystem_read_text_file", {"path": "x.py"})]


def test_execute_mcp_read_refuses_write_tool(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    called = {"n": 0}

    async def fake_exec(name, params):
        called["n"] += 1
        return {"success": True, "data": "sollte nie passieren"}

    monkeypatch.setattr(bridge, "execute_mcp_action", fake_exec)
    res = asyncio.run(core._execute_mcp_read("mcp_filesystem_write_file", {"path": "x", "content": "y"}))
    assert res["success"] is False
    assert "nicht erlaubt" in res["error"]
    assert called["n"] == 0  # execute_mcp_action NIE aufgerufen


def test_default_execute_tool_fn_routes_mcp(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    seen = []

    async def fake_exec(name, params):
        seen.append(name)
        return {"success": True, "data": "ok"}

    monkeypatch.setattr(bridge, "execute_mcp_action", fake_exec)
    res = asyncio.run(core._default_execute_tool_fn("mcp_filesystem_list_directory", {"path": "."}))
    assert res["success"] is True and seen == ["mcp_filesystem_list_directory"]


# ── End-to-End: Gate im Sub-Agenten + Warmup-Event ───────────────────────────
def _collect(agen):
    async def _run():
        return [ev async for ev in agen]
    return asyncio.run(_run())


def test_code_subagent_can_read_mcp_but_not_write():
    """Injizierter Executor (kein Warmup): mcp-Read laeuft, mcp-Write wird geblockt."""
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"code","objective":"Lies main.py"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Fertig."}
        joined = " ".join(str(m.get("content", "")) for m in messages)
        if "[TOOL-ERGEBNIS" in joined or "nicht erlaubt" in joined or "NICHT erlaubt" in joined:
            return {"type": "text", "content": "Sub-Agent fertig."}
        # erst Read (erlaubt), dann — im naechsten Lauf erreicht der Pfad oben schon Text
        return {"type": "tool_call", "tool_calls": [
            {"function": {"name": "mcp_filesystem_read_text_file", "arguments": '{"path":"main.py"}'}}
        ], "content": ""}

    executed = []

    def fake_exec(name, params):
        executed.append(name)
        return {"success": True, "data": "inhalt"}

    events = _collect(run_orchestration("Lies main.py", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    steps = [e for e in events if e["type"] == "subagent_step"]
    assert any(s["step"]["tool"] == "mcp_filesystem_read_text_file" and s["step"]["status"] == "done" for s in steps)
    assert "mcp_filesystem_read_text_file" in executed
    # injizierter Executor -> kein Warmup-Event
    assert "mcp" not in [e["type"] for e in events]


def test_code_subagent_blocks_mcp_write():
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"code","objective":"x"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Fertig."}
        joined = " ".join(str(m.get("content", "")) for m in messages)
        if "nicht erlaubt" in joined or "NICHT erlaubt" in joined:
            return {"type": "text", "content": "Ok, nur Text."}
        return {"type": "tool_call", "tool_calls": [
            {"function": {"name": "mcp_filesystem_write_file", "arguments": '{"path":"x","content":"y"}'}}
        ], "content": ""}

    executed = []

    def fake_exec(name, params):
        executed.append(name)
        return {"success": True, "data": "sollte nie passieren"}

    events = _collect(run_orchestration("x", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    steps = [e for e in events if e["type"] == "subagent_step"]
    assert "mcp_filesystem_write_file" not in executed
    assert any(s["step"]["status"] == "blocked" for s in steps)


def test_warmup_emits_mcp_event_for_code_plan(monkeypatch):
    import backend.mcp_chat_bridge as bridge

    async def fake_warm(servers=("filesystem",)):
        return {"filesystem": "connected"}

    monkeypatch.setattr(bridge, "ensure_coding_servers_connected", fake_warm)

    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"code","objective":"x"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Fertig."}
        return {"type": "text", "content": "Sub-Agent fertig."}  # kein Tool -> Default-Executor nie genutzt

    # KEIN execute_tool_fn injiziert -> Default-Executor -> Warmup aktiv
    events = _collect(run_orchestration("Analysiere den Code", mode="fast", chat_fn=fake_chat))
    mcp_events = [e for e in events if e["type"] == "mcp"]
    assert len(mcp_events) == 1
    assert mcp_events[0]["servers"] == {"filesystem": "connected"}
    assert events[-1]["run"]["mcp_servers"] == {"filesystem": "connected"}


def test_no_warmup_without_code_subtask(monkeypatch):
    import backend.mcp_chat_bridge as bridge
    warm_called = {"n": 0}

    async def fake_warm(servers=("filesystem",)):
        warm_called["n"] += 1
        return {"filesystem": "connected"}

    monkeypatch.setattr(bridge, "ensure_coding_servers_connected", fake_warm)

    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"research","objective":"x"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Fertig."}
        return {"type": "text", "content": "Sub-Agent fertig."}

    events = _collect(run_orchestration("Recherche", mode="fast", chat_fn=fake_chat))
    assert "mcp" not in [e["type"] for e in events]
    assert warm_called["n"] == 0
    assert events[-1]["run"]["mcp_servers"] == {}
