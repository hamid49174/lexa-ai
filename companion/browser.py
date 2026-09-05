"""Lexa AI — Browser Automation via Playwright + yt-dlp Fallback
YouTube, Preis-Tracking, Web-Scraping, Screenshots — alles ohne API

yt-dlp wird als robuster Fallback für YouTube-Suchen genutzt,
da Playwright-Selektoren bei YouTube-DOM-Änderungen brechen können.
"""

import json
import logging
import subprocess
import shutil
import webbrowser
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

from backend.config import LEXA_DATA_DIR
from backend.i18n import t

logger = logging.getLogger("lexa.browser")

_BLOCKED_HOSTS: frozenset[str] = frozenset({
    "169.254.169.254",
    "169.254.169.253",
    "metadata.google.internal",
    "metadata.google",
    "100.100.100.200",
    "169.254.0.1",
})
_LOCAL_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
})
_REDIRECT_STATUS_CODES: frozenset[int] = frozenset({301, 302, 303, 307, 308})
_MAX_SAFE_REDIRECTS = 5
_BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class _UnsafeBrowserUrl(ValueError):
    """Raised when a browser helper is redirected to a blocked target."""


def _is_dangerous_ip_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _is_dangerous_ip(hostname: str) -> bool:
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return _is_dangerous_ip_address(addr)


def _validate_url(url: str) -> str | None:
    """Returns error message if URL is unsafe, None if OK."""
    if not url:
        return "URL fehlt."
    if not url.startswith(("http://", "https://")):
        return "Nur http:// und https:// URLs erlaubt."
    # Block dangerous URL schemes that might be embedded after the http prefix
    url_lower = url.lower()
    for scheme in ("javascript:", "data:", "vbscript:", "file://"):
        if scheme in url_lower:
            return f"Unsicheres URL-Schema: {scheme}"
    if len(url) > 2000:
        return "URL zu lang (max 2000 Zeichen)."
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        return "Ungueltige URL."
    try:
        parsed.port
    except ValueError:
        return "Ungueltiger URL-Port."
    if hostname in _BLOCKED_HOSTS:
        return t("security.blockedInternal", host=hostname)
    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(".localhost"):
        return t("security.blockedInternal", host=hostname)
    if _is_dangerous_ip(hostname):
        return t("security.blockedPrivate", host=hostname)
    return None


def _safe_redirect_target(current_url: str, location: str | None) -> tuple[str, str | None]:
    if not location:
        return "", "Weiterleitung ohne Ziel blockiert."
    target = urljoin(current_url, location)
    err = _validate_url(target)
    if err:
        return "", err
    return target, None


def _raise_if_unsafe_browser_url(url: str) -> None:
    err = _validate_url(url)
    if err:
        raise _UnsafeBrowserUrl(err)
    err = _resolved_browser_url_error(url)
    if err:
        raise _UnsafeBrowserUrl(err)


def _resolved_browser_url_error(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return None
    for _, _, _, _, addr in resolved:
        try:
            ip = ipaddress.ip_address(addr[0])
        except ValueError:
            continue
        if _is_dangerous_ip_address(ip):
            return t("security.blockedSsrf", ip=ip)
    return None


def _httpx_get_checked_html(httpx_module, url: str) -> str:
    current_url = url
    with httpx_module.Client(
        timeout=15,
        follow_redirects=False,
        headers={"User-Agent": _BROWSER_USER_AGENT},
    ) as client:
        for _ in range(_MAX_SAFE_REDIRECTS + 1):
            _raise_if_unsafe_browser_url(current_url)
            resp = client.get(current_url)
            if resp.status_code not in _REDIRECT_STATUS_CODES:
                return resp.text
            location = resp.headers.get("location") or resp.headers.get("Location")
            next_url, err = _safe_redirect_target(str(resp.url), location)
            if err:
                raise _UnsafeBrowserUrl(err)
            current_url = next_url
    raise _UnsafeBrowserUrl("Zu viele Weiterleitungen blockiert.")


def _is_playwright_navigation_request(request) -> bool:
    marker = getattr(request, "is_navigation_request", None)
    if callable(marker):
        try:
            return bool(marker())
        except Exception:
            pass
    if marker is not None:
        return bool(marker)
    return getattr(request, "resource_type", "") == "document"


def _playwright_request_error(url: str, is_navigation: bool) -> str | None:
    if url.startswith(("http://", "https://")):
        err = _validate_url(url)
        if err:
            return err
        if is_navigation:
            return _resolved_browser_url_error(url)
        return None
    if is_navigation:
        return _validate_url(url) or "Unsichere Browser-Navigation blockiert."
    return None


def _install_playwright_navigation_guard(page) -> dict[str, str | None]:
    blocked = {"message": None}

    def _guard(route):
        request = getattr(route, "request", None)
        request_url = getattr(request, "url", "")
        is_navigation = _is_playwright_navigation_request(request)
        err = _playwright_request_error(request_url, is_navigation)
        if err:
            if is_navigation:
                blocked["message"] = err
            try:
                route.abort()
            finally:
                logger.warning("Blocked unsafe browser request: %s", request_url)
            return
        route.continue_()

    try:
        page.route("**/*", _guard)
    except Exception as exc:
        raise RuntimeError(f"Browser-Sicherheitsfilter konnte nicht aktiviert werden: {exc}") from exc
    return blocked


def _guarded_page_goto(page, url: str, **kwargs):
    _raise_if_unsafe_browser_url(url)
    blocked = _install_playwright_navigation_guard(page)
    try:
        response = page.goto(url, **kwargs)
    except Exception as exc:
        if blocked["message"]:
            raise _UnsafeBrowserUrl(blocked["message"]) from exc
        raise
    final_url = getattr(page, "url", "") or ""
    if final_url and final_url != "about:blank":
        _raise_if_unsafe_browser_url(final_url)
    return response


SCREENSHOTS_DIR = LEXA_DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Lazy browser instances — one visible (open_url/play_youtube), one headless
# (scrape_text/check_price/website_screenshot/website_to_pdf, no UI needed).
_browser = None            # visible (headless=False)
_headless_browser = None   # headless=True
_playwright = None

# yt-dlp availability cache
_ytdlp_available = None


# ══════════════════════════════════════════════════
#  YT-DLP FALLBACK (robust gegen YouTube DOM-Änderungen)
# ══════════════════════════════════════════════════

def _check_ytdlp() -> bool:
    """Check if yt-dlp is available."""
    global _ytdlp_available
    if _ytdlp_available is None:
        _ytdlp_available = shutil.which("yt-dlp") is not None
        if _ytdlp_available:
            logger.info("yt-dlp gefunden — wird als YouTube-Fallback genutzt")
        else:
            logger.info("yt-dlp nicht installiert — nutze Playwright für YouTube")
    return _ytdlp_available


_MAX_YTDLP_QUERY_LEN = 200


def _clean_ytdlp_query(query: str) -> str | None:
    """Strip control characters and length-cap the query before passing to yt-dlp.

    Returns None if nothing usable remains. shell=False already prevents
    command injection; this guards against control chars and oversized input.
    """
    if not query:
        return None
    cleaned = "".join(ch for ch in query if ch.isprintable()).strip()
    cleaned = cleaned[:_MAX_YTDLP_QUERY_LEN]
    return cleaned or None


def _ytdlp_search(query: str, max_results: int = 5) -> list[dict] | None:
    """Search YouTube via yt-dlp (community-maintained, robust gegen DOM-Änderungen)."""
    if not _check_ytdlp():
        return None

    query = _clean_ytdlp_query(query)
    if not query:
        return None

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                f"ytsearch{max_results}:{query}",
                "--dump-json",
                "--flat-playlist",
                "--no-warnings",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "title": data.get("title", "Unbekannt"),
                    "url": f"https://youtube.com/watch?v={data.get('id', '')}",
                    "channel": data.get("channel", data.get("uploader", "Unbekannt")),
                    "duration": data.get("duration_string", ""),
                    "views": data.get("view_count", 0),
                })
            except json.JSONDecodeError:
                continue

        return videos if videos else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"yt-dlp Suche fehlgeschlagen: {e}")
        return None


def _ytdlp_get_url(query: str) -> dict | None:
    """Get the best video URL for playback via yt-dlp."""
    if not _check_ytdlp():
        return None

    query = _clean_ytdlp_query(query)
    if not query:
        return None

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                f"ytsearch1:{query}",
                "--dump-json",
                "--no-warnings",
                "--quiet",
            ],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0].strip():
            return None
        data = json.loads(lines[0])
        return {
            "title": data.get("title", "Unbekannt"),
            "url": data.get("webpage_url", f"https://youtube.com/watch?v={data.get('id', '')}"),
            "channel": data.get("channel", data.get("uploader", "Unbekannt")),
            "duration": data.get("duration_string", ""),
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"yt-dlp URL-Abruf fehlgeschlagen: {e}")
        return None


# ══════════════════════════════════════════════════
#  PLAYWRIGHT BROWSER
# ══════════════════════════════════════════════════

def _get_browser(headless: bool = False):
    """Lazy-load Playwright browser with auto-detection of common issues.

    headless=False: sichtbares Fenster (open_url/play_youtube — UI gewollt).
    headless=True:  unsichtbar (scrape_text/check_price/website_screenshot/
                    website_to_pdf — reine Datenoperationen, kein Fenster nötig).
    Beide Modi werden getrennt gecacht; der Playwright-Treiber wird geteilt.

    Provides clear, actionable error messages for:
    - Playwright not installed (pip)
    - Browser binaries missing (playwright install)
    - Permission issues, crashes, display issues
    """
    global _browser, _headless_browser
    cached = _headless_browser if headless else _browser
    if cached is not None:
        return cached

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright nicht installiert — Browser-Features deaktiviert")
        raise RuntimeError(
            "Playwright ist nicht installiert.\n"
            "Installation:\n"
            "  1. pip install playwright\n"
            "  2. playwright install chromium"
        )

    def _launch():
        global _playwright
        if _playwright is None:
            _playwright = sync_playwright().start()
        return _playwright.chromium.launch(headless=headless)

    try:
        launched = _launch()
        logger.info("Playwright browser launched (headless=%s)", headless)
    except Exception as e:
        err_str = str(e).lower()
        if "executable doesn't exist" in err_str or "browsertype.launch" in err_str:
            logger.error("Playwright browser binaries not found")
            # Try to auto-install
            launched = None
            try:
                import subprocess as _sp
                logger.info("Attempting automatic Playwright browser install...")
                result = _sp.run(
                    ["playwright", "install", "chromium"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    # Retry launch
                    launched = _launch()
                    logger.info("Playwright browser auto-installed and launched")
            except Exception as install_err:
                logger.error(f"Auto-install failed: {install_err}")

            if launched is None:
                raise RuntimeError(
                    "Playwright-Browser nicht gefunden.\n"
                    "Lösung: playwright install chromium\n"
                    "(Einmalig nötig — lädt ~150MB Chromium-Browser herunter)"
                )
        else:
            logger.error(f"Playwright Browser-Start fehlgeschlagen: {e}")
            raise RuntimeError(
                f"Browser konnte nicht gestartet werden: {e}\n"
                "Versuche: playwright install chromium"
            )

    if headless:
        _headless_browser = launched
    else:
        _browser = launched
    return launched


def open_url(url: str) -> dict:
    """Open URL in the automated browser, with a system-browser fallback."""
    err = _validate_url(url)
    if err:
        return {"error": err}
    try:
        browser = _get_browser()
    except RuntimeError as e:
        logger.info("Playwright unavailable for web_open; falling back to system browser: %s", e)
        opened = webbrowser.open(url)
        if opened:
            return {
                "url": url,
                "status": "opened",
                "fallback": True,
                "message": "Im Standardbrowser geoeffnet.",
                "note": "Automatisierter Browser ist nicht eingerichtet; Standardbrowser genutzt.",
            }
        return {
            "error": (
                f"{e}\n"
                "Fallback im Standardbrowser konnte nicht gestartet werden."
            )
        }
    page = browser.new_page()
    try:
        _guarded_page_goto(page, url, timeout=30000)
        title = page.title()
        return {"url": url, "title": title, "status": "opened"}
    except Exception as e:
        page.close()
        return {"error": f"Seite konnte nicht geladen werden: {e}"}


# ══════════════════════════════════════════════════
#  YOUTUBE (mit yt-dlp Fallback)
# ══════════════════════════════════════════════════

def search_youtube(query: str) -> dict:
    """Search YouTube — uses yt-dlp first, falls back to Playwright."""
    # Strategy 1: yt-dlp (robust, community-maintained)
    ytdlp_results = _ytdlp_search(query)
    if ytdlp_results:
        return {"query": query, "results": ytdlp_results, "source": "yt-dlp"}

    # Strategy 2: Playwright (can break if YouTube changes DOM)
    try:
        browser = _get_browser()
    except RuntimeError as e:
        return {"query": query, "results": [], "error": str(e)}
    page = browser.new_page()
    try:
        from urllib.parse import quote_plus
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        _guarded_page_goto(page, search_url, timeout=30000)
        page.wait_for_selector("ytd-video-renderer", timeout=10000)

        results = page.evaluate("""
            () => {
                const videos = document.querySelectorAll('ytd-video-renderer');
                return Array.from(videos).slice(0, 5).map(v => {
                    const titleEl = v.querySelector('#video-title');
                    const href = titleEl ? titleEl.getAttribute('href') : null;
                    return {
                        title: titleEl?.textContent?.trim(),
                        url: href ? 'https://youtube.com' + href : null,
                        channel: v.querySelector('#channel-name')?.textContent?.trim(),
                    };
                }).filter(r => r.url && r.title);
            }
        """)
        return {"query": query, "results": results, "source": "playwright"}
    except Exception as e:
        logger.warning(f"YouTube Playwright-Suche fehlgeschlagen: {e}")
        return {"query": query, "results": [], "error": str(e)}
    finally:
        try:
            page.close()
        except Exception:
            pass


def play_youtube(query: str) -> dict:
    """Search YouTube and play first result — yt-dlp for search, browser for playback."""
    # Try yt-dlp for reliable URL
    video = _ytdlp_get_url(query)
    if video:
        # Open in browser for playback
        try:
            try:
                browser = _get_browser()
            except RuntimeError:
                return {"status": "url_found", "title": video["title"], "url": video["url"], "note": "Playwright nicht verfügbar", "source": "yt-dlp"}
            page = browser.new_page()
            _guarded_page_goto(page, video["url"], timeout=30000)
            page.wait_for_load_state("domcontentloaded")
            return {
                "status": "playing",
                "title": video["title"],
                "url": video["url"],
                "channel": video.get("channel", ""),
                "source": "yt-dlp+playwright",
            }
        except Exception as e:
            # Even if browser fails, return the URL so user can open manually
            return {
                "status": "url_found",
                "title": video["title"],
                "url": video["url"],
                "note": f"Browser-Wiedergabe fehlgeschlagen: {e}",
                "source": "yt-dlp",
            }

    # Pure Playwright fallback
    try:
        try:
            browser = _get_browser()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}
        page = browser.new_page()
        from urllib.parse import quote_plus
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        _guarded_page_goto(page, search_url, timeout=30000)
        page.wait_for_selector("ytd-video-renderer", timeout=10000)

        first_video = page.query_selector("ytd-video-renderer #video-title")
        if first_video:
            title = first_video.text_content().strip()
            first_video.click()
            page.wait_for_load_state("domcontentloaded")
            return {"status": "playing", "title": title, "url": page.url, "source": "playwright"}
        return {"status": "error", "message": "Kein Video gefunden"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════
#  WEB TOOLS
# ══════════════════════════════════════════════════

def website_screenshot(url: str, filename: str = "") -> str:
    """Take a screenshot of a website."""
    err = _validate_url(url)
    if err:
        return t("error.generic", error=str(err))
    try:
        browser = _get_browser(headless=True)
    except RuntimeError as e:
        return t("error.generic", error=str(e))
    if filename:
        # Strip path separators and dangerous chars
        filename = Path(filename).name
        filename = "".join(c for c in filename if c.isalnum() or c in "._-")[:100]
        if not filename:
            filename = ""  # will be regenerated below
    page = browser.new_page()
    try:
        _guarded_page_goto(page, url, timeout=30000)
        page.wait_for_load_state("networkidle")

        if not filename:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"web_{ts}.png"

        path = str(SCREENSHOTS_DIR / filename)
        page.screenshot(path=path, full_page=True)
        return path
    except Exception as e:
        return t("error.generic", error=str(e))
    finally:
        try:
            page.close()
        except Exception:
            pass


def website_to_pdf(url: str, filename: str = "") -> str:
    """Save website as PDF."""
    err = _validate_url(url)
    if err:
        return t("error.generic", error=str(err))
    try:
        browser = _get_browser(headless=True)
    except RuntimeError as e:
        return t("error.generic", error=str(e))
    if filename:
        # Strip path separators and dangerous chars
        filename = Path(filename).name
        filename = "".join(c for c in filename if c.isalnum() or c in "._-")[:100]
        if not filename:
            filename = ""  # will be regenerated below
    context = browser.new_context()
    page = context.new_page()
    try:
        _guarded_page_goto(page, url, timeout=30000)
        page.wait_for_load_state("networkidle")

        if not filename:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"web_{ts}.pdf"

        path = str(SCREENSHOTS_DIR / filename)
        page.pdf(path=path)
        return path
    except Exception as e:
        return t("error.generic", error=str(e))
    finally:
        try:
            page.close()
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass


def _scrape_lightweight(url: str, max_chars: int = 5000) -> dict | None:
    """Lightweight scraping via trafilatura (no browser needed, ~50ms).

    trafilatura is the gold standard for web content extraction in Python.
    Used by academic researchers, news aggregators, and NLP pipelines.
    Falls back to None if trafilatura is not installed.
    """
    try:
        import trafilatura
    except ImportError:
        return None

    try:
        import httpx
        html = _httpx_get_checked_html(httpx, url)
    except ImportError:
        # Fallback to urllib
        import urllib.request

        class _SafeBrowserRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                target, err = _safe_redirect_target(req.full_url, newurl)
                if err:
                    raise _UnsafeBrowserUrl(err)
                _raise_if_unsafe_browser_url(target)
                return super().redirect_request(req, fp, code, msg, headers, target)

        _raise_if_unsafe_browser_url(url)
        req = urllib.request.Request(url, headers={
            "User-Agent": _BROWSER_USER_AGENT
        })
        opener = urllib.request.build_opener(_SafeBrowserRedirectHandler)
        with opener.open(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

    if not html:
        return None

    # trafilatura extraction with metadata
    result = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,  # Use fallback extractors for better coverage
        favor_recall=True,
        output_format="txt",
    )
    if not result or len(result) < 50:
        return None

    # Get metadata (title, author, date)
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata and metadata.title else ""
    author = metadata.author if metadata and metadata.author else ""
    date = metadata.date if metadata and metadata.date else ""

    text = result[:max_chars]
    return {
        "url": url,
        "title": title,
        "author": author,
        "date": date,
        "text": text,
        "chars": len(text),
        "method": "trafilatura",
    }


# Mozilla Readability.js — injected into Playwright for professional extraction.
# This is the EXACT algorithm Firefox Reader Mode uses.
# CDN URL for the minified Readability.js library.
_READABILITY_JS_CDN = "https://cdn.jsdelivr.net/npm/@mozilla/readability@0.5.0/Readability.min.js"
_readability_js_cache: str | None = None


def _get_readability_js() -> str | None:
    """Fetch and cache Mozilla Readability.js (once per session)."""
    global _readability_js_cache
    if _readability_js_cache is not None:
        return _readability_js_cache
    try:
        import urllib.request
        req = urllib.request.Request(_READABILITY_JS_CDN, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            _readability_js_cache = resp.read().decode("utf-8")
        logger.info("Readability.js loaded from CDN")
        return _readability_js_cache
    except Exception as e:
        logger.debug(f"Could not load Readability.js: {e}")
        return None


def scrape_text(url: str, max_chars: int = 5000, use_browser: bool = False) -> dict:
    """Scrape main text content from a website — 3-strategy extraction.

    Strategy 1: trafilatura (Python-native, no browser, ~50ms, best for articles)
    Strategy 2: Playwright + Mozilla Readability.js (same as Firefox Reader Mode)
    Strategy 3: Playwright + custom DOM scoring (fallback if Readability.js unavailable)

    use_browser=True forces Playwright (for JS-rendered pages like SPAs).
    """
    err = _validate_url(url)
    if err:
        return {"error": err}
    max_chars = max(500, min(50000, max_chars))

    # Strategy 1: trafilatura (lightweight, no browser)
    if not use_browser:
        try:
            result = _scrape_lightweight(url, max_chars)
            if result and result.get("text") and len(result["text"]) >= 100:
                return result
        except _UnsafeBrowserUrl as e:
            return {"error": str(e)}
        except Exception as e:
            logger.debug(f"trafilatura scrape failed: {e}")

    # Strategy 2+3: Playwright (for JS-rendered pages)
    try:
        browser = _get_browser(headless=True)
    except RuntimeError as e:
        return {"error": str(e)}
    page = browser.new_page()
    try:
        _guarded_page_goto(page, url, timeout=30000)
        page.wait_for_load_state("networkidle")

        # Strategy 2: Inject Mozilla Readability.js (same as Firefox Reader Mode)
        readability_js = _get_readability_js()
        if readability_js:
            try:
                page.evaluate(readability_js)
                result = page.evaluate("""
                    (maxChars) => {
                        try {
                            const clone = document.cloneNode(true);
                            const article = new Readability(clone).parse();
                            if (article && article.textContent && article.textContent.length > 100) {
                                return {
                                    title: article.title || '',
                                    author: article.byline || '',
                                    text: article.textContent.substring(0, maxChars),
                                    excerpt: article.excerpt || '',
                                    method: 'readability'
                                };
                            }
                        } catch(e) {}
                        return null;
                    }
                """, max_chars)
                if result and result.get("text"):
                    title = result.get("title") or page.title()
                    page.close()
                    return {
                        "url": url,
                        "title": title,
                        "author": result.get("author", ""),
                        "text": result["text"],
                        "excerpt": result.get("excerpt", ""),
                        "chars": len(result["text"]),
                        "method": "readability",
                    }
            except Exception as e:
                logger.debug(f"Readability.js extraction failed: {e}")

        # Strategy 3: Custom DOM scoring (fallback)
        result = page.evaluate("""
            (maxChars) => {
                const removeSelectors = [
                    'nav', 'header', 'footer', '.nav', '.navbar', '.header', '.footer',
                    '.sidebar', '.side-bar', '.ad', '.ads', '.advertisement', '.banner',
                    '.cookie', '.popup', '.modal', '.overlay', '.social', '.share',
                    '.comments', '#comments', '.comment-section', '.related',
                    'script', 'style', 'noscript', 'iframe', 'svg',
                    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
                    '[aria-hidden="true"]'
                ];
                const clone = document.body.cloneNode(true);
                removeSelectors.forEach(sel => {
                    clone.querySelectorAll(sel).forEach(el => el.remove());
                });

                const candidates = clone.querySelectorAll(
                    'article, main, [role="main"], .content, .post, .entry, ' +
                    '.article, .post-content, .entry-content, .article-content, ' +
                    '.story, .text, #content, #main, #article, .page-content, ' +
                    'section, .container > div, .wrapper > div'
                );

                let bestNode = null;
                let bestScore = 0;

                function scoreNode(node) {
                    const text = node.innerText || '';
                    if (text.length < 100) return 0;
                    const paragraphs = node.querySelectorAll('p');
                    const textLen = text.length;
                    const htmlLen = node.innerHTML.length || 1;
                    const density = textLen / htmlLen;
                    const paraScore = Math.min(paragraphs.length * 10, 100);
                    const sentences = (text.match(/[.!?]+/g) || []).length;
                    const links = node.querySelectorAll('a');
                    const linkText = Array.from(links).reduce((acc, a) => acc + (a.innerText || '').length, 0);
                    const linkPenalty = textLen > 0 ? (linkText / textLen) * 50 : 0;
                    return (density * 100) + paraScore + (sentences * 2) + (textLen / 100) - linkPenalty;
                }

                candidates.forEach(node => {
                    const score = scoreNode(node);
                    if (score > bestScore) {
                        bestScore = score;
                        bestNode = node;
                    }
                });

                if (!bestNode || bestScore < 20) {
                    bestNode = clone;
                }

                let text = (bestNode.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();
                return text.substring(0, maxChars);
            }
        """, max_chars)
        title = page.title()
        page.close()
        return {"url": url, "title": title, "text": result, "chars": len(result), "method": "dom_scoring"}
    except Exception as e:
        try:
            page.close()
        except Exception:
            pass
        return {"url": url, "error": f"Scraping fehlgeschlagen: {e}"}


_PRICE_CHECK_JS = """
(userSelector) => {
    let price = null;
    let source = null;
    let currency = null;

    // 1. User-provided selector
    if (userSelector) {
        const el = document.querySelector(userSelector);
        if (el) {
            price = el.textContent.trim();
            source = 'user_selector';
        }
    }

    // 2. JSON-LD structured data (most reliable, used by Google Shopping)
    if (!price) {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        for (const s of scripts) {
            try {
                let data = JSON.parse(s.textContent);
                if (Array.isArray(data)) data = data[0];
                const offers = data?.offers || data?.['@graph']?.find(g => g.offers)?.offers;
                if (offers) {
                    const offer = Array.isArray(offers) ? offers[0] : offers;
                    if (offer.price) {
                        price = String(offer.price);
                        currency = offer.priceCurrency || null;
                        source = 'json_ld';
                    }
                }
            } catch(e) {}
        }
    }

    // 3. Meta tags (itemprop, og:price)
    if (!price) {
        const metaPrice = document.querySelector('meta[itemprop="price"]') ||
                          document.querySelector('meta[property="product:price:amount"]') ||
                          document.querySelector('meta[property="og:price:amount"]');
        if (metaPrice) {
            price = metaPrice.getAttribute('content');
            source = 'meta_tag';
            const metaCurrency = document.querySelector('meta[itemprop="priceCurrency"]') ||
                                 document.querySelector('meta[property="product:price:currency"]');
            if (metaCurrency) currency = metaCurrency.getAttribute('content');
        }
    }

    // 4. Common CSS selectors (wide coverage across shops)
    if (!price) {
        const selectors = [
            '[itemprop="price"]', '[data-price]',
            '.a-price .a-offscreen', '.a-price-whole',
            '#priceblock_ourprice', '#priceblock_dealprice',
            '[data-testid="price"]', '[data-testid="product-price"]',
            '.price--current', '.price-current', '.current-price',
            '.product-price', '.product-info-price .price',
            '.price-box .price', '.special-price .price',
            '.price-tag', '.price-value', '.sale-price',
            '.offer-price', '.final-price', '.now-price',
            '#price', '.price', '[class*="price" i]',
        ];
        for (const sel of selectors) {
            try {
                const el = document.querySelector(sel);
                if (el) {
                    const text = (el.getAttribute('content') || el.textContent || '').trim();
                    if (text && /\\d/.test(text) && text.length < 50) {
                        price = text;
                        source = 'css_selector';
                        break;
                    }
                }
            } catch(e) {}
        }
    }

    // 5. Regex fallback: scan visible text for price patterns
    if (!price) {
        const bodyText = document.body.innerText || '';
        const patterns = [
            /[\\u20ac$\\u00a3\\u00a5\\u20b9]\\s?\\d{1,6}[.,]\\d{2}/,
            /\\d{1,6}[.,]\\d{2}\\s?[\\u20ac$\\u00a3\\u00a5\\u20b9]/,
            /(EUR|USD|GBP|CHF)\\s?\\d{1,6}[.,]\\d{2}/i,
            /\\d{1,6}[.,]\\d{2}\\s?(EUR|USD|GBP|CHF)/i,
        ];
        for (const pat of patterns) {
            const match = bodyText.match(pat);
            if (match) {
                price = match[0].trim();
                source = 'regex_scan';
                break;
            }
        }
    }

    return { price, currency, source };
}
"""


def check_price(url: str, selector: str = "") -> dict:
    """Check price on a product page — works on any shop worldwide.

    Strategy:
    1. User-provided CSS selector (if given)
    2. Structured data: JSON-LD, meta[itemprop=price], og:price
    3. Common CSS selectors across major shops
    4. Regex-based price pattern detection on full page text
    """
    err = _validate_url(url)
    if err:
        return {"url": url, "error": err}
    try:
        browser = _get_browser(headless=True)
    except RuntimeError as e:
        return {"url": url, "error": str(e)}
    page = browser.new_page()
    try:
        _guarded_page_goto(page, url, timeout=30000)
        page.wait_for_load_state("networkidle")

        result = page.evaluate(_PRICE_CHECK_JS, selector)

        title = page.title()
        page.close()
        return {
            "url": url,
            "title": title,
            "price": result.get("price"),
            "currency": result.get("currency"),
            "detection_method": result.get("source"),
        }
    except Exception as e:
        try:
            page.close()
        except Exception:
            pass
        return {"url": url, "error": f"Preis-Check fehlgeschlagen: {e}"}


def close_browser():
    """Close Playwright browser(s)."""
    global _browser, _headless_browser, _playwright
    if _browser:
        _browser.close()
        _browser = None
    if _headless_browser:
        _headless_browser.close()
        _headless_browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None
    logger.info("Browser closed")
