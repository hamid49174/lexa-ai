"""Quellen-Registry fuer zitierte Synthese (Phase 49 #3).

Sammelt die Quellen aller Sub-Agenten, dedupliziert nach normalisierter URL und vergibt
stabile, globale [n]-IDs — Grundlage fuer Perplexity-artige Zitate ([1], [2] ...) in der
Synthese und fuer die claim-level Verifikation gegen echte Quellen.
"""
from __future__ import annotations

import re

_TRAIL_SLASH = re.compile(r"/+$")


def _norm_url(url: str) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    u = u.split("#", 1)[0]            # Fragment weg
    u = _TRAIL_SLASH.sub("", u)       # trailing slash weg
    return u.lower()


class SourceRegistry:
    """Dedupliziert Quellen und vergibt globale 1-basierte IDs."""

    def __init__(self) -> None:
        self._by_key: dict[str, int] = {}
        self._items: list[dict] = []  # [{id, title, url, snippet}]

    def register(self, raw_sources: list[dict]) -> None:
        for s in (raw_sources or []):
            if not isinstance(s, dict):
                continue
            url = str(s.get("url") or "").strip()
            title = str(s.get("title") or "").strip()
            key = _norm_url(url) or ("title:" + title.lower())
            if not key or key in self._by_key:
                continue
            nid = len(self._items) + 1
            self._by_key[key] = nid
            self._items.append({
                "id": nid,
                "title": (title or url or f"Quelle {nid}")[:160],
                "url": url[:500],
                "snippet": str(s.get("snippet") or "")[:200],
            })

    def as_list(self) -> list[dict]:
        return [dict(it) for it in self._items]

    def count(self) -> int:
        return len(self._items)

    def numbered_block(self) -> str:
        """Quellen als nummerierte Liste fuer den LLM-Prompt ([n] Titel — URL)."""
        lines = []
        for it in self._items:
            line = f"[{it['id']}] {it['title']}"
            if it["url"]:
                line += f" — {it['url']}"
            lines.append(line)
        return "\n".join(lines)
