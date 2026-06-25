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
