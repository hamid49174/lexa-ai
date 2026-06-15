"""Echte Web-Recherche fuer 'Antwort mit Quellen pruefen'.

Serverseitig: DuckDuckGo-HTML-Suche + SSRF-sicheres Fetchen beliebiger
Ergebnis-URLs + HTML->Text. Kein API-Key noetig. Wird vom Verify-Endpoint
genutzt, damit Behauptungen gegen ECHTE Quellen geprueft werden (mit URLs)
statt nur aus Modell-Wissen.

Alle Funktionen sind synchron (urllib); der Aufrufer kapselt sie in
asyncio.to_thread, damit der FastAPI-Event-Loop frei bleibt.
"""
from __future__ import annotations

import html as _html
import ipaddress
import logging
import re
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("lexa.web_research")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_SEARCH_TIMEOUT = 8
_FETCH_TIMEOUT = 8
_SEARCH_MAX_BYTES = 90_000
_FETCH_MAX_BYTES = 500_000
_MAX_TEXT_CHARS = 6000  # pro Quelle ans LLM


# ── SSRF-Schutz ──────────────────────────────────────────────────────────────
def _is_safe_public_host(host: str) -> bool:
    """True nur, wenn ALLE aufgeloesten IPs oeffentlich sind.

    Blockt private/loopback/link-local (inkl. 169.254.169.254 Metadata),
    reserved, multicast und unspezifizierte Adressen.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def _safe_url(url: str) -> str | None:
    """Gibt die URL zurueck, wenn http/https + oeffentlicher Host; sonst None."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if not _is_safe_public_host(parsed.hostname):
        logger.warning("blocked non-public/invalid host: %s", parsed.hostname)
        return None
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validiert jede Redirect-Ziel-URL (kein Redirect-SSRF-Bypass)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_get(url: str, timeout: int, max_bytes: int) -> str:
    safe = _safe_url(url)
    if not safe:
        raise ValueError("unsafe or invalid url")
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    req = urllib.request.Request(
        safe,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "de,en;q=0.9",
        },
    )
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read(max_bytes + 1)
    return raw[:max_bytes].decode("utf-8", errors="replace")


# ── HTML-Hilfen ──────────────────────────────────────────────────────────────
def _clean_html(text: str) -> str:
    clean = _html.unescape(str(text or ""))
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = _html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def _percent_decode(text: str) -> str:
    def _replace(match):
        try:
            return bytes([int(match.group(1), 16)]).decode("utf-8", errors="replace")
        except ValueError:
            return match.group(0)
    return re.sub(r"%([0-9a-fA-F]{2})", _replace, str(text or "").replace("+", " "))


# ── Suche (DuckDuckGo HTML) ──────────────────────────────────────────────────
_LINK_RE = re.compile(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)


def _parse_ddg_html(raw_html: str, max_results: int) -> list[dict]:
    results = []
    matches = list(_LINK_RE.finditer(raw_html))
    for i, link_match in enumerate(matches[:max_results]):
        raw_url, raw_title = link_match.group(1), link_match.group(2)
        block_start = link_match.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_html)
        block = raw_html[block_start:block_end]
        snippet_match = _SNIPPET_RE.search(block)
        title = _clean_html(raw_title)
        snippet = _clean_html(snippet_match.group(1)) if snippet_match else ""
        actual_url = raw_url
        if "uddg=" in raw_url:
            m = re.search(r"uddg=([^&]+)", raw_url)
            if m:
                actual_url = _percent_decode(m.group(1))
        elif raw_url.startswith("//"):
            actual_url = "https:" + raw_url
        if title and actual_url.startswith("http"):
            results.append({"title": title[:200], "url": actual_url[:500], "snippet": snippet[:300]})
    return results


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo-HTML-Suche. Liefert [{title, url, snippet}] (leer bei Fehler)."""
    if not query or not query.strip():
        return []
    max_results = max(1, min(int(max_results or 5), 15))
    qs = urllib.parse.urlencode({"q": query.strip()})
    try:
        raw = _http_get(f"https://html.duckduckgo.com/html/?{qs}", _SEARCH_TIMEOUT, _SEARCH_MAX_BYTES)
    except Exception as e:
        logger.warning("web search failed: %s", e)
        return []
    return _parse_ddg_html(raw, max_results)


# ── Fetch (lesbarer Text einer beliebigen URL) ───────────────────────────────
def fetch_readable(url: str) -> str:
    """Holt eine URL (SSRF-sicher) und extrahiert lesbaren Text. '' bei Fehler."""
    try:
        raw = _http_get(url, _FETCH_TIMEOUT, _FETCH_MAX_BYTES)
    except Exception as e:
        logger.info("fetch failed for %s: %s", url, e)
        return ""
    raw = re.sub(r"(?is)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<(nav|footer|header|aside|form|noscript)\b.*?</\1>", " ", raw)
    text = _clean_html(raw)
    return text[:_MAX_TEXT_CHARS]


def _source_domain(url: str) -> str:
    """Registrierbare Host-Domain (ohne fuehrendes www.) fuer Quellen-Deduplizierung."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def gather_sources(query: str, max_sources: int = 4) -> list[dict]:
    """Suche + parallel fetchen. Liefert [{title, url, snippet, content}].

    Dedupliziert nach Domain (eine Quelle je Domain, wie ChatGPT/Gemini) und akzeptiert
    Quellen mit lesbarem Inhalt ODER Such-Snippet (JS-lastige Seiten ohne extrahierbaren
    Text gehen nicht verloren; _build_web_grounding faellt auf den Snippet zurueck).
    """
    hits = search_web(query, max_results=max_sources + 4)
    if not hits:
        return []

    def _one(hit: dict) -> dict:
        return {**hit, "content": fetch_readable(hit["url"])}

    out: list[dict] = []
    seen_domains: set[str] = set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(_one, hits):
            if not (res.get("content") or res.get("snippet")):
                continue
            domain = _source_domain(res.get("url", ""))
            if domain and domain in seen_domains:
                continue
            if domain:
                seen_domains.add(domain)
            out.append(res)
            if len(out) >= max_sources:
                break
    return out
