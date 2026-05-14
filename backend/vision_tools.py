"""
Vision Tools fuer das Tool-Use System.
OpenAI-compatible function calling Definitionen fuer Bildschirm-Analyse.

Definiert 5 Vision-Tools die der AI Agent aufrufen kann:
- screenshot_analyze: Screenshot machen und mit Prompt analysieren
- screenshot_describe: Aktuellen Bildschirm beschreiben
- screenshot_read_text: Text vom Bildschirm lesen (OCR-aehnlich)
- screenshot_find_element: Visuelles Element auf dem Bildschirm finden
- screenshot_capture: Nur Screenshot machen (ohne Analyse)

Plus execute_vision_tool() Dispatcher fuer die Tool-Ausfuehrung.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

logger = logging.getLogger("lexa.vision.tools")


# ══════════════════════════════════════════════════
#  TOOL DEFINITIONS (OpenAI function-calling Format)
# ══════════════════════════════════════════════════

VISION_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "screenshot_analyze",
            "description": (
                "Macht einen Screenshot des Bildschirms und analysiert ihn mit einer Frage. "
                "Nuetzlich um zu verstehen was der User gerade sieht oder macht."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Frage oder Anweisung zur Analyse des Screenshots",
                    },
                    "window": {
                        "type": "string",
                        "description": "Optional: Fenstertitel fuer gezielten Screenshot (z.B. 'Chrome', 'VS Code')",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot_describe",
            "description": (
                "Beschreibt detailliert was aktuell auf dem Bildschirm zu sehen ist. "
                "Nennt geoeffnete Programme, sichtbare Texte und UI-Elemente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {
                        "type": "string",
                        "description": "Optional: Nur ein bestimmtes Fenster beschreiben",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot_read_text",
            "description": (
                "Liest allen sichtbaren Text vom Bildschirm (OCR-aehnlich). "
                "Extrahiert Text aus Fenstern, Menues, Dialogen und Statusleisten."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {
                        "type": "string",
                        "description": "Optional: Nur Text aus bestimmtem Fenster lesen",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot_find_element",
            "description": (
                "Findet ein visuelles Element auf dem Bildschirm anhand einer Beschreibung. "
                "Gibt Position und Aussehen des gefundenen Elements zurueck."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Beschreibung des gesuchten Elements (z.B. 'der Speichern-Button', 'das Suchfeld')",
                    },
                    "window": {
                        "type": "string",
                        "description": "Optional: Nur in bestimmtem Fenster suchen",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot_capture",
            "description": (
                "Macht nur einen Screenshot des Bildschirms ohne Analyse. "
                "Gibt die Bildgroesse zurueck. Nuetzlich wenn der Screenshot "
                "spaeter weiterverarbeitet werden soll."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {
                        "type": "string",
                        "description": "Optional: Screenshot eines bestimmten Fensters",
                    },
                },
            },
        },
    },
]


# ══════════════════════════════════════════════════
#  TOOL EXECUTION DISPATCHER
# ══════════════════════════════════════════════════

async def execute_vision_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Fuehrt ein Vision-Tool aus und gibt das Ergebnis zurueck.

    Args:
        name: Tool-Name (z.B. 'screenshot_analyze')
        args: Tool-Argumente als Dict
    Returns:
        Ergebnis-Dict mit tool-spezifischen Daten
    Raises:
        ValueError: Unbekannter Tool-Name
        RuntimeError: Ausfuehrungsfehler
    """
    try:
        if name == "screenshot_analyze":
            from backend.vision import analyze_screenshot
            prompt = args.get("prompt", "Was ist auf dem Bildschirm zu sehen?")
            window = args.get("window")
            result = await analyze_screenshot(prompt=prompt, window_title=window)
            return {
                "status": "success",
                "tool": name,
                "analysis": result["analysis"],
                "screenshot_size": result["screenshot_size"],
            }

        elif name == "screenshot_describe":
            from backend.vision import describe_screen
            window = args.get("window")
            description = await describe_screen(window_title=window)
            return {
                "status": "success",
                "tool": name,
                "description": description,
            }

        elif name == "screenshot_read_text":
            from backend.vision import read_screen_text
            window = args.get("window")
            text = await read_screen_text(window_title=window)
            return {
                "status": "success",
                "tool": name,
                "text": text,
            }

        elif name == "screenshot_find_element":
            from backend.vision import find_on_screen
            description = args.get("description", "")
            if not description:
                return {
                    "status": "error",
                    "tool": name,
                    "error": "Beschreibung des gesuchten Elements fehlt.",
                }
            window = args.get("window")
            result = await find_on_screen(description=description, window_title=window)
            return {
                "status": "success",
                "tool": name,
                "result": result,
                "searched_for": description,
            }

        elif name == "screenshot_capture":
            from backend.vision import capture_screenshot, capture_active_window
            window = args.get("window")
            if window:
                image_bytes = await capture_active_window(window)
            else:
                image_bytes = await capture_screenshot()
            return {
                "status": "success",
                "tool": name,
                "size_bytes": len(image_bytes),
                "format": "png",
                "message": f"Screenshot aufgenommen ({len(image_bytes) // 1024}KB)",
            }

        else:
            raise ValueError(f"Unbekanntes Vision-Tool: {name}")

    except ValueError:
        raise
    except RuntimeError as e:
        logger.warning(f"Vision-Tool '{name}' fehlgeschlagen: {e}")
        return {
            "status": "error",
            "tool": name,
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Vision-Tool '{name}' Fehler: {e}", exc_info=True)
        return {
            "status": "error",
            "tool": name,
            "error": f"Unerwarteter Fehler: {e}",
        }


def get_vision_tool_names() -> list[str]:
    """Gibt alle Vision-Tool-Namen zurueck."""
    return [t["function"]["name"] for t in VISION_TOOLS]


def is_vision_tool(name: str) -> bool:
    """Prueft ob ein Tool-Name ein Vision-Tool ist."""
    return name in get_vision_tool_names()
