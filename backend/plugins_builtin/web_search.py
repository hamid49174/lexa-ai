"""
Lexa AI -- Web Search Plugin
Durchsucht das Web mit DuckDuckGo HTML Lite (kein API Key noetig).
Nutzt den kontrollierten Plugin-HTTP-Helper des PluginManagers.
"""

import html
import re

LEXA_PLUGIN_HTTP_GET = None

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
                "name": "web_search_news",
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


async def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """Fuehrt eine DuckDuckGo HTML Lite Suche durch.

    Returns:
        Liste von {"title": str, "url": str, "snippet": str}
    """
    if not query or not query.strip():
        return []

    max_results = max(1, min(max_results, 15))
    http_get = LEXA_PLUGIN_HTTP_GET
    if http_get is None:
        return [{"title": "Fehler", "url": "", "snippet": "Plugin-HTTP-Helper nicht verfuegbar."}]

    url = "https://html.duckduckgo.com/html/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de,en;q=0.9",
    }

    try:
        response = await http_get(
            url,
            params={"q": query},
            headers=headers,
            timeout=8,
            max_bytes=20000,
        )
        raw_html = response.get("body", "")
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

    # WICHTIG: Titel/URL und Snippet muessen aus DEMSELBEN Ergebnis-Block stammen.
    # DuckDuckGo liefert nicht fuer jeden Treffer ein Snippet (Werbe-/Sonderbloecke),
    # daher wuerde eine rein positionelle Zuordnung (snippets[i] zu links[i]) bei
    # einem fehlenden Snippet alle nachfolgenden Ergebnisse verschieben. Deshalb wird
    # die Seite zuerst in Bloecke entlang der Ergebnis-Links zerlegt und das Snippet
    # nur innerhalb desselben Blocks gesucht.
    link_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    matches = list(link_pattern.finditer(raw_html))

    for i, link_match in enumerate(matches[:max_results]):
        raw_url, raw_title = link_match.group(1), link_match.group(2)
        # Block = Text vom Ende dieses Links bis zum Anfang des naechsten Links.
        block_start = link_match.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_html)
        block = raw_html[block_start:block_end]

        snippet_match = snippet_pattern.search(block)
        title = _clean_html(raw_title).strip()
        snippet = _clean_html(snippet_match.group(1)).strip() if snippet_match else ""

        # DuckDuckGo Redirect-URL aufloesung
        actual_url = raw_url
        if "uddg=" in raw_url:
            match = re.search(r"uddg=([^&]+)", raw_url)
            if match:
                actual_url = _percent_decode(match.group(1))
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
    clean = html.unescape(text)
    # Tags entfernen
    clean = re.sub(r"<[^>]+>", "", clean)
    # HTML-Entities dekodieren
    clean = html.unescape(clean)
    # Mehrfache Leerzeichen reduzieren
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _percent_decode(text: str) -> str:
    def _replace(match):
        try:
            return bytes([int(match.group(1), 16)]).decode("utf-8", errors="replace")
        except ValueError:
            return match.group(0)

    return re.sub(r"%([0-9a-fA-F]{2})", _replace, str(text or "").replace("+", " "))


def _coerce_max_results(value, default: int = 5) -> int:
    """Parst max_results defensiv.

    Der Endpoint /plugins/execute durchlaeuft keine Schema-Validierung, daher
    kann max_results ein nicht-numerischer String (z.B. 'abc') sein. In dem
    Fall wird auf den Default zurueckgefallen statt einen ValueError zu werfen.
    _ddg_search clampt den Wert anschliessend ohnehin auf 1..15.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def execute(tool_name: str, args: dict) -> dict:
    """Plugin-Eintrittspunkt -- wird vom PluginManager aufgerufen."""
    if tool_name == "web_search":
        query = args.get("query", "")
        max_results = _coerce_max_results(args.get("max_results", 5))
        results = await _ddg_search(query, max_results)
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
        results = await _ddg_search(f"{query} news aktuell", 5)
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
