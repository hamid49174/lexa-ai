"""Adaptive ranking helpers for memory search results."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Optional

from backend.memory_core.nlp import normalize_memory_type

_MEMORY_RANKING_WEIGHTS: dict[str, float] = {
    "lexical_score": 0.34,
    "semantic_score": 0.24,
    "recency_score": 0.10,
    "importance_score": 0.14,
    "access_score": 0.06,
    "memory_type_weight": 0.12,
}

_MEMORY_QUERY_TYPE_MARKERS: dict[str, tuple[str, ...]] = {
    "preference": (
        "preference", "preferences", "prefer", "favorite", "favourite",
        "personality", "personalization", "like", "love", "mag", "liebe",
        "lieblings", "praeferenz", "praferenz", "vorliebe", "geschmack",
    ),
    "procedural": (
        "how", "workflow", "tool", "command", "steps", "process", "procedure",
        "use", "wie", "befehl", "ablauf", "schritte", "anleitung", "nutze",
    ),
    "episodic": (
        "meeting", "event", "history", "happened", "timeline", "appointment",
        "termin", "ereignis", "verlauf", "wann", "gestern", "heute", "morgen",
    ),
    "semantic": (
        "fact", "facts", "know", "knowledge", "explain", "what", "fakt",
        "wissen", "erklaere",
    ),
    "system": (
        "system", "config", "configuration", "diagnostic", "diagnostics",
        "lexa", "provider", "konfiguration", "diagnose",
    ),
    "working": (
        "todo", "task", "remember", "note", "scratch", "aufgabe", "merkzettel",
        "notiz", "erinner",
    ),
}


def _score_memory_lexical(memory_content: str, query_keywords: list[str], query: str = "") -> float:
    """Score direct lexical overlap without importance or recency weighting."""
    if not query_keywords:
        return 0.0
    content_lower = str(memory_content or "").lower()
    matches = sum(1 for kw in query_keywords if kw in content_lower)
    if matches == 0:
        return 0.0
    score = matches / len(query_keywords)
    query_lower = str(query or "").strip().lower()
    if query_lower and len(query_lower) >= 8 and query_lower in content_lower:
        score = max(score, 1.0)
    return min(1.0, score)


def _parse_memory_timestamp(value: Any) -> Optional[datetime]:
    """Parse SQLite localtime strings for deterministic ranking."""
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _score_memory_recency(created_at: Any) -> float:
    """Score recent memories higher while keeping old memories discoverable."""
    created = _parse_memory_timestamp(created_at)
    if created is None:
        return 0.0
    age_days = max(0.0, (datetime.now() - created).total_seconds() / 86400.0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.85
    if age_days <= 30:
        return 0.60
    if age_days <= 90:
        return 0.35
    if age_days <= 365:
        return 0.15
    return 0.05


def _score_memory_importance(importance: Any) -> float:
    try:
        value = int(importance)
    except (TypeError, ValueError):
        value = 5
    return max(0.1, min(1.0, value / 10.0))


def _score_memory_access(access_count: Any) -> float:
    try:
        count = max(0, int(access_count or 0))
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return 0.0
    return min(1.0, math.log1p(count) / math.log1p(20))


def _score_memory_query_specificity(query: str, keywords: list[str]) -> float:
    """Estimate whether semantic similarity should dominate freshness signals."""
    text = str(query or "")
    words = re.findall(r"[\w.-]+", text, flags=re.UNICODE)
    if not words:
        return 0.0

    long_keywords = sum(1 for kw in keywords if len(kw) >= 7)
    has_structured_terms = bool(re.search(r"[_./\\:-]|\d", text))
    score = 0.0
    if len(words) >= 6:
        score += 0.30
    elif len(words) >= 4:
        score += 0.18
    if len(keywords) >= 4:
        score += 0.28
    elif len(keywords) >= 2:
        score += 0.16
    score += min(0.22, long_keywords * 0.08)
    if has_structured_terms:
        score += 0.20
    return max(0.0, min(1.0, score))


def _memory_ranking_weights_for_query(
    query: str,
    keywords: list[str],
    *,
    has_semantic_scores: bool,
) -> dict[str, float]:
    if not has_semantic_scores:
        return _MEMORY_RANKING_WEIGHTS

    specificity = _score_memory_query_specificity(query, keywords)
    return {
        "lexical_score": 0.34 - 0.08 * specificity,
        "semantic_score": 0.16 + 0.31 * specificity,
        "recency_score": 0.18 - 0.13 * specificity,
        "importance_score": 0.15 - 0.02 * specificity,
        "access_score": 0.08 - 0.04 * specificity,
        "memory_type_weight": 0.09 - 0.04 * specificity,
    }


def _detect_memory_query_types(query: str, keywords: list[str]) -> set[str]:
    query_lower = str(query or "").lower()
    keyword_text = " ".join(keywords).lower()
    detected: set[str] = set()
    for memory_type, markers in _MEMORY_QUERY_TYPE_MARKERS.items():
        if any(marker in query_lower or marker in keyword_text for marker in markers):
            detected.add(memory_type)
    return detected


def _score_memory_type_weight(memory_type: str, query_types: set[str]) -> float:
    normalized = normalize_memory_type(memory_type) or "semantic"
    if normalized in query_types:
        return 1.0
    if normalized == "system":
        return 0.20 if "system" in query_types else 0.05
    if query_types:
        return 0.35
    return 0.50 if normalized != "system" else 0.10


def rank_memory_results(
    memories: list[dict],
    query: str,
    keywords: list[str],
    *,
    include_ranking: bool = False,
) -> list[dict]:
    """Apply adaptive memory ranking to memory result dictionaries."""
    query_types = _detect_memory_query_types(query, keywords)
    weights = _memory_ranking_weights_for_query(
        query,
        keywords,
        has_semantic_scores=any(float(mem.get("_semantic_score", 0.0) or 0.0) > 0 for mem in memories),
    )
    ranked: list[dict] = []
    for mem in memories:
        lexical_score = _score_memory_lexical(mem.get("content", ""), keywords, query)
        semantic_score = max(0.0, min(1.0, float(mem.get("_semantic_score", 0.0) or 0.0)))
        recency_score = _score_memory_recency(mem.get("created_at"))
        importance_score = _score_memory_importance(mem.get("importance", 5))
        access_score = _score_memory_access(mem.get("access_count", 0))
        memory_type_weight = _score_memory_type_weight(mem.get("memory_type", "semantic"), query_types)
        final_score = (
            weights["lexical_score"] * lexical_score
            + weights["semantic_score"] * semantic_score
            + weights["recency_score"] * recency_score
            + weights["importance_score"] * importance_score
            + weights["access_score"] * access_score
            + weights["memory_type_weight"] * memory_type_weight
        )
        mem["_final_score"] = round(final_score, 6)
        if include_ranking:
            mem["_ranking"] = {
                "lexical_score": round(lexical_score, 6),
                "semantic_score": round(semantic_score, 6),
                "recency_score": round(recency_score, 6),
                "importance_score": round(importance_score, 6),
                "access_score": round(access_score, 6),
                "memory_type_weight": round(memory_type_weight, 6),
                "final_score": round(final_score, 6),
            }
        ranked.append(mem)
    ranked.sort(
        key=lambda m: (
            m.get("_final_score", 0.0),
            _score_memory_importance(m.get("importance", 5)),
            str(m.get("created_at") or ""),
        ),
        reverse=True,
    )
    return ranked
