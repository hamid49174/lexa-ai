"""Regression tests for CompanionEngine browser_open URL handling."""

import webbrowser

from companion.engine import CompanionEngine


def test_browser_open_normalizes_bare_public_url(monkeypatch):
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)

    result = CompanionEngine.open_url(object(), "example.com/path")

    assert opened == ["https://example.com/path"]
    assert "https://example.com/path" in result


def test_browser_open_blocks_internal_url_before_webbrowser(monkeypatch):
    monkeypatch.setattr(
        webbrowser,
        "open",
        lambda url: (_ for _ in ()).throw(AssertionError("webbrowser should not open")),
    )

    result = CompanionEngine.open_url(object(), "http://localhost:8000/health")

    assert "blockiert" in result or "blocked" in result.lower()


def test_browser_open_blocks_unsafe_scheme_before_webbrowser(monkeypatch):
    monkeypatch.setattr(
        webbrowser,
        "open",
        lambda url: (_ for _ in ()).throw(AssertionError("webbrowser should not open")),
    )

    result = CompanionEngine.open_url(object(), "javascript:alert(1)")

    assert "Unsicheres URL-Schema" in result
