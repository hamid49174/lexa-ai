"""Short-lived AI response cache for safe, text-only chat answers."""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from difflib import SequenceMatcher
from typing import Any


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    """Parse a positive integer env var, falling back to default and clamping to a lower bound.

    Invalid (non-numeric) values must never break the backend import, and values
    below ``minimum`` would silently disable the cache, so clamp them instead.
    """
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return max(minimum, default)
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return max(minimum, default)
    return max(minimum, parsed)


_CACHE_TTL_SECONDS = _env_int("LEXA_RESPONSE_CACHE_TTL", 300)
_CACHE_MAX_ENTRIES = _env_int("LEXA_RESPONSE_CACHE_MAX", 64)
_SIMILARITY_THRESHOLD = 0.92
_SHORT_QUERY_EXACT_LENGTH = 24
_cache_lock = threading.Lock()
_response_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

_SENSITIVE_RE = re.compile(
    r"(?:\b[A-Za-z]:\\|~[/\\]|/Users/|/home/|\.env\b|api[_-]?key|token|secret|password|passwort|"
    r"bearer\s+[A-Za-z0-9._~+/=-]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    re.IGNORECASE,
)
_ACTION_LIKE_RE = re.compile(
    r"\b(?:loesch|losch|delete|remove|entfern|oeffne|offne|open|starte|start|run|execute|"
    r"schreib|write|speicher|save|file|datei|ordner|folder|shutdown|restart|kill)\b",
    re.IGNORECASE,
)
_FOLLOWUP_RE = re.compile(
    r"^(?:und|auch|dann|noch|nochmal|weiter|mehr|warum|wieso|wie|was|das|die|den|ihn|sie|es|"
    r"dazu|davon|damit|darauf|hier|diese|dieser|dieses)\b",
    re.IGNORECASE,
)


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_cache_query(text: str) -> str:
    folded = _ascii_fold(str(text or "")).lower()
    folded = folded.replace("ß", "ss")
    folded = re.sub(r"[^\w\s.-]", " ", folded, flags=re.UNICODE)
    return re.sub(r"\s+", " ", folded).strip()


def _context_signature(history: list[dict] | None) -> str:
    relevant: list[str] = []
    for msg in (history or [])[-4:]:
        role = str(msg.get("role") or "")[:16]
        content = str(msg.get("content") or "")[:600]
        relevant.append(f"{role}:{content}")
    payload = "\n".join(relevant)
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _is_context_free_query(message: str) -> bool:
    normalized = normalize_cache_query(message)
    if not normalized:
        return False
    if _FOLLOWUP_RE.search(normalized):
        return False
    return len(normalized.split()) >= 4


def _is_cacheable_prompt(message: str) -> bool:
    text = str(message or "")
    normalized = normalize_cache_query(text)
    if len(normalized) < 12 or len(normalized) > 700:
        return False
    if _SENSITIVE_RE.search(text) or _ACTION_LIKE_RE.search(normalized):
        return False
    return True


def _is_cacheable_reply(reply: str) -> bool:
    text = str(reply or "").strip()
    if len(text) < 8 or len(text) > 6000:
        return False
    return not _SENSITIVE_RE.search(text)


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if len(left) < _SHORT_QUERY_EXACT_LENGTH or len(right) < _SHORT_QUERY_EXACT_LENGTH:
        return 1.0 if left == right else 0.0
    return SequenceMatcher(None, left, right).ratio()


def clear_response_cache() -> None:
    with _cache_lock:
        _response_cache.clear()


def get_cached_chat_response(message: str, history: list[dict] | None = None) -> dict[str, Any] | None:
    if not _is_cacheable_prompt(message):
        return None

    normalized = normalize_cache_query(message)
    signature = _context_signature(history)
    context_free = _is_context_free_query(message)
    exact_key = hashlib.sha256(f"{signature}\n{normalized}".encode("utf-8", errors="ignore")).hexdigest()[:24]
    now = time.time()

    with _cache_lock:
        expired = [key for key, entry in _response_cache.items() if now - float(entry.get("ts", 0)) > _CACHE_TTL_SECONDS]
        for key in expired:
            _response_cache.pop(key, None)

        # Fast path: identical prompt+context hits the stored key directly,
        # avoiding the O(n) similarity scan for the common repeated-question case.
        exact_entry = _response_cache.get(exact_key)
        if exact_entry is not None:
            _response_cache.move_to_end(exact_key)
            return {
                "reply": exact_entry["reply"],
                "similarity": 1.0,
                "cached": True,
            }

        best_key = ""
        best_entry: dict[str, Any] | None = None
        best_score = 0.0
        for key, entry in _response_cache.items():
            same_context = entry.get("context_signature") == signature
            context_free_match = context_free and entry.get("context_free")
            if not same_context and not context_free_match:
                continue
            score = _similarity(normalized, str(entry.get("normalized_query") or ""))
            if score > best_score:
                best_key = key
                best_entry = entry
                best_score = score
                if score >= 1.0:
                    break

        if best_entry is None or best_score < _SIMILARITY_THRESHOLD:
            return None
        _response_cache.move_to_end(best_key)
        return {
            "reply": best_entry["reply"],
            "similarity": round(best_score, 4),
            "cached": True,
        }


def remember_chat_response(message: str, history: list[dict] | None, reply: str) -> bool:
    if not _is_cacheable_prompt(message) or not _is_cacheable_reply(reply):
        return False

    normalized = normalize_cache_query(message)
    signature = _context_signature(history)
    key = hashlib.sha256(f"{signature}\n{normalized}".encode("utf-8", errors="ignore")).hexdigest()[:24]
    entry = {
        "ts": time.time(),
        "normalized_query": normalized,
        "context_signature": signature,
        "context_free": _is_context_free_query(message),
        "reply": str(reply),
    }

    with _cache_lock:
        _response_cache[key] = entry
        _response_cache.move_to_end(key)
        while len(_response_cache) > max(1, _CACHE_MAX_ENTRIES):
            _response_cache.popitem(last=False)
    return True
