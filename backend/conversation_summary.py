"""Conversation keyword extraction and local summarization.

This module is deliberately deterministic and API-free. It is used when old chat
history needs to be compressed before building the model prompt, so it must stay
fast, bounded, and safe to run on every request.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from typing import Any

from backend.i18n import t


STOP_WORDS = frozenset({
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "eines",
    "und", "oder", "aber", "doch", "wenn", "weil", "dass", "als", "wie",
    "nicht", "kein", "keine", "keinen", "keinem", "keiner",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mir", "mich", "dir", "dich",
    "sich", "uns", "euch", "ihm", "ihn", "ihnen", "mein", "dein", "sein",
    "bitte", "danke", "kannst", "koenntest", "wuerdest", "sollst", "moechtest",
    "mal", "auch", "noch", "schon", "jetzt", "dann", "hier", "dort",
    "ja", "nein", "hey", "lexa", "hallo", "guten", "morgen", "abend",
    "tag", "nacht", "was", "wer", "wo", "wann", "warum", "welche", "welcher",
    "hab", "habe", "hat", "hast", "bin", "bist", "ist", "sind", "war", "waren",
    "kann", "will", "soll", "muss", "darf", "mag", "werde", "wird", "werden",
    "fuer", "mit", "von", "auf", "aus", "bei", "nach", "vor", "ueber", "unter",
    "zum", "zur", "vom", "ins", "ans", "ums",
    "mach", "sag", "zeig", "gib", "lass",
    "sehr", "ganz", "etwas", "nur", "denn", "wohl",
    "unser", "euer", "moechte",
    "im", "am", "um", "zu", "in", "an",
    "hinter", "zwischen", "durch", "gegen", "ohne", "bis", "seit",
    "okay", "alles", "chef",
    "the", "is", "are", "was", "has", "have", "and", "or", "not",
    "this", "that", "for", "with", "from", "you", "your",
})

_ACTION_PATTERN = re.compile(r'"action"\s*:\s*"([a-z_]+)"', re.IGNORECASE)
_FACT_PATTERNS = (
    re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b"),
    re.compile(r"\b(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)\b", re.I),
    re.compile(
        r"\b(januar|februar|maerz|april|mai|juni|juli|august|september|oktober|november|dezember)\b",
        re.I,
    ),
    re.compile(r"\b(deadline|termin|meeting|projekt|aufgabe)\s+[\"']?(\w[\w\s]{2,30})[\"']?\b", re.I),
)
_CREATED_ACTION_LABELS = {
    "note_create": "Notiz",
    "todo_create": "Todo",
    "memory_add": "Erinnerung",
}
_UMLAUT_REPLACEMENTS = {
    "ä": "ae",
    "Ä": "ae",
    "ö": "oe",
    "Ö": "oe",
    "ü": "ue",
    "Ü": "ue",
    "ß": "ss",
    "ẞ": "ss",
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "ß": "ss",
    "Ã¤": "ae",
    "Ã¶": "oe",
    "Ã¼": "ue",
    "ÃŸ": "ss",
}


def _normalize_text(text: Any) -> str:
    value = str(text or "").lower()
    for source, target in _UMLAUT_REPLACEMENTS.items():
        value = value.replace(source, target)
    value = unicodedata.normalize("NFKC", value)
    return value


def _clip_one_line(text: Any, limit: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _dedupe_append(items: list[str], value: str, *, limit: int = 120) -> None:
    clipped = _clip_one_line(value, limit)
    if clipped and clipped not in items:
        items.append(clipped)


def extract_keywords(user_message: str, max_keywords: int = 5) -> list[str]:
    """Extract stable German/English keywords for memory search and summaries."""
    text = _normalize_text(user_message)
    words = re.findall(r"[a-z0-9_+-]{3,}", text)
    counts = Counter(w for w in words if w not in STOP_WORDS)
    if not counts:
        return []

    # Prefer specific terms: frequency first, then length, then original order.
    first_index = {word: words.index(word) for word in counts}
    ranked = sorted(
        counts,
        key=lambda word: (-counts[word], -min(len(word), 16), first_index[word]),
    )
    return ranked[: max(0, max_keywords)]


def _interesting_user_messages(messages: list[dict[str, Any]], max_items: int = 12) -> list[str]:
    user_messages = [
        _clip_one_line(msg.get("content", ""), 80)
        for msg in messages
        if msg.get("role") == "user" and msg.get("content")
    ]
    if len(user_messages) <= max_items:
        return user_messages
    head_count = max(2, max_items // 3)
    tail_count = max_items - head_count
    return user_messages[:head_count] + user_messages[-tail_count:]


def summarize_messages_local(messages: list[dict[str, Any]]) -> str:
    """Summarize older conversation messages with bounded local text analysis."""
    messages = list(messages or [])

    if len(messages) > 20:
        sampled = _interesting_user_messages(messages)
        lines = ["[Bisheriger Gespraechsverlauf]"]
        if sampled:
            topics_str = " | ".join(sampled[:12])
            lines.append(f"- User besprach: {topics_str}")
        else:
            lines.append(f"- {len(messages)} aeltere Nachrichten (keine User-Nachrichten extrahiert)")
        return "\n".join(lines)

    user_topics: list[str] = []
    executed_actions: list[str] = []
    user_facts: list[str] = []
    lexa_created: list[str] = []

    for msg in messages:
        role = str(msg.get("role", ""))
        content = str(msg.get("content", "") or "")
        if not content:
            continue

        if role == "user":
            for keyword in extract_keywords(content, max_keywords=5):
                _dedupe_append(user_topics, keyword, limit=50)

            normalized = _normalize_text(content)
            for pattern in _FACT_PATTERNS:
                for match in pattern.finditer(normalized):
                    fact = match.group(0).strip()
                    if len(fact) > 2:
                        _dedupe_append(user_facts, fact, limit=80)

        elif role == "assistant":
            for action in _ACTION_PATTERN.findall(content):
                _dedupe_append(executed_actions, action, limit=80)

            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(parsed, dict):
                continue

            action_name = str(parsed.get("action", ""))
            params = parsed.get("params", {})
            if not isinstance(params, dict) or action_name not in _CREATED_ACTION_LABELS:
                continue
            item_name = params.get("title") or params.get("content", "")
            if item_name:
                label = _CREATED_ACTION_LABELS[action_name]
                _dedupe_append(lexa_created, f'{label}: "{_clip_one_line(item_name, 40)}"', limit=80)

    lines = ["[Bisheriger Gespraechsverlauf]"]
    if user_topics:
        lines.append(f"- User fragte nach: {', '.join(user_topics[:12])}")
    if executed_actions:
        lines.append(f"- Lexa fuehrte aus: {', '.join(executed_actions[:10])}")
    if lexa_created:
        lines.append(f"- Lexa erstellte: {'; '.join(lexa_created[:6])}")
    if user_facts:
        lines.append(f"- User erwaehnte: {', '.join(user_facts[:8])}")
    if len(lines) == 1:
        lines.append(t("ai.noHistory", count=len(messages)))

    words = "\n".join(lines).split()
    if len(words) > 200:
        return " ".join(words[:200]) + "..."
    return "\n".join(lines)
