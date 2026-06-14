"""
Lexa AI — Context Tools fuer AI Agent
Tool-Definitionen und Ausfuehrungsfunktion fuer kontextbezogene AI-Tools.
Der AI Agent kann diese Tools aufrufen um System-Kontext abzufragen.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lexa.context_tools")


# ══════════════════════════════════════════════════════════
#  TOOL DEFINITIONEN (OpenAI/Groq Function Calling Format)
# ══════════════════════════════════════════════════════════

CONTEXT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_screen_context",
            "description": "Gibt den aktuellen System-Kontext zurueck (aktives Fenster, CPU, RAM, laufende Apps, Idle-Zeit, Uhrzeit, Batterie)",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard_content",
            "description": "Liest den aktuellen Inhalt der Zwischenablage und erkennt den Typ (Code, URL, E-Mail, Dateipfad, JSON, Text)",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_browser_tabs",
            "description": "Zeigt die zuletzt besuchten Browser-Tabs aus der Chrome-History",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Anzahl der Tabs (1-100, Standard: 10)",
                        "default": 10,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_spotify",
            "description": "Steuert Spotify-Wiedergabe (play, pause, next, previous)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous"],
                        "description": "Aktion: play, pause, next oder previous",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_files",
            "description": "Zeigt kuerzlich geaenderte Dateien auf dem Desktop, in Dokumenten und Downloads",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Stunden zurueckschauen (1-168, Standard: 24)",
                        "default": 24,
                    },
                    "directory": {
                        "type": "string",
                        "description": "Optionales spezifisches Verzeichnis zum Durchsuchen",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_project",
            "description": "Erkennt das aktive Projekt aus VS Code, PyCharm oder anderen IDEs",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spotify_status",
            "description": "Zeigt den aktuell spielenden Song in Spotify (Artist und Titel)",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clipboard_history",
            "description": "Zeigt die letzten 20 Clipboard-Eintraege mit Typ-Erkennung",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ══════════════════════════════════════════════════════════
#  TOOL EXECUTION
# ══════════════════════════════════════════════════════════

def execute_context_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Fuehrt ein Context-Tool aus und gibt das Ergebnis zurueck.

    Args:
        name: Tool-Name (muss in CONTEXT_TOOLS definiert sein).
        args: Optionale Argumente als Dict.

    Returns:
        {"success": True, "data": {...}} oder {"success": False, "error": "..."}
    """
    if args is None:
        args = {}

    # Audit-Logging: Diese Tools fuehren auf KI-Anweisung sensible System-/
    # Subprozess-Operationen aus (Browser-History, Dateisystem-Scan, Spotify).
    # Wie der Companion-Pfad wird jeder Aufruf protokolliert.
    from backend.security import audit_log

    # Tool-Name validieren
    valid_tools = {t["function"]["name"] for t in CONTEXT_TOOLS}
    if name not in valid_tools:
        audit_log(f"context_tool:{name}", "rejected", "unbekanntes Context-Tool")
        return {"success": False, "error": f"Unbekanntes Context-Tool: {name}"}

    try:
        if name == "get_screen_context":
            result = _exec_screen_context()
        elif name == "get_clipboard_content":
            result = _exec_clipboard_content()
        elif name == "get_browser_tabs":
            result = _exec_browser_tabs(args)
        elif name == "control_spotify":
            result = _exec_control_spotify(args)
        elif name == "get_recent_files":
            result = _exec_recent_files(args)
        elif name == "get_active_project":
            result = _exec_active_project()
        elif name == "get_spotify_status":
            result = _exec_spotify_status()
        elif name == "get_clipboard_history":
            result = _exec_clipboard_history()
        else:
            audit_log(f"context_tool:{name}", "error", "nicht implementiert")
            return {"success": False, "error": f"Tool nicht implementiert: {name}"}
        audit_log(
            f"context_tool:{name}",
            "success" if result.get("success") else "failed",
        )
        return result
    except Exception as e:
        logger.warning(f"Context-Tool '{name}' Fehler: {e}", exc_info=True)
        audit_log(f"context_tool:{name}", "error", str(e))
        return {"success": False, "error": f"Tool-Ausfuehrung fehlgeschlagen: {str(e)}"}


# ══════════════════════════════════════════════════════════
#  TOOL IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════

def _exec_screen_context() -> dict[str, Any]:
    """Holt den gesamten System-Kontext."""
    from backend.context_monitor import context_monitor
    ctx = context_monitor.get_system_context()
    return {"success": True, "data": ctx}


def _exec_clipboard_content() -> dict[str, Any]:
    """Analysiert den aktuellen Clipboard-Inhalt."""
    from backend.integrations import clipboard_intel
    analysis = clipboard_intel.analyze_clipboard()
    return {"success": True, "data": analysis}


def _exec_browser_tabs(args: dict[str, Any]) -> dict[str, Any]:
    """Liest die Chrome Browser-History."""
    from backend.integrations import get_browser_tabs
    limit = args.get("limit", 10)
    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10
    limit = max(1, min(100, limit))
    tabs = get_browser_tabs(limit=limit)
    return {"success": True, "data": {"tabs": tabs, "count": len(tabs)}}


def _exec_control_spotify(args: dict[str, Any]) -> dict[str, Any]:
    """Steuert Spotify."""
    from backend.integrations import spotify_control
    action = args.get("action", "")
    if not action:
        return {"success": False, "error": "Aktion fehlt (play, pause, next, previous)"}
    result = spotify_control(action)
    return {"success": result.get("success", False), "data": result}


def _exec_recent_files(args: dict[str, Any]) -> dict[str, Any]:
    """Listet kuerzlich geaenderte Dateien."""
    from backend.integrations import get_recent_files
    hours = args.get("hours", 24)
    if not isinstance(hours, int):
        try:
            hours = int(hours)
        except (ValueError, TypeError):
            hours = 24
    hours = max(1, min(168, hours))
    directory = args.get("directory")
    if directory and not isinstance(directory, str):
        directory = None
    files = get_recent_files(hours=hours, directory=directory)
    return {"success": True, "data": {"files": files, "count": len(files)}}


def _exec_active_project() -> dict[str, Any]:
    """Erkennt das aktive Projekt."""
    from backend.integrations import get_project_context
    project = get_project_context()
    return {"success": True, "data": project}


def _exec_spotify_status() -> dict[str, Any]:
    """Holt den Spotify-Status."""
    from backend.integrations import get_spotify_status
    status = get_spotify_status()
    return {"success": True, "data": status}


def _exec_clipboard_history() -> dict[str, Any]:
    """Gibt die Clipboard-History zurueck."""
    from backend.integrations import clipboard_intel
    history = clipboard_intel.get_history()
    return {"success": True, "data": {"history": history, "count": len(history)}}
