from voice.wakeword import _command_after_wake_phrase, _contains_wake_phrase
from voice.wakeword_engines import (
    TranscriptWakeWordEngine,
    WakeDetection,
    create_default_wakeword_engine,
    get_wakeword_engine_capabilities,
)
from voice.wakeword import WakeWordDetector


def test_wake_phrase_matches_exact_token():
    assert _contains_wake_phrase("Hey Lexa, bist du da?", ["lexa"])


def test_wake_phrase_matches_multi_token_phrase():
    assert _contains_wake_phrase("okay lexa", ["ok lexa", "okay lexa"])


def test_wake_phrase_accepts_alexa_alias():
    assert _contains_wake_phrase("Alexa, starte den Chat", ["lexa", "alexa"])


def test_wake_phrase_does_not_match_inside_words():
    assert not _contains_wake_phrase("Das ist reflexartig komplex.", ["lex", "lexa"])


def test_wake_phrase_does_not_match_partial_token():
    assert not _contains_wake_phrase("Lexapro ist kein Wake Word.", ["lex", "lexa"])


def test_extracts_command_after_wake_phrase():
    assert _command_after_wake_phrase(
        "Lexa, starte den Chat",
        ["lexa", "alexa"],
    ) == "starte den chat"


def test_extracts_command_after_longest_wake_phrase():
    assert _command_after_wake_phrase(
        "Hey Lexa bitte öffne die Einstellungen",
        ["lexa", "hey lexa"],
    ) == "öffne die einstellungen"


def test_empty_command_when_only_wake_phrase():
    assert _command_after_wake_phrase("Okay Lexa", ["lexa", "okay lexa"]) == ""


def test_transcript_wake_engine_reports_fallback_status():
    status = TranscriptWakeWordEngine().status()
    assert status["name"] == "legacy_transcript_phrase_match"
    assert status["uses_stt"] is True
    assert status["ready"] is False
    assert status["legacy"] is True


def test_default_wake_engine_is_real_local_keyword_spotter():
    status = create_default_wakeword_engine().status()
    assert status["name"] == "openwakeword"
    assert status["uses_stt"] is False
    assert status["local"] is True


def test_wake_detection_carries_source_and_score():
    detection = WakeDetection(True, text="lexa", score=0.75, source="openwakeword")
    assert detection.detected is True
    assert detection.text == "lexa"
    assert detection.source == "openwakeword"
    assert detection.score == 0.75


def test_wakeword_capabilities_describe_local_target():
    caps = get_wakeword_engine_capabilities()
    assert caps["target"] == "siri_style_local_keyword_spotting"
    assert "legacy" in caps
    assert caps["configured_mode"] == "openwakeword"


def test_wakeword_status_reports_fallback_stt_throttle():
    detector = WakeWordDetector()
    status = detector.status
    assert "skipped_stt_checks" in status
    assert status["fallback_stt_min_interval_s"] > 0
    assert status["fallback_stt_interval_s"] == status["fallback_stt_min_interval_s"]


def test_wakeword_fallback_backoff_grows_and_resets():
    detector = WakeWordDetector()
    detector._wake_engine = TranscriptWakeWordEngine()
    start_interval = detector.status["fallback_stt_interval_s"]
    detector._record_non_wake_transcript()
    detector._record_non_wake_transcript()
    assert detector.status["fallback_stt_interval_s"] > start_interval
    assert detector.status["non_wake_transcripts"] == 2
    detector._reset_fallback_stt_backoff()
    assert detector.status["fallback_stt_interval_s"] == start_interval
    assert detector.status["non_wake_transcripts"] == 0


def test_wakeword_status_reports_full_phrase_set_and_responsive_cap():
    detector = WakeWordDetector()
    detector._wake_engine = TranscriptWakeWordEngine()
    for _ in range(10):
        detector._record_non_wake_transcript()
    status = detector.status
    assert "hey lexa" in status["phrases"]
    assert status["fallback_stt_interval_s"] <= 1.5


def test_wakeword_empty_command_emits_timeout_and_end(monkeypatch):
    from backend import voice_ws

    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(voice_ws, "push_event", lambda event, text="", **_kwargs: calls.append(("event", event, text)))
    monkeypatch.setattr(voice_ws, "push_state", lambda state: calls.append(("state", state, "")))

    detector = WakeWordDetector()
    detector._finish_wake_without_command("No command heard.")

    assert ("event", "wake_timeout", "No command heard.") in calls
    assert ("state", "conversation_end", "") in calls
    assert detector.status["last_command"] == ""
