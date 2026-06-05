"""Shared validation helpers for untrusted image uploads."""

from __future__ import annotations

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"}
ALLOWED_IMAGE_FORMATS = "PNG, JPEG, WEBP, GIF, BMP"


def normalized_upload_content_type(content_type: str | None) -> str:
    return str(content_type or "").split(";", 1)[0].strip().lower()


def supported_image_signature(image_bytes: bytes) -> str | None:
    data = bytes(image_bytes or b"")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def unsupported_upload_format_error(content_type: str) -> str:
    if content_type:
        return f"Nicht unterstuetztes Format: {content_type}. Erlaubt: {ALLOWED_IMAGE_FORMATS}"
    return f"Nicht unterstuetztes Format. Erlaubt: {ALLOWED_IMAGE_FORMATS}"


def invalid_image_upload_error() -> str:
    return f"Upload ist kein unterstuetztes Bild. Erlaubt: {ALLOWED_IMAGE_FORMATS}"
