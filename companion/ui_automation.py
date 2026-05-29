"""Windows UI Automation tools for Hermes.

This layer gives Hermes a semantic view of the desktop: windows, buttons,
text fields and other controls. It is intentionally small and conservative.
Read-only discovery tools are allowed directly; clicks still go through Lexa's
confirmation flow.
"""

from __future__ import annotations

import ctypes
import logging
import time
from typing import Any

from companion import desktop_control

try:
    from rapidfuzz import fuzz as _fuzz
except ImportError:  # pragma: no cover - rapidfuzz is a normal dependency
    _fuzz = None

logger = logging.getLogger("lexa.ui_automation")

MAX_TREE_DEPTH = 5
MAX_TREE_CONTROLS = 160
MAX_FIND_RESULTS = 20
MAX_UI_TARGET_CHARS = 80
MAX_CLICKABLE_NAME_CHARS = 140
LAST_UI_CONTEXT_TTL_SECONDS = 180.0

_ACTIONABLE_CONTROL_TYPES = {
    "Button",
    "CheckBox",
    "ComboBox",
    "DataItem",
    "Edit",
    "Hyperlink",
    "ListItem",
    "MenuItem",
    "RadioButton",
    "SplitButton",
    "TabItem",
    "TreeItem",
}

_LAST_UI_CONTEXT = {
    "window_title": "",
    "target_text": "",
    "target_control_type": "",
    "updated_at": 0.0,
    "target_updated_at": 0.0,
}

_DEFAULT_EXCLUDED_WINDOW_TITLES = (
    "lexa",
    "lexa ai",
    "codex",
    "taskleiste",
    "taskbar",
    "program manager",
    "start",
)

_MEDIA_PRIMARY_NAMES = {
    "play",
    "pause",
    "abspielen",
    "wiedergabe",
    "fortsetzen",
    "stopp",
    "stop",
    "weiter",
    "zurueck",
    "zuruck",
    "next",
    "previous",
}

_DEICTIC_TARGETS = {
    "darauf",
    "daruf",
    "drauf",
    "da drauf",
    "dadrueck",
    "dadruecken",
    "das",
    "den",
    "die",
    "diesen",
    "diese",
    "diesen button",
    "diese taste",
    "ihn",
    "sie",
    "es",
}


def _require_desktop():
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Windows UI Automation is only available on Windows")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise RuntimeError("pywinauto is not installed; install requirements.txt") from exc
    return Desktop(backend="uia")


def _foreground_hwnd() -> int:
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Windows UI Automation is only available on Windows")
    return int(ctypes.windll.user32.GetForegroundWindow())


def _safe_call(obj: Any, method_name: str, default: Any = None) -> Any:
    try:
        method = getattr(obj, method_name)
        return method()
    except Exception:
        return default


def _safe_attr(obj: Any, attr_name: str, default: Any = "") -> Any:
    try:
        return getattr(obj, attr_name)
    except Exception:
        return default


def _rect_to_dict(rect: Any) -> dict[str, int]:
    return {
        "left": int(_safe_attr(rect, "left", 0) or 0),
        "top": int(_safe_attr(rect, "top", 0) or 0),
        "right": int(_safe_attr(rect, "right", 0) or 0),
        "bottom": int(_safe_attr(rect, "bottom", 0) or 0),
    }


def _rect_center(rect: dict[str, int]) -> tuple[int, int]:
    x = int(round((rect["left"] + rect["right"]) / 2))
    y = int(round((rect["top"] + rect["bottom"]) / 2))
    return x, y


def _control_name(control: Any) -> str:
    name = str(_safe_call(control, "window_text", "") or "")
    if name:
        return name
    info = _safe_attr(control, "element_info", None)
    return str(_safe_attr(info, "name", "") or "")


def _control_type(control: Any) -> str:
    info = _safe_attr(control, "element_info", None)
    return str(_safe_attr(info, "control_type", "") or _safe_call(control, "friendly_class_name", "") or "")


def _control_to_dict(control: Any, *, window_title: str = "", depth: int = 0, score: float | None = None) -> dict:
    info = _safe_attr(control, "element_info", None)
    rect = _rect_to_dict(_safe_call(control, "rectangle", None))
    payload = {
        "name": _control_name(control),
        "control_type": _control_type(control),
        "class_name": str(_safe_call(control, "friendly_class_name", "") or ""),
        "automation_id": str(_safe_attr(info, "automation_id", "") or ""),
        "window_title": window_title,
        "depth": int(depth),
        "enabled": bool(_safe_call(control, "is_enabled", False)),
        "visible": bool(_safe_call(control, "is_visible", False)),
        "rect": rect,
    }
    if score is not None:
        payload["score"] = round(float(score), 3)
    return payload


def _normalize(value: str) -> str:
    return desktop_control._normalize_visible_text(value)


def _is_excluded_window_title(title: str) -> bool:
    normalized = _normalize(title)
    if not normalized:
        return True
    if normalized in _DEFAULT_EXCLUDED_WINDOW_TITLES:
        return True
    return normalized.startswith("lexa ") or normalized.startswith("codex ")


def _window_has_real_rect(window: Any) -> bool:
    rect = _rect_to_dict(_safe_call(window, "rectangle", None))
    return rect["right"] > rect["left"] and rect["bottom"] > rect["top"]


def _is_default_excluded_window(window: Any) -> bool:
    return _is_excluded_window_title(_window_title(window)) or not _window_has_real_rect(window)


def _remember_window_title(title: str) -> None:
    clean = str(title or "").strip()
    if not clean or _is_excluded_window_title(clean):
        return
    _LAST_UI_CONTEXT["window_title"] = clean
    _LAST_UI_CONTEXT["updated_at"] = time.time()


def _recent_window_title() -> str:
    title = str(_LAST_UI_CONTEXT.get("window_title") or "").strip()
    updated_at = float(_LAST_UI_CONTEXT.get("updated_at") or 0.0)
    if not title or time.time() - updated_at > LAST_UI_CONTEXT_TTL_SECONDS:
        return ""
    return title


def _remember_target_control(control: dict) -> None:
    if not isinstance(control, dict):
        return
    label = str(control.get("name") or control.get("automation_id") or "").strip()
    control_type = str(control.get("control_type") or "").strip()
    window_title = str(control.get("window_title") or "").strip()
    if not label or len(label) > MAX_CLICKABLE_NAME_CHARS:
        return
    if not _is_actionable_type(control_type):
        return
    if window_title and not _is_excluded_window_title(window_title):
        _remember_window_title(window_title)
    _LAST_UI_CONTEXT["target_text"] = label
    _LAST_UI_CONTEXT["target_control_type"] = control_type
    _LAST_UI_CONTEXT["target_updated_at"] = time.time()


def _recent_target_text() -> str:
    target = str(_LAST_UI_CONTEXT.get("target_text") or "").strip()
    updated_at = float(_LAST_UI_CONTEXT.get("target_updated_at") or 0.0)
    if not target or time.time() - updated_at > LAST_UI_CONTEXT_TTL_SECONDS:
        return ""
    return target


def _resolve_click_target_text(text: str) -> str:
    clean = str(text or "").strip()
    normalized = _normalize(clean)
    if normalized in _DEICTIC_TARGETS:
        recent = _recent_target_text()
        if recent:
            return recent
        raise ValueError("Kein zuletzt gesehenes UI-Control vorhanden. Bitte erst mit ui_find oder ui_tree orientieren.")
    return clean


def _is_actionable_type(control_type: str) -> bool:
    return str(control_type or "") in _ACTIONABLE_CONTROL_TYPES


def _window_title(window: Any) -> str:
    return _control_name(window) or str(_safe_call(window, "texts", [""])[0] if _safe_call(window, "texts", []) else "")


def _dedupe_windows(windows: list[Any]) -> list[Any]:
    seen: set[int] = set()
    unique: list[Any] = []
    for window in windows:
        handle = int(_safe_attr(window, "handle", 0) or 0)
        if handle and handle in seen:
            continue
        if handle:
            seen.add(handle)
        unique.append(window)
    return unique


def _candidate_windows(window: str = "", *, all_visible: bool = True, prefer_recent: bool = False) -> list[Any]:
    desktop = _require_desktop()
    explicit_query = str(window or "").strip()
    remembered_query = "" if explicit_query or not prefer_recent else _recent_window_title()
    query = _normalize(explicit_query or remembered_query)
    candidates: list[Any] = []
    allow_excluded = bool(explicit_query)

    if not query:
        try:
            foreground = desktop.window(handle=_foreground_hwnd()).wrapper_object()
            if allow_excluded or not _is_default_excluded_window(foreground):
                candidates.append(foreground)
        except Exception as exc:
            logger.debug("Could not read foreground UIA window: %s", exc)

    if query or all_visible or (not candidates and not query):
        try:
            for top in desktop.windows(visible_only=True):
                title = _normalize(_window_title(top))
                if not query or query in title or title in query:
                    if allow_excluded or not _is_default_excluded_window(top):
                        candidates.append(top)
        except Exception as exc:
            logger.debug("Could not enumerate UIA windows: %s", exc)

    unique = _dedupe_windows(candidates)
    if remembered_query and not unique:
        return _candidate_windows("", all_visible=all_visible, prefer_recent=False)
    if explicit_query and query and not unique:
        raise ValueError(f"window not found: {window}")
    return unique


def _iter_controls(window: Any, *, max_depth: int) -> list[tuple[Any, int]]:
    controls: list[tuple[Any, int]] = [(window, 0)]
    try:
        for control in window.descendants(depth=max_depth):
            controls.append((control, 1))
    except Exception as exc:
        logger.debug("Could not enumerate UIA descendants: %s", exc)
    return controls


def _score_control(control: Any, query: str, control_type: str = "") -> float:
    needle = _normalize(query)
    if not needle:
        return 0.0
    name = _normalize(_control_name(control))
    auto_id = _normalize(str(_safe_attr(_safe_attr(control, "element_info", None), "automation_id", "") or ""))
    haystacks = [value for value in (name, auto_id) if value]
    if not haystacks:
        return 0.0

    score = 0.0
    tokens = [token for token in needle.split() if token]
    for haystack in haystacks:
        if haystack == needle:
            score = max(score, 100.0)
        elif haystack.startswith(needle) or needle.startswith(haystack):
            score = max(score, 86.0)
        elif needle in haystack:
            score = max(score, 76.0)
        elif tokens and all(token in haystack for token in tokens):
            score = max(score, 64.0 + min(12.0, len(tokens) * 2.0))
        elif _fuzz is not None and len(haystack) <= MAX_CLICKABLE_NAME_CHARS:
            ratio = max(_fuzz.ratio(needle, haystack), _fuzz.partial_ratio(needle, haystack))
            if ratio >= 78:
                score = max(score, 68.0 + min(18.0, (float(ratio) - 78.0) / 1.2))

    if score <= 0:
        return 0.0

    current_type = _control_type(control)
    if control_type:
        wanted = _normalize(control_type)
        actual = _normalize(current_type)
        if wanted and wanted not in actual:
            return 0.0
        score += 10.0

    if current_type in _ACTIONABLE_CONTROL_TYPES:
        score += 18.0
    if bool(_safe_call(control, "is_enabled", False)):
        score += 4.0
    if bool(_safe_call(control, "is_visible", False)):
        score += 4.0

    rect = _rect_to_dict(_safe_call(control, "rectangle", None))
    if rect["right"] <= rect["left"] or rect["bottom"] <= rect["top"]:
        score -= 20.0

    return max(0.0, score)


def _find_controls(
    text: str,
    *,
    control_type: str = "",
    window: str = "",
    max_results: int = MAX_FIND_RESULTS,
    actionable_only: bool = False,
    prefer_recent: bool = False,
) -> list[dict]:
    target = str(text or "").strip()
    if not target:
        raise ValueError("text is required")
    if len(target) > MAX_UI_TARGET_CHARS:
        raise ValueError(f"text too long, max {MAX_UI_TARGET_CHARS} characters")

    results: list[dict] = []
    for window_index, top in enumerate(_candidate_windows(window, all_visible=True, prefer_recent=prefer_recent)):
        title = _window_title(top)
        for control, depth in _iter_controls(top, max_depth=MAX_TREE_DEPTH):
            current_type = _control_type(control)
            current_name = _control_name(control)
            if actionable_only and not _is_actionable_type(current_type):
                continue
            if actionable_only and len(current_name) > MAX_CLICKABLE_NAME_CHARS:
                continue
            score = _score_control(control, target, control_type)
            if score <= 0:
                continue
            payload = _control_to_dict(control, window_title=title, depth=depth, score=score)
            payload["_control"] = control
            payload["_window_index"] = window_index
            results.append(payload)

    results.sort(key=lambda item: (-float(item.get("score", 0)), int(item.get("_window_index", 999))))
    limit = max(1, min(MAX_FIND_RESULTS, int(max_results or MAX_FIND_RESULTS)))
    limited = results[:limit]
    if limited:
        _remember_target_control(limited[0])
    return limited


def _public_control_result(item: dict) -> dict:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _rank_primary_control(control: dict) -> tuple[int, int]:
    label = _normalize(str(control.get("name") or control.get("automation_id") or ""))
    control_type = str(control.get("control_type") or "")
    media_bonus = 0 if label in _MEDIA_PRIMARY_NAMES else 1
    type_bonus = 0 if control_type in {"Button", "SplitButton"} else 1
    return media_bonus, type_bonus


def _remember_primary_control(controls: list[dict]) -> None:
    actionable = [
        control
        for control in controls
        if _is_actionable_type(str(control.get("control_type") or ""))
        and str(control.get("name") or control.get("automation_id") or "").strip()
        and len(str(control.get("name") or control.get("automation_id") or "")) <= MAX_CLICKABLE_NAME_CHARS
    ]
    if not actionable:
        return
    actionable.sort(key=_rank_primary_control)
    _remember_target_control(actionable[0])


def ui_tree(window: str = "", max_depth: int = 3, max_controls: int = 80) -> dict:
    """Return a compact semantic UI tree for the foreground or named window."""
    depth = max(1, min(MAX_TREE_DEPTH, int(max_depth or 3)))
    limit = max(1, min(MAX_TREE_CONTROLS, int(max_controls or 80)))
    windows_payload: list[dict] = []
    total_controls = 0

    for top in _candidate_windows(window, all_visible=True):
        title = _window_title(top)
        _remember_window_title(title)
        controls: list[dict] = []
        for control, control_depth in _iter_controls(top, max_depth=depth):
            if len(controls) >= limit:
                break
            item = _control_to_dict(control, window_title=title, depth=control_depth)
            if item["name"] or item["automation_id"] or item["control_type"] in _ACTIONABLE_CONTROL_TYPES:
                controls.append(item)
        total_controls += len(controls)
        _remember_primary_control(controls)
        windows_payload.append({
            "title": title,
            "rect": _rect_to_dict(_safe_call(top, "rectangle", None)),
            "controls": controls,
        })
        if total_controls >= limit:
            break

    return {
        "windows": windows_payload,
        "window_count": len(windows_payload),
        "control_count": total_controls,
        "engine": "pywinauto-uia",
    }


def ui_find(text: str = "", control_type: str = "", window: str = "", max_results: int = 10) -> dict:
    """Find visible UI Automation controls by name or automation id."""
    matches = _find_controls(text, control_type=control_type, window=window, max_results=max_results)
    return {
        "matches": [_public_control_result(item) for item in matches],
        "count": len(matches),
        "engine": "pywinauto-uia",
    }


def ui_click(
    text: str = "",
    control_type: str = "",
    window: str = "",
    occurrence: int = 1,
    button: str = "left",
    fallback_ocr: bool = True,
) -> dict:
    """Click a semantic Windows UI control by text/name, with OCR fallback."""
    target_text = _resolve_click_target_text(text)
    matches = _find_controls(
        target_text,
        control_type=control_type,
        window=window,
        max_results=MAX_FIND_RESULTS,
        actionable_only=True,
        prefer_recent=True,
    )
    if not matches:
        if fallback_ocr:
            result = desktop_control.desktop_click_text(text=target_text, button=button, occurrence=occurrence, window=window)
            result["method"] = "ocr-fallback"
            return result
        raise ValueError(f"UI control not found: {target_text}")

    index = max(1, int(occurrence or 1)) - 1
    match = matches[min(index, len(matches) - 1)]
    _remember_target_control(match)
    rect = match["rect"]
    x, y = _rect_center(rect)
    click_result = desktop_control.desktop_click(x=x, y=y, button=button, clicks=1)
    return {
        "clicked": True,
        "target": target_text,
        "matched_text": match.get("name") or match.get("automation_id") or str(text or "").strip(),
        "control_type": match.get("control_type", ""),
        "automation_id": match.get("automation_id", ""),
        "window_title": match.get("window_title", ""),
        "x": click_result["x"],
        "y": click_result["y"],
        "score": match.get("score"),
        "method": "ui-automation",
    }
