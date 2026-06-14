"""Lexa AI — Calendar Router
API Endpoints for Google Calendar integration.
"""

import asyncio
import logging
import threading
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from backend.security import check_rate_limit, audit_log
from companion import calendar_integration as calendar_int

logger = logging.getLogger("lexa.router.calendar")

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
        return JSONResponse({"error": f"Fehler: {e}"}, status_code=500)


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
        return JSONResponse({"error": f"Verbindungsfehler: {e}"}, status_code=500)
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
        return JSONResponse({"error": f"Fehler: {e}"}, status_code=500)


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
        return JSONResponse({"error": f"Fehler: {e}"}, status_code=500)
