"""
Vision Router — Screenshot & Bildanalyse Endpoints.

Stellt REST-API Endpoints fuer das Lexa Vision System bereit:
- Screenshot aufnehmen (ganzer Bildschirm oder bestimmtes Fenster)
- Bildanalyse mit Gemini/OpenAI Vision
- Bildschirm beschreiben, Text lesen, Elemente finden
- Status-Abfrage (verfuegbare Provider)
"""

from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from backend.security import check_rate_limit

logger = logging.getLogger("lexa.vision.router")

router = APIRouter(prefix="/vision", tags=["vision"])


# ══════════════════════════════════════════════════
#  REQUEST MODELS
# ══════════════════════════════════════════════════

class ScreenshotRequest(BaseModel):
    window: Optional[str] = Field(None, description="Fenstertitel fuer gezielten Screenshot", max_length=500)


class AnalyzeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000, description="Frage/Anweisung zum Bild")
    auto_capture: bool = Field(True, description="Automatisch Screenshot machen vor Analyse")
    window: Optional[str] = Field(None, description="Fenstertitel (nur wenn auto_capture=true)", max_length=500)
    quality_mode: bool = Field(False, description="True = Gemini Pro (langsamer, besser)")


class DescribeRequest(BaseModel):
    window: Optional[str] = Field(None, description="Fenstertitel", max_length=500)


class FindRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000, description="Beschreibung des gesuchten Elements")
    window: Optional[str] = Field(None, description="Fenstertitel", max_length=500)


class ReadTextRequest(BaseModel):
    window: Optional[str] = Field(None, description="Fenstertitel", max_length=500)


# ══════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════

def _success(data: dict) -> dict:
    """Konsistentes Erfolgs-Response-Format."""
    return {"success": True, "data": data}


def _error(message: str, status_code: int = 500) -> JSONResponse:
    """Konsistentes Fehler-Response-Format."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message},
    )


# ══════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════

@router.post("/screenshot")
async def take_screenshot(req: ScreenshotRequest = ScreenshotRequest()):
    """Macht einen Screenshot und gibt ihn als Base64 zurueck.

    Optional: Fenster-spezifischer Screenshot via `window` Parameter.
    """
    check_rate_limit("vision")
    try:
        from backend.vision import capture_screenshot, capture_active_window

        if req.window:
            image_bytes = await capture_active_window(req.window)
        else:
            image_bytes = await capture_screenshot()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        return _success({
            "image_base64": b64,
            "size_bytes": len(image_bytes),
            "format": "png",
            "window": req.window,
        })

    except RuntimeError as e:
        logger.warning(f"Screenshot fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Screenshot-Fehler: {e}", exc_info=True)
        return _error(f"Screenshot fehlgeschlagen: {e}", 500)


@router.post("/analyze")
async def analyze_screenshot_endpoint(req: AnalyzeRequest):
    """Analysiert einen Screenshot mit Vision AI.

    Wenn auto_capture=true (Standard), wird zuerst ein Screenshot gemacht.
    Body: {"prompt": "Was siehst du?", "auto_capture": true}
    """
    check_rate_limit("vision")
    try:
        from backend.vision import analyze_screenshot

        if req.auto_capture:
            result = await analyze_screenshot(
                prompt=req.prompt,
                window_title=req.window,
                quality_mode=req.quality_mode,
            )
            return _success({
                "analysis": result["analysis"],
                "screenshot_size": result["screenshot_size"],
                "auto_captured": True,
            })
        else:
            return _error("auto_capture=false erfordert ein Bild. Nutze /vision/analyze-file.", 400)

    except RuntimeError as e:
        logger.warning(f"Analyse fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Analyse-Fehler: {e}", exc_info=True)
        return _error(f"Analyse fehlgeschlagen: {e}", 500)


@router.post("/analyze-file")
async def analyze_uploaded_file(
    prompt: str = "Beschreibe dieses Bild detailliert.",
    quality_mode: bool = False,
    file: UploadFile = File(...),
):
    """Analysiert ein hochgeladenes Bild mit Vision AI.

    Unterstuetzte Formate: PNG, JPEG, WEBP, GIF, BMP
    Max. Dateigroesse: 10MB
    """
    check_rate_limit("vision")

    # Validierung: Dateityp
    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"}
    if file.content_type and file.content_type not in allowed_types:
        return _error(f"Nicht unterstuetztes Format: {file.content_type}. Erlaubt: PNG, JPEG, WEBP, GIF, BMP", 400)

    try:
        # Datei lesen (max 10MB)
        image_bytes = await file.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            return _error("Datei zu gross (max. 10MB)", 413)
        if len(image_bytes) == 0:
            return _error("Leere Datei", 400)

        from backend.vision import analyze_image

        analysis = await analyze_image(
            image_input=image_bytes,
            prompt=prompt,
            quality_mode=quality_mode,
        )
        return _success({
            "analysis": analysis,
            "filename": file.filename,
            "file_size": len(image_bytes),
        })

    except RuntimeError as e:
        logger.warning(f"Datei-Analyse fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Datei-Analyse-Fehler: {e}", exc_info=True)
        return _error(f"Analyse fehlgeschlagen: {e}", 500)


@router.post("/describe")
async def describe_screen_endpoint(req: DescribeRequest = DescribeRequest()):
    """Beschreibt den aktuellen Bildschirminhalt.

    Macht Screenshot und beschreibt alle sichtbaren Elemente,
    Programme, Texte und den allgemeinen Desktop-Zustand.
    """
    check_rate_limit("vision")
    try:
        from backend.vision import describe_screen

        description = await describe_screen(window_title=req.window)
        return _success({
            "description": description,
            "window": req.window,
        })

    except RuntimeError as e:
        logger.warning(f"Bildschirm-Beschreibung fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Beschreibung-Fehler: {e}", exc_info=True)
        return _error(f"Bildschirm-Beschreibung fehlgeschlagen: {e}", 500)


@router.post("/find")
async def find_on_screen_endpoint(req: FindRequest):
    """Findet ein visuelles Element auf dem Bildschirm.

    Body: {"description": "der rote Button", "window": "optional"}
    Gibt eine Beschreibung zurueck wo das Element zu finden ist.
    """
    check_rate_limit("vision")
    try:
        from backend.vision import find_on_screen

        result = await find_on_screen(
            description=req.description,
            window_title=req.window,
        )
        return _success({
            "result": result,
            "searched_for": req.description,
            "window": req.window,
        })

    except RuntimeError as e:
        logger.warning(f"Element-Suche fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Element-Suche-Fehler: {e}", exc_info=True)
        return _error(f"Element-Suche fehlgeschlagen: {e}", 500)


@router.post("/read-text")
async def read_screen_text_endpoint(req: ReadTextRequest = ReadTextRequest()):
    """Liest allen sichtbaren Text vom Bildschirm (OCR-aehnlich).

    Extrahiert und strukturiert den gesamten sichtbaren Text,
    gruppiert nach Bildschirm-Bereichen.
    """
    check_rate_limit("vision")
    try:
        from backend.vision import read_screen_text

        text = await read_screen_text(window_title=req.window)
        return _success({
            "text": text,
            "window": req.window,
        })

    except RuntimeError as e:
        logger.warning(f"Text-Erkennung fehlgeschlagen: {e}")
        return _error(str(e), 500)
    except Exception as e:
        logger.error(f"Text-Erkennung-Fehler: {e}", exc_info=True)
        return _error(f"Text-Erkennung fehlgeschlagen: {e}", 500)


@router.post("/ocr")
async def ocr_screen_endpoint(req: ReadTextRequest = ReadTextRequest()):
    """Lokale OCR-Texterkennung vom Bildschirm (offline, schnell).

    Nutzt rapidocr-onnxruntime (primaer) oder pytesseract (Fallback).
    Braucht keine Cloud-API — laeuft komplett lokal.
    """
    check_rate_limit("vision")
    try:
        from companion.ocr import ocr_screenshot

        result = await asyncio.to_thread(ocr_screenshot, window_title=req.window)
        if result.get("success"):
            return _success(result["data"])
        return _error(result.get("error", "OCR fehlgeschlagen"), 500)

    except Exception as e:
        logger.error(f"OCR-Fehler: {e}", exc_info=True)
        return _error(f"OCR fehlgeschlagen: {e}", 500)


@router.get("/status")
async def vision_status():
    """Prueft ob Vision verfuegbar ist.

    Gibt Informationen ueber verfuegbare Provider,
    Screenshot-Faehigkeit und Modelle zurueck.
    """
    try:
        from backend.vision import get_vision_status

        status = await asyncio.to_thread(get_vision_status)
        return _success(status)

    except Exception as e:
        logger.error(f"Vision-Status-Fehler: {e}", exc_info=True)
        return _error(f"Status-Abfrage fehlgeschlagen: {e}", 500)
