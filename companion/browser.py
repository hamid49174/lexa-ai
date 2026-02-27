"""Lexa AI — Browser Automation via Playwright
YouTube, Preis-Tracking, Web-Scraping, Screenshots — alles ohne API
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("lexa.browser")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Lazy browser instance
_browser = None
_playwright = None


def _get_browser():
    """Lazy-load Playwright browser."""
    global _browser, _playwright
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=False)
        logger.info("Playwright browser launched")
    return _browser


def open_url(url: str) -> dict:
    """Open URL in Playwright browser."""
    browser = _get_browser()
    page = browser.new_page()
    page.goto(url, timeout=30000)
    title = page.title()
    return {"url": url, "title": title, "status": "opened"}


def search_youtube(query: str) -> dict:
    """Search YouTube and return results."""
    browser = _get_browser()
    page = browser.new_page()
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    page.goto(search_url, timeout=30000)
    page.wait_for_selector("ytd-video-renderer", timeout=10000)

    results = page.evaluate("""
        () => {
            const videos = document.querySelectorAll('ytd-video-renderer');
            return Array.from(videos).slice(0, 5).map(v => ({
                title: v.querySelector('#video-title')?.textContent?.trim(),
                url: 'https://youtube.com' + v.querySelector('#video-title')?.getAttribute('href'),
                channel: v.querySelector('#channel-name')?.textContent?.trim(),
            }));
        }
    """)
    page.close()
    return {"query": query, "results": results}


def play_youtube(query: str) -> dict:
    """Search YouTube and play first result."""
    browser = _get_browser()
    page = browser.new_page()
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    page.goto(search_url, timeout=30000)
    page.wait_for_selector("ytd-video-renderer", timeout=10000)

    # Click first video
    first_video = page.query_selector("ytd-video-renderer #video-title")
    if first_video:
        title = first_video.text_content().strip()
        first_video.click()
        page.wait_for_load_state("domcontentloaded")
        return {"status": "playing", "title": title, "url": page.url}
    return {"status": "error", "message": "Kein Video gefunden"}


def website_screenshot(url: str, filename: str = "") -> str:
    """Take a screenshot of a website."""
    browser = _get_browser()
    page = browser.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")

    if not filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"web_{ts}.png"

    path = str(SCREENSHOTS_DIR / filename)
    page.screenshot(path=path, full_page=True)
    page.close()
    return path


def website_to_pdf(url: str, filename: str = "") -> str:
    """Save website as PDF."""
    browser = _get_browser()
    # PDF requires headless context
    context = browser.new_context()
    page = context.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")

    if not filename:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"web_{ts}.pdf"

    path = str(SCREENSHOTS_DIR / filename)
    page.pdf(path=path)
    page.close()
    context.close()
    return path


def scrape_text(url: str) -> dict:
    """Scrape text content from a website."""
    browser = _get_browser()
    page = browser.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")

    text = page.evaluate("""
        () => {
            const el = document.querySelector('article') || document.querySelector('main') || document.body;
            return el.innerText.substring(0, 5000);
        }
    """)
    title = page.title()
    page.close()
    return {"url": url, "title": title, "text": text}


def check_price(url: str, selector: str = "") -> dict:
    """Check price on a product page (Amazon, etc.)."""
    browser = _get_browser()
    page = browser.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")

    # Try common price selectors
    price_selectors = [
        selector,
        ".a-price-whole",  # Amazon
        "[data-testid='price']",
        ".price",
        ".product-price",
        "[itemprop='price']",
    ]

    price = None
    for sel in price_selectors:
        if not sel:
            continue
        el = page.query_selector(sel)
        if el:
            price = el.text_content().strip()
            break

    title = page.title()
    page.close()
    return {"url": url, "title": title, "price": price}


def close_browser():
    """Close Playwright browser."""
    global _browser, _playwright
    if _browser:
        _browser.close()
        _browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None
    logger.info("Browser closed")
