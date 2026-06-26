"""Regressionstests aus dem Gesamt-Scan (2026-06-25) — Companion-Funde."""
import json
from pathlib import Path

from companion.engine import companion
from companion import hermes_desktop
from backend import tool_registry


def test_weather_will_it_rain_is_registered_and_whitelisted():
    # War implementiert (weather.py), aber nicht erreichbar (fehlte im Command-Dict,
    # in der Whitelist UND in der LLM-Tool-Registry).
    assert "weather_will_it_rain" in companion.commands

    whitelist = json.loads(
        (Path(__file__).resolve().parent.parent / "command_whitelist.json").read_text(encoding="utf-8")
    )
    always = whitelist["commands"]["always_allowed"]["list"]
    assert "weather_will_it_rain" in always

    # Self-Review-Korrektur: muss auch in der LLM-Tool-Registry stehen, sonst
    # bietet get_tools_for_context() es dem Modell nie an und validate_tool_arguments
    # blockt es als "unknown tool".
    assert tool_registry.get_tool("weather_will_it_rain") is not None


def test_focused_title_matches_target_tolerates_partial():
    assert hermes_desktop._focused_title_matches_target("Notepad", "*Test - Notepad") is True
    assert hermes_desktop._focused_title_matches_target("chrome", "Google - Google Chrome") is True
    # Self-Review-Korrektur: toleranter Matcher (Notepad<->Editor-Alias, Umlaut-Faltung)
    # statt naivem Substring -> blockiert legitime Tipp-Faelle nicht mehr.
    assert hermes_desktop._focused_title_matches_target("Notepad", "Unbenannt - Editor") is True
    # Klarer Mismatch
    assert hermes_desktop._focused_title_matches_target("Notepad", "Rechner") is False
    # Fehlendes Signal -> kein Fehlalarm (True = nicht abbrechen)
    assert hermes_desktop._focused_title_matches_target("Notepad", "") is True
    assert hermes_desktop._focused_title_matches_target("", "irgendwas") is True


def test_known_window_launcher_resolves_any_installed_app(monkeypatch, tmp_path):
    # Bereich B: Launcher war fest auf notepad verdrahtet -> jetzt generisch via
    # app_discovery (echte .exe-Pfade).
    import companion.app_discovery as ad
    fake_exe = tmp_path / "chrome.exe"
    fake_exe.write_text("", encoding="utf-8")

    # Notepad-Spezialfall bleibt
    assert hermes_desktop._known_window_launcher("notepad") == ["notepad.exe"]

    # Beliebige installierte App mit echtem .exe-Pfad -> wird zurueckgegeben
    monkeypatch.setattr(ad, "find_app", lambda q: {"name": "Chrome", "app_id": str(fake_exe)})
    assert hermes_desktop._known_window_launcher("chrome") == [str(fake_exe)]

    # Store/UWP/URI-App ohne echten Datei-Pfad -> [] (kein Popen-Fokus-Pfad)
    monkeypatch.setattr(ad, "find_app", lambda q: {"name": "Foo", "app_id": "shell:AppsFolder\\Foo"})
    assert hermes_desktop._known_window_launcher("foo-store-app") == []

    # Kein Treffer -> []
    monkeypatch.setattr(ad, "find_app", lambda q: None)
    assert hermes_desktop._known_window_launcher("gibtsnicht") == []


def test_reachability_shutdown_cancel_offered_and_whitelisted():
    # Bereich B: shutdown_cancel war beworben (Hinweis in shutdown_pc/restart_pc),
    # aber weder registriert noch whitelisted -> nicht aufrufbar.
    from backend import tool_registry as tr
    names = {(t.get("function", {}).get("name") or t.get("name")) for t in tr.get_all_tools()}
    assert "shutdown_cancel" in names
    assert tr.get_tool("shutdown_cancel") is not None

    whitelist = json.loads(
        (Path(__file__).resolve().parent.parent / "command_whitelist.json").read_text(encoding="utf-8")
    )
    assert "shutdown_cancel" in whitelist["commands"]["always_allowed"]["list"]
