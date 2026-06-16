"""Test fuer den search_web-Fallback bei ueber-quotierten Queries (0 Treffer)."""
import backend.web_research as wr


def test_simplify_query_strips_quotes_and_brackets():
    assert wr._simplify_query('"Tauri" "Electron" "Flutter" desktop ("bundle size")') == "Tauri Electron Flutter desktop bundle size"
    assert wr._simplify_query("   plain   query  ") == "plain query"


def test_search_web_retries_with_simplified_query(monkeypatch):
    seen = []

    def fake_once(query, max_results):
        seen.append(query)
        # Die quotierte Query liefert nichts, die vereinfachte einen Treffer.
        if '"' in query:
            return []
        return [{"title": "T", "url": "https://example.com/x", "snippet": "s"}]

    monkeypatch.setattr(wr, "_ddg_search_once", fake_once)
    res = wr.search_web('"Tauri" "Electron" vergleich')
    assert res and res[0]["url"] == "https://example.com/x"
    assert len(seen) == 2 and '"' in seen[0] and '"' not in seen[1]


def test_search_web_no_redundant_retry_when_results(monkeypatch):
    seen = []

    def fake_once(query, max_results):
        seen.append(query)
        return [{"title": "T", "url": "https://example.com/x", "snippet": "s"}]

    monkeypatch.setattr(wr, "_ddg_search_once", fake_once)
    res = wr.search_web("Tauri Electron vergleich")
    assert res and len(seen) == 1  # kein Fallback noetig


def test_search_web_empty_query():
    assert wr.search_web("   ") == []
