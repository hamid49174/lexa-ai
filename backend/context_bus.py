"""Small shared context bus between chat and Personal OS surfaces."""
from __future__ import annotations

import re
import threading
import time
from typing import Any

_context_lock = threading.RLock()
_shared_context: dict[str, Any] = {
    "updatedAt": 0.0,
    "activeDomain": "",
    "recentIntents": [],
    "entities": {},
    "topic": "",
    "lastUserMessage": "",
    "source": "",
}

_TOPIC_BLOCKLIST = re.compile(
    r"\b(?:loesch|losch|delete|entfern|oeffne|offne|starte|start|run|execute|"
    r"passwort|password|secret|token|api[_-]?key)\b",
    re.IGNORECASE,
)
_FOLLOWUP_PREFIX = re.compile(r"^(?:und|auch|dann|noch|weiter|mehr|das|die|den|dazu|davon|damit)\b", re.IGNORECASE)


def _clip(text: Any, limit: int = 240) -> str:
    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    return value[:limit].rstrip()


def _safe_topic_from_message(message: str) -> str:
    text = _clip(message)
    if len(text) < 8:
        return ""
    normalized = text.lower()
    if _TOPIC_BLOCKLIST.search(normalized) or _FOLLOWUP_PREFIX.search(normalized):
        return ""
    return text


def publish_chat_context(
    user_message: str,
    *,
    intent_context: Any = None,
    source: str = "chat",
) -> dict[str, Any]:
    """Publish a compact chat-derived context snapshot for read-only consumers."""
    recent_intents = list(getattr(intent_context, "recent_intents", []) or [])
    active_domain = str(getattr(intent_context, "active_domain", "") or "")
    entities = dict(getattr(intent_context, "entities", {}) or {})
    topic = _safe_topic_from_message(user_message)

    with _context_lock:
        if topic:
            _shared_context["topic"] = topic
        _shared_context.update({
            "updatedAt": time.time(),
            "activeDomain": active_domain,
            "recentIntents": recent_intents[-6:],
            "entities": {str(k): _clip(v, 300) for k, v in entities.items()},
            "lastUserMessage": _clip(user_message),
            "source": source,
        })
        return get_shared_context_snapshot()


def get_shared_context_snapshot(max_age_seconds: int = 1800) -> dict[str, Any]:
    with _context_lock:
        snapshot = dict(_shared_context)
        snapshot["recentIntents"] = list(snapshot.get("recentIntents") or [])
        snapshot["entities"] = dict(snapshot.get("entities") or {})

    age = max(0.0, time.time() - float(snapshot.get("updatedAt") or 0.0))
    if not snapshot.get("updatedAt") or age > max_age_seconds:
        snapshot["fresh"] = False
        snapshot["ageSeconds"] = int(age)
        return snapshot
    snapshot["fresh"] = True
    snapshot["ageSeconds"] = int(age)
    return snapshot


def suggest_personal_os_topic(fallback: str = "") -> str:
    snapshot = get_shared_context_snapshot()
    if snapshot.get("fresh") and snapshot.get("topic"):
        return str(snapshot["topic"])
    return _clip(fallback)


def clear_shared_context() -> None:
    with _context_lock:
        _shared_context.clear()
        _shared_context.update({
            "updatedAt": 0.0,
            "activeDomain": "",
            "recentIntents": [],
            "entities": {},
            "topic": "",
            "lastUserMessage": "",
            "source": "",
        })
