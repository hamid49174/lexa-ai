"""
Lexa AI — Context & Integration API Router
Endpoints fuer System-Kontext, Browser-Tabs, Spotify, Dateisystem, Clipboard.
"""
from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.context_monitor import context_monitor
from backend.integrations import (
    get_browser_tabs,
    get_current_url,
    get_spotify_status,
    spotify_control,
    get_recent_files,
    get_project_context,
    clipboard_intel,
)
from backend.security import check_rate_limit

logger = logging.getLogger("lexa.router_context")
router = APIRouter(prefix="/context", tags=["context"])


# ── Request/Response Models ──────────────────────────────

class SpotifyControlRequest(BaseModel):
    action: str  # play, pause, next, prev


# ══════════════════════════════════════════════════════════
#  SYSTEM CONTEXT
# ══════════════════════════════════════════════════════════

@router.get("")
async def get_context():
    """Gesamter System-Kontext (aktives Fenster, Clipboard, CPU, RAM, Apps, Idle)."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    try:
        ctx = await asyncio.to_thread(context_monitor.get_system_context)
        return {"status": "ok", **ctx}
    except Exception as e:
        logger.warning(f"Context-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Context-Abfrage fehlgeschlagen")


@router.get("/active-window")
async def get_active_window():
    """Nur das aktuell aktive Fenster."""
    try:
        window = await asyncio.to_thread(context_monitor.get_active_window)
        return {"status": "ok", **window}
    except Exception as e:
        logger.warning(f"Active-Window-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Active-Window-Abfrage fehlgeschlagen")


@router.get("/clipboard")
async def get_clipboard():
    """Clipboard-Inhalt mit Typ-Erkennung (code, url, email, text, etc.)."""
    try:
        analysis = await asyncio.to_thread(clipboard_intel.analyze_clipboard)
        return {"status": "ok", **analysis}
    except Exception as e:
        logger.warning(f"Clipboard-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Clipboard-Abfrage fehlgeschlagen")


@router.get("/apps")
async def get_running_apps():
    """Liste aller laufenden Apps mit sichtbaren Fenstern."""
    try:
        apps = await asyncio.to_thread(context_monitor.get_running_apps)
        return {"status": "ok", "apps": apps, "count": len(apps)}
    except Exception as e:
        logger.warning(f"App-Liste fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="App-Liste fehlgeschlagen")


@router.get("/idle")
async def get_idle_time():
    """Idle-Zeit in Sekunden seit letzter Maus/Tastatur-Eingabe."""
    try:
        idle = await asyncio.to_thread(context_monitor.get_idle_time)
        return {"status": "ok", "idle_seconds": round(idle, 1)}
    except Exception as e:
        logger.warning(f"Idle-Zeit-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Idle-Zeit-Abfrage fehlgeschlagen")


# ══════════════════════════════════════════════════════════
#  FILE SYSTEM
# ══════════════════════════════════════════════════════════

@router.get("/recent-files")
async def recent_files(
    hours: int = Query(default=24, ge=1, le=168, description="Stunden zurueck"),
    directory: str = Query(default="", description="Optionales Verzeichnis"),
):
    """Kuerzlich geaenderte Dateien in Standard-Verzeichnissen oder einem bestimmten Ordner."""
    try:
        dir_param = directory.strip() if directory else None
        files = await asyncio.to_thread(get_recent_files, hours, dir_param)
        return {"status": "ok", "files": files, "count": len(files)}
    except Exception as e:
        logger.warning(f"Recent-Files-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Recent-Files-Abfrage fehlgeschlagen")


@router.get("/project")
async def project_context():
    """Erkanntes aktives Projekt (VS Code, PyCharm, etc.)."""
    try:
        project = await asyncio.to_thread(get_project_context)
        return {"status": "ok", **project}
    except Exception as e:
        logger.warning(f"Projekt-Erkennung fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Projekt-Erkennung fehlgeschlagen")


# ══════════════════════════════════════════════════════════
#  BROWSER
# ══════════════════════════════════════════════════════════

@router.get("/browser/tabs")
async def browser_tabs(
    limit: int = Query(default=20, ge=1, le=100, description="Max Anzahl Tabs"),
):
    """Zuletzt besuchte Browser-Tabs (Chrome History)."""
    try:
        tabs = await asyncio.to_thread(get_browser_tabs, limit)
        return {"status": "ok", "tabs": tabs, "count": len(tabs)}
    except Exception as e:
        logger.warning(f"Browser-Tabs-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Browser-Tabs-Abfrage fehlgeschlagen")


@router.get("/browser/current")
async def browser_current_url():
    """Aktuelle URL aus dem Browser-Fenstertitel."""
    try:
        url = await asyncio.to_thread(get_current_url)
        return {"status": "ok", "url": url}
    except Exception as e:
        logger.warning(f"Browser-URL-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Browser-URL-Abfrage fehlgeschlagen")


# ══════════════════════════════════════════════════════════
#  SPOTIFY
# ══════════════════════════════════════════════════════════

@router.get("/spotify")
async def spotify_status():
    """Aktueller Spotify-Song (aus Fenstertitel)."""
    try:
        status = await asyncio.to_thread(get_spotify_status)
        return {"status": "ok", **status}
    except Exception as e:
        logger.warning(f"Spotify-Status-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Spotify-Status-Abfrage fehlgeschlagen")


@router.post("/spotify/control")
async def spotify_ctrl(req: SpotifyControlRequest):
    """Spotify steuern: play, pause, next, previous."""
    allowed_actions = {"play", "pause", "next", "previous", "prev"}
    action = req.action.strip().lower()
    if action not in allowed_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Ungueltige Aktion: {action}. Erlaubt: play, pause, next, previous",
        )
    try:
        result = await asyncio.to_thread(spotify_control, action)
        return {"status": "ok", **result}
    except Exception as e:
        logger.warning(f"Spotify-Control fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Spotify-Control fehlgeschlagen")


# ══════════════════════════════════════════════════════════
#  CLIPBOARD HISTORY
# ══════════════════════════════════════════════════════════

@router.get("/history")
async def clipboard_history():
    """Clipboard-History (letzte 20 Eintraege, In-Memory Ring-Buffer)."""
    try:
        history = clipboard_intel.get_history()
        return {"status": "ok", "history": history, "count": len(history)}
    except Exception as e:
        logger.warning(f"Clipboard-History-Abfrage fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Clipboard-History fehlgeschlagen")
