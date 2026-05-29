"""Tests for companion/browser.py fallback behavior."""

import sys
import types

import pytest

from companion import browser


class _FakePlaywrightRequest:
    def __init__(self, url, navigation=True, resource_type=None):
        self.url = url
        self._navigation = navigation
        self.resource_type = resource_type or ("document" if navigation else "image")

    def is_navigation_request(self):
        return self._navigation


class _FakePlaywrightRoute:
    def __init__(self, url, navigation=True, resource_type=None):
        self.request = _FakePlaywrightRequest(url, navigation, resource_type)
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class _FakePlaywrightPage:
    def __init__(self, routes=None, final_url=None):
        self.routes = routes or []
        self.final_url = final_url
        self.url = "about:blank"
        self.closed = False
        self.route_pattern = None
        self.route_handler = None

    def route(self, pattern, handler):
        self.route_pattern = pattern
        self.route_handler = handler

    def goto(self, url, **kwargs):
        self.url = url
        self.goto_args = (url, kwargs)
        for route in self.routes:
            self.route_handler(route)
            if route.aborted and route.request.is_navigation_request():
                raise RuntimeError("net::ERR_FAILED")
        if self.final_url is not None:
            self.url = self.final_url
        elif self.routes:
            self.url = self.routes[-1].request.url
        return types.SimpleNamespace(status=200)

    def title(self):
        return "Example"

    def close(self):
        self.closed = True


class _FakePlaywrightBrowser:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


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


def test_web_open_reports_invalid_port_without_starting_browser(monkeypatch):
    monkeypatch.setattr(
        browser,
        "_get_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser should not start")),
    )
    monkeypatch.setattr(
        browser.webbrowser,
        "open",
        lambda _url: (_ for _ in ()).throw(AssertionError("fallback should not start")),
    )

    result = browser.open_url("https://example.com:notaport/path")

    assert result == {"error": "Ungueltiger URL-Port."}


@pytest.mark.parametrize("url", [
    "http://localhost:8000/health",
    "http://app.localhost/status",
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1:8000/health",
    "http://0.0.0.0:8000/health",
    "http://224.0.0.1/",
    "http://[::ffff:127.0.0.1]/",
])
def test_web_open_blocks_internal_hosts_before_browser(monkeypatch, url):
    monkeypatch.setattr(
        browser,
        "_get_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser should not start")),
    )
    monkeypatch.setattr(
        browser.webbrowser,
        "open",
        lambda target: (_ for _ in ()).throw(AssertionError("fallback should not start")),
    )

    result = browser.open_url(url)

    assert "error" in result
    assert "blockiert" in result["error"] or "blocked" in result["error"].lower()


def test_scrape_text_blocks_unsafe_lightweight_redirect_before_browser(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, url):
            calls.append(url)
            return types.SimpleNamespace(
                status_code=302,
                headers={"location": "http://127.0.0.1/admin"},
                url=url,
                text="",
            )

    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        types.SimpleNamespace(extract=lambda *_args, **_kwargs: "", extract_metadata=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(browser, "_resolved_browser_url_error", lambda _url: None)
    monkeypatch.setattr(
        browser,
        "_get_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser fallback should not start")),
    )

    result = browser.scrape_text("https://example.com/article")

    assert calls == ["https://example.com/article"]
    assert "error" in result
    assert "blockiert" in result["error"] or "blocked" in result["error"].lower()


def test_scrape_text_blocks_private_dns_before_lightweight_request(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def get(self, _url):
            raise AssertionError("request should not be sent after private DNS resolution")

    monkeypatch.setitem(
        sys.modules,
        "trafilatura",
        types.SimpleNamespace(extract=lambda *_args, **_kwargs: "", extract_metadata=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(browser, "_resolved_browser_url_error", lambda _url: "SSRF blockiert")
    monkeypatch.setattr(
        browser,
        "_get_browser",
        lambda: (_ for _ in ()).throw(AssertionError("browser fallback should not start")),
    )

    result = browser.scrape_text("https://example.com/article")

    assert result == {"error": "SSRF blockiert"}


def test_playwright_guard_continues_public_navigation(monkeypatch):
    route = _FakePlaywrightRoute("https://example.org/next")
    page = _FakePlaywrightPage(routes=[route])
    monkeypatch.setattr(browser, "_resolved_browser_url_error", lambda _url: None)

    browser._guarded_page_goto(page, "https://example.com/start", timeout=10)

    assert page.route_pattern == "**/*"
    assert route.continued is True
    assert route.aborted is False


def test_playwright_guard_blocks_private_redirect_before_follow(monkeypatch):
    route = _FakePlaywrightRoute("http://127.0.0.1/admin")
    page = _FakePlaywrightPage(routes=[route])
    monkeypatch.setattr(browser, "_resolved_browser_url_error", lambda _url: None)

    with pytest.raises(browser._UnsafeBrowserUrl):
        browser._guarded_page_goto(page, "https://example.com/start", timeout=10)

    assert route.aborted is True
    assert route.continued is False


def test_web_open_blocks_playwright_redirect_before_load(monkeypatch):
    route = _FakePlaywrightRoute("http://127.0.0.1/admin")
    page = _FakePlaywrightPage(routes=[route])
    monkeypatch.setattr(browser, "_get_browser", lambda: _FakePlaywrightBrowser(page))
    monkeypatch.setattr(browser, "_resolved_browser_url_error", lambda _url: None)

    result = browser.open_url("https://example.com/start")

    assert "error" in result
    assert "blockiert" in result["error"] or "blocked" in result["error"].lower()
    assert route.aborted is True
    assert page.closed is True
