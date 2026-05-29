"""Text processing and memory taxonomy helpers for backend.memory."""

from __future__ import annotations

import re

MEMORY_TYPES: tuple[str, ...] = (
    "working",
    "episodic",
    "semantic",
    "procedural",
    "preference",
    "system",
)

_VALID_MEMORY_TYPES: frozenset[str] = frozenset(MEMORY_TYPES)
_MEMORY_TYPE_CATEGORY_MAP: dict[str, str] = {
    "preference": "preference",
    "preferences": "preference",
    "explicit": "working",
    "task": "working",
    "todo": "working",
    "reminder": "working",
    "working": "working",
    "scratch": "working",
    "session": "working",
    "event": "episodic",
    "meeting": "episodic",
    "appointment": "episodic",
    "calendar": "episodic",
    "routine": "procedural",
    "procedure": "procedural",
    "workflow": "procedural",
    "howto": "procedural",
    "command": "procedural",
    "system": "system",
    "config": "system",
    "diagnostic": "system",
    "fact": "semantic",
    "identity": "semantic",
    "person": "semantic",
}
_MEMORY_SYSTEM_PREFIXES: tuple[str, ...] = (
    "system:",
    "lexa:",
    "config:",
    "configuration:",
    "diagnostic:",
)
_MEMORY_WORKING_PREFIXES: tuple[str, ...] = (
    "merkzettel:",
    "todo:",
    "aufgabe:",
    "notiz:",
    "scratch:",
)
_MEMORY_EPISODIC_MARKERS: tuple[str, ...] = (
    "termin:",
    "meeting:",
    "event:",
    "gestern",
    "heute",
    "morgen",
)
_MEMORY_PROCEDURAL_MARKERS: tuple[str, ...] = (
    "der befehl ",
    "befehl ",
    "command ",
    "workflow:",
    "routine:",
    "how to ",
    "wie man ",
    "schritt ",
)
_MEMORY_PREFERENCE_MARKERS: tuple[str, ...] = (
    "praeferenz:",
    "praferenz:",
    "lieblings",
    "ich mag ",
    "ich liebe ",
    "interesse",
    "hobby",
)

_GERMAN_STOP_WORDS: frozenset[str] = frozenset({
    "der", "die", "das", "ein", "eine", "den", "dem", "des",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mir", "mich",
    "dir", "dich", "sich", "mein", "dein", "sein", "unser", "euer",
    "ist", "sind", "war", "hat", "haben", "wird", "werden",
    "kannst", "koenntest", "wuerdest", "soll", "kann", "moechte",
    "will", "lass", "mach",
    "und", "oder", "nicht", "kein", "keine", "bitte", "mal",
    "auch", "noch", "ja", "nein", "doch", "nur", "schon", "sehr",
    "hey", "lexa", "hallo", "guten", "morgen", "tag", "abend",
    "was", "wie", "wo", "wann", "warum", "wer", "welche", "welcher", "welches",
    "im", "am", "um", "zu", "von", "mit", "fuer", "auf", "in", "an",
    "bei", "nach", "ueber", "unter", "vor", "hinter", "zwischen",
    "durch", "gegen", "ohne", "bis", "seit", "waehrend",
})
_ENGLISH_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "not", "no", "yes", "to", "of", "for",
    "with", "without", "in", "on", "at", "by", "from", "about", "into",
    "over", "under", "between", "through", "since", "during", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "should", "would", "will", "just", "please", "my",
    "your", "his", "her", "their", "our", "me", "you", "we", "they", "it",
    "this", "that", "these", "those", "what", "when", "where", "why", "how",
})
_MEMORY_STOP_WORDS: frozenset[str] = _GERMAN_STOP_WORDS | _ENGLISH_STOP_WORDS


def escape_fts5_query(terms: list[str]) -> str:
    """Escape search terms for safe FTS5 MATCH usage."""
    escaped = []
    for term in terms:
        safe = term.replace('"', "")
        if safe:
            escaped.append(f'"{safe}"')
    return " OR ".join(escaped) if escaped else ""


def extract_search_terms(query: str) -> list[str]:
    """Extract meaningful search keywords from a German/English query."""
    words = str(query or "").lower().split()
    keywords = []
    for word in words:
        term = word.strip(".,;:!?\"'()[]{}/-")
        if len(term) < 3:
            continue
        if term in _MEMORY_STOP_WORDS:
            continue
        if term not in keywords:
            keywords.append(term)
    keywords.sort(key=len, reverse=True)
    return keywords[:5]


def score_memory_relevance(memory_content: str, query_keywords: list[str], importance: int = 5) -> float:
    """Score keyword relevance plus importance for legacy callers."""
    if not query_keywords:
        return 0.0
    content_lower = str(memory_content or "").lower()
    matches = sum(1 for kw in query_keywords if kw in content_lower)
    if matches == 0:
        return 0.0
    keyword_ratio = matches / len(query_keywords)
    try:
        importance_value = int(importance or 5)
    except (TypeError, ValueError):
        importance_value = 5
    importance_factor = max(0.1, importance_value / 10.0)
    return min(1.0, 0.7 * keyword_ratio + 0.3 * importance_factor)


def normalize_for_dedup(content: str) -> str:
    """Normalize content string for deduplication comparison."""
    normalized = str(content or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:120]


def similarity_ratio(a: str, b: str) -> float:
    """Compute a lightweight similarity ratio between two normalized strings."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len(shorter) / len(longer)

    words_a = set(a.split())
    words_b = set(b.split())
    if words_a and words_b:
        overlap = len(words_a & words_b)
        total = len(words_a) + len(words_b)
        if total > 0:
            return (2 * overlap) / total

    common = 0
    for ca, cb in zip(shorter, longer):
        if ca == cb:
            common += 1
        else:
            break
    return common / len(longer) if longer else 0.0


def normalize_memory_type(memory_type: str | None) -> str | None:
    """Return a valid canonical memory type, or None for unknown input."""
    value = str(memory_type or "").strip().lower()
    return value if value in _VALID_MEMORY_TYPES else None


def classify_memory_type(content: str, category: str = "fact", source: str = "user") -> str:
    """Classify a memory into Lexa's explicit memory type taxonomy."""
    source_key = str(source or "").strip().lower()
    category_key = str(category or "").strip().lower()
    category_type = _MEMORY_TYPE_CATEGORY_MAP.get(category_key)
    text = str(content or "").strip().lower()

    if source_key == "system":
        return "system"
    if category_type and category_type != "semantic":
        return category_type
    if any(text.startswith(prefix) for prefix in _MEMORY_SYSTEM_PREFIXES):
        return "system"
    if any(text.startswith(prefix) for prefix in _MEMORY_WORKING_PREFIXES):
        return "working"
    if any(marker in text for marker in _MEMORY_PREFERENCE_MARKERS):
        return "preference"
    if any(marker in text for marker in _MEMORY_PROCEDURAL_MARKERS):
        return "procedural"
    if (
        any(marker in text for marker in _MEMORY_EPISODIC_MARKERS)
        or re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text)
    ):
        return "episodic"
    if category_type:
        return category_type
    return "semantic"
