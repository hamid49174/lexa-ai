"""Lexa AI — Calendar Router
API Endpoints for Google Calendar integration.
"""

import asyncio
import logging
import re
import threading
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from backend.security import check_rate_limit, audit_log
from backend.agent_protocol import redacted_summary
from companion import calendar_integration as calendar_int

logger = logging.getLogger("lexa.router.calendar")

# Lokale Pfade aus Fehlertexten entfernen (wie router_vision/router_voice).
_LOCAL_PATH_RE = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>|]+|\\\\[^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc|mnt)/[^\s\"'<>|]+)"
)


def _calendar_safe_error(exc, prefix: str = "Kalender-Fehler") -> str:
    """Client-sichere Fehlermeldung: Secrets + lokale Pfade entfernt."""
    text = _LOCAL_PATH_RE.sub("[pfad]", redacted_summary(str(exc or ""), max_chars=200))
    return f"{prefix}: {text}" if text else prefix

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Guard against concurrent OAuth connect attempts. The OAuth flow opens a
# browser window and blocks the worker thread until the user finishes (or
# abandons) the consent. Allowing parallel connects would stack multiple
# blocked threads and can exhaust the executor pool, so only one connect runs
# at a time; further requests get a clear, immediate response instead.
_connect_lock = threading.Lock()


def _rate_limited() -> JSONResponse | None:
    if check_rate_limit("execute"):
        return None
    return JSONResponse({"error": "Zu viele Kalender-Anfragen. Bitte kurz warten."}, status_code=429)


@router.get("/status")
async def calendar_status():
    """Check if Google Calendar is connected."""
    try:
        result = await asyncio.to_thread(calendar_int.get_calendar_status)
        return result
    except Exception as e:
        logger.error("calendar_status failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e)}, status_code=500)


@router.post("/connect")
async def calendar_connect():
    """Trigger OAuth2 flow to connect Google Calendar."""
    limited = _rate_limited()
    if limited is not None:
        return limited
    # Reject overlapping connect attempts instead of stacking blocked threads.
    if not _connect_lock.acquire(blocking=False):
        return JSONResponse(
            {"success": False, "error": "Verbindung läuft bereits. Bitte schließe das geöffnete Browser-Fenster ab."},
            status_code=409,
        )
    audit_log("calendar_connect", "requested")
    try:
        # This will open a browser window for OAuth2 consent
        service = await asyncio.to_thread(calendar_int._get_calendar_service)
        if service:
            audit_log("calendar_connect", "success")
            return {"success": True, "message": "Google Kalender erfolgreich verbunden."}
        else:
            return JSONResponse(
                {"success": False, "error": "Verbindung fehlgeschlagen. Stelle sicher, dass google_client_secret.json vorhanden ist."},
                status_code=400,
            )
    except Exception as e:
        logger.error("calendar_connect failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e, "Verbindungsfehler")}, status_code=500)
    finally:
        _connect_lock.release()


@router.get("/today")
async def calendar_today():
    """Get today's calendar events."""
    limited = _rate_limited()
    if limited is not None:
        return limited
    try:
        result = await asyncio.to_thread(calendar_int.calendar_today)
        if not result.get("success"):
            return JSONResponse(result, status_code=400)
        return result
    except Exception as e:
        logger.error("calendar_today failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e)}, status_code=500)


@router.get("/week")
async def calendar_week():
    """Get this week's calendar events."""
    limited = _rate_limited()
    if limited is not None:
        return limited
    try:
        result = await asyncio.to_thread(calendar_int.calendar_week)
        if not result.get("success"):
            return JSONResponse(result, status_code=400)
        return result
    except Exception as e:
        logger.error("calendar_week failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e)}, status_code=500)


@router.get("/next")
async def calendar_next():
    """Get the next upcoming calendar event."""
    limited = _rate_limited()
    if limited is not None:
        return limited
    try:
        result = await asyncio.to_thread(calendar_int.calendar_next)
        if not result.get("success"):
            return JSONResponse(result, status_code=400)
        return result
    except Exception as e:
        logger.error("calendar_next failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e)}, status_code=500)


@router.get("/search")
async def calendar_search(q: str = Query("", max_length=200), days: int = Query(30, ge=1, le=365)):
    """Search calendar events by title/text over the next N days (read-only)."""
    limited = _rate_limited()
    if limited is not None:
        return limited
    query = (q or "").strip()
    if not query:
        return JSONResponse({"error": "Suchbegriff darf nicht leer sein."}, status_code=400)
    try:
        result = await asyncio.to_thread(calendar_int.calendar_search, query, days)
        if not result.get("success"):
            return JSONResponse(result, status_code=400)
        return result
    except Exception as e:
        logger.error("calendar_search failed: %s", e, exc_info=True)
        return JSONResponse({"error": _calendar_safe_error(e)}, status_code=500)
