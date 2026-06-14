"""Deterministic Lexa/OS/Hermes chat answers.

These answers cover the product/system questions that should not depend on an
external model. They make the visible app feel grounded in the local health and
Personal OS state.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from backend.hermes_adapter import (
    get_hermes_gateway_autostart_status,
    get_hermes_gateway_log_summary,
    get_hermes_status,
)


def _normalize(text: str) -> str:
    # Replacements run BEFORE lower(), so Gross-/Kleinbuchstaben und die
    # Mojibake-Sequenzen (UTF-8 als Latin-1 gelesen) treffen tatsaechlich.
    value = str(text or "")
    replacements = {
        "ä": "ae",
        "Ä": "ae",
        "ö": "oe",
        "Ö": "oe",
        "ü": "ue",
        "Ü": "ue",
        "ß": "ss",
        "ẞ": "ss",
        "Ã¤": "ae",
        "Ã¶": "oe",
        "Ã¼": "ue",
        "ÃŸ": "ss",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = value.lower()
    return re.sub(r"\s+", " ", value).strip()


def _has_system_subject(value: str) -> bool:
    return (
        "lexa" in value
        or "hermes" in value
        or "obsidian" in value
        or "personal os" in value
        or "mein os" in value
        or re.search(r"\bos\b", value) is not None
    )


def _has_system_intent(value: str) -> bool:
    patterns = (
        "wie findest",
        "was findest",
        "was haeltst",
        "was haltst",
        "was denkst",
        "dein urteil",
        "ehrlich",
        "schlau",
        "architektur",
        "was bringt",
        "wofuer",
        "sinn",
        "veroeffentlich",
        "veroffentlich",
        "release",
        "produkt",
        "fertig",
        "stand",
        "was kann",
    )
    return any(pattern in value for pattern in patterns) or re.search(r"\bwert\b", value) is not None


def _looks_like_task_or_memory_request(value: str) -> bool:
    return bool(re.search(
        r"\b(?:merke|merk|speicher|aendere|andere|mach|mache|erstelle|fasse|"
        r"vergleiche|stelle|antworte|erklaere|pruefe)\b",
        value,
    ))


def looks_like_lexa_system_question(text: str) -> bool:
    value = _normalize(text)
    if not value or value.startswith("/"):
        return False
    if _looks_like_task_or_memory_request(value):
        return False
    return _has_system_subject(value) and _has_system_intent(value)


async def _to_thread_or_empty(fn, *args) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(fn, *args)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


async def _draft_counts() -> dict[str, Any]:
    try:
        from backend.router_hermes import list_hermes_os_drafts

        payload = await list_hermes_os_drafts("all", 50, True)
        counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
        return counts
    except Exception:
        return {}


def _yes_no(value: bool) -> str:
    return "ok" if value else "Achtung"


def _draft_line(counts: dict[str, Any]) -> str:
    if not counts:
        return "Draft-Queue gerade nicht lesbar"
    return (
        f"{counts.get('pending', 0)} pending, "
        f"{counts.get('approved', 0)} approved, "
        f"{counts.get('rejected', 0)} rejected"
    )


async def build_lexa_system_answer() -> str:
    hermes, autostart, logs, counts = await asyncio.gather(
        _to_thread_or_empty(get_hermes_status),
        _to_thread_or_empty(get_hermes_gateway_autostart_status),
        _to_thread_or_empty(get_hermes_gateway_log_summary, 80),
        _draft_counts(),
    )

    hermes_ready = hermes.get("health_state") == "ready"
    telegram_ready = bool((hermes.get("gateway") or {}).get("configured"))
    obsidian_ready = bool((hermes.get("obsidian_context") or {}).get("ok"))
    autostart_on = bool(autostart.get("enabled"))
    logs_ok = logs.get("status") == "ok" and logs.get("health_state") == "ok"

    log_summary = str(logs.get("summary") or "Log-Zusammenfassung gerade nicht lesbar").rstrip(".")
    draft_summary = _draft_line(counts)

    return "\n".join([
        "Kurzes Urteil: Die Architektur ist stark, aber das Produktgefuehl ist noch nicht stark genug.",
        "",
        f"- OS: {_yes_no(obsidian_ready)}. Gute Basis als agentenlesbares Gedaechtnis: Markdown, Indexe, Current Brief, Draft/Approval.",
        f"- Hermes: {_yes_no(hermes_ready)}. Sinnvoll als Remote-/Admin-Schicht: Status, Logs, Tasks, Kontext und sichere Drafts.",
        "- Schwaeche: In der App sieht man diesen Wert noch zu wenig. Genau deshalb fuehlt es sich gerade kleiner an, als es technisch ist.",
        f"- Live: Telegram {'bereit' if telegram_ready else 'nicht bereit'}, Autostart {'an' if autostart_on else 'aus'}, Drafts {draft_summary}, Logs {_yes_no(logs_ok)}.",
        f"- Logbild: {log_summary}.",
        "",
        "Was das spaeter fuer Lexa bringt: weniger Support-Blindflug, bessere Antworten aus deinem eigenen Kontext und sichere Aenderungen statt wildem KI-Geschreibe.",
        "Naechster sichtbarer Schritt: OS/Hermes als klares Cockpit in Lexa zeigen und solche Antworten direkt mit Kontext, Health und naechster Aktion ausgeben.",
    ])


async def try_lexa_system_answer(user_message: str) -> str | None:
    if not looks_like_lexa_system_question(user_message):
        return None
    return await build_lexa_system_answer()
