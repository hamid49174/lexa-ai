from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PLUGIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "hermes_workspace"
    / ".hermes"
    / "plugins"
    / "lexa-status"
    / "__init__.py"
)

# hermes_workspace/ is a local, git-ignored workspace. Skip the whole module
# when it is not mounted (e.g. on CI or a fresh clone).
pytestmark = pytest.mark.skipif(
    not _PLUGIN_PATH.exists(),
    reason=f"Hermes workspace plugin not mounted: {_PLUGIN_PATH}",
)


def _load_plugin():
    plugin_path = _PLUGIN_PATH
    spec = importlib.util.spec_from_file_location("lexa_status_plugin", plugin_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lexa_status_plugin_rewrites_natural_status_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_status_question("Was ist der Stand von Lexa/OS?")
    assert plugin._looks_like_status_question("Wie laeuft Hermes?")
    assert plugin._looks_like_status_question("Wie läuft Hermes?")
    assert plugin._looks_like_status_question("Was kann Hermes?")
    assert plugin._looks_like_status_question("OS Status bitte")
    assert plugin._looks_like_status_question("Status Obsidian")


def test_lexa_status_plugin_rewrites_overview_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_overview_question("Wie findest du mein OS und Hermes?")
    assert plugin._looks_like_overview_question("Was bringt das spaeter fuer Lexa?")
    assert plugin._looks_like_overview_question("OS Architektur und Produktwert?")
    assert plugin._pre_gateway_dispatch(type("Event", (), {"text": "Wie findest du mein OS und Hermes?"})()) == {
        "action": "rewrite",
        "text": "/lexa_overview",
    }


def test_lexa_status_plugin_rewrites_natural_log_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_log_question("Hermes Logs bitte")
    assert plugin._looks_like_log_question("Gibt es Gateway Fehler?")
    assert plugin._looks_like_log_question("Telegram Warnungen?")


def test_lexa_status_plugin_rewrites_natural_task_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_task_question("Was sind offene Lexa Aufgaben?")
    assert plugin._looks_like_task_question("Welche Hermes Baustellen sind offen?")
    assert plugin._looks_like_task_question("Was ist der naechste OS Task?")


def test_lexa_status_plugin_rewrites_natural_context_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_context_question("Such im OS nach Provider-Fallback")
    assert plugin._looks_like_context_question("Zeig mir Obsidian Kontext zu Hermes")
    assert plugin._looks_like_context_question("Welche Lexa Dateien sind dazu relevant?")


def test_lexa_status_plugin_rewrites_explicit_draft_create_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_draft_create_question("Erstelle einen Lexa OS Draft: Status merken")
    assert plugin._looks_like_draft_create_question("Mach einen Hermes Kontext Entwurf daraus")
    assert not plugin._looks_like_draft_create_question("Welche Drafts sind offen?")


def test_lexa_status_plugin_rewrites_draft_list_questions():
    plugin = _load_plugin()

    assert plugin._looks_like_draft_list_question("Welche Drafts sind offen?")
    assert plugin._looks_like_draft_list_question("Zeig Lexa pending drafts")
    assert plugin._pre_gateway_dispatch(type("Event", (), {"text": "Welche Drafts sind offen?"})()) == {
        "action": "rewrite",
        "text": "/lexa_drafts",
    }


def test_lexa_status_plugin_does_not_rewrite_regular_chat():
    plugin = _load_plugin()

    assert not plugin._looks_like_status_question("Schreib mir eine kurze Antwort.")
    assert not plugin._looks_like_status_question("/lexa_status")


def test_lexa_status_plugin_prefers_visible_hermes_next_work():
    plugin = _load_plugin()
    text = "\n".join([
        "- [ ] Keep runtime artifacts out of commits.",
        "- [ ] Add a small Hermes gateway log-rotation or log-summary routine if logs keep growing.",
    ])

    assert plugin._first_open_task(text, preferred_terms=("gateway log",)) == (
        "Add a small Hermes gateway log-rotation or log-summary routine if logs keep growing"
    )


def test_lexa_logs_plugin_formats_backend_summary(monkeypatch):
    plugin = _load_plugin()

    def fake_read_json(url, timeout=2.0):
        assert "/hermes/gateway/logs" in url
        return {
            "status": "ok",
            "exists": True,
            "health_state": "ok",
            "summary": "Keine Fehler/Warnungen in den letzten 20 Logzeilen; 1 Telegram-Eingaenge, 1 Antworten.",
            "size_mb": 0.1,
            "tail_lines": 20,
            "counts": {"inbound_messages": 1, "responses_ready": 1, "memory_heartbeats": 2},
            "issues": [],
            "latest": [{"timestamp": "2026-05-19 01:00:00", "level": "INFO", "message": "Gateway running"}],
            "log_path": "gateway.log",
        }

    monkeypatch.setattr(plugin, "_read_json", fake_read_json)

    result = plugin._plugin_logs("")

    assert "Hermes Gateway Logs:" in result
    assert "Zustand: ok" in result
    assert "Auffaellig: keine aktuellen Fehler" in result


def test_lexa_overview_plugin_formats_backend_overview(monkeypatch):
    plugin = _load_plugin()

    def fake_read_json(url, timeout=2.0):
        assert "/hermes/overview" in url
        return {
            "summary": "Lexa/Hermes/OS ist arbeitsfaehig.",
            "nextAction": "Build visible OS/Hermes cockpit",
            "telegramText": "Lexa/Hermes Overview:\n- Stand: ok\n- Naechste Aktion: Build visible OS/Hermes cockpit",
        }

    monkeypatch.setattr(plugin, "_read_json", fake_read_json)

    result = plugin._plugin_overview("")

    assert "Lexa/Hermes Overview:" in result
    assert "Naechste Aktion" in result


def test_lexa_tasks_plugin_prefers_visible_remote_control_tasks(monkeypatch, tmp_path):
    plugin = _load_plugin()
    os_root = tmp_path / "os"
    tasks_dir = os_root / "08_Lexa" / "Tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "Lexa_Next_Work.md").write_text(
        "\n".join([
            "- [ ] Keep approved OS context changes synchronized into `Current_AI_Brief.md`.",
            "- [ ] Add next Telegram remote command: `/lexa_tasks` or `/lexa_context`.",
            "- [ ] Later: add direct formatting helpers.",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("LEXA_PERSONAL_OS_ROOT", str(os_root))

    result = plugin._plugin_tasks("")

    assert "Lexa Tasks:" in result
    assert "/lexa_tasks" in result
    assert "Naechste Aktion:" in result


def test_lexa_context_plugin_formats_bounded_context(monkeypatch):
    plugin = _load_plugin()

    def fake_post_json(url, payload, timeout=5.0):
        assert url.endswith("/hermes/context")
        assert payload["topic"] == "Hermes Status"
        assert payload["maxFiles"] == 6
        return {
            "ok": True,
            "context": {
                "counts": {"selectedFiles": 2},
                "policy": {"readMode": "bounded-index-routed"},
                "files": [
                    {
                        "title": "Hermes Capabilities",
                        "path": "08_Lexa/Architecture/Hermes_Capabilities.md",
                        "tags": ["lexa", "hermes"],
                        "bodyPreview": "# Hermes\nTelegram status command.",
                    },
                    {
                        "title": "Live Status",
                        "path": "08_Lexa/Tasks/Lexa_OS_Live_Status.md",
                        "tags": ["status"],
                        "bodyPreview": "Fast answer surface.",
                    },
                ],
            },
        }

    monkeypatch.setattr(plugin, "_post_json", fake_post_json)

    result = plugin._plugin_context("Hermes Status")

    assert "Lexa Kontext: Hermes Status" in result
    assert "kein Full-Vault-Dump" in result
    assert "08_Lexa/Architecture/Hermes_Capabilities.md" in result
    assert "Draft/Approval" in result


def test_lexa_draft_plugin_creates_safe_review_draft(monkeypatch):
    plugin = _load_plugin()

    def fake_post_json(url, payload, timeout=5.0):
        assert url.endswith("/hermes/draft")
        assert payload["body"] == "Merke Hermes kann jetzt Status und Logs."
        return {
            "success": True,
            "title": "Merke Hermes kann jetzt Status und Logs.",
            "draftPath": "06_Inbox/Drafts/example_update.md",
            "targetPath": "05_Memory/Session/example.md",
        }

    monkeypatch.setattr(plugin, "_post_json", fake_post_json)

    result = plugin._plugin_draft("Merke Hermes kann jetzt Status und Logs.")

    assert "Lexa Draft erstellt:" in result
    assert "06_Inbox/Drafts/example_update.md" in result
    assert "Stable OS-Dateien wurden nicht veraendert" in result


def test_lexa_drafts_plugin_formats_review_queue(monkeypatch):
    plugin = _load_plugin()

    def fake_read_json(url, timeout=2.0):
        assert "/hermes/drafts" in url
        return {
            "ok": True,
            "approval": "pending",
            "counts": {"pending": 1, "approved": 2, "rejected": 0, "missing": 0},
            "drafts": [{
                "title": "Hermes capability update",
                "path": "06_Inbox/Drafts/hermes.md",
                "approval": "pending",
                "updated": "2026-05-19",
            }],
        }

    monkeypatch.setattr(plugin, "_read_json", fake_read_json)

    result = plugin._plugin_drafts("pending")

    assert "Lexa Drafts:" in result
    assert "pending=1" in result
    assert "06_Inbox/Drafts/hermes.md" in result
    assert "Read-only" in result
