"""Tests for companion/browser.py fallback behavior."""

from companion import browser


def test_web_open_falls_back_to_system_browser_when_playwright_missing(monkeypatch):
    opened = []

    def raise_missing_browser():
        raise RuntimeError("Playwright-Browser nicht gefunden.")

    monkeypatch.setattr(browser, "_get_browser", raise_missing_browser)
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: opened.append(url) or True)

    result = browser.open_url("https://example.com")

    assert result["status"] == "opened"
    assert result["fallback"] is True
    assert result["url"] == "https://example.com"
    assert opened == ["https://example.com"]


def test_web_open_does_not_fallback_for_unsafe_url(monkeypatch):
    monkeypatch.setattr(browser.webbrowser, "open", lambda url: True)

    result = browser.open_url("javascript:alert(1)")

    assert "error" in result
    assert "http" in result["error"].lower()
