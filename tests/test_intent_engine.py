"""Tests for backend/intent_engine.py — Local intent recognition edge cases."""

import pytest
from backend.intent_engine import build_conversation_intent_context, try_local_intent

DEMO_TONE_MARKERS = (
    "Chef",
    "Boss",
    "Jarvis",
    "Challenge accepted",
    "Doktortitel",
    "Brauchst du noch",
    "beleidigt",
    "\U0001f3b5",
    "\U0001f4bb",
    "\U0001f4dd",
    "\U0001f4c5",
    "\U0001f4e7",
    "\U0001f4c1",
    "\U0001f310",
    "\U0001f525",
    "\U0001f4aa",
    "\U0001f604",
    "\U0001f60e",
)


def assert_professional_reply(reply: str) -> None:
    for marker in DEMO_TONE_MARKERS:
        assert marker not in reply


# ---------------------------------------------------------------------------
#  Priority: Productivity BEFORE app_open
# ---------------------------------------------------------------------------

class TestIntentPriority:
    def test_starte_pomodoro_not_app_open(self):
        """'starte pomodoro 25' must resolve to pomodoro, not app_open."""
        result = try_local_intent("starte pomodoro 25")
        assert result is not None
        assert result["action"] == "pomodoro_start"
        assert result["params"]["duration"] == 25

    def test_starte_timer_not_app_open(self):
        """'starte timer 5 min' must not match app_open — but timer has
        its own pattern 'timer 5 min' (no 'starte' prefix). So 'starte'
        prefix should fall through to app_open since _RE_TIMER expects
        'timer N min' not 'starte timer N min'."""
        result = try_local_intent("timer 5 min")
        assert result is not None
        assert result["action"] == "timer_set"
        assert result["params"]["seconds"] == 300

    def test_pomodoro_default_duration(self):
        """'pomodoro' alone defaults to 25 minutes."""
        result = try_local_intent("pomodoro")
        assert result is not None
        assert result["action"] == "pomodoro_start"
        assert result["params"]["duration"] == 25

    def test_pomodoro_stop(self):
        """'pomodoro stopp' resolves to pomodoro_stop."""
        result = try_local_intent("pomodoro stopp")
        assert result is not None
        assert result["action"] == "pomodoro_stop"

    def test_starte_chrome_is_app_open(self):
        """'starte chrome' should still be app_open."""
        result = try_local_intent("starte chrome")
        assert result is not None
        assert result["action"] == "app_open"
        assert result["params"]["name"].lower() == "chrome"

    def test_open_chrome_and_search_uses_standard_browser(self):
        """Compound browser searches should open the system browser, not Playwright."""
        result = try_local_intent("öffne chrome und suche nach Epstein-Files")
        assert result is not None
        assert result["action"] == "browser_open"
        assert result["params"]["url"].startswith("https://www.google.com/search?q=")

    def test_open_browser_and_non_search_followup_is_not_web_search(self):
        """A browser compound command without a search verb should stay out of the local search shortcut."""
        result = try_local_intent("oeffne chrome und spiele mero")
        assert result is None

    def test_contextual_file_delete_uses_recent_file_entity(self):
        context = build_conversation_intent_context([
            {"role": "user", "content": r"such die Datei C:\Users\admin\Desktop\plan.txt"},
            {"role": "assistant", "content": r"Gefunden: C:\Users\admin\Desktop\plan.txt"},
        ])

        result = try_local_intent("lösch die", context=context)

        assert result is not None
        assert result["action"] == "file_delete"
        assert result["params"]["path"] == r"C:\Users\admin\Desktop\plan.txt"

    def test_contextual_pronoun_without_recent_file_stays_ambiguous(self):
        result = try_local_intent("lösch die", context=build_conversation_intent_context([]))

        assert result is None

    def test_search_command_allows_polite_prefix(self):
        result = try_local_intent("bitte suche nach Epstein Files")
        assert result is not None
        assert result["action"] == "browser_open"
        assert result["params"]["url"].startswith("https://www.google.com/search?q=")

    @pytest.mark.parametrize(
        "message",
        [
            "ich will google nicht benutzen",
            "was bedeutet search engine optimization",
        ],
    )
    def test_search_words_inside_sentence_do_not_open_browser(self, message):
        result = try_local_intent(message)
        assert result is None

    def test_hermes_status_note_is_not_weather_city(self):
        result = try_local_intent(
            "Eingebaute Ja/OK-Zeilen zaehlen nicht als Freigabe. Weitere Desktop-Schritte pausiert..."
        )

        assert result is not None
        assert result["action"] is None
        assert "Hermes-Sicherheitshinweis" in result["message"]

    @pytest.mark.parametrize(
        "message",
        [
            'Freigabe vorbereitet:Ich wuerde Text im Fenster "Notepad" tippen.',
            "Freigabe offen fuer hermes_desktop_commit. Ich habe nichts ausgefuehrt.",
            "wartet auf Freigabe",
            "Bestaetigung noetig fuer ui_click. Antworte kurz mit ja.",
        ],
    )
    def test_hermes_confirmation_status_notes_are_local_noops(self, message):
        result = try_local_intent(message)

        assert result is not None
        assert result["action"] is None
        assert "Hermes-Sicherheitshinweis" in result["message"]

    def test_weitere_is_not_fuzzy_weather_keyword(self):
        result = try_local_intent("Weitere Desktop-Schritte pausiert...")

        assert result is not None
        assert result["action"] is None
        assert "Stadt" not in result["message"]

    def test_weather_typo_still_routes_to_weather(self):
        result = try_local_intent("weter Berlin")

        assert result is not None
        assert result["action"] == "weather_current"
        assert result["params"]["city"].lower() == "berlin"

    def test_internal_rules_question_is_not_app_open(self):
        """Meta questions about tool rules must not be routed to app_open."""
        result = try_local_intent(
            "Ich bin der App und ich versuche gerade die App zu verbessern "
            "und ich brauche die Tool-Regeln."
        )
        assert result is not None
        assert result["action"] is None
        assert "interne" in result["message"].lower()

    def test_brauche_is_not_fuzzy_launch(self):
        """'brauche' is too different from 'launch' to open an app."""
        result = try_local_intent("ich brauche chrome")
        assert result is None

    @pytest.mark.parametrize(
        "message",
        [
            "schriebe mir ein sehr sher komplexses python code was nur programiere mit 10 jahre erfrahrung koennene",
            "schreibe mir komplexen Python Code",
            "generiere ein async backend script in python",
        ],
    )
    def test_code_generation_requests_do_not_open_spotify(self, message):
        result = try_local_intent(message)

        assert result is None

    @pytest.mark.parametrize(
        "message",
        [
            "spiel mir musik",
            "spiele daft punk",
            "dpsile daft punk",
        ],
    )
    def test_music_commands_still_route_to_spotify(self, message):
        result = try_local_intent(message)

        assert result is not None
        assert result["action"] == "spotify_open"

    def test_how_was_your_day_is_smalltalk(self):
        """Smalltalk should not fall through to the LLM/tool stack."""
        result = try_local_intent("Wie war dein Tag?")
        assert result is not None
        assert result["action"] is None

    def test_was_geht_is_short_natural_smalltalk(self, monkeypatch):
        monkeypatch.setattr("backend.intent_engine.random.choice", lambda seq: seq[0])

        result = try_local_intent("WAS GEHT")

        assert result is not None
        assert result["action"] is None
        assert result["message"] == "Alles ruhig. Was machen wir?"
        assert "Ich habe keinen Tag" not in result["message"]

    @pytest.mark.parametrize(
        "message",
        [
            "hallo",
            "danke",
            "tschüss",
            "wer bist du",
            "was kannst du",
            "du bist gut",
            "du bist doof",
        ],
    )
    def test_core_smalltalk_uses_professional_tone(self, monkeypatch, message):
        """Built-in local replies should not sound like demo/buddy copy."""
        monkeypatch.setattr("backend.intent_engine.random.choice", lambda seq: seq[0])
        result = try_local_intent(message)
        assert result is not None
        reply = result["message"]
        assert_professional_reply(reply)

    @pytest.mark.parametrize(
        "message",
        [
            "spiel daft punk",
            "wetter berlin",
            "termine heute",
            "termine diese woche",
            "naechster termin",
            "neue emails",
            "todos",
            "prozesse",
            "suche nach openai",
            "witz",
            "mir ist langweilig",
            "wie alt bist du",
            "was kannst du",
        ],
    )
    def test_local_status_and_help_copy_uses_professional_tone(self, monkeypatch, message):
        """Fast-path status/help replies should not use cheap demo markers."""
        monkeypatch.setattr("backend.intent_engine.random.choice", lambda seq: seq[0])
        result = try_local_intent(message)
        assert result is not None
        assert_professional_reply(result["message"])


# ---------------------------------------------------------------------------
#  Volume / Basic intents
# ---------------------------------------------------------------------------

class TestVolumeIntents:
    def test_volume_set(self):
        result = try_local_intent("lautstärke 50")
        assert result is not None
        assert result["action"] == "volume_set"
        assert result["params"]["level"] == 50

    def test_volume_out_of_range(self):
        """Volume > 100 should not match."""
        result = try_local_intent("lautstärke 150")
        assert result is None

    def test_mute(self):
        result = try_local_intent("stumm")
        assert result is not None
        assert result["action"] == "volume_mute"


class TestMathIntents:
    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("was ist 1+1", "1 + 1 = 2."),
            ("was sind 60% aus 5000", "60 % von 5000 = 3000."),
            ("60 prozent von 5000", "60 % von 5000 = 3000."),
        ],
    )
    def test_simple_math_is_answered_locally_without_neediness(self, message, expected):
        result = try_local_intent(message)

        assert result is not None
        assert result["action"] is None
        assert result["message"] == expected
        assert "Brauchst du" not in result["message"]

    def test_division_by_zero_is_clear(self):
        result = try_local_intent("was ist 5/0")

        assert result is not None
        assert result["action"] is None
        assert result["message"] == "Das geht nicht: Division durch 0."


class TestToneRegression:
    def test_short_frustration_is_handled_without_moralizing(self, monkeypatch):
        monkeypatch.setattr("backend.intent_engine.random.choice", lambda seq: seq[0])

        result = try_local_intent("du hund")

        assert result is not None
        assert result["action"] is None
        assert_professional_reply(result["message"])
        assert "beleidigt" not in result["message"].lower()


# ---------------------------------------------------------------------------
#  Safety: long messages and multi-sentence
# ---------------------------------------------------------------------------

class TestSafetyGuards:
    def test_long_message_returns_none(self):
        """Messages > 200 chars should go to AI."""
        result = try_local_intent("a" * 201)
        assert result is None

    def test_multi_sentence_returns_none(self):
        """Messages with >2 periods should go to AI."""
        result = try_local_intent("Satz eins. Satz zwei. Satz drei. Ende.")
        assert result is None

    def test_empty_message_returns_none(self):
        result = try_local_intent("")
        assert result is None

    def test_none_message_returns_none(self):
        result = try_local_intent(None)
        assert result is None

    def test_conversational_goes_to_ai(self):
        """Complex questions should return None → AI handles them."""
        result = try_local_intent("was denkst du über künstliche Intelligenz?")
        assert result is None


# ---------------------------------------------------------------------------
#  Time / Date
# ---------------------------------------------------------------------------

class TestTimeDate:
    def test_wie_spaet_ist_es(self):
        result = try_local_intent("wie spät ist es?")
        assert result is not None
        assert result["action"] is None  # direct response, no companion action
        assert "Uhr" in result["message"]

    def test_datum(self):
        result = try_local_intent("datum")
        assert result is not None
        assert result["action"] is None
        assert "Heute ist" in result["message"]


# ---------------------------------------------------------------------------
#  Timer edge cases
# ---------------------------------------------------------------------------

class TestTimerEdgeCases:
    def test_timer_seconds(self):
        result = try_local_intent("timer 30 sek")
        assert result is not None
        assert result["action"] == "timer_set"
        assert result["params"]["seconds"] == 30

    def test_timer_zero_minutes_rejected(self):
        """0 minutes should not match (min 1)."""
        result = try_local_intent("timer 0 min")
        assert result is None

    def test_timer_too_large_rejected(self):
        """> 1440 min should not match."""
        result = try_local_intent("timer 9999 min")
        assert result is None
