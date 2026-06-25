"""Regressionstests aus dem Gesamt-Scan (2026-06-25) — Companion-Funde."""
import json
from pathlib import Path

from companion.engine import companion
from companion import hermes_desktop


def test_weather_will_it_rain_is_registered_and_whitelisted():
    # War implementiert (weather.py), aber nicht erreichbar (fehlte im Command-Dict
    # und in der Whitelist).
    assert "weather_will_it_rain" in companion.commands

    whitelist = json.loads(
        (Path(__file__).resolve().parent.parent / "command_whitelist.json").read_text(encoding="utf-8")
    )
    always = whitelist["commands"]["always_allowed"]["list"]
    assert "weather_will_it_rain" in always


def test_focused_title_matches_target_tolerates_partial():
    assert hermes_desktop._focused_title_matches_target("Notepad", "*Test - Notepad") is True
    assert hermes_desktop._focused_title_matches_target("chrome", "Google - Google Chrome") is True
    # Klarer Mismatch
    assert hermes_desktop._focused_title_matches_target("Notepad", "Rechner") is False
    # Fehlendes Signal -> kein Fehlalarm (True = nicht abbrechen)
    assert hermes_desktop._focused_title_matches_target("Notepad", "") is True
    assert hermes_desktop._focused_title_matches_target("", "irgendwas") is True
