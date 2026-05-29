"""Lexa AI — Local OCR Engine (Upgrade 6)
Fast offline text extraction from screenshots.
Primary: rapidocr-onnxruntime (accurate, ~150ms)
Fallback: pytesseract if installed
"""

from __future__ import annotations

import io
import logging
import time
from typing import Optional

logger = logging.getLogger("lexa.ocr")

# ── Lazy Imports (optional dependencies) ──────────
_RAPIDOCR_AVAILABLE = False
_RapidOCR = None
try:
    from rapidocr_onnxruntime import RapidOCR as _RapidOCR
    _RAPIDOCR_AVAILABLE = True
    logger.info("RapidOCR (onnxruntime) verfuegbar")
except ImportError:
    logger.info("rapidocr-onnxruntime nicht installiert — Fallback wird geprueft")

_TESSERACT_AVAILABLE = False
try:
    import pytesseract as _pytesseract
    _TESSERACT_AVAILABLE = True
    logger.info("pytesseract verfuegbar (Fallback)")
except ImportError:
    _pytesseract = None
    logger.info("pytesseract nicht installiert — kein Fallback-OCR")

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    Image = None
    ImageGrab = None
    logger.warning("Pillow nicht installiert — Screenshot fuer OCR nicht moeglich")

# ── Singleton RapidOCR instance ──────────────────
_rapid_instance = None


def _get_rapid_ocr():
    """Return cached RapidOCR instance."""
    global _rapid_instance
    if _rapid_instance is None and _RapidOCR is not None:
        try:
            _rapid_instance = _RapidOCR()
            logger.info("RapidOCR instance erstellt")
        except Exception as e:
            logger.warning(f"RapidOCR init fehlgeschlagen: {e}")
    return _rapid_instance


# ══════════════════════════════════════════════════
#  OCR ENGINES
# ══════════════════════════════════════════════════

def _ocr_rapidocr_details(image_bytes: bytes, lang: str = "en") -> tuple[Optional[str], list[dict]]:
    """Run OCR via rapidocr-onnxruntime. Returns extracted text and boxes."""
    ocr = _get_rapid_ocr()
    if ocr is None:
        return None, []
    try:
        img = Image.open(io.BytesIO(image_bytes))
        import numpy as np
        img_array = np.array(img)
        result, _ = ocr(img_array)
        if result is None:
            return "", []
        # result is list of [box, text, confidence]
        lines = []
        blocks = []
        for item in result:
            if not item or len(item) < 2:
                continue
            box = item[0]
            text = str(item[1] or "")
            confidence = float(item[2]) if len(item) >= 3 else None
            lines.append(text)
            try:
                xs = [float(point[0]) for point in box]
                ys = [float(point[1]) for point in box]
                blocks.append({
                    "text": text,
                    "confidence": confidence,
                    "bbox": {
                        "left": min(xs),
                        "top": min(ys),
                        "right": max(xs),
                        "bottom": max(ys),
                    },
                })
            except Exception:
                continue
        return "\n".join(lines), blocks
    except Exception as e:
        logger.warning(f"RapidOCR Fehler: {e}")
        return None, []


def _ocr_rapidocr(image_bytes: bytes, lang: str = "en") -> Optional[str]:
    """Run OCR via rapidocr-onnxruntime. Returns extracted text or None."""
    text, _blocks = _ocr_rapidocr_details(image_bytes, lang)
    return text


def _ocr_tesseract(image_bytes: bytes, lang: str = "eng") -> Optional[str]:
    """Run OCR via pytesseract. Returns extracted text or None."""
    if _pytesseract is None or not _PIL_AVAILABLE:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = _pytesseract.image_to_string(img, lang=lang)
        return text.strip()
    except Exception as e:
        logger.warning(f"Tesseract OCR Fehler: {e}")
        return None


# ══════════════════════════════════════════════════
#  SCREENSHOT CAPTURE (for OCR)
# ══════════════════════════════════════════════════

def _capture_for_ocr(window_title: Optional[str] = None) -> bytes:
    """Take a screenshot and return PNG bytes. Optionally target a window."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow nicht installiert — Screenshot nicht moeglich.")

    try:
        if window_title:
            # Try to capture specific window via ctypes
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            hwnd = user32.FindWindowW(None, None)
            found_hwnd = None
            while hwnd:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if window_title.lower() in buf.value.lower():
                            found_hwnd = hwnd
                            break
                hwnd = user32.GetWindow(hwnd, 2)  # GW_HWNDNEXT

            if found_hwnd:
                rect = wintypes.RECT()
                user32.GetWindowRect(found_hwnd, ctypes.byref(rect))
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                width = right - left
                height = bottom - top
                if width > 10 and height > 10:
                    img = ImageGrab.grab(bbox=(left, top, right, bottom))
                else:
                    img = ImageGrab.grab(all_screens=True)
            else:
                img = ImageGrab.grab(all_screens=True)
        else:
            img = ImageGrab.grab(all_screens=True)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"OCR Screenshot fehlgeschlagen: {e}")
        raise RuntimeError(f"Screenshot fuer OCR fehlgeschlagen: {e}")


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

def ocr_screenshot(image_bytes: bytes = None, window_title: str = None) -> dict:
    """Take a screenshot (or use provided bytes), run OCR, return result.

    Args:
        image_bytes: Optional pre-captured image bytes (PNG/JPEG)
        window_title: Optional window title to capture

    Returns:
        {"success": True, "data": {"text": "...", "word_count": N, "engine": "rapidocr", "duration_ms": X}}
    """
    start = time.monotonic()

    try:
        if image_bytes is None:
            image_bytes = _capture_for_ocr(window_title)

        text, engine, blocks = _run_ocr_with_blocks(image_bytes)
        duration_ms = round((time.monotonic() - start) * 1000)

        if text is None:
            return {
                "success": False,
                "error": "Kein OCR-Engine verfuegbar. Installiere: pip install rapidocr-onnxruntime",
            }

        word_count = len(text.split()) if text else 0
        return {
            "success": True,
            "data": {
                "text": text,
                "word_count": word_count,
                "engine": engine,
                "duration_ms": duration_ms,
                "blocks": blocks,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def ocr_from_bytes(image_bytes: bytes, lang: str = "en") -> dict:
    """Run OCR on raw image bytes.

    Args:
        image_bytes: Image data (PNG, JPEG, etc.)
        lang: Language hint (default "en")

    Returns:
        {"success": True, "data": {"text": "...", "word_count": N, "engine": "...", "duration_ms": X}}
    """
    start = time.monotonic()
    text, engine, blocks = _run_ocr_with_blocks(image_bytes, lang)
    duration_ms = round((time.monotonic() - start) * 1000)

    if text is None:
        return {
            "success": False,
            "error": "Kein OCR-Engine verfuegbar.",
        }

    word_count = len(text.split()) if text else 0
    return {
        "success": True,
        "data": {
            "text": text,
            "word_count": word_count,
            "engine": engine,
            "duration_ms": duration_ms,
            "blocks": blocks,
        },
    }


def _run_ocr(image_bytes: bytes, lang: str = "en") -> tuple:
    """Try OCR engines in order. Returns (text, engine_name) or (None, None)."""
    text, engine, _blocks = _run_ocr_with_blocks(image_bytes, lang)
    return text, engine


def _run_ocr_with_blocks(image_bytes: bytes, lang: str = "en") -> tuple:
    """Try OCR engines in order. Returns (text, engine_name, blocks)."""
    # 1. Try RapidOCR (fastest, most accurate)
    if _RAPIDOCR_AVAILABLE:
        text, blocks = _ocr_rapidocr_details(image_bytes, lang)
        if text is not None:
            return text, "rapidocr", blocks

    # 2. Fallback: pytesseract
    if _TESSERACT_AVAILABLE:
        tess_lang = "deu+eng" if lang == "de" else "eng"
        text = _ocr_tesseract(image_bytes, tess_lang)
        if text is not None:
            return text, "pytesseract", []

    return None, None, []


def get_ocr_status() -> dict:
    """Check which OCR engines are available.

    Returns:
        {"available": bool, "engines": [...], "primary": str|None}
    """
    engines = []
    primary = None

    if _RAPIDOCR_AVAILABLE:
        engines.append("rapidocr")
        if primary is None:
            primary = "rapidocr"

    if _TESSERACT_AVAILABLE:
        engines.append("pytesseract")
        if primary is None:
            primary = "pytesseract"

    return {
        "available": len(engines) > 0,
        "engines": engines,
        "primary": primary,
        "screenshot": _PIL_AVAILABLE,
    }
