from backend.response_cache import (
    clear_response_cache,
    get_cached_chat_response,
    normalize_cache_query,
    remember_chat_response,
)


def setup_function():
    clear_response_cache()


def teardown_function():
    clear_response_cache()


def test_normalize_cache_query_folds_case_and_punctuation():
    assert normalize_cache_query("Erzaehl mir: Mond-Fakt!") == "erzaehl mir mond-fakt"


def test_response_cache_matches_similar_context_free_question_after_history_changes():
    first_history = []
    later_history = [
        {"role": "user", "content": "Erzaehl mir einen kurzen Fakt ueber den Mond."},
        {"role": "assistant", "content": "Der Mond entfernt sich langsam von der Erde."},
    ]

    stored = remember_chat_response(
        "Erzaehl mir einen kurzen Fakt ueber den Mond.",
        first_history,
        "Der Mond entfernt sich langsam von der Erde.",
    )
    hit = get_cached_chat_response(
        "Erzaehl mir einen kurzen Fakt ueber den Mond bitte.",
        later_history,
    )

    assert stored is True
    assert hit is not None
    assert hit["reply"] == "Der Mond entfernt sich langsam von der Erde."


def test_response_cache_keeps_followups_bound_to_same_context():
    history = [
        {"role": "user", "content": "Python ist unser Thema."},
        {"role": "assistant", "content": "Klar."},
    ]
    other_history = [
        {"role": "user", "content": "JavaScript ist unser Thema."},
        {"role": "assistant", "content": "Klar."},
    ]

    assert remember_chat_response("Und was ist wichtig daran?", history, "Python Lesbarkeit.")
    assert get_cached_chat_response("Und was ist wichtig daran?", other_history) is None
    assert get_cached_chat_response("Und was ist wichtig daran?", history)["reply"] == "Python Lesbarkeit."


def test_response_cache_ignores_sensitive_or_action_like_prompts():
    assert remember_chat_response("Mein API key ist sk-test-secret, was nun?", [], "Nicht teilen.") is False
    assert remember_chat_response("Loesch die Datei C:\\temp\\x.txt", [], "Nein.") is False

    assert get_cached_chat_response("Mein API key ist sk-test-secret, was nun?", []) is None
    assert get_cached_chat_response("Loesch die Datei C:\\temp\\x.txt", []) is None
