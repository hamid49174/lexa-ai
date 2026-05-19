"""Shared backend error payload helpers.

The envelope keeps old `error`/`detail` consumers working while giving the
app, preload bridge, and Hermes surfaces one stable shape to parse.
"""
from __future__ import annotations

from typing import Any


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    408: "timeout",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
    504: "timeout",
}


def error_message(value: Any, fallback: str = "Request failed") -> str:
    """Extract one compact user-safe error message from common FastAPI shapes."""
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                text = str(item).strip()
                if text:
                    parts.append(text)
                continue
            loc = item.get("loc") or ""
            if isinstance(loc, (list, tuple)):
                loc = ".".join(str(part) for part in loc if part != "body")
            msg = item.get("msg") or item.get("message") or item.get("error") or ""
            if loc and msg:
                parts.append(f"{loc}: {msg}")
            elif msg:
                parts.append(str(msg))
        return "; ".join(parts) or fallback
    if isinstance(value, dict):
        for key in ("message", "error", "detail"):
            text = error_message(value.get(key), "")
            if text:
                return text
    return str(value).strip() or fallback


def error_payload(
    *,
    status_code: int,
    detail: Any,
    request_id: str = "",
    code: str = "",
    retryable: bool | None = None,
) -> dict[str, Any]:
    """Build the canonical JSON error envelope."""
    http_status = int(status_code or 500)
    message = error_message(detail, "Request failed")
    payload: dict[str, Any] = {
        "ok": False,
        "status": "error",
        "error": message,
        "message": message,
        "errorCode": code or _STATUS_CODES.get(http_status, "http_error"),
        "httpStatus": http_status,
        "detail": detail,
    }
    if request_id:
        payload["requestId"] = request_id
    if retryable is not None:
        payload["retryable"] = bool(retryable)
    return payload
