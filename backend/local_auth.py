"""Local authentication helpers for Lexa's localhost control plane."""
from __future__ import annotations

import hmac
import os

from fastapi import Request

LOCAL_AUTH_HEADER = "X-Lexa-Local-Token"
LOCAL_AUTH_COOKIE = "lexa_local_auth"
_PUBLIC_PATHS = {"/health"}
_DEV_DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
_DEV_ENVS = {"dev", "development", "local", "test", "testing"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def get_local_auth_token() -> str:
    return (os.environ.get("LEXA_INSTANCE_TOKEN") or "").strip()


def is_local_auth_required() -> bool:
    raw = (os.environ.get("LEXA_LOCAL_AUTH_REQUIRED") or "").strip().lower()
    if raw in _FALSE_VALUES:
        return False
    return True


def is_dev_mode() -> bool:
    return (os.environ.get("LEXA_ENV") or "").strip().lower() in _DEV_ENVS


def is_public_path(path: str) -> bool:
    clean_path = "/" + (path or "/").lstrip("/")
    if clean_path in _PUBLIC_PATHS:
        return True
    return is_dev_mode() and clean_path in _DEV_DOC_PATHS


def request_has_valid_local_token(request: Request) -> bool:
    expected = get_local_auth_token()
    if not expected:
        return False
    supplied_header = (request.headers.get(LOCAL_AUTH_HEADER) or "").strip()
    supplied_cookie = (request.cookies.get(LOCAL_AUTH_COOKIE) or "").strip()
    return (
        bool(supplied_header) and hmac.compare_digest(supplied_header, expected)
    ) or (
        bool(supplied_cookie) and hmac.compare_digest(supplied_cookie, expected)
    )


def health_auth_fields(request: Request) -> dict[str, bool]:
    return {
        "auth_required": is_local_auth_required(),
        "instance_authenticated": (
            request_has_valid_local_token(request) if is_local_auth_required() else False
        ),
    }
