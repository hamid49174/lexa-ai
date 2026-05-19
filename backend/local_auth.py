"""Local authentication helpers for Lexa's localhost control plane."""
from __future__ import annotations

import hmac
import os

from fastapi import Request

LOCAL_AUTH_HEADER = "X-Lexa-Local-Token"
_PUBLIC_PATHS = {"/health"}
_DEV_DOC_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
_DEV_ENVS = {"dev", "development", "local", "test", "testing"}


def get_local_auth_token() -> str:
    return (os.environ.get("LEXA_INSTANCE_TOKEN") or "").strip()


def is_local_auth_required() -> bool:
    return bool(get_local_auth_token())


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
        return True
    supplied = (request.headers.get(LOCAL_AUTH_HEADER) or "").strip()
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def health_auth_fields(request: Request) -> dict[str, bool]:
    return {
        "auth_required": is_local_auth_required(),
        "instance_authenticated": (
            request_has_valid_local_token(request) if is_local_auth_required() else False
        ),
    }
