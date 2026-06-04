"""Provider facade for Hermes desktop observation.

Hermes should not care which low-level engine can read a window best. This
module keeps a stable Lexa-owned contract while providers can evolve behind it:
Windows UIA, OCR, and later optional external engines such as Touchpoint or
SikuliX.
"""

from __future__ import annotations

import time
import ctypes
import importlib.util
import os
import queue
import shutil
import threading
from pathlib import Path
from typing import Any

from companion import ocr, ui_automation

ENGINE_ID = "lexa-hermes-desktop-engine"
TEXT_PREVIEW_CHARS = 500
UIA_TEXT_TIMEOUT_SECONDS = 4.0
UI_TREE_TIMEOUT_SECONDS = 5.0
TEXT_READ_TIMEOUT_SECONDS = 10.0


def _call_with_timeout(func, *, timeout_seconds: float, label: str) -> Any:
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, func()))
        except Exception as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, name=f"hermes-desktop-{label}", daemon=True)
    thread.start()
    thread.join(max(0.1, float(timeout_seconds or 1.0)))
    if thread.is_alive():
        raise TimeoutError(f"{label} timed out after {timeout_seconds:.1f}s")
    ok, payload = result_queue.get_nowait()
    if ok:
        return payload
    raise payload


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _command_available(*names: str) -> bool:
    return any(bool(shutil.which(name)) for name in names)


def _env_path_exists(name: str) -> bool:
    value = os.getenv(name, "").strip().strip('"')
    if not value:
        return False
    try:
        return Path(value).exists()
    except OSError:
        return False


def _provider(
    provider_id: str,
    role: str,
    *,
    available: bool,
    active: bool,
    optional: bool = False,
    backend: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": provider_id,
        "role": role,
        "available": bool(available),
        "active": bool(active),
        "optional": bool(optional),
    }
    if backend:
        item["backend"] = backend
    return item


def provider_status() -> dict[str, Any]:
    """Return the current Hermes desktop provider stack.

    This is intentionally read-only. Lexa can expose it to the model so Hermes
    knows which engines can observe, ground, and act on the desktop.
    """
    uia_available = hasattr(ctypes, "windll") and _module_available("pywinauto")
    ocr_available = bool(
        getattr(ocr, "_PIL_AVAILABLE", False)
        and (getattr(ocr, "_RAPIDOCR_AVAILABLE", False) or getattr(ocr, "_TESSERACT_AVAILABLE", False))
    )
    touchpoint_available = _module_available("touchpoint") or _command_available("touchpoint")
    sikulix_available = _command_available("sikulix", "runsikulix", "sikulixide")
    ufo_available = _env_path_exists("LEXA_UFO_PATH") or _module_available("ufo")

    return {
        "engine": ENGINE_ID,
        "providers": [
            _provider("uia", "semantic_windows_controls", available=uia_available, active=uia_available, backend="pywinauto"),
            _provider("ocr", "visual_text_fallback", available=ocr_available, active=ocr_available, backend="rapidocr_or_tesseract"),
            _provider("touchpoint", "external_accessibility_mcp", available=touchpoint_available, active=False, optional=True),
            _provider("sikulix", "vision_click_fallback", available=sikulix_available, active=False, optional=True),
            _provider("ufo", "windows_agent_reference_runtime", available=ufo_available, active=False, optional=True),
        ],
        "strategy": [
            "Use UIA for semantic windows, controls, and safe target grounding.",
            "Use OCR when text is visible but not exposed as UIA controls.",
            "Keep mutating actions behind Lexa confirmation.",
            "Allow optional external providers to be added behind this facade.",
        ],
        "safety": {
            "read_only_observation": True,
            "mutating_actions_require_confirmation": True,
            "raw_coordinates_are_fallback_only": True,
        },
    }


def ocr_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    return payload if isinstance(payload, dict) else {}


def readable_ui_text(data: dict[str, Any]) -> str:
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    primary: list[str] = []
    secondary: list[str] = []
    seen: set[str] = set()
    for window in windows:
        if not isinstance(window, dict):
            continue
        title = str(window.get("title") or "").strip().casefold()
        for control in window.get("controls") or []:
            if not isinstance(control, dict):
                continue
            label = str(control.get("name") or control.get("value") or "").strip()
            if not label:
                continue
            folded = label.casefold()
            if folded in seen or folded == title:
                continue
            seen.add(folded)
            ctype = str(control.get("control_type") or "")
            if ctype in {"Document", "Edit"}:
                primary.append(label)
            elif ctype == "Text" and len(label) > 2:
                secondary.append(label)
    chosen = primary or secondary
    return "\n".join(chosen).strip()


def _word_count(text: str) -> int:
    return len(str(text or "").split())


def _text_preview(text: str, limit: int = TEXT_PREVIEW_CHARS) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def read_screen_text(window: str = "") -> dict[str, Any]:
    """Read visible text through the best available local provider.

    OCR stays the first provider because it works across arbitrary apps. If a
    named window returns empty OCR text, UI Automation is tried as a semantic
    fallback. This fixes apps like Notepad where the real document text is
    exposed as a UIA Document control even when the screenshot OCR is blank.
    """
    started = time.monotonic()
    target_window = str(window or "").strip()
    providers_tried = ["ocr"]
    ocr_result = ocr.ocr_screenshot(window_title=target_window or None)
    payload = ocr_payload(ocr_result)
    text = str(payload.get("text") or "").strip()
    if ocr_result.get("success") and text:
        payload["method"] = payload.get("method") or "ocr"
        payload["provider"] = payload.get("provider") or "ocr"
        payload["providers_tried"] = providers_tried
        return ocr_result

    ui_tree_data: dict[str, Any] | None = None
    ui_error = ""
    if target_window:
        providers_tried.append("uia_text")
        try:
            ui_tree_data = _call_with_timeout(
                lambda: ui_automation.ui_tree(window=target_window, max_depth=3, max_controls=120),
                timeout_seconds=UIA_TEXT_TIMEOUT_SECONDS,
                label="uia_text",
            )
            ui_text = readable_ui_text(ui_tree_data)
        except Exception as exc:
            ui_error = str(exc)
            ui_text = ""
        if ui_text:
            duration_ms = round((time.monotonic() - started) * 1000)
            return {
                "success": True,
                "data": {
                    "text": ui_text,
                    "word_count": _word_count(ui_text),
                    "engine": "uia",
                    "method": "uia_text",
                    "provider": "uia_text",
                    "providers_tried": providers_tried,
                    "duration_ms": duration_ms,
                    "window": target_window,
                },
                "ui_text_data": ui_tree_data,
                "ocr": ocr_result,
            }

    if isinstance(payload, dict):
        payload["method"] = payload.get("method") or "ocr"
        payload["provider"] = payload.get("provider") or "ocr"
        payload["providers_tried"] = providers_tried
        if ui_error:
            payload["uia_error"] = ui_error[:200]
    return ocr_result


def observe(
    window: str = "",
    include_text: bool = True,
    max_depth: int = 3,
    max_controls: int = 80,
    window_title: str = "",
) -> dict[str, Any]:
    """Observe a desktop window with the configured provider stack.

    This combines a semantic UI tree with optional readable screen text. It is
    the stable read-only API for future Hermes agent planning.
    """
    started = time.monotonic()
    target_window = str(window or window_title or "").strip()
    depth = max(1, min(5, int(max_depth or 3)))
    control_limit = max(1, min(160, int(max_controls or 80)))

    ui_data: dict[str, Any] = {}
    ui_error = ""
    try:
        ui_data = _call_with_timeout(
            lambda: ui_automation.ui_tree(window=target_window, max_depth=depth, max_controls=control_limit),
            timeout_seconds=UI_TREE_TIMEOUT_SECONDS,
            label="ui_tree",
        )
    except Exception as exc:
        ui_error = str(exc)

    text_result: dict[str, Any] = {}
    text_payload: dict[str, Any] = {}
    if include_text:
        try:
            text_result = _call_with_timeout(
                lambda: read_screen_text(window=target_window),
                timeout_seconds=TEXT_READ_TIMEOUT_SECONDS,
                label="read_screen_text",
            )
            text_payload = ocr_payload(text_result)
        except Exception as exc:
            text_result = {"success": False, "error": str(exc)}

    windows = ui_data.get("windows") if isinstance(ui_data.get("windows"), list) else []
    window_titles = [str(item.get("title") or "") for item in windows if isinstance(item, dict)]
    text = str(text_payload.get("text") or "")
    text_success = bool(text_result.get("success") and text.strip())
    ui_success = bool(windows or int(ui_data.get("control_count") or 0) > 0)

    return {
        "engine": ENGINE_ID,
        "success": bool(ui_success or text_success),
        "window": target_window,
        "providers": provider_status()["providers"],
        "ui": ui_data,
        "text": text_payload if include_text else {},
        "text_result": text_result if include_text else {},
        "summary": {
            "window_titles": window_titles[:10],
            "window_count": int(ui_data.get("window_count") or len(window_titles)),
            "control_count": int(ui_data.get("control_count") or 0),
            "text_preview": _text_preview(text),
            "providers_tried": text_payload.get("providers_tried", []),
        },
        "errors": {
            "ui": ui_error,
            "text": str(text_result.get("error") or "") if include_text and not text_result.get("success") else "",
        },
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
