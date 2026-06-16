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


# ── High-End Such-API-Provider ──
def test_api_search_returns_empty_without_key(monkeypatch):
    monkeypatch.setattr(wr, "_search_key_for", lambda p: "")
    assert wr._api_search("frage", 5) == []


def test_search_web_prefers_api_provider_over_scrape(monkeypatch):
    monkeypatch.setattr(wr, "_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(wr, "_search_key_for", lambda p: "KEY" if p == "tavily" else "")
    monkeypatch.setattr(wr, "_search_tavily", lambda q, n, k: [{"title": "T", "url": "https://x", "snippet": "s", "content": "c"}])
    ddg = []
    monkeypatch.setattr(wr, "_ddg_search_once", lambda q, n: (ddg.append(q), [])[1])
    res = wr.search_web("frage")
    assert res and res[0]["url"] == "https://x"
    assert ddg == []  # API genutzt -> DDG gar nicht erst befragt


def test_search_web_falls_back_to_ddg_without_key(monkeypatch):
    monkeypatch.setattr(wr, "_search_key_for", lambda p: "")
    monkeypatch.setattr(wr, "_ddg_search_once", lambda q, n: [{"title": "T", "url": "https://y", "snippet": "s"}])
    res = wr.search_web("frage")
    assert res and res[0]["url"] == "https://y"


def test_api_search_skips_provider_on_error(monkeypatch):
    monkeypatch.setattr(wr, "_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(wr, "_search_key_for", lambda p: "KEY")

    def boom(q, n, k):
        raise RuntimeError("api down")

    monkeypatch.setattr(wr, "_search_tavily", boom)
    monkeypatch.setattr(wr, "_search_brave", lambda q, n, k: [{"title": "B", "url": "https://b", "snippet": "s"}])
    res = wr._api_search("frage", 5)
    assert res and res[0]["url"] == "https://b"  # tavily-Fehler -> brave


def test_gather_sources_skips_fetch_when_content_present(monkeypatch):
    monkeypatch.setattr(wr, "search_web", lambda q, max_results=5: [
        {"title": "T", "url": "https://x", "snippet": "s", "content": "vorhandener inhalt"},
    ])
    fetched = []
    monkeypatch.setattr(wr, "fetch_readable", lambda u: (fetched.append(u), "GEFETCHT")[1])
    out = wr.gather_sources("frage", 2)
    assert out and out[0]["content"] == "vorhandener inhalt"
    assert fetched == []  # kein doppelter Fetch
