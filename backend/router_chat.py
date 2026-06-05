"""Lexa AI — Chat Router
Chat endpoints: /chat, /chat/file, /chat/stream, /chat/confirm
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import re
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent_protocol import redacted_summary
from backend.config import (
    MAX_HISTORY,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_FILE_SIZE,
    MAX_FILE_SIZE_MB,
    MAX_TEXT_CHARS,
    TEXT_EXTENSIONS,
    BLOCKED_EXTENSIONS,
)
from backend.shared import (
    conversation_history,
    _history_lock,
    set_pending_confirmation,
    get_pending_confirmation,
    clear_pending_confirmation,
)
from backend.ai_engine import chat, chat_stream
from backend.action_parser import process_ai_response, process_chat_result, update_history
from backend.context_bus import publish_chat_context
from backend.i18n import t
from backend.intent_engine import build_conversation_intent_context, try_local_intent
from backend.lexa_system_answer import try_lexa_system_answer
from backend.lexa_voice import lexa_user_error
from backend.response_cache import get_cached_chat_response, remember_chat_response
from backend.vision_uploads import (
    invalid_image_upload_error,
    normalized_upload_content_type,
    supported_image_signature,
)
from backend.security import (
    sanitize_input,
    check_rate_limit,
    get_rate_limit_info,
    audit_log,
)

# Words that indicate the user is confirming a pending action
_CONFIRMATION_WORDS = frozenset({
    "ja", "yes", "bestätige", "bestätigen", "bestätige es", "confirm",
    "mach es", "mach das", "tu es", "ok", "okay", "klar", "sicher",
    "go", "do it", "los", "ausführen", "machen", "jap", "jep", "yep",
    "jawohl", "genau", "stimmt", "richtig", "bitte", "gerne",
})
_PENDING_CANCEL_WORDS = frozenset({
    "nein", "no", "nee", "nope", "abbrechen", "abbruch", "cancel",
    "stop", "stopp", "verwerfen", "nicht ausfuehren",
})
_LOCAL_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc)/[^\s\"'<>|]+)"
)
_GENERIC_UPLOAD_MIME_TYPES = frozenset({"application/octet-stream", "binary/octet-stream"})


_CONFIRMATION_WORDS = frozenset(_CONFIRMATION_WORDS | {
    "bestatige", "bestaetige", "bestatigen", "bestaetigen", "bestatige es", "bestaetige es",
    "ausfuhren", "ausfuehren",
})
_PENDING_CANCEL_WORDS = frozenset(_PENDING_CANCEL_WORDS | {"nicht ausfuhren", "nicht ausfuehren"})


def _normalize_pending_confirmation_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("ß", "ss")
    normalized = re.sub(r"\s+", " ", normalized).strip().rstrip("!.?")
    return normalized.strip()


def _is_confirmation_message(text: str) -> bool:
    """Check if the user message is a short confirmation of a pending action."""
    normalized = _normalize_pending_confirmation_text(text)
    # Only treat as confirmation if it's short (1-4 words) and matches patterns
    if len(normalized.split()) > 4:
        return False
    return normalized in _CONFIRMATION_WORDS


def _is_pending_cancel_message(text: str) -> bool:
    normalized = _normalize_pending_confirmation_text(text)
    if len(normalized.split()) > 4:
        return False
    return normalized in _PENDING_CANCEL_WORDS


def _pending_confirmation_wait_reply(pending: dict) -> str:
    action_name = str(pending.get("action") or "Aktion")
    return (
        f"Freigabe offen fuer {action_name}. Ich habe nichts ausgefuehrt. "
        "Antworte kurz mit 'Ja' zum Ausfuehren oder 'Abbrechen' zum Verwerfen."
    )


def _normalize_hermes_worker_text(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .strip()
    )


def _ascii_fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return folded.replace("ß", "ss")


def _has_inline_confirmation(text: str) -> bool:
    folded = _ascii_fold(text)
    return any(term in folded for term in (
        "ich bestatige",
        "ich bestaetige",
        "bestatige es",
        "bestaetige es",
        "freigabe",
        "confirm",
    ))


def _is_hermes_worker_request(text: str) -> bool:
    normalized = _normalize_hermes_worker_text(text)
    return bool(
        re.match(r"^/hermes\s+", normalized)
        or re.match(r"^hermes\b", normalized)
        or re.match(r"^lexa\s+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes\b", normalized)
    )


def _is_hermes_desktop_control_request(text: str) -> bool:
    normalized = _normalize_hermes_worker_text(text)
    return bool(re.match(
        r"^(?:klick(?:e|en)?|kilck(?:e|en)?|klcik(?:e|en)?|klcick(?:e|en)?|click|drueck(?:e|en)?|druck(?:e|en)?|"
        r"tippe|tipp|schreib(?:e)?|scroll(?:e)?|bewege|move)\b",
        normalized,
    ))


def _short_action_label(value: object, fallback: str = "Position", limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _client_safe_chat_error(value: object, *, max_chars: int = 220) -> str:
    """Return a compact client-facing error without local paths or secrets."""
    text = redacted_summary(str(value or ""), max_chars=max_chars)
    text = _LOCAL_PATH_RE.sub("[local-path-redacted]", text)
    return text or "Details wurden lokal protokolliert."


def _audit_message_details(message: str) -> str:
    text = str(message or "")
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"messageChars={len(text)} messageHash={digest}"


def _audit_file_details(filename: str) -> str:
    text = str(filename or "")
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    suffix = Path(text).suffix.lower()[:20] or "none"
    return f"fileChars={len(text)} fileHash={digest} ext={suffix}"


def _format_confirmed_action_reply(action_name: str, result: dict) -> str:
    if result.get("success"):
        data = result.get("data")
        if isinstance(data, dict):
            if action_name == "hermes_desktop_commit":
                summary = data.get("summary")
                if summary:
                    verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
                    if verification.get("checked") and verification.get("summary"):
                        suffix = " Verifikation fehlgeschlagen." if _hermes_verification_failed(result) else ""
                        return f"{summary} Danach geprueft: {verification.get('summary')}{suffix}"
                    return str(summary)
            if action_name in {"desktop_click", "desktop_click_text", "ui_click"}:
                target = _short_action_label(data.get("matched_text") or data.get("target"))
                x = data.get("x", "?")
                y = data.get("y", "?")
                return f"Ausgefuehrt: Ich habe '{target}' bei X={x}, Y={y} geklickt."
            summary = data.get("summary") or data.get("message")
            if summary:
                return str(summary)
        if isinstance(data, str) and data.strip():
            return data
        return f"Ausgefuehrt: {action_name}."
    error = _client_safe_chat_error(result.get("error") or "unbekannter Fehler")
    return f"Ich konnte {action_name} nicht ausfuehren: {error}"


def _hermes_verification_failed(result: dict) -> bool:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
    if verification.get("passed") is False:
        return True
    return str(verification.get("status") or "").strip().lower() == "failed"


async def _execute_pending_confirmation(pending: dict, source: str) -> str:
    action_name = str(pending.get("action") or "")
    action = {"action": action_name, "params": pending.get("params") or {}}
    from backend.action_executor import execute_action

    result = await asyncio.to_thread(execute_action, action, source=source, confirmed=True)
    reply = _format_confirmed_action_reply(action_name, result)
    if result.get("success"):
        if action_name == "hermes_desktop_commit" and _hermes_verification_failed(result):
            return f"{reply}\nWeitere Desktop-Schritte gestoppt: Die letzte Aktion hat die Pruefung nicht bestanden."
        reply = await _continue_hermes_desktop_queue(pending, reply, source)
    elif action_name == "hermes_desktop_commit":
        set_pending_confirmation(pending)
        reply = f"{reply}\nFreigabe bleibt offen: Du kannst nach dem Korrigieren erneut mit 'Ja' fortsetzen."
    return reply


async def _continue_hermes_desktop_queue(pending: dict, reply: str, source: str) -> str:
    if str(pending.get("action") or "") != "hermes_desktop_commit":
        return reply
    queue = pending.get("queue") if isinstance(pending.get("queue"), dict) else {}
    if queue.get("type") != "hermes_desktop_instructions":
        return reply
    instructions = [
        str(item).strip()
        for item in (queue.get("instructions") or [])
        if str(item or "").strip()
    ]
    if not instructions:
        return reply
    try:
        from companion import hermes_desktop

        queued_message = "\n".join(instructions)
        initial_context = queue.get("context") if isinstance(queue.get("context"), dict) else None
        data = await asyncio.to_thread(
            hermes_desktop.hermes_desktop_task,
            queued_message,
            initial_context=initial_context,
        )
    except Exception as exc:
        logger.warning("Hermes queue continuation failed from %s: %s", source, exc)
        return f"{reply}\nNaechster Hermes-Schritt konnte nicht vorbereitet werden: {_client_safe_chat_error(exc)}"

    summary = str(data.get("summary") or "").strip()
    if not summary:
        return reply
    if data.get("needs_confirmation"):
        return f"{reply}\nNaechste Freigabe vorbereitet: {summary}"
    return f"{reply}\nNaechster Hermes-Schritt erledigt: {summary}"


async def _maybe_execute_inline_confirmation(message: str, reply: str, source: str) -> str:
    if not _has_inline_confirmation(message):
        return reply
    pending = get_pending_confirmation()
    if not pending:
        return reply
    action_name = pending.get("action", "")
    logger.info("Inline confirmation detected for pending action: %s", action_name)
    audit_log(source, "inline_confirm", f"ACTION={action_name}")
    clear_pending_confirmation()
    return await _execute_pending_confirmation(pending, source)


async def _collect_hermes_worker_reply(user_message: str, history_snapshot: list[dict]) -> tuple[str, list[dict], dict]:
    from backend.agent_loop import run_agent

    steps: list[dict] = []
    summary = ""
    run_data: dict = {}
    async for event in run_agent(user_message, history_snapshot, worker="hermes"):
        etype = event.get("type", "")
        if etype in {"step_done", "step_blocked"}:
            steps.append(event.get("step", {}))
        elif etype == "thinking" and event.get("message"):
            summary = event.get("message", summary)
        elif etype == "done":
            run_data = event.get("run", {}) or {}
            summary = run_data.get("summary", summary)
        elif etype == "error":
            summary = _client_safe_chat_error(event.get("message", "Hermes-Worker Fehler"))
    return summary or "Hermes hat den Auftrag verarbeitet.", steps, run_data

logger = logging.getLogger("lexa.chat")

router = APIRouter(tags=["chat"])


# ══════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None
    requires_confirmation: bool = False


_WEATHER_CLOTHING_FOLLOWUP_RE = re.compile(
    r"\b(?:anzieh\w*|zieh\w*|tragen|kleidung|outfit|jacke|mantel|pullover|hoodie|schuhe)\b",
    re.IGNORECASE,
)
_WEATHER_FOLLOWUP_REFERENCE_RE = re.compile(
    r"\b(?:dazu|wetter|temperatur|draussen|draußen|heute|jetzt|kann|soll|was)\b",
    re.IGNORECASE,
)
_WEATHER_SUMMARY_RE = re.compile(
    r"(?:^|\n)[^\wÄÖÜäöüß-]*(?P<city>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß .-]{1,60}):\s*"
    r"(?P<temp>-?\d+(?:[.,]\d+)?)\s*(?:°C|Â°C|C)\s*,\s*(?P<description>[^.]+)",
    re.IGNORECASE,
)
_WEATHER_HUMIDITY_RE = re.compile(r"Luftfeuchtigkeit\s+(?P<humidity>\d+(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_WEATHER_WIND_RE = re.compile(r"Wind\s+(?P<wind>\d+(?:[.,]\d+)?)\s*km/h", re.IGNORECASE)
_CONTEXT_NUMBER_PATTERN = r"-?\d+(?:[,.]\d+)?"
_PERCENT_OF_LAST_RESULT_RE = re.compile(
    rf"^(?:und\s+)?(?P<percent>{_CONTEXT_NUMBER_PATTERN})\s*(?:%|prozent)\s*(?:davon|darauf|drauf)?[\s?.!]*$",
    re.IGNORECASE,
)
_PERCENT_RESULT_RE = re.compile(
    rf"(?P<percent>{_CONTEXT_NUMBER_PATTERN})\s*%\s*von\s*(?P<base>{_CONTEXT_NUMBER_PATTERN})\s*=\s*(?P<result>{_CONTEXT_NUMBER_PATTERN})",
    re.IGNORECASE,
)
_MATH_RESULT_RE = re.compile(rf"=\s*(?P<result>{_CONTEXT_NUMBER_PATTERN})(?:\s|\.|$)")
_NET_GROSS_RE = re.compile(r"\b(?:netto|brutto|mwst|mehrwertsteuer)\b", re.IGNORECASE)
_DAY_PLAN_SIGNAL_RE = re.compile(
    r"\b(?:arbeitstag|tagesplan|realistisch\w*\s+plan|realistisch\w*\s+tagesplan)\b",
    re.IGNORECASE,
)
_WORK_WINDOW_RE = re.compile(
    r"(?:von\s*)?(?P<start>\d{1,2})(?::(?P<smin>\d{2}))?\s*"
    r"(?:bis|-|–)\s*(?P<end>\d{1,2})(?::(?P<emin>\d{2}))?\s*(?:uhr)?"
    r"(?:\s+\w+){0,4}?\s*(?:arbeit|arbeiten|job)?",
    re.IGNORECASE,
)
_TASKS_RE = re.compile(r"aufgaben?\s*:\s*(?P<tasks>[^.\n]+)", re.IGNORECASE)
_SPORT_RE = re.compile(r"(?P<minutes>\d{1,3})\s*(?:minuten|min\.?|m)\s+sport", re.IGNORECASE)
_TEMP_RE = re.compile(r"(?P<temp>-?\d+(?:[,.]\d+)?)\s*(?:°C|Â°C|C)\b", re.IGNORECASE)
_CITY_RE = re.compile(r"\bin\s+(?P<city>[A-ZÄÖÜ][A-Za-zÄÖÜäöüß .-]{1,40})\b")
_START_UPDATE_RE = re.compile(
    r"\b(?:erst\s+um|um)\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?:uhr)?\s*(?:starte|anfange|beginne|beginn)",
    re.IGNORECASE,
)
_SHORTER_PLAN_RE = re.compile(r"\b(?:kuerzer|kürzer|kurzfassung|knapper|kompakt|zusammenfassen)\b", re.IGNORECASE)
_TODO_PLAN_RE = re.compile(r"\b(?:daraus|mach|mache|erstell|erstelle).*\b(?:todo|to-do|checkliste|liste)\b", re.IGNORECASE)
_PRIORITY_PLAN_RE = re.compile(r"\b(?:welche\s+aufgabe\s+zuerst|was\s+zuerst|priorisier|prioritaet|priorität)\b", re.IGNORECASE)


def _float_from_match(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _format_weather_number(value: float | None) -> str:
    if value is None:
        return "?"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _parse_context_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _format_context_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f").rstrip("0").rstrip(".") or "0"


def _parse_clock_minutes(hour: str | int, minute: str | int | None = None) -> int:
    h = max(0, min(23, int(hour)))
    m = max(0, min(59, int(minute or 0)))
    return h * 60 + m


def _format_clock(minutes: int) -> str:
    minutes = max(0, minutes)
    hour = (minutes // 60) % 24
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def _duration_text(minutes: int) -> str:
    minutes = max(0, int(minutes))
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def _extract_tasks(text: str) -> list[str]:
    match = _TASKS_RE.search(text or "")
    if not match:
        return ["Projekt planen", "Rechnung schreiben", "Wohnung aufraeumen"]
    raw = match.group("tasks")
    parts = re.split(r",|\s+und\s+", raw, flags=re.IGNORECASE)
    tasks = [re.sub(r"\s+", " ", part).strip(" .;:") for part in parts]
    return [task for task in tasks if task][:6] or ["Projekt planen", "Rechnung schreiben", "Wohnung aufraeumen"]


def _task_by_keyword(tasks: list[str], keyword: str, fallback: str) -> str:
    lowered = keyword.lower()
    for task in tasks:
        if lowered in task.lower():
            return task
    return fallback


def _day_plan_context_from_text(text: str) -> dict | None:
    source = text or ""
    if not _DAY_PLAN_SIGNAL_RE.search(source):
        return None
    work_match = _WORK_WINDOW_RE.search(source)
    if work_match:
        work_start = _parse_clock_minutes(work_match.group("start"), work_match.group("smin"))
        work_end = _parse_clock_minutes(work_match.group("end"), work_match.group("emin"))
    else:
        work_start = 9 * 60
        work_end = 17 * 60
    if work_end <= work_start:
        work_end += 12 * 60

    city_match = _CITY_RE.search(source)
    city = (city_match.group("city").strip() if city_match else "Hamburg")
    if len(city.split()) > 3:
        city = city.split()[0]
    city = city.strip(".,;:")

    temp_match = _TEMP_RE.search(source)
    temp = _parse_context_decimal(temp_match.group("temp") if temp_match else None)
    temp_text = _format_context_decimal(temp) if temp is not None else "15"
    lower = source.lower()
    weather_desc = "klar" if "klar" in lower else "dem Wetter"
    humidity = "hohe Luftfeuchtigkeit" if "luftfeuchtigkeit" in lower and ("hoch" in lower or "hohe" in lower) else ""
    wind = "leichter Wind" if "wind" in lower and ("leicht" in lower or "leichter" in lower) else ""

    sport_match = _SPORT_RE.search(source)
    sport_minutes = int(sport_match.group("minutes")) if sport_match else 45
    return {
        "city": city,
        "temp": temp_text,
        "weather_desc": weather_desc,
        "humidity": humidity,
        "wind": wind,
        "work_start": work_start,
        "work_end": work_end,
        "work_duration": work_end - work_start,
        "sport_minutes": sport_minutes,
        "tasks": _extract_tasks(source),
        "sleep": 22 * 60 + 30,
    }


def _latest_day_plan_context(history: list[dict]) -> dict | None:
    latest: dict | None = None
    latest_index = -1
    for index, msg in enumerate(history or []):
        if msg.get("role") != "user":
            continue
        parsed = _day_plan_context_from_text(str(msg.get("content") or ""))
        if parsed:
            latest = parsed
            latest_index = index
    if latest is None:
        return None

    for msg in (history or [])[latest_index + 1:]:
        if msg.get("role") != "user":
            continue
        _apply_day_plan_start_update(latest, str(msg.get("content") or ""))
    return latest


def _apply_day_plan_start_update(context: dict, text: str) -> bool:
    match = _START_UPDATE_RE.search(text or "")
    if not match:
        return False
    new_start = _parse_clock_minutes(match.group("hour"), match.group("minute"))
    context["work_start"] = new_start
    context["work_end"] = new_start + int(context.get("work_duration") or 8 * 60)
    return True


def _day_plan_wake_minutes(context: dict) -> int:
    work_start = int(context.get("work_start") or 9 * 60)
    sport_minutes = int(context.get("sport_minutes") or 45)
    return min(7 * 60 + 15, max(6 * 60, work_start - sport_minutes - 75))


def _day_plan_free_minutes(context: dict, *, wake: int | None = None) -> int:
    if wake is None:
        wake = _day_plan_wake_minutes(context)
    awake_minutes = int(context.get("sleep") or 22 * 60 + 30) - wake
    committed = (
        int(context.get("work_duration") or 8 * 60)
        + int(context.get("sport_minutes") or 45)
        + 135  # breakfast, lunch, dinner, shower, evening shutdown
        + 30   # apartment reset
    )
    return max(0, awake_minutes - committed)


def _day_plan_clothing_reply(context: dict) -> str:
    weather_bits = [f"{context['temp']}°C", str(context.get("weather_desc") or "Wetter")]
    if context.get("humidity"):
        weather_bits.append(str(context["humidity"]))
    if context.get("wind"):
        weather_bits.append(str(context["wind"]))
    return (
        f"Fuer {context['city']} bei {', '.join(weather_bits)}: Shirt plus Hoodie oder leichte Jacke, "
        "lange Hose und Sneaker. Fuer Sport draussen: lange Sporthose, atmungsaktives Shirt, "
        "duenne Laufjacke; danach eine trockene Schicht einplanen."
    )


def _day_plan_priority_reply(context: dict) -> str:
    tasks = context.get("tasks") or []
    project = _task_by_keyword(tasks, "projekt", "Projekt planen")
    invoice = _task_by_keyword(tasks, "rechnung", "Rechnung schreiben")
    apartment = _task_by_keyword(tasks, "wohnung", "Wohnung aufraeumen")
    return (
        f"Zuerst {project}. Das braucht am meisten Kopf und legt die Richtung fuer den Tag fest. "
        f"Danach {invoice}, weil es klar abgrenzbar ist. {apartment} zuletzt oder verschieben, "
        "weil es weniger kritisch ist und bei Muedigkeit am ehesten gekuerzt werden kann."
    )


def _day_plan_todo_reply(context: dict) -> str:
    project = _task_by_keyword(context["tasks"], "projekt", "Projekt planen")
    invoice = _task_by_keyword(context["tasks"], "rechnung", "Rechnung schreiben")
    apartment = _task_by_keyword(context["tasks"], "wohnung", "Wohnung aufraeumen")
    return (
        "Todo fuer morgen:\n"
        f"- {project} als erste Fokusaufgabe erledigen\n"
        f"- {invoice} danach abschliessen\n"
        f"- Arbeit blocken: {_format_clock(context['work_start'])}-{_format_clock(context['work_end'])}\n"
        f"- Sport: {context['sport_minutes']} Minuten\n"
        f"- {apartment}: 20-30 Minuten, optional wenn du muede bist\n"
        "- Outfit bereitlegen: Shirt, Hoodie/leichte Jacke, lange Hose, Sneaker\n"
        "- Abends rechtzeitig runterfahren; Schlaf nicht kuerzen"
    )


def _day_plan_short_reply(context: dict) -> str:
    return (
        f"Kurzfassung: {_format_clock(context['work_start'])}-{_format_clock(context['work_end'])} Arbeit "
        "mit Projekt zuerst, dann Rechnung. Sport 45 Min, Wohnung nur 20-30 Min nach der Arbeit, "
        "abends runterfahren und ca. 22:30 schlafen. Outfit: Shirt plus Hoodie/leichte Jacke, "
        f"lange Hose, Sneaker. Puffer/Freizeit: ca. {_duration_text(_day_plan_free_minutes(context))}. "
        "Wenn muede: Sport kuerzen oder Wohnung verschieben, nicht Essen oder Schlaf."
    )


def _day_plan_full_reply(context: dict) -> str:
    project = _task_by_keyword(context["tasks"], "projekt", "Projekt planen")
    invoice = _task_by_keyword(context["tasks"], "rechnung", "Rechnung schreiben")
    apartment = _task_by_keyword(context["tasks"], "wohnung", "Wohnung aufraeumen")
    work_start = int(context["work_start"])
    work_end = int(context["work_end"])
    wake = _day_plan_wake_minutes(context)
    sport_start = wake + 30
    sport_end = sport_start + int(context["sport_minutes"])
    free = _day_plan_free_minutes(context, wake=wake)
    return (
        f"Realistischer Plan fuer morgen in {context['city']}:\n"
        f"- {_format_clock(wake)} Aufstehen, Fruehstueck, kurz sortieren\n"
        f"- {_format_clock(sport_start)}-{_format_clock(sport_end)} Sport\n"
        f"- {_format_clock(sport_end)}-{_format_clock(work_start)} Duschen, anziehen, Start vorbereiten\n"
        f"- {_format_clock(work_start)}-{_format_clock(work_start + 120)} {project} (zuerst, hoechste Denklast)\n"
        f"- {_format_clock(work_start + 120)}-{_format_clock(work_start + 165)} {invoice}\n"
        f"- 12:30-13:15 Mittagspause, bei klarem Wetter kurz raus\n"
        f"- 13:15-{_format_clock(work_end)} restliche Arbeit und Abschluss\n"
        f"- {_format_clock(work_end + 30)}-{_format_clock(work_end + 60)} {apartment} nur als 30-Minuten-Reset\n"
        "- 19:00 Abendessen, danach ruhiger Abend\n"
        "- 21:45 runterfahren, ca. 22:30 schlafen\n\n"
        f"Kleidung: {_day_plan_clothing_reply(context)}\n\n"
        f"Freie Zeit/Puffer: ungefaehr {_duration_text(free)} zwischen Aufstehen und Schlafen. "
        f"Wenn du muede bist: {apartment} verschieben oder Sport auf 20-30 Minuten kuerzen; "
        "Essen und Schlaf bleiben drin."
    )


def _day_plan_shifted_reply(context: dict) -> str:
    return (
        f"Dann rechne mit {_format_clock(context['work_start'])}-{_format_clock(context['work_end'])} Arbeit. "
        "Mach Sport nur, wenn du danach nicht hetzt: sonst auf 20-30 Minuten kuerzen. "
        "Prioritaet bleibt: Projekt planen zuerst, Rechnung danach, Wohnung nur kurz nach der Arbeit. "
        f"Der Abendpuffer wird enger; Gesamtpuffer bleibt bei fruehem Aufstehen ca. "
        f"{_duration_text(_day_plan_free_minutes(context))}. Schlaf nicht nach hinten schieben."
    )


def try_day_plan_reply(user_message: str, history: list[dict]) -> str | None:
    """Handle day-plan requests and compact follow-ups with consistent math."""
    text = user_message or ""
    direct_context = _day_plan_context_from_text(text)
    if direct_context:
        return _day_plan_full_reply(direct_context)

    context = _latest_day_plan_context(history)
    if not context:
        return None
    if _apply_day_plan_start_update(context, text):
        return _day_plan_shifted_reply(context)
    if _SHORTER_PLAN_RE.search(text):
        return _day_plan_short_reply(context)
    if _TODO_PLAN_RE.search(text):
        return _day_plan_todo_reply(context)
    if _PRIORITY_PLAN_RE.search(text):
        return _day_plan_priority_reply(context)
    if _WEATHER_CLOTHING_FOLLOWUP_RE.search(text):
        return _day_plan_clothing_reply(context)
    return None


def _latest_math_result_context(history: list[dict]) -> dict | None:
    for msg in reversed((history or [])[-10:]):
        if msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        percent_match = _PERCENT_RESULT_RE.search(content)
        if percent_match:
            percent = _parse_context_decimal(percent_match.group("percent"))
            base = _parse_context_decimal(percent_match.group("base"))
            result = _parse_context_decimal(percent_match.group("result"))
            if percent is not None and base is not None and result is not None:
                return {"kind": "percent", "percent": percent, "base": base, "result": result}
        result_match = _MATH_RESULT_RE.search(content)
        if result_match:
            result = _parse_context_decimal(result_match.group("result"))
            if result is not None:
                return {"kind": "math", "result": result}
    return None


def try_contextual_math_followup(user_message: str, history: list[dict]) -> str | None:
    """Answer short math follow-ups from the last deterministic math result."""
    text = user_message or ""
    latest = _latest_math_result_context(history)
    if not latest:
        return None

    percent_match = _PERCENT_OF_LAST_RESULT_RE.match(text.strip())
    if percent_match:
        percent = _parse_context_decimal(percent_match.group("percent"))
        base = latest.get("result")
        if percent is None or not isinstance(base, Decimal):
            return None
        result = (percent / Decimal("100")) * base
        return (
            f"{_format_context_decimal(percent)} % von {_format_context_decimal(base)} = "
            f"{_format_context_decimal(result)}."
        )

    if not _NET_GROSS_RE.search(text):
        return None
    if latest.get("kind") != "percent":
        return None
    percent = latest["percent"]
    base = latest["base"]
    tax = latest["result"]
    gross = base + tax
    return (
        f"Wenn die {_format_context_decimal(tax)} EUR die {_format_context_decimal(percent)} % MwSt sind: "
        f"Netto {_format_context_decimal(base)} EUR, MwSt {_format_context_decimal(tax)} EUR, "
        f"Brutto {_format_context_decimal(gross)} EUR."
    )


def _latest_weather_context(history: list[dict]) -> dict | None:
    for msg in reversed(history or []):
        if msg.get("role") != "assistant":
            continue
        content = str(msg.get("content") or "")
        match = _WEATHER_SUMMARY_RE.search(content)
        if not match:
            continue
        temp = _float_from_match(match.group("temp"))
        if temp is None:
            continue
        humidity_match = _WEATHER_HUMIDITY_RE.search(content)
        wind_match = _WEATHER_WIND_RE.search(content)
        return {
            "city": match.group("city").strip(),
            "temp": temp,
            "description": match.group("description").strip(),
            "humidity": _float_from_match(humidity_match.group("humidity") if humidity_match else None),
            "wind": _float_from_match(wind_match.group("wind") if wind_match else None),
        }
    return None


def _recent_user_asked_for_clothing(history: list[dict]) -> bool:
    for msg in reversed((history or [])[-6:]):
        if msg.get("role") == "user" and _WEATHER_CLOTHING_FOLLOWUP_RE.search(str(msg.get("content") or "")):
            return True
    return False


def _weather_clothing_reply(context: dict) -> str:
    city = context["city"]
    temp = float(context["temp"])
    temp_text = _format_weather_number(temp)
    description = context.get("description") or "dem Wetter"
    humidity = context.get("humidity")
    wind = context.get("wind")

    if temp <= 0:
        outfit = "Winterjacke, warmer Pulli, Muetze, Schal, Handschuhe und feste Schuhe"
    elif temp <= 8:
        outfit = "warme Jacke oder Mantel, Pulli, lange Hose und geschlossene Schuhe"
    elif temp <= 14:
        outfit = "Jacke, Pullover oder Hoodie, lange Hose und normale Sneaker"
    elif temp <= 19:
        outfit = "leichte Jacke oder Hoodie ueber einem Shirt, lange Hose und Sneaker"
    elif temp <= 24:
        outfit = "T-Shirt oder leichter Pulli; nimm fuer spaeter eine duenne Jacke mit"
    else:
        outfit = "leichte Kleidung, atmungsaktive Schuhe und bei Sonne Sonnenschutz"

    extras: list[str] = []
    desc_lower = description.lower()
    if any(word in desc_lower for word in ("regen", "niesel", "schauer", "gewitter")):
        extras.append("Regenschutz oder kleiner Schirm waere sinnvoll")
    if wind is not None and wind >= 25:
        extras.append("Wegen des Winds lieber eine winddichte Schicht")
    if humidity is not None and humidity >= 80 and temp < 20:
        extras.append("Bei der hohen Luftfeuchtigkeit fuehlt es sich etwas kuehler an")

    reply = f"Bei {temp_text}°C und {description} in {city}: {outfit}."
    if extras:
        reply += " " + " ".join(extras) + "."
    return reply


def try_weather_clothing_followup(user_message: str, history: list[dict]) -> str | None:
    """Answer clothing follow-ups from the latest weather result in chat history."""
    has_clothing = bool(_WEATHER_CLOTHING_FOLLOWUP_RE.search(user_message or ""))
    has_weather_reference = bool(_WEATHER_FOLLOWUP_REFERENCE_RE.search(user_message or ""))
    if not has_clothing and not (has_weather_reference and _recent_user_asked_for_clothing(history)):
        return None
    if has_clothing and not has_weather_reference:
        return None
    context = _latest_weather_context(history)
    if not context:
        return None
    return _weather_clothing_reply(context)


def try_contextual_followup(user_message: str, history: list[dict]) -> str | None:
    """Resolve compact follow-ups that need the last chat context."""
    return (
        try_contextual_math_followup(user_message, history)
        or try_day_plan_reply(user_message, history)
        or try_weather_clothing_followup(user_message, history)
    )


# ══════════════════════════════════════════════════
#  FILE UPLOAD HELPERS
# ══════════════════════════════════════════════════

def extract_file_content(filepath: Path, original_name: str, content_type: str | None = None) -> dict:
    """Extract content and metadata from uploaded file."""
    stat = filepath.stat()
    size_kb = round(stat.st_size / 1024, 1)
    ext = Path(original_name).suffix.lower()
    reported_mime = normalized_upload_content_type(content_type)
    guessed_mime = mimetypes.guess_type(original_name)[0] or ""
    display_reported_mime = "" if reported_mime in _GENERIC_UPLOAD_MIME_TYPES else reported_mime
    mime = display_reported_mime or guessed_mime or reported_mime or "application/octet-stream"

    result = {
        "filename": original_name,
        "size_kb": size_kb,
        "extension": ext,
        "mime": mime,
        "content": None,
        "type": "unknown",
        "preview": None,
    }

    if reported_mime.startswith("image/") or guessed_mime.startswith("image/"):
        result["type"] = "image"
        result["preview"] = f"Bild: {original_name} ({size_kb} KB)"
    elif ext in TEXT_EXTENSIONS or reported_mime.startswith("text/") or guessed_mime.startswith("text/"):
        result["type"] = "text"
        try:
            raw_bytes = filepath.read_bytes()
            text = raw_bytes.decode("utf-8", errors="replace")
            if "\ufffd" in text:
                logger.warning(f"File '{original_name}' contained non-UTF-8 bytes (replaced with replacement char)")
            if len(text) > MAX_TEXT_CHARS:
                result["content"] = text[:MAX_TEXT_CHARS]
                result["preview"] = f"[Erste {MAX_TEXT_CHARS} Zeichen von {len(text)} gesamt]"
            else:
                result["content"] = text
            result["line_count"] = text.count("\n") + 1
        except Exception as e:
            result["content"] = None
            result["preview"] = t("error.readFile", error=_client_safe_chat_error(e))
    elif ext == ".pdf":
        result["type"] = "pdf"
        result["preview"] = f"PDF: {original_name} ({size_kb} KB)"
    else:
        result["type"] = "binary"
        result["preview"] = f"Datei: {original_name} ({size_kb} KB, {mime})"

    return result


# ══════════════════════════════════════════════════
#  CHAT ENDPOINTS
# ══════════════════════════════════════════════════

def validate_chat_upload_filename(filename: str | None) -> tuple[str, str]:
    """Return a safe display filename and suffix, or raise for unsafe uploads."""
    original = str(filename or "upload").strip() or "upload"
    safe_filename = Path(original).name
    if not safe_filename or safe_filename != original:
        raise HTTPException(status_code=400, detail="Ungueltiger Dateiname.")

    suffix = Path(safe_filename).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        audit_log("chat_file", "blocked_extension", f"EXT={suffix}")
        raise HTTPException(
            status_code=400,
            detail=f"Dateityp '{suffix}' ist nicht erlaubt.",
        )
    return safe_filename, suffix


def chat_file_public_info(file_info: dict, *, analysis_status: str | None = None) -> dict:
    """Return the stable file metadata payload exposed to the renderer."""
    payload = {
        "filename": file_info["filename"],
        "size_kb": file_info["size_kb"],
        "type": file_info["type"],
        "extension": file_info["extension"],
        "mime": file_info["mime"],
        "line_count": file_info.get("line_count"),
        "preview": file_info["preview"],
    }
    if analysis_status:
        payload["analysis_status"] = analysis_status
    return payload


def image_upload_provider_required_reply(file_info: dict) -> str:
    """Friendly, non-fake fallback when an uploaded image cannot be analyzed yet."""
    return (
        f"Ich habe das Bild '{file_info['filename']}' erhalten "
        f"({file_info['size_kb']} KB). Die Bildanalyse ist vorbereitet, "
        "aber aktuell ist kein Vision-Provider fuer Uploads verbunden. "
        "Sobald ein Vision-Provider konfiguriert ist, kann ich Bildinhalt, "
        "UI, Text und Details direkt auswerten."
    )


def chat_file_vision_available() -> bool:
    """Check whether image uploads can be routed to the Vision pipeline."""
    try:
        from backend.vision import get_vision_status

        status = get_vision_status()
        return bool(status.get("available"))
    except Exception as e:
        logger.info("Vision status unavailable for chat file upload: %s", e)
        return False


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Standard chat endpoint (non-streaming)."""
    if not check_rate_limit("chat"):
        audit_log("chat", "rate_limited")
        rl = get_rate_limit_info("chat")
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anfragen. Bitte kurz warten.",
            headers={
                "X-RateLimit-Limit": str(rl["limit"]),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            },
        )

    sanitized = sanitize_input(req.message)
    audit_log("chat", "received", _audit_message_details(sanitized))

    # Fast path: check if this is a confirmation of a pending action
    pending = get_pending_confirmation()
    if pending and _is_confirmation_message(sanitized):
        action_name = pending.get("action", "")
        logger.info(f"User confirmed pending action: {action_name}")
        audit_log("chat", "auto_confirm", f"ACTION={action_name}")
        clear_pending_confirmation()
        reply = await _execute_pending_confirmation(pending, "chat_confirm")
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)
        return ChatResponse(reply=reply, action=None, requires_confirmation=False)
    if pending:
        if _is_pending_cancel_message(sanitized):
            action_name = pending.get("action", "")
            clear_pending_confirmation()
            reply = f"Freigabe fuer {action_name} verworfen. Ich habe nichts ausgefuehrt."
        else:
            reply = _pending_confirmation_wait_reply(pending)
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)
        return ChatResponse(reply=reply, action=None, requires_confirmation=False)

    system_reply = await try_lexa_system_answer(sanitized)
    if system_reply:
        audit_log("chat", "lexa_system_answer", _audit_message_details(sanitized))
        async with _history_lock:
            update_history(conversation_history, sanitized, system_reply, MAX_HISTORY)
        return ChatResponse(reply=system_reply, action=None, requires_confirmation=False)

    async with _history_lock:
        history_snapshot = list(conversation_history)
    intent_context = build_conversation_intent_context(history_snapshot)
    publish_chat_context(sanitized, intent_context=intent_context, source="chat")
    if _is_hermes_worker_request(sanitized) or _is_hermes_desktop_control_request(sanitized):
        audit_log("chat", "hermes_worker", _audit_message_details(sanitized))
        reply_msg, _steps, _run_data = await _collect_hermes_worker_reply(sanitized, history_snapshot)
        reply_msg = await _maybe_execute_inline_confirmation(sanitized, reply_msg, "chat_inline_confirm")
        async with _history_lock:
            update_history(conversation_history, sanitized, f"[Hermes] {reply_msg[:2000]}", MAX_HISTORY)
        return ChatResponse(reply=reply_msg, action=None, requires_confirmation=False)

    contextual_reply = try_contextual_followup(sanitized, history_snapshot)
    if contextual_reply:
        audit_log("chat", "contextual_followup", _audit_message_details(sanitized))
        async with _history_lock:
            update_history(conversation_history, sanitized, contextual_reply, MAX_HISTORY)
        return ChatResponse(reply=contextual_reply, action=None, requires_confirmation=False)

    # Fast path: try local intent recognition first (avoids AI API call)
    local_result = try_local_intent(sanitized, context=intent_context)
    if local_result is not None:
        audit_log("chat", "local_intent", f"ACTION={local_result.get('action')}")
        reply_msg = local_result["message"]
        action = None
        requires_confirmation = False

        if local_result["action"] is not None:
            synthetic = json.dumps({
                "action": local_result["action"],
                "params": local_result["params"],
                "message": reply_msg,
            })
            reply_msg, action, requires_confirmation = process_ai_response(
                synthetic, source="chat_local"
            )

        # Track pending confirmation
        if requires_confirmation and action:
            set_pending_confirmation(action)
        elif action and not requires_confirmation:
            clear_pending_confirmation()
            # Execute server-side — user sees real result, not placeholder
            try:
                from backend.action_executor import execute_action
                exec_result = await asyncio.to_thread(
                    execute_action, action, source="chat_local"
                )
                if exec_result.get("success"):
                    data = exec_result.get("data")
                    if data and isinstance(data, str):
                        reply_msg = data
                    elif data and isinstance(data, dict):
                        reply_msg = (
                            data.get("summary")
                            or data.get("message")
                            or data.get("error")
                            or ". ".join(
                                f"{k}: {v}" for k, v in data.items()
                                if v and k not in ("icon", "icon_code", "will_rain", "success")
                            )
                            or reply_msg
                        )
                    action = None  # Already executed
                else:
                    reply_msg = exec_result.get("error", reply_msg)
                    action = None
            except Exception as e:
                logger.error(f"[Intent:Exec] Failed: {e}", exc_info=True)

        async with _history_lock:
            update_history(conversation_history, sanitized, reply_msg, MAX_HISTORY)
        logger.info(f"Local intent resolved: {local_result.get('action', 'direct_reply')}")
        return ChatResponse(reply=reply_msg, action=action, requires_confirmation=requires_confirmation)

    cached_reply = get_cached_chat_response(sanitized, history_snapshot)
    if cached_reply is not None:
        reply = cached_reply["reply"]
        audit_log("chat", "ai_response_cache_hit", f"similarity={cached_reply.get('similarity')}")
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)
        return ChatResponse(reply=reply, action=None, requires_confirmation=False)

    # AI call in thread pool (blocking requests library)
    try:
        ai_result = await asyncio.to_thread(chat, sanitized, history_snapshot)
    except ConnectionError as e:
        logger.error(f"AI connection error: {e}")
        raise HTTPException(status_code=503, detail="AI service unavailable. Please try again later.")
    except Exception:
        logger.exception("AI chat() call failed")
        raise HTTPException(status_code=502, detail="KI-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.")

    # Phase 40: process_chat_result handles both tool calls and text
    reply, action, requires_confirmation = process_chat_result(ai_result, source="chat")

    # Track pending confirmation
    if requires_confirmation and action:
        set_pending_confirmation(action)
    elif action:
        clear_pending_confirmation()

    async with _history_lock:
        update_history(conversation_history, sanitized, reply, MAX_HISTORY)
    if not action and not requires_confirmation and ai_result.get("type", "text") == "text":
        remember_chat_response(sanitized, history_snapshot, reply)

    return ChatResponse(reply=reply, action=action, requires_confirmation=requires_confirmation)


@router.post("/chat/file")
async def chat_file_endpoint(
    file: UploadFile = File(...),
    message: str = Form(""),
):
    """Upload a file and analyze it with AI context."""
    if not check_rate_limit("chat"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    safe_filename, suffix = validate_chat_upload_filename(file.filename)

    # Stream the upload directly to disk so large configured uploads do not pile up in RAM.
    tmp_path: Path | None = None
    total_size = 0
    too_large = False
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                too_large = True
                break
            tmp.write(chunk)

    if too_large:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=413,
            detail=f"Datei zu gross (max {MAX_FILE_SIZE_MB} MB).",
        )

    # Analyze the already validated temporary upload.
    try:
        file_info = extract_file_content(tmp_path, safe_filename, file.content_type)
        user_msg = sanitize_input(message) if message else "Analysiere diese Datei."

        if file_info["type"] == "image":
            image_bytes = tmp_path.read_bytes()
            if supported_image_signature(image_bytes) is None:
                raise HTTPException(status_code=400, detail=invalid_image_upload_error())

            analysis_status = "vision_provider_required"
            reply = image_upload_provider_required_reply(file_info)
            if chat_file_vision_available():
                try:
                    from backend.vision import analyze_image

                    reply = await analyze_image(
                        image_input=image_bytes,
                        prompt=user_msg,
                        quality_mode=False,
                    )
                    analysis_status = "analyzed"
                except RuntimeError as e:
                    logger.warning("Vision image upload unavailable: %s", e)
                    reply = image_upload_provider_required_reply(file_info)
                except Exception:
                    logger.exception("Vision image upload analysis failed")
                    raise HTTPException(status_code=502, detail="Bildanalyse fehlgeschlagen. Bitte erneut versuchen.")

            audit_log("chat_file", analysis_status, _audit_file_details(file_info["filename"]))
            return {
                "status": "ok",
                "reply": reply,
                "action": None,
                "requires_confirmation": False,
                "analysis_status": analysis_status,
                "analysis_kind": "image",
                "file_info": chat_file_public_info(file_info, analysis_status=analysis_status),
            }

        if file_info["content"]:
            file_context = (
                f"[Datei: {file_info['filename']} | {file_info['size_kb']} KB | "
                f"{file_info.get('line_count', '?')} Zeilen | {file_info['extension']}]\n"
                f"```\n{file_info['content']}\n```"
            )
            full_prompt = f"{user_msg}\n\n{file_context}"
        else:
            full_prompt = (
                f"{user_msg}\n\n[Datei: {file_info['filename']} "
                f"({file_info['size_kb']} KB, {file_info['mime']})]"
            )

        audit_log("chat_file", "received", _audit_file_details(file_info["filename"]))

        # AI call in thread pool
        try:
            async with _history_lock:
                history_snapshot = list(conversation_history)
            ai_result = await asyncio.to_thread(chat, full_prompt, history_snapshot)
        except ConnectionError as e:
            logger.error(f"AI connection error (file): {e}")
            raise HTTPException(status_code=503, detail="AI service unavailable. Please try again later.")
        except Exception:
            logger.exception("AI chat() call failed (file)")
            raise HTTPException(status_code=502, detail="KI-Verarbeitung fehlgeschlagen. Bitte erneut versuchen.")

        # Phase 40: unified processing for tool calls + text
        reply, action, requires_confirmation = process_chat_result(ai_result, source="chat_file")

        async with _history_lock:
            update_history(conversation_history, full_prompt[:2000], reply, MAX_HISTORY)

        return {
            "status": "ok",
            "reply": reply,
            "action": action,
            "requires_confirmation": requires_confirmation,
            "analysis_status": "text_analyzed" if file_info["type"] == "text" else "metadata_only",
            "file_info": chat_file_public_info(
                file_info,
                analysis_status="text_analyzed" if file_info["type"] == "text" else "metadata_only",
            ),
        }
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Stream AI response via Server-Sent Events."""
    if not check_rate_limit("chat"):
        rl = get_rate_limit_info("chat")
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anfragen. Bitte kurz warten.",
            headers={
                "X-RateLimit-Limit": str(rl["limit"]),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            },
        )

    sanitized = sanitize_input(req.message)
    audit_log("chat_stream", "received", _audit_message_details(sanitized))

    # Fast path: check if this is a confirmation of a pending action
    pending = get_pending_confirmation()
    if pending and _is_confirmation_message(sanitized):
        action_name = pending.get("action", "")
        logger.info(f"User confirmed pending action (stream): {action_name}")
        audit_log("chat_stream", "auto_confirm", f"ACTION={action_name}")
        clear_pending_confirmation()
        reply = await _execute_pending_confirmation(pending, "chat_stream_confirm")
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)

        async def confirm_stream():
            yield f"data: {json.dumps({'c': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"

        return StreamingResponse(
            confirm_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if pending:
        if _is_pending_cancel_message(sanitized):
            action_name = pending.get("action", "")
            clear_pending_confirmation()
            reply = f"Freigabe fuer {action_name} verworfen. Ich habe nichts ausgefuehrt."
        else:
            reply = _pending_confirmation_wait_reply(pending)
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)

        async def pending_wait_stream():
            yield f"data: {json.dumps({'c': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"

        return StreamingResponse(
            pending_wait_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    system_reply = await try_lexa_system_answer(sanitized)
    if system_reply:
        audit_log("chat_stream", "lexa_system_answer", _audit_message_details(sanitized))
        async with _history_lock:
            update_history(conversation_history, sanitized, system_reply, MAX_HISTORY)

        async def system_stream():
            yield f"data: {json.dumps({'c': system_reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"

        return StreamingResponse(
            system_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async with _history_lock:
        history_snapshot = list(conversation_history)
    intent_context = build_conversation_intent_context(history_snapshot)
    publish_chat_context(sanitized, intent_context=intent_context, source="chat_stream")
    if _is_hermes_worker_request(sanitized) or _is_hermes_desktop_control_request(sanitized):
        audit_log("chat_stream", "hermes_worker", _audit_message_details(sanitized))

        async def hermes_worker_stream():
            from backend.agent_loop import run_agent

            full_text = ""
            final_reply = ""
            inline_confirmation = _has_inline_confirmation(sanitized)
            try:
                async for event in run_agent(sanitized, history_snapshot, worker="hermes"):
                    etype = event.get("type", "")
                    chunk = ""
                    if etype == "thinking":
                        chunk = str(event.get("message") or "")
                    elif etype == "step_blocked":
                        if not inline_confirmation:
                            step = event.get("step", {}) or {}
                            error = _client_safe_chat_error(step.get("error", ""))
                            chunk = f"\nBestaetigung noetig fuer {step.get('action', 'Aktion')}: {error}"
                    elif etype == "error":
                        chunk = _client_safe_chat_error(event.get("message") or "Hermes-Worker Fehler")
                    elif etype == "done":
                        run_data = event.get("run", {}) or {}
                        final_reply = str(run_data.get("summary") or final_reply or full_text or "Hermes hat den Auftrag verarbeitet.")
                        if inline_confirmation and "Bestaetigung noetig" in final_reply:
                            final_reply = ""
                        if final_reply and final_reply not in full_text:
                            chunk = final_reply
                    if chunk:
                        full_text += chunk
                        yield f"data: {json.dumps({'c': chunk}, ensure_ascii=False)}\n\n"
                reply = final_reply or full_text or "Hermes hat den Auftrag verarbeitet."
                if inline_confirmation:
                    confirmed_reply = await _maybe_execute_inline_confirmation(
                        sanitized,
                        reply,
                        "chat_stream_inline_confirm",
                    )
                    if confirmed_reply != reply:
                        reply = confirmed_reply
                        yield f"data: {json.dumps({'c': reply}, ensure_ascii=False)}\n\n"
                async with _history_lock:
                    update_history(conversation_history, sanitized, f"[Hermes] {reply[:2000]}", MAX_HISTORY)
                yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False, 'reply': reply}, ensure_ascii=False)}\n\n"
            except asyncio.CancelledError:
                logger.info("Hermes worker stream cancelled by client")
            except Exception as e:
                logger.exception("Hermes worker stream failed")
                yield f"data: {json.dumps({'error': _client_safe_chat_error(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            hermes_worker_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    contextual_reply = try_contextual_followup(sanitized, history_snapshot)
    if contextual_reply:
        audit_log("chat_stream", "contextual_followup", _audit_message_details(sanitized))
        async with _history_lock:
            update_history(conversation_history, sanitized, contextual_reply, MAX_HISTORY)

        async def contextual_stream():
            yield f"data: {json.dumps({'c': contextual_reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"

        return StreamingResponse(
            contextual_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Fast path: local intent -> execute server-side, return result immediately
    local_result = try_local_intent(sanitized, context=intent_context)
    if local_result is not None:
        audit_log("chat_stream", "local_intent", f"ACTION={local_result.get('action')}")
        reply_msg = local_result["message"]
        action = None
        requires_confirmation = False

        if local_result["action"] is not None:
            synthetic = json.dumps({
                "action": local_result["action"],
                "params": local_result["params"],
                "message": reply_msg,
            })
            reply_msg, action, requires_confirmation = process_ai_response(
                synthetic, source="chat_stream_local"
            )

        # Track pending confirmation
        if requires_confirmation and action:
            set_pending_confirmation(action)
        elif action and not requires_confirmation:
            clear_pending_confirmation()
            # Execute action SERVER-SIDE and return real result
            # This prevents the "Führe X aus" problem — user sees actual result
            try:
                from backend.action_executor import execute_action
                exec_result = await asyncio.to_thread(
                    execute_action, action, source="chat_stream_local"
                )
                if exec_result.get("success"):
                    data = exec_result.get("data")
                    if data and isinstance(data, str):
                        reply_msg = data
                    elif data and isinstance(data, dict):
                        reply_msg = (
                            data.get("summary")
                            or data.get("message")
                            or data.get("error")
                            or ". ".join(
                                f"{k}: {v}" for k, v in data.items()
                                if v and k not in ("icon", "icon_code", "will_rain", "success")
                            )
                            or reply_msg
                        )
                    # Action already executed — don't send it to frontend
                    action = None
                    logger.info(f"[Intent:Exec] {local_result['action']} → {reply_msg[:80]}")
                else:
                    reply_msg = exec_result.get("error", reply_msg)
                    action = None
            except Exception as e:
                logger.error(f"[Intent:Exec] Failed: {e}", exc_info=True)
                # Fall through with original reply_msg + action for frontend

        async with _history_lock:
            update_history(conversation_history, sanitized, reply_msg, MAX_HISTORY)
        logger.info(f"Local intent resolved (stream): {local_result.get('action', 'direct_reply')}")

        async def local_stream():
            yield f"data: {json.dumps({'c': reply_msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation})}\n\n"

        return StreamingResponse(
            local_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    cached_reply = get_cached_chat_response(sanitized, history_snapshot)
    if cached_reply is not None:
        reply = cached_reply["reply"]
        audit_log("chat_stream", "ai_response_cache_hit", f"similarity={cached_reply.get('similarity')}")
        async with _history_lock:
            update_history(conversation_history, sanitized, reply, MAX_HISTORY)

        async def cached_stream():
            yield f"data: {json.dumps({'c': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False, 'reply': reply})}\n\n"

        return StreamingResponse(
            cached_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        loop = asyncio.get_running_loop()
        gen = None
        full_text = ""
        _sentinel = object()
        tool_call_result = None  # Phase 40: accumulates tool call dict

        try:
            try:
                gen = chat_stream(sanitized, history_snapshot)
            except Exception:
                logger.exception("chat_stream() generator creation failed")
                yield f"data: {json.dumps({'error': lexa_user_error('ai_unavailable')})}\n\n"
                return

            while True:
                try:
                    chunk = await loop.run_in_executor(
                        None, lambda g=gen, s=_sentinel: next(g, s)
                    )
                except Exception as e:
                    logger.error(f"Stream chunk error: {e}")
                    yield f"data: {json.dumps({'error': t('error.streamError')})}\n\n"
                    break
                if chunk is _sentinel:
                    break

                # Phase 40: stream yields either str chunks or a tool_call dict
                if isinstance(chunk, dict) and chunk.get("type") == "tool_call":
                    tool_call_result = chunk
                    break
                elif isinstance(chunk, str):
                    full_text += chunk
                    yield f"data: {json.dumps({'c': chunk})}\n\n"

            # Phase 40: Handle tool call from stream
            if tool_call_result is not None:
                from backend.action_parser import process_tool_call
                reply, action, requires_confirmation = process_tool_call(
                    tool_call_result.get("tool_calls", []),
                    ai_message=full_text,  # any text before the tool call
                    source="chat_stream",
                )
                # Track pending confirmation for follow-up messages
                if requires_confirmation and action:
                    set_pending_confirmation(action)
                elif action:
                    clear_pending_confirmation()
                # Store richer context in history so AI remembers what was proposed
                history_reply = reply
                if action and requires_confirmation:
                    action_name = action.get("action", "")
                    params = action.get("params", {})
                    params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
                    history_reply = f"{reply} [Aktion: {action_name}({params_str}) wartet auf Bestätigung]"
                async with _history_lock:
                    update_history(conversation_history, sanitized, history_reply, MAX_HISTORY)
                audit_log("chat_stream", "tool_call", f"ACTION={action.get('action') if action else 'none'}")
                yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation, 'reply': reply})}\n\n"

            # Standard text response
            elif full_text:
                async with _history_lock:
                    update_history(conversation_history, sanitized, full_text, MAX_HISTORY)
                reply, action, requires_confirmation = process_ai_response(full_text, source="chat_stream")

                # Fallback: detect tool calls described as text (happens when fallback model has no tools)
                # e.g. "weather_current(location='Hamburg')" or "Führe weather_current aus"
                if action is None and full_text:
                    import re as _re
                    _tool_patterns = [
                        _re.compile(r'(\w+)\(.*?\)'),  # function_name(args)
                        _re.compile(r"[Ff]ühre\s+['\"]?(\w+)['\"]?\s+aus"),
                        _re.compile(r"[Rr]ufe\s+['\"]?(\w+)['\"]?\s+auf"),
                    ]
                    for pat in _tool_patterns:
                        m = pat.search(full_text)
                        if not m:
                            continue
                        detected_tool = m.group(1)
                        try:
                            from backend.tool_registry import get_tool_names
                            if detected_tool not in get_tool_names():
                                continue
                            logger.warning(f"[ChatStream] AI described tool '{detected_tool}' as text — building synthetic call")
                            # Extract params heuristically from the user message
                            args = {}
                            try:
                                from backend.tool_registry import get_tool
                                schema = get_tool(detected_tool)
                                if schema and "parameters" in schema.get("function", {}):
                                    props = schema["function"]["parameters"].get("properties", {})
                                    words = sanitized.split()
                                    lower_words = sanitized.lower().split()
                                    if "city" in props:
                                        for i, w in enumerate(lower_words):
                                            if w in ("in", "für", "von") and i + 1 < len(words):
                                                args["city"] = " ".join(words[i + 1:])
                                                break
                                    if "name" in props:
                                        for trigger in ("öffne", "starte", "open", "start"):
                                            if trigger in lower_words:
                                                idx = lower_words.index(trigger)
                                                if idx + 1 < len(words):
                                                    args["name"] = " ".join(words[idx + 1:])
                                                break
                                    if "query" in props or "search" in props:
                                        key = "query" if "query" in props else "search"
                                        for trigger in ("suche", "such", "search", "find"):
                                            if trigger in lower_words:
                                                idx = lower_words.index(trigger)
                                                if idx + 1 < len(words):
                                                    args[key] = " ".join(words[idx + 1:])
                                                break
                            except Exception:
                                pass

                            from backend.action_parser import process_tool_call
                            synthetic_tc = [{"id": "fallback", "name": detected_tool, "arguments": args}]
                            reply, action, requires_confirmation = process_tool_call(
                                synthetic_tc, ai_message=full_text, source="chat_stream_fallback"
                            )
                            logger.info(f"[ChatStream] Fallback tool: {detected_tool}({json.dumps(args)})")
                        except ImportError:
                            pass
                        break

                # Track pending confirmation for follow-up messages
                if requires_confirmation and action:
                    set_pending_confirmation(action)
                elif action:
                    clear_pending_confirmation()
                elif not requires_confirmation:
                    remember_chat_response(sanitized, history_snapshot, full_text)

                audit_log("chat_stream", "done", f"LEN={len(full_text)}")
                yield f"data: {json.dumps({'done': True, 'action': action, 'rc': requires_confirmation})}\n\n"
            else:
                fallback = lexa_user_error("empty_response")
                async with _history_lock:
                    update_history(conversation_history, sanitized, fallback, MAX_HISTORY)
                audit_log("chat_stream", "empty_response", "no chunks returned")
                yield f"data: {json.dumps({'c': fallback})}\n\n"
                yield f"data: {json.dumps({'done': True, 'action': None, 'rc': False})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled by client (partial LEN={len(full_text)})")
        except Exception:
            logger.exception("Unexpected error in event_stream")
            yield f"data: {json.dumps({'error': t('error.internalStream')})}\n\n"
        finally:
            if gen is not None:
                gen.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/confirm-clear")
async def clear_confirm_endpoint():
    """Clear pending confirmation state (called when user clicks confirm/deny button)."""
    clear_pending_confirmation()
    return {"status": "ok"}


# /chat/confirm removed (Phase 40A) — was dead code.
# Confirmation execution happens via /companion/execute with confirmed=true.
