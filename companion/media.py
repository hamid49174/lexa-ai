"""Lexa AI — Media-Steuerung
Spotify, lokale Musik, Medien-Tasten, ffmpeg

Media keys use ctypes keybd_event (OS-level virtual key codes).
This is keyboard-layout independent and works on ALL Windows systems.
Same approach as PowerToys, AutoHotkey, Flow Launcher.

Spotify integration:
- Primary: Spotify Web API (Client Credentials, free, no Premium)
  → Search artist/track → get URI → open with spotify:track:{id} (auto-plays)
- Fallback: spotify:search:{query} URI + delayed media play key
"""

import ctypes
import os
import subprocess
import logging
import threading
import time
import urllib.parse
from pathlib import Path

import keyring
from backend.config import LEXA_DATA_DIR
from backend.i18n import t

logger = logging.getLogger("lexa.media")

_DATA_DIR = LEXA_DATA_DIR

# ══════════════════════════════════════════════════
#  WINDOWS VIRTUAL KEY CODES — OS-level, layout-independent
# ══════════════════════════════════════════════════
_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_MEDIA_STOP = 0xB2
_KEYEVENTF_KEYUP = 0x0002


def _press_media_key(vk_code: int) -> None:
    """Simulate a media key press + release using Windows keybd_event API.

    Works with any media player (Spotify, VLC, foobar2000, Windows Media Player, etc.)
    because media key events are handled at the OS level, not per-application.
    """
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)                # key down
    ctypes.windll.user32.keybd_event(vk_code, 0, _KEYEVENTF_KEYUP, 0)  # key up


def _validate_media_path(path: str, must_exist: bool = True) -> str | None:
    """Returns error string if path is invalid, None if OK."""
    if not path:
        return "Kein Pfad angegeben."
    p = Path(path)
    if must_exist and not p.exists():
        return f"Datei nicht gefunden: {path}"
    # Block system directories
    resolved = str(p.resolve()).lower()
    blocked = ["system32", "syswow64", "windows\\system", "program files\\windows"]
    if any(b in resolved for b in blocked):
        return "Systemverzeichnis nicht erlaubt."
    return None


# ══════════════════════════════════════════════════
#  MEDIA KEYS — instant, no PowerShell spawn
# ══════════════════════════════════════════════════

def media_play_pause() -> str:
    """Play/Pause toggle via OS-level media key."""
    _press_media_key(_VK_MEDIA_PLAY_PAUSE)
    return "Play/Pause umgeschaltet."


def media_next() -> str:
    """Next track via OS-level media key."""
    _press_media_key(_VK_MEDIA_NEXT_TRACK)
    return "Nächster Track."


def media_prev() -> str:
    """Previous track via OS-level media key."""
    _press_media_key(_VK_MEDIA_PREV_TRACK)
    return "Vorheriger Track."


def media_stop() -> str:
    """Stop playback via OS-level media key."""
    _press_media_key(_VK_MEDIA_STOP)
    return "Wiedergabe gestoppt."


# ══════════════════════════════════════════════════
#  SPOTIFY — Web API + URI scheme
# ══════════════════════════════════════════════════

# Cache the Spotify access token (expires after 3600s)
_spotify_token_cache: dict = {"token": None, "expires_at": 0}


def _get_spotify_token() -> str | None:
    """Get a Spotify access token via Client Credentials flow (free, no Premium).

    Requires 'spotify_client_id' and 'spotify_client_secret' in keyring.
    Get them free at https://developer.spotify.com/dashboard
    """
    now = time.time()
    if _spotify_token_cache["token"] and now < _spotify_token_cache["expires_at"] - 60:
        return _spotify_token_cache["token"]

    try:
        client_id = keyring.get_password("lexa-ai", "spotify_client_id")
        client_secret = keyring.get_password("lexa-ai", "spotify_client_secret")
    except Exception:
        return None

    if not client_id or not client_secret:
        return None

    try:
        import base64
        import requests
        auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {auth}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            _spotify_token_cache["token"] = data["access_token"]
            _spotify_token_cache["expires_at"] = now + data.get("expires_in", 3600)
            return data["access_token"]
    except Exception as e:
        logger.debug(f"Spotify token fetch failed: {e}")

    return None


def _spotify_api_search(query: str, type_: str = "artist,track") -> dict | None:
    """Search Spotify via Web API. Returns first result with URI.

    Returns: {"type": "track"|"artist", "name": str, "uri": str, "artist": str}
    """
    token = _get_spotify_token()
    if not token:
        return None

    try:
        import requests
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query[:200], "type": type_, "limit": 5, "market": "DE"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()

        # Check tracks first (user probably wants to hear a song)
        tracks = data.get("tracks", {}).get("items", [])
        if tracks:
            t = tracks[0]
            artist_names = ", ".join(a["name"] for a in t.get("artists", []))
            return {
                "type": "track",
                "name": t["name"],
                "uri": t["uri"],
                "artist": artist_names,
                "id": t["id"],
            }

        # Then check artists
        artists = data.get("artists", {}).get("items", [])
        if artists:
            a = artists[0]
            return {
                "type": "artist",
                "name": a["name"],
                "uri": a["uri"],
                "artist": a["name"],
                "id": a["id"],
            }
    except Exception as e:
        logger.debug(f"Spotify API search failed: {e}")

    return None


def _find_spotify_window() -> int | None:
    """Find Spotify main window via Win32 EnumWindows. Returns HWND or None."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    spotify_hwnd = None

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        nonlocal spotify_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            # Spotify window titles: "Spotify", "Artist - Song - Spotify", "Spotify Premium"
            if "spotify" in title:
                spotify_hwnd = hwnd
                return False
        return True

    user32.EnumWindows(_enum_cb, 0)
    return spotify_hwnd


def _focus_spotify_window(hwnd: int) -> bool:
    """Focus + restore Spotify window. Returns True if successful."""
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        return True
    except Exception:
        return False


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Get window position: (left, top, right, bottom)."""
    from ctypes import wintypes
    rect = wintypes.RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def _get_window_title(hwnd: int) -> str:
    """Get window title text."""
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    return ""


def _click_at(x: int, y: int) -> None:
    """Click at screen coordinates using ctypes (no pyautogui needed)."""
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.05)
    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP = 0x0004
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _double_click_at(x: int, y: int) -> None:
    """Double-click at screen coordinates."""
    _click_at(x, y)
    time.sleep(0.08)
    _click_at(x, y)


def _is_playing(hwnd: int, idle_titles: set) -> bool:
    """Check if Spotify is playing by window title change.

    When playing: title = "Artist - Song - Spotify"
    When idle: title = "Spotify" or "Spotify Premium" or "Spotify Free"
    """
    title = _get_window_title(hwnd).strip()
    return bool(title and title.lower() not in idle_titles)


def _get_dpi_scale() -> float:
    """Get Windows DPI scaling factor (1.0 = 100%, 1.25 = 125%, etc.)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def _spotify_auto_play(delay: float = 3.5) -> None:
    """Wait for Spotify to load search results, then click the first song.

    Zero-config approach — no API keys, no pyautogui:
    1. Wait for Spotify to load
    2. Find + focus Spotify window via Win32 API
    3. Scan multiple click positions (hybrid: fixed px header + ratio body)
    4. After each click, check window title to detect playback
    5. Fallback: media play key
    """
    time.sleep(delay)

    hwnd = _find_spotify_window()
    if not hwnd:
        time.sleep(2.5)
        hwnd = _find_spotify_window()

    if not hwnd:
        _press_media_key(_VK_MEDIA_PLAY_PAUSE)
        logger.info("Spotify: fallback media play key (window not found)")
        return

    idle_titles = {"spotify", "spotify premium", "spotify free", "spotify – suche"}

    _focus_spotify_window(hwnd)

    rect = _get_window_rect(hwnd)
    if not rect:
        _press_media_key(_VK_MEDIA_PLAY_PAUSE)
        return

    left, top, right, bottom = rect
    w = right - left
    h = bottom - top

    # DPI-aware pixel offsets
    scale = _get_dpi_scale()

    # Spotify layout (2024+ desktop app):
    # - Title bar: ~32px
    # - Nav bar + search: ~64px
    # - Filter pills ("All", "Songs", ...): ~48px
    # - Content padding: ~16px
    # Total header ≈ 160px (at 100% DPI)
    #
    # Content area:
    # - Left ~45%: "Top Result" card
    # - Right ~55%: "Songs" list (each row ~56px)
    #
    # Sidebar: ~250-300px expanded, ~72px collapsed
    header_px = int(160 * scale)
    row_height = int(56 * scale)

    # Scan positions: (x_ratio, y_pixels_from_top)
    # Try Songs list first (most reliable), then Top Result area
    scan_positions = [
        # Songs list — first 4 rows at different heights
        (0.60, header_px + int(28 * scale)),    # Row 1 center
        (0.60, header_px + row_height + int(28 * scale)),  # Row 2 center
        (0.55, header_px + int(28 * scale)),    # Row 1, slightly left
        (0.65, header_px + int(28 * scale)),    # Row 1, slightly right
        # Top Result play button area (hover to reveal, then click)
        (0.33, header_px + int(100 * scale)),   # Top Result center
        (0.33, header_px + int(60 * scale)),    # Top Result higher
        # Songs at larger offsets (maximized window, ads banner, etc.)
        (0.60, header_px + int(100 * scale)),   # Further down
        (0.60, header_px + int(140 * scale)),   # Even further
    ]

    for x_ratio, y_offset in scan_positions:
        click_x = left + int(w * x_ratio)
        click_y = top + y_offset

        # Safety: don't click outside window or in bottom player bar (~90px)
        if click_y >= bottom - int(90 * scale) or click_y <= top:
            continue

        _double_click_at(click_x, click_y)
        logger.debug(f"Spotify scan: click at ({click_x}, {click_y}), ratio=({x_ratio}, {y_offset})")
        time.sleep(1.2)

        if _is_playing(hwnd, idle_titles):
            logger.info(f"Spotify: playback started after click at ({click_x}, {click_y})")
            return

    # Last resort: media play key (resumes last track if nothing else works)
    _press_media_key(_VK_MEDIA_PLAY_PAUSE)
    logger.info(f"Spotify: fallback media play key (scan of {len(scan_positions)} positions failed, window={w}x{h})")


def open_spotify(search: str = "", auto_play: bool = True) -> str:
    """Open Spotify and optionally search + auto-play.

    Strategy (best to worst):
    1. Spotify Web API → find track/artist URI → open spotify:track:{id} (auto-plays!)
       Optional: spotify_client_id + spotify_client_secret in keyring
    2. spotify:search:{query} → focus window → keyboard Tab+Enter (zero-config!)
    3. Just open Spotify (no search)

    Strategy 2 works out of the box without ANY configuration (uses ctypes only).
    Strategy 1 is an optional upgrade for users who want exact track matching.
    """
    if not search:
        subprocess.Popen(["cmd", "/c", "start", "", "spotify:"], shell=False)
        return "Spotify geöffnet."

    # Strategy 1: Spotify Web API (precise, auto-plays) — optional
    result = _spotify_api_search(search)
    if result:
        uri = result["uri"]
        subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)
        if result["type"] == "track":
            logger.info(f"Spotify: playing track '{result['name']}' by {result['artist']}")
            return f"Spotify: Spiele '{result['name']}' von {result['artist']}."
        else:
            logger.info(f"Spotify: opening artist '{result['name']}'")
            if auto_play:
                threading.Thread(
                    target=_spotify_auto_play, args=(4.0,), daemon=True
                ).start()
            return f"Spotify: Öffne Künstler '{result['name']}'."

    # Strategy 2: Search URI + keyboard auto-play (ZERO CONFIG)
    safe_search = urllib.parse.quote(search[:200], safe='')
    subprocess.Popen(["cmd", "/c", "start", "", f"spotify:search:{safe_search}"], shell=False)

    if auto_play:
        threading.Thread(
            target=_spotify_auto_play, args=(4.0,), daemon=True
        ).start()
        logger.info(f"Spotify: search + keyboard auto-play for '{search}'")

    return f"Spotify geöffnet, spiele '{search}'."


# ══════════════════════════════════════════════════
#  FFMPEG — Convert, Extract, Record
# ══════════════════════════════════════════════════

ALLOWED_FORMATS = {"mp3", "mp4", "wav", "aac", "ogg", "flac", "avi", "mkv", "webm", "m4a"}


def convert_media(input_path: str, output_path: str = "", format: str = "mp3") -> str:
    """Convert media files using ffmpeg."""
    if format.lower() not in ALLOWED_FORMATS:
        return f"Format '{format}' nicht unterstützt. Erlaubt: {', '.join(sorted(ALLOWED_FORMATS))}"
    format = format.lower()

    if not output_path:
        p = Path(input_path)
        output_path = str(p.with_suffix(f".{format}"))

    err = _validate_media_path(input_path, must_exist=True)
    if err:
        return t("error.generic", error=str(err))

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", input_path, "-y", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return f"Konvertiert: {output_path}"
        return t("error.stderr", stderr=result.stderr[:200])
    except FileNotFoundError:
        logger.warning("ffmpeg not found")
        return "ffmpeg nicht installiert. Bitte installieren: https://ffmpeg.org"
    except subprocess.TimeoutExpired:
        return "Konvertierung hat zu lange gedauert (Timeout)."


def extract_audio(video_path: str, output_path: str = "") -> str:
    """Extract audio from video file."""
    err = _validate_media_path(video_path, must_exist=True)
    if err:
        return t("error.generic", error=str(err))

    if not output_path:
        p = Path(video_path)
        output_path = str(p.with_suffix(".mp3"))

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-y", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return f"Audio extrahiert: {output_path}"
        return t("error.stderr", stderr=result.stderr[:200])
    except FileNotFoundError:
        logger.warning("ffmpeg not found")
        return "ffmpeg nicht installiert. Bitte installieren: https://ffmpeg.org"


def screen_record(duration: int = 10, output_path: str = "") -> str:
    """Record screen for X seconds using ffmpeg. Returns path to recording."""
    duration = max(1, min(3600, duration))  # cap at 1 hour

    if not output_path:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_dir = Path(_DATA_DIR) / "recordings"
        rec_dir.mkdir(exist_ok=True)
        output_path = str(rec_dir / f"recording_{ts}.mp4")

    try:
        proc = subprocess.Popen(
            ["ffmpeg", "-f", "gdigrab", "-framerate", "30", "-t", str(duration),
             "-i", "desktop", "-y", output_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Wait briefly to check for immediate errors (e.g. ffmpeg not found, no display)
        try:
            proc.wait(timeout=2)
            # If it exited within 2s, there was likely an error
            if proc.returncode != 0:
                stderr = proc.stderr.read().decode(errors="replace")[:300]
                return f"Aufnahme fehlgeschlagen: {stderr}"
        except subprocess.TimeoutExpired:
            # Still running = good, it's recording
            pass
        return f"Bildschirmaufnahme gestartet ({duration}s) → {output_path}"
    except FileNotFoundError:
        return "ffmpeg nicht installiert."
