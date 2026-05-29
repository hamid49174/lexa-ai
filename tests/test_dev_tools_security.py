"""Security regression tests for companion/dev_tools.py."""

import urllib.request

import pytest

from companion import dev_tools


@pytest.mark.parametrize("url", [
    "http://localhost:8000/health",
    "http://app.localhost/status",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://224.0.0.1/",
    "http://[::ffff:127.0.0.1]/",
])
def test_http_request_blocks_internal_hostnames_before_network(monkeypatch, url):
    monkeypatch.setattr(
        dev_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS should not run")),
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("request should not run")),
    )

    result = dev_tools.http_request(url)

    assert "error" in result
    assert (
        "blockiert" in result["error"]
        or "blocked" in result["error"].lower()
        or "SSRF" in result["error"]
    )


def test_http_request_normalizes_bare_public_hosts():
    url, error = dev_tools._normalize_public_http_url("example.com/status")

    assert error is None
    assert url == "https://example.com/status"


def test_http_request_blocks_multicast_dns_result_before_request(monkeypatch):
    monkeypatch.setattr(
        dev_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(dev_tools.socket.AF_INET, dev_tools.socket.SOCK_STREAM, 0, "", ("224.0.0.1", 80))],
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("request should not run")),
    )

    result = dev_tools.http_request("https://example.com/status")

    assert "error" in result
    assert "SSRF" in result["error"]


def test_http_redirect_handler_blocks_internal_redirect_before_follow(monkeypatch):
    monkeypatch.setattr(
        dev_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DNS should not run")),
    )

    handler = dev_tools._SafePublicRedirectHandler()

    with pytest.raises(ValueError, match="interne Adresse"):
        handler.redirect_request(None, None, 302, "Found", {}, "http://localhost:8000/health")


def test_http_redirect_handler_blocks_private_dns_answer_before_follow(monkeypatch):
    monkeypatch.setattr(
        dev_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(dev_tools.socket.AF_INET, dev_tools.socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )

    handler = dev_tools._SafePublicRedirectHandler()

    with pytest.raises(ValueError, match="SSRF"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/private")


def _public_getaddrinfo(*args, **kwargs):
    return [(dev_tools.socket.AF_INET, dev_tools.socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]


class _FakeSocket:
    addresses = []

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect_ex(self, address):
        self.addresses.append(address)
        return 0

    def close(self):
        pass


def test_server_check_accepts_registry_url_param(monkeypatch):
    _FakeSocket.addresses = []
    monkeypatch.setattr(dev_tools.socket, "getaddrinfo", _public_getaddrinfo)
    monkeypatch.setattr(dev_tools.socket, "socket", lambda *args, **kwargs: _FakeSocket())

    result = dev_tools.server_check(url="https://example.com/status")

    assert result["up"] is True
    assert result["host"] == "example.com"
    assert result["port"] == 443
    assert _FakeSocket.addresses == [("example.com", 443)]


def test_multi_server_check_accepts_registry_urls_param(monkeypatch):
    _FakeSocket.addresses = []
    monkeypatch.setattr(dev_tools.socket, "getaddrinfo", _public_getaddrinfo)
    monkeypatch.setattr(dev_tools.socket, "socket", lambda *args, **kwargs: _FakeSocket())

    result = dev_tools.multi_server_check(urls=["https://example.com/status", "http://example.org:8080/health"])

    assert [item["host"] for item in result] == ["example.com", "example.org"]
    assert [item["port"] for item in result] == [443, 8080]
    assert _FakeSocket.addresses == [("example.com", 443), ("example.org", 8080)]


def test_server_check_url_blocks_private_dns_answer_before_socket(monkeypatch):
    monkeypatch.setattr(
        dev_tools.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(dev_tools.socket.AF_INET, dev_tools.socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))],
    )
    monkeypatch.setattr(
        dev_tools.socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("socket should not open")),
    )

    result = dev_tools.server_check(url="https://example.com/status")

    assert "error" in result
    assert "SSRF" in result["error"]


def test_server_check_url_blocks_internal_hosts_before_socket(monkeypatch):
    monkeypatch.setattr(
        dev_tools.socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("socket should not open")),
    )

    result = dev_tools.server_check(url="http://localhost:8000/health")

    assert "error" in result
    assert "blockiert" in result["error"] or "blocked" in result["error"].lower()
