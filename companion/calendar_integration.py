"""Lexa AI — Google Calendar Integration
OAuth2 via google-api-python-client, credentials stored securely.
Supports reading, creating, deleting, and searching calendar events.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("lexa.calendar")

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
_CREDENTIALS_FILE = os.path.join(_DATA_DIR, "google_calendar_credentials.json")
_CLIENT_SECRET_FILE = os.path.join(_DATA_DIR, "google_client_secret.json")

# OAuth2 scopes — read + write
_SCOPES_READ = ["https://www.googleapis.com/auth/calendar.readonly"]
_SCOPES_WRITE = ["https://www.googleapis.com/auth/calendar.events"]
_SCOPES = _SCOPES_READ + _SCOPES_WRITE


def _get_calendar_service():
    """Handle OAuth2 flow and return an authorized Calendar API service.

    First time: Opens browser for Google login, saves refresh token.
    Subsequent calls: Uses saved refresh token silently (auto-refresh if expired).
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request as GoogleRequest
        from googleapiclient.discovery import build
    except ImportError:
        logger.error("google-api-python-client or google-auth-oauthlib not installed")
        return None

    creds = None

    # Load saved credentials
    if os.path.exists(_CREDENTIALS_FILE):
        try:
            creds = Credentials.from_authorized_user_file(_CREDENTIALS_FILE, _SCOPES)
        except Exception as e:
            logger.warning("Failed to load saved credentials: %s", e)
            creds = None

    # Refresh expired token or run OAuth flow
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleRequest())
            logger.info("Google Calendar token refreshed successfully")
        except Exception as e:
            logger.warning("Token refresh failed, re-authenticating: %s", e)
            creds = None

    if not creds or not creds.valid:
        if not os.path.exists(_CLIENT_SECRET_FILE):
            logger.debug("Google Calendar client secret not configured at %s", _CLIENT_SECRET_FILE)
            return None
        try:
            flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRET_FILE, _SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Google Calendar OAuth2 flow completed successfully")
        except Exception as e:
            logger.error("OAuth2 flow failed: %s", e, exc_info=True)
            return None

    # Save credentials for next time
    try:
        with open(_CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception as e:
        logger.warning("Failed to save credentials: %s", e)

    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except Exception as e:
        logger.error("Failed to build Calendar service: %s", e, exc_info=True)
        return None


def get_calendar_status() -> dict:
    """Return whether the Google Calendar is connected."""
    connected = os.path.exists(_CREDENTIALS_FILE)
    has_client_secret = os.path.exists(_CLIENT_SECRET_FILE)
    return {
        "connected": connected,
        "has_client_secret": has_client_secret,
        "credentials_path": _CREDENTIALS_FILE,
    }


def _parse_event(event: dict) -> dict:
    """Parse a Google Calendar event into a simplified dict."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id", ""),
        "title": event.get("summary", "(Kein Titel)"),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "status": event.get("status", ""),
        "html_link": event.get("htmlLink", ""),
    }


def _parse_natural_date(text: str) -> str | None:
    """Parse natural language date string to ISO format using dateparser.

    Supports German and English expressions like:
    - 'morgen um 14 Uhr', 'übermorgen', 'nächsten Montag'
    - 'tomorrow at 2pm', 'next Monday at 3:30 PM'
    """
    # If already ISO format, return as-is
    if text and ("T" in text or len(text) == 10):
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
            return text
        except (ValueError, TypeError):
            pass

    try:
        import dateparser
        parsed = dateparser.parse(
            text,
            languages=["de", "en"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
        )
        if parsed:
            return parsed.isoformat()
    except ImportError:
        logger.warning("dateparser not installed, falling back to ISO parse only")
    except Exception as e:
        logger.warning("dateparser failed for '%s': %s", text, e)

    return None


def calendar_today() -> dict:
    """Return today's events as a list of dicts."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()

        events = [_parse_event(e) for e in result.get("items", [])]
        return {
            "success": True,
            "events": events,
            "count": len(events),
            "date": now.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.error("calendar_today failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Kalender-Fehler: {e}"}


def calendar_week() -> dict:
    """Return this week's events."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        now = datetime.now(timezone.utc)
        # Start of current week (Monday)
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=7)

        result = service.events().list(
            calendarId="primary",
            timeMin=start_of_week.isoformat(),
            timeMax=end_of_week.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=100,
        ).execute()

        events = [_parse_event(e) for e in result.get("items", [])]
        return {
            "success": True,
            "events": events,
            "count": len(events),
            "week_start": start_of_week.strftime("%Y-%m-%d"),
            "week_end": end_of_week.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.error("calendar_week failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Kalender-Fehler: {e}"}


def calendar_next() -> dict:
    """Return the next upcoming event."""
    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        now = datetime.now(timezone.utc).isoformat()

        result = service.events().list(
            calendarId="primary",
            timeMin=now,
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        ).execute()

        items = result.get("items", [])
        if not items:
            return {"success": True, "event": None, "message": "Keine anstehenden Termine."}

        event = _parse_event(items[0])
        return {"success": True, "event": event}
    except Exception as e:
        logger.error("calendar_next failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Kalender-Fehler: {e}"}


def calendar_create(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = "",
) -> dict:
    """Create a calendar event.

    Args:
        title: Event title (required, max 200 chars)
        start: Start time as ISO string or natural language ('morgen um 14 Uhr')
        end: End time (optional, defaults to 1 hour after start)
        description: Event description (max 5000 chars)
        location: Event location (max 200 chars)
    """
    # Input validation
    if not title or not title.strip():
        return {"success": False, "error": "Titel darf nicht leer sein."}
    title = title.strip()[:200]

    if not start or not start.strip():
        return {"success": False, "error": "Startzeit erforderlich."}

    description = (description or "").strip()[:5000]
    location = (location or "").strip()[:200]

    # Parse natural language dates
    start_iso = _parse_natural_date(start.strip())
    if not start_iso:
        return {"success": False, "error": f"Startzeit nicht erkannt: '{start}'"}

    if end and end.strip():
        end_iso = _parse_natural_date(end.strip())
        if not end_iso:
            return {"success": False, "error": f"Endzeit nicht erkannt: '{end}'"}
    else:
        # Default: 1 hour after start
        try:
            start_dt = datetime.fromisoformat(start_iso)
            end_dt = start_dt + timedelta(hours=1)
            end_iso = end_dt.isoformat()
        except (ValueError, TypeError):
            end_iso = start_iso

    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        event_body = {
            "summary": title,
            "start": {"dateTime": start_iso, "timeZone": "Europe/Berlin"},
            "end": {"dateTime": end_iso, "timeZone": "Europe/Berlin"},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        created = service.events().insert(calendarId="primary", body=event_body).execute()
        logger.info("Calendar event created: %s (id=%s)", title, created.get("id"))

        return {
            "success": True,
            "event": _parse_event(created),
            "message": f"Termin erstellt: {title}",
        }
    except Exception as e:
        logger.error("calendar_create failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Termin konnte nicht erstellt werden: {e}"}


def calendar_delete(event_id: str) -> dict:
    """Delete a calendar event by ID. Requires confirmation."""
    if not event_id or not event_id.strip():
        return {"success": False, "error": "Event-ID erforderlich."}
    event_id = event_id.strip()

    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        # First fetch the event to confirm it exists and get the title
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        title = event.get("summary", "(Kein Titel)")

        service.events().delete(calendarId="primary", eventId=event_id).execute()
        logger.info("Calendar event deleted: %s (id=%s)", title, event_id)

        return {
            "success": True,
            "deleted_id": event_id,
            "message": f"Termin gelöscht: {title}",
        }
    except Exception as e:
        logger.error("calendar_delete failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Termin konnte nicht gelöscht werden: {e}"}


def calendar_search(query: str, days: int = 30) -> dict:
    """Search calendar events by keyword within the next N days.

    Args:
        query: Search term (required, max 200 chars)
        days: Number of days to search ahead (default 30, max 365)
    """
    if not query or not query.strip():
        return {"success": False, "error": "Suchbegriff erforderlich."}
    query = query.strip()[:200]

    # Clamp days
    days = max(1, min(365, int(days)))

    service = _get_calendar_service()
    if not service:
        return {"success": False, "error": "Kalender nicht verbunden. Bitte in Settings verbinden."}

    try:
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days)

        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end_date.isoformat(),
            q=query,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()

        events = [_parse_event(e) for e in result.get("items", [])]
        return {
            "success": True,
            "events": events,
            "count": len(events),
            "query": query,
            "days_searched": days,
        }
    except Exception as e:
        logger.error("calendar_search failed: %s", e, exc_info=True)
        return {"success": False, "error": f"Kalender-Suche fehlgeschlagen: {e}"}
