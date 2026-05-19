"""
Lexa AI -- Web Search Plugin
Durchsucht das Web mit DuckDuckGo HTML Lite (kein API Key noetig).
Nutzt nur urllib.request aus der Standardbibliothek.
"""

import html
import re
import urllib.parse
import urllib.request

PLUGIN_META = {
    "name": "Web Search",
    "version": "1.0.0",
    "description": "Durchsucht das Web mit DuckDuckGo (kein API Key noetig)",
    "author": "Lexa AI",
    "trusted": True,
    "admin_approved": True,
    "permissions": {
        "network": {
            "allowed_hosts": ["html.duckduckgo.com"],
        },
    },
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Durchsucht das Web mit DuckDuckGo und gibt die Top-Ergebnisse zurueck",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Suchbegriff",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximale Anzahl Ergebnisse (Standard: 5, Max: 15)",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_search_news"  ,
                "description": "Durchsucht DuckDuckGo nach aktuellen News zu einem Thema",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "News-Suchbegriff",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ],
}


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """Fuehrt eine DuckDuckGo HTML Lite Suche durch.

    Returns:
        Liste von {"title": str, "url": str, "snippet": str}
    """
    if not query or not query.strip():
        return []

    max_results = max(1, min(max_results, 15))
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de,en;q=0.9",
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw_html = response.read().decode("utf-8", errors="replace")
    except Exception as e:
        return [{"title": "Fehler", "url": "", "snippet": f"Suche fehlgeschlagen: {e}"}]

    results = _parse_ddg_html(raw_html, max_results)
    return results


def _parse_ddg_html(raw_html: str, max_results: int) -> list[dict]:
    """Parst die DuckDuckGo HTML Lite Ergebnis-Seite."""
    results = []

    # DuckDuckGo HTML Lite Result-Blocks finden
    # Ergebnis-Links: <a rel="nofollow" class="result__a" href="...">Title</a>
    # Snippets: <a class="result__snippet" ...>Snippet text</a>

    # Pattern fuer Ergebnis-Bloecke
    result_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = result_pattern.findall(raw_html)
    snippets = snippet_pattern.findall(raw_html)

    for i, (raw_url, raw_title) in enumerate(links[:max_results]):
        title = _clean_html(raw_title).strip()
        snippet = _clean_html(snippets[i]).strip() if i < len(snippets) else ""

        # DuckDuckGo Redirect-URL aufloesung
        actual_url = raw_url
        if "uddg=" in raw_url:
            match = re.search(r"uddg=([^&]+)", raw_url)
            if match:
                actual_url = urllib.parse.unquote(match.group(1))
        elif raw_url.startswith("//"):
            actual_url = "https:" + raw_url

        if title and actual_url:
            results.append({
                "title": title[:200],
                "url": actual_url[:500],
                "snippet": snippet[:300],
            })

    return results


def _clean_html(text: str) -> str:
    """Entfernt HTML-Tags und dekodiert HTML-Entities."""
    # Tags entfernen
    clean = re.sub(r"<[^>]+>", "", text)
    # HTML-Entities dekodieren
    clean = html.unescape(clean)
    # Mehrfache Leerzeichen reduzieren
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


async def execute(tool_name: str, args: dict) -> dict:
    """Plugin-Eintrittspunkt -- wird vom PluginManager aufgerufen."""
    if tool_name == "web_search":
        query = args.get("query", "")
        max_results = int(args.get("max_results", 5))
        results = _ddg_search(query, max_results)
        if not results:
            return {"result": "Keine Ergebnisse gefunden.", "results": []}
        # Formatierte Ausgabe
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. **{r['title']}**\n   {r['url']}\n   {r['snippet']}")
        return {
            "result": "\n\n".join(formatted),
            "results": results,
            "count": len(results),
        }

    elif tool_name == "web_search_news":
        query = args.get("query", "")
        # News-Suche = normaler Query + "news" Keyword
        results = _ddg_search(f"{query} news aktuell", 5)
        if not results:
            return {"result": "Keine News gefunden.", "results": []}
        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. **{r['title']}**\n   {r['url']}\n   {r['snippet']}")
        return {
            "result": "\n\n".join(formatted),
            "results": results,
            "count": len(results),
        }

    return {"result": f"Unbekanntes Tool: {tool_name}", "error": True}
