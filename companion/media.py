"""Lexa AI — Media-Steuerung
Spotify, lokale Musik, Medien-Tasten, ffmpeg
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("lexa.media")


def media_play_pause() -> str:
    """Play/Pause toggle via media key."""
    subprocess.run(
        ["powershell", "-Command",
         "(New-Object -ComObject WScript.Shell).SendKeys([char]179)"],
        capture_output=True, timeout=5,
    )
    return "Play/Pause umgeschaltet."


def media_next() -> str:
    """Next track via media key."""
    subprocess.run(
        ["powershell", "-Command",
         "(New-Object -ComObject WScript.Shell).SendKeys([char]176)"],
        capture_output=True, timeout=5,
    )
    return "Nächster Track."


def media_prev() -> str:
    """Previous track via media key."""
    subprocess.run(
        ["powershell", "-Command",
         "(New-Object -ComObject WScript.Shell).SendKeys([char]177)"],
        capture_output=True, timeout=5,
    )
    return "Vorheriger Track."


def media_stop() -> str:
    """Stop playback via media key."""
    subprocess.run(
        ["powershell", "-Command",
         "(New-Object -ComObject WScript.Shell).SendKeys([char]178)"],
        capture_output=True, timeout=5,
    )
    return "Wiedergabe gestoppt."


def open_spotify(search: str = "") -> str:
    """Open Spotify and optionally search."""
    subprocess.Popen("start spotify:", shell=True)
    if search:
        import time
        time.sleep(2)
        # Use Spotify URI search
        subprocess.Popen(f"start spotify:search:{search.replace(' ', '%20')}", shell=True)
        return f"Spotify geöffnet, suche nach '{search}'."
    return "Spotify geöffnet."


def convert_media(input_path: str, output_path: str = "", format: str = "mp3") -> str:
    """Convert media files using ffmpeg."""
    if not output_path:
        p = Path(input_path)
        output_path = str(p.with_suffix(f".{format}"))

    try:
        result = subprocess.run(
            ["ffmpeg", "-i", input_path, "-y", output_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return f"Konvertiert: {output_path}"
        return f"Fehler: {result.stderr[:200]}"
    except FileNotFoundError:
        return "ffmpeg nicht installiert. Bitte installieren: https://ffmpeg.org"
    except subprocess.TimeoutExpired:
        return "Konvertierung hat zu lange gedauert (Timeout)."


def extract_audio(video_path: str, output_path: str = "") -> str:
    """Extract audio from video file."""
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
        return f"Fehler: {result.stderr[:200]}"
    except FileNotFoundError:
        return "ffmpeg nicht installiert."


def screen_record(duration: int = 10, output_path: str = "") -> str:
    """Record screen for X seconds using ffmpeg."""
    if not output_path:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"recording_{ts}.mp4"

    try:
        subprocess.Popen(
            ["ffmpeg", "-f", "gdigrab", "-framerate", "30", "-t", str(duration),
             "-i", "desktop", "-y", output_path],
        )
        return f"Bildschirmaufnahme gestartet ({duration}s) → {output_path}"
    except FileNotFoundError:
        return "ffmpeg nicht installiert."
