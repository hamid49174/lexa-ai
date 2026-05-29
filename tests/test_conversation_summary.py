from backend.ai_engine import _extract_keywords, _summarize_messages_local
from backend.conversation_summary import extract_keywords, summarize_messages_local


def test_ai_engine_keeps_conversation_summary_compatibility_aliases():
    assert _extract_keywords is extract_keywords
    assert _summarize_messages_local is summarize_messages_local


def test_large_history_summary_keeps_recent_user_topic():
    messages = [
        {"role": "user", "content": f"Altes Thema Nummer {index}"}
        for index in range(24)
    ]
    messages.append({"role": "user", "content": "Aktueller Projektplan Apollo"})

    summary = summarize_messages_local(messages)

    assert "Aktueller Projektplan Apollo" in summary
    assert "Altes Thema Nummer 0" in summary


def test_keyword_extraction_normalizes_umlauts_and_ranks_repeated_terms():
    keywords = extract_keywords("Projekt Alpha Alpha mit Lautstaerke und Qualität")

    assert keywords[0] == "alpha"
    assert "projekt" in keywords
    assert "qualitaet" in keywords


def test_keyword_extraction_normalizes_real_umlauts():
    keywords = extract_keywords("Projekt Alpha mit Lautst\u00e4rke und Qualit\u00e4t")

    assert "lautstaerke" in keywords
    assert "qualitaet" in keywords
