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
import os
import re
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    from backend.config import SEARCH_PROVIDER as _SEARCH_PROVIDER
except Exception:  # pragma: no cover - defensive
    _SEARCH_PROVIDER = "auto"

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


# ── Such-API-Provider (High-End: strukturierte, ranked Treffer wie Perplexity) ──
# Primaer-Pfad, wenn ein Key konfiguriert ist (keyring 'lexa-ai' oder env). Ohne Key
# faellt search_web auf das key-freie DuckDuckGo-Scraping zurueck — Lexa bleibt voll
# funktionsfaehig, der Key ist reine Qualitaets-/Zuverlaessigkeitsstufe.
_SEARCH_KEY_MAP = {
    "tavily": ("tavily_api_key", "TAVILY_API_KEY"),
    "brave": ("brave_api_key", "BRAVE_API_KEY"),
    "exa": ("exa_api_key", "EXA_API_KEY"),
}


def _get_search_secret(keyring_name: str, env_var: str) -> str:
    val = (os.environ.get(env_var, "") or "").strip()
    if val:
        return val
    try:
        import keyring
        return (keyring.get_password("lexa-ai", keyring_name) or "").strip()
    except Exception:
        return ""


def _search_key_for(provider: str) -> str:
    pair = _SEARCH_KEY_MAP.get(provider)
    return _get_search_secret(*pair) if pair else ""


def _search_tavily(query: str, max_results: int, key: str) -> list[dict]:
    import requests
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": max_results,
              "search_depth": "basic", "include_raw_content": True},
        timeout=_SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    out: list[dict] = []
    for item in (resp.json().get("results") or []):
        url = _safe_url(str(item.get("url", "")))
        if not url:
            continue
        out.append({
            "title": str(item.get("title", ""))[:200],
            "url": url[:500],
            "snippet": str(item.get("content", ""))[:300],
            "content": str(item.get("raw_content") or item.get("content") or "")[:_MAX_TEXT_CHARS],
            "score": item.get("score", 0),
        })
        if len(out) >= max_results:
            break
    return out


def _search_brave(query: str, max_results: int, key: str) -> list[dict]:
    import requests
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        params={"q": query, "count": max_results},
        timeout=_SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    out: list[dict] = []
    for item in ((resp.json().get("web") or {}).get("results") or []):
        url = _safe_url(str(item.get("url", "")))
        if not url:
            continue
        out.append({
            "title": str(item.get("title", ""))[:200],
            "url": url[:500],
            "snippet": str(item.get("description", ""))[:300],
        })
        if len(out) >= max_results:
            break
    return out


def _search_exa(query: str, max_results: int, key: str) -> list[dict]:
    import requests
    resp = requests.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": key},
        json={"query": query, "numResults": max_results, "contents": {"text": True}},
        timeout=_SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    out: list[dict] = []
    for item in (resp.json().get("results") or []):
        url = _safe_url(str(item.get("url", "")))
        if not url:
            continue
        text = str(item.get("text", ""))
        out.append({
            "title": str(item.get("title", ""))[:200],
            "url": url[:500],
            "snippet": text[:300],
            "content": text[:_MAX_TEXT_CHARS],
        })
        if len(out) >= max_results:
            break
    return out


_SEARCH_PROVIDER_ORDER = ("tavily", "brave", "exa")


def _api_search(query: str, max_results: int) -> list[dict]:
    """Versucht hochwertige Such-APIs (nur wenn Key konfiguriert). [] wenn keiner passt."""
    provider = (_SEARCH_PROVIDER or "auto").lower()
    order = [provider] if provider in _SEARCH_PROVIDER_ORDER else (list(_SEARCH_PROVIDER_ORDER) if provider == "auto" else [])
    for name in order:
        key = _search_key_for(name)
        if not key:
            continue
        func = globals().get("_search_" + name)  # via globals() -> respektiert monkeypatch/Tests
        if not func:
            continue
        try:
            res = func(query, max_results, key)
            if res:
                logger.info("web search via %s: %d Treffer", name, len(res))
                return res
        except Exception as exc:
            logger.warning("search provider %s failed: %s", name, exc)
    return []


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


def _simplify_query(query: str) -> str:
    """Entfernt Quotes/Klammern/Operatoren — fuer den Fallback, wenn die (oft ueber-
    quotierte) LLM-Query 0 Treffer liefert (z.B. '"Tauri" "Electron"' -> 'Tauri Electron')."""
    q = re.sub(r"[\"'()\[\]]+", " ", query or "")
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _ddg_search_once(query: str, max_results: int) -> list[dict]:
    qs = urllib.parse.urlencode({"q": query})
    try:
        raw = _http_get(f"https://html.duckduckgo.com/html/?{qs}", _SEARCH_TIMEOUT, _SEARCH_MAX_BYTES)
    except Exception as e:
        logger.warning("web search failed: %s", e)
        return []
    return _parse_ddg_html(raw, max_results)


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo-HTML-Suche. Liefert [{title, url, snippet}] (leer bei Fehler).

    Bei 0 Treffern automatisch ein Fallback mit vereinfachter Query (ohne Quotes/Klammern),
    damit ueber-quotierte LLM-Reformulierungen nicht in 'keine Treffer' enden.
    """
    if not query or not query.strip():
        return []
    q = query.strip()
    max_results = max(1, min(int(max_results or 5), 15))
    # 1) Hochwertige Such-API (Tavily/Brave/Exa), falls ein Key konfiguriert ist.
    api = _api_search(q, max_results)
    if api:
        return api
    # 2) Key-freier Fallback: DuckDuckGo (+ vereinfachte Query bei 0 Treffern).
    results = _ddg_search_once(q, max_results)
    if not results:
        simplified = _simplify_query(query)
        if simplified and simplified != q:
            results = _ddg_search_once(simplified, max_results)
    return results


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
        # API-Provider (Tavily/Exa) liefern Content oft schon mit -> spart den Fetch-Hop.
        if hit.get("content"):
            return hit
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
