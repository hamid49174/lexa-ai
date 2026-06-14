"""Controlled desktop input tools for Hermes.

These functions intentionally expose small, auditable primitives instead of a
raw shell. Read-only state is allowed directly; actions that move/click/type are
listed as confirmation-required in the command whitelist.
"""

from __future__ import annotations

import ctypes
import re
import time
import unicodedata
from ctypes import wintypes


user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

MAX_TYPE_CHARS = 1000
MAX_HOTKEY_KEYS = 4
MAX_CLICKS = 3
MAX_WAIT_SECONDS = 10.0
MAX_SCROLL_CLICKS = 20
MAX_CLICK_TEXT_CHARS = 80

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


_KEY_MAP = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "win": 0x5B,
    "meta": 0x5B,
    "cmd": 0x5B,
    "menu": 0x5D,
    "plus": 0xBB,
    "minus": 0xBD,
}
for _idx in range(1, 13):
    _KEY_MAP[f"f{_idx}"] = 0x6F + _idx
for _char in "abcdefghijklmnopqrstuvwxyz":
    _KEY_MAP[_char] = ord(_char.upper())
for _digit in "0123456789":
    _KEY_MAP[_digit] = ord(_digit)

_HOTKEY_KEY_ALIASES = {
    "strg": "ctrl",
    "control": "ctrl",
    "steuerung": "ctrl",
    "umschalt": "shift",
    "links": "left",
    "rechts": "right",
    "oben": "up",
    "unten": "down",
    "pfeillinks": "left",
    "pfeilrechts": "right",
    "pfeiloben": "up",
    "pfeilunten": "down",
    "pfeilhoch": "up",
    "pfeilrunter": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "arrowup": "up",
    "arrowdown": "down",
    "bildauf": "pageup",
    "bildhoch": "pageup",
    "bildab": "pagedown",
    "bildrunter": "pagedown",
    "pos1": "home",
    "anfang": "home",
    "ende": "end",
    "einfg": "insert",
    "einfuegen": "insert",
    "eingabe": "enter",
    "eingabetaste": "enter",
    "entf": "delete",
    "loeschen": "delete",
    "loschen": "delete",
    "ruecktaste": "backspace",
    "rucktaste": "backspace",
    "leer": "space",
    "leertaste": "space",
}
_HOTKEY_CONNECTOR_TOKENS = {"und", "plus", "mit"}


def _screen_size() -> tuple[int, int]:
    api = _require_user32()
    return int(api.GetSystemMetrics(0)), int(api.GetSystemMetrics(1))


def _require_user32():
    if user32 is None:
        raise RuntimeError("Desktop control is only available on Windows")
    return user32


def _screen_bounds() -> tuple[int, int, int, int]:
    api = _require_user32()
    left = int(api.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(api.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(api.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(api.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        width, height = _screen_size()
        return 0, 0, width, height
    return left, top, width, height


def _clamp_point(x: int, y: int) -> tuple[int, int]:
    left, top, width, height = _screen_bounds()
    right = left + width - 1
    bottom = top + height - 1
    return max(left, min(int(x), right)), max(top, min(int(y), bottom))


def _cursor_position() -> tuple[int, int]:
    api = _require_user32()
    point = POINT()
    api.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _send_input(*inputs: INPUT) -> None:
    api = _require_user32()
    array_type = INPUT * len(inputs)
    sent = api.SendInput(len(inputs), array_type(*inputs), ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise OSError("SendInput did not accept all input events")


def _key_input(vk: int, *, up: bool = False) -> INPUT:
    return INPUT(
        type=1,
        union=INPUT_UNION(ki=KEYBDINPUT(
            wVk=vk,
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP if up else 0,
            time=0,
            dwExtraInfo=None,
        )),
    )


def _unicode_input(code_unit: int, *, up: bool = False) -> INPUT:
    # code_unit must be a single UTF-16 code unit (16 bit). Code points beyond
    # the BMP have to be split into a surrogate pair by the caller, because
    # wScan is a 16-bit WORD and would silently truncate larger values.
    return INPUT(
        type=1,
        union=INPUT_UNION(ki=KEYBDINPUT(
            wVk=0,
            wScan=int(code_unit) & 0xFFFF,
            dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
            time=0,
            dwExtraInfo=None,
        )),
    )


def _char_to_code_units(char: str) -> list[int]:
    # Return the UTF-16 code units for a character. BMP characters yield a
    # single unit; characters beyond the BMP (e.g. emoji) yield a surrogate
    # pair so each unit can be sent as its own KEYEVENTF_UNICODE input.
    if ord(char) <= 0xFFFF:
        return [ord(char)]
    encoded = char.encode("utf-16-le")
    return [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]


def _mouse_event(flags: int, data: int = 0) -> None:
    _require_user32().mouse_event(flags, 0, 0, data, 0)


def _parse_hotkey_keys(keys: str | list[str]) -> list[str]:
    if isinstance(keys, str):
        explicit_separator = "+" in keys or "," in keys
        raw = _split_hotkey_string(keys)
    elif isinstance(keys, list):
        explicit_separator = False
        raw = keys
    else:
        raise ValueError("keys must be a string like 'ctrl+l' or a list")
    parsed = []
    for key in raw:
        normalized = _normalize_hotkey_key(key)
        if not str(key).strip() or not normalized:
            continue
        if normalized in _HOTKEY_CONNECTOR_TOKENS and not (explicit_separator and normalized in _KEY_MAP):
            continue
        parsed.append(normalized)
    if not parsed or len(parsed) > MAX_HOTKEY_KEYS:
        raise ValueError(f"hotkeys need 1-{MAX_HOTKEY_KEYS} keys")
    unknown = [key for key in parsed if key not in _KEY_MAP]
    if unknown:
        raise ValueError(f"unknown key(s): {', '.join(unknown)}")
    return parsed


def _split_hotkey_string(keys: str) -> list[str]:
    text = str(keys or "").strip()
    if not text:
        return []
    if "+" in text or "," in text:
        return re.split(r"[+,]", text)
    if _normalize_hotkey_key(text) in _KEY_MAP:
        return [text]
    return text.split()


def _normalize_hotkey_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", "", normalized)
    return _HOTKEY_KEY_ALIASES.get(normalized, normalized)


def _normalize_visible_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _window_capture_origin(window_title: str) -> tuple[int, int] | None:
    """Return the screen top-left of the window OCR captured, or None.

    ocr._capture_for_ocr grabs only the window region via GetWindowRect when a
    window title is given, so OCR bbox coordinates are relative to that window's
    top-left corner. To turn them into absolute screen coordinates we must add
    exactly that corner. The window lookup mirrors ocr._capture_for_ocr (visible
    windows, case-insensitive substring match) so the same hwnd is resolved.
    Returns None when no window is targeted or no match is found, in which case
    OCR fell back to the full virtual screen and _screen_bounds() applies.
    """
    target = str(window_title or "").strip()
    if not target:
        return None
    api = _require_user32()
    needle = target.lower()
    hwnd = api.FindWindowW(None, None)
    found_hwnd = None
    while hwnd:
        if api.IsWindowVisible(hwnd):
            length = api.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                api.GetWindowTextW(hwnd, buf, length + 1)
                if needle in str(buf.value or "").lower():
                    found_hwnd = hwnd
                    break
        hwnd = api.GetWindow(hwnd, 2)  # GW_HWNDNEXT
    if not found_hwnd:
        return None
    rect = wintypes.RECT()
    if not api.GetWindowRect(found_hwnd, ctypes.byref(rect)):
        # GetWindowRect failed; rect would stay zero-filled and yield a bogus
        # (0, 0) origin. Treat this like "no match" so the caller falls back to
        # the full-screen origin from _screen_bounds() instead of misclicking.
        return None
    width = int(rect.right) - int(rect.left)
    height = int(rect.bottom) - int(rect.top)
    # Mirror ocr._capture_for_ocr: tiny windows fall back to full-screen capture.
    if width <= 10 or height <= 10:
        return None
    return int(rect.left), int(rect.top)


def _block_center(block: dict, *, offset_x: int = 0, offset_y: int = 0) -> tuple[int, int]:
    bbox = block.get("bbox") if isinstance(block, dict) else None
    if not isinstance(bbox, dict):
        raise ValueError("OCR block has no bbox")
    try:
        left = float(bbox["left"])
        top = float(bbox["top"])
        right = float(bbox["right"])
        bottom = float(bbox["bottom"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("OCR block has invalid bbox") from exc
    return int(round(offset_x + (left + right) / 2)), int(round(offset_y + (top + bottom) / 2))


def _find_ocr_text_block(blocks: list[dict], query: str, occurrence: int = 1) -> dict | None:
    needle = _normalize_visible_text(query)
    if not needle:
        return None
    matches: list[dict] = []
    for block in blocks or []:
        haystack = _normalize_visible_text(block.get("text", "") if isinstance(block, dict) else "")
        if needle and (needle in haystack or haystack in needle):
            matches.append(block)
    if not matches:
        return None
    index = max(1, int(occurrence or 1)) - 1
    return matches[min(index, len(matches) - 1)]


def desktop_position() -> dict:
    """Return cursor position and screen size."""
    x, y = _cursor_position()
    width, height = _screen_size()
    left, top, virtual_width, virtual_height = _screen_bounds()
    return {
        "x": x,
        "y": y,
        "screen_width": width,
        "screen_height": height,
        "virtual_x": left,
        "virtual_y": top,
        "virtual_width": virtual_width,
        "virtual_height": virtual_height,
    }


def desktop_move(x: int = 0, y: int = 0) -> dict:
    """Move cursor to an absolute screen coordinate."""
    api = _require_user32()
    target_x, target_y = _clamp_point(int(x), int(y))
    if not api.SetCursorPos(target_x, target_y):
        raise OSError("SetCursorPos failed")
    return {"moved": True, "x": target_x, "y": target_y, **desktop_position()}


def desktop_click(x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1) -> dict:
    """Click at the current or supplied coordinate."""
    button = str(button or "left").lower().strip()
    clicks = max(1, min(MAX_CLICKS, int(clicks or 1)))
    if x is not None and y is not None:
        desktop_move(int(x), int(y))
    down_up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button)
    if not down_up:
        raise ValueError("button must be left, right, or middle")
    down, up = down_up
    for _ in range(clicks):
        _mouse_event(down)
        time.sleep(0.03)
        _mouse_event(up)
        time.sleep(0.05)
    pos = desktop_position()
    return {"clicked": True, "button": button, "clicks": clicks, "x": pos["x"], "y": pos["y"]}


def desktop_click_text(text: str = "", button: str = "left", occurrence: int = 1, window: str = "") -> dict:
    """Find visible OCR text on the desktop and click its center."""
    target = str(text or "").strip()
    if not target:
        raise ValueError("text is required")
    if len(target) > MAX_CLICK_TEXT_CHARS:
        raise ValueError(f"text too long, max {MAX_CLICK_TEXT_CHARS} characters")

    from companion import ocr

    window_title = str(window or "").strip()
    result = ocr.ocr_screenshot(window_title=window_title or None)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or "OCR failed")
    payload = result.get("data") or {}
    blocks = payload.get("blocks") or []
    match = _find_ocr_text_block(blocks, target, occurrence)
    if match is None:
        raise ValueError(f"visible text not found: {target}")

    # When a window is targeted, OCR captured only that window region, so block
    # coordinates are relative to the window's top-left corner. Add the window
    # origin in that case; only the full-screen capture is relative to the
    # virtual screen origin from _screen_bounds().
    window_origin = _window_capture_origin(window_title) if window_title else None
    if window_origin is not None:
        offset_x, offset_y = window_origin
    else:
        offset_x, offset_y, _, _ = _screen_bounds()
    x, y = _block_center(match, offset_x=offset_x, offset_y=offset_y)
    click_result = desktop_click(x=x, y=y, button=button, clicks=1)
    return {
        "clicked": True,
        "target": target,
        "matched_text": match.get("text", ""),
        "x": click_result["x"],
        "y": click_result["y"],
        "engine": payload.get("engine"),
    }


def desktop_scroll(clicks: int = -3) -> dict:
    """Scroll at the current cursor position. Negative scrolls down, positive up.

    Windows delivers mouse-wheel events to the window under the cursor, not to
    the focused window. Callers that want to scroll a specific window must park
    the cursor over it first (hermes_desktop._center_cursor_on_window does this
    before invoking this function).
    """
    amount = max(-MAX_SCROLL_CLICKS, min(MAX_SCROLL_CLICKS, int(clicks or 0)))
    if amount == 0:
        return {"scrolled": False, "clicks": 0}
    _mouse_event(MOUSEEVENTF_WHEEL, amount * 120)
    return {"scrolled": True, "clicks": amount}


def desktop_type(text: str = "", interval_ms: int = 0) -> dict:
    """Type unicode text into the active control."""
    if not isinstance(text, str) or not text:
        raise ValueError("text is required")
    if len(text) > MAX_TYPE_CHARS:
        raise ValueError(f"text too long, max {MAX_TYPE_CHARS} characters")
    interval = max(0, min(500, int(interval_ms or 0))) / 1000.0
    for char in text:
        code_units = _char_to_code_units(char)
        # Surrogate pairs (non-BMP, e.g. emoji) must be delivered together: send
        # all key-down units, then all key-up units, so Windows reassembles the
        # full code point instead of receiving two truncated halves.
        downs = [_unicode_input(unit) for unit in code_units]
        ups = [_unicode_input(unit, up=True) for unit in code_units]
        _send_input(*downs, *ups)
        if interval:
            time.sleep(interval)
    return {"typed": True, "characters": len(text)}


def desktop_hotkey(keys: str | list[str] = "") -> dict:
    """Press a bounded hotkey combination such as ctrl+l or alt+tab."""
    parsed = _parse_hotkey_keys(keys)
    vks = [_KEY_MAP[key] for key in parsed]
    pressed: list[int] = []
    try:
        for vk in vks:
            _send_input(_key_input(vk))
            pressed.append(vk)
            time.sleep(0.01)
    finally:
        # Always release every key we managed to press, even if a down/up event
        # failed midway. Otherwise a modifier (ctrl/alt/shift) could stay stuck
        # in the pressed state until the user presses it manually.
        for vk in reversed(pressed):
            try:
                _send_input(_key_input(vk, up=True))
            except OSError:
                continue
            time.sleep(0.01)
    return {"pressed": True, "keys": parsed}


def desktop_wait(seconds: float = 1.0) -> dict:
    """Pause a desktop automation chain for a short, bounded time."""
    value = max(0.0, min(MAX_WAIT_SECONDS, float(seconds or 0)))
    time.sleep(value)
    return {"waited": True, "seconds": value}
