"""Server-side companion command confirmations.

Patch 2 keeps this intentionally in-memory and fail-closed: a backend restart
drops pending confirmations instead of preserving stale execution grants.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.local_auth import get_local_auth_token

CONFIRMATION_TTL_SECONDS = 90
_HASH_VERSION = "companion-confirmation-v1"
_lock = threading.Lock()
_store: dict[str, "ConfirmationRecord"] = {}


@dataclass
class ConfirmationRecord:
    confirmation_id: str
    command: str
    params: dict[str, Any]
    command_hash: str
    action_scope: str
    instance_hash: str
    created_at: float
    expires_at: float
    used: bool = False


class ConfirmationError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _canonical_params(params: dict | None) -> dict[str, Any]:
    return dict(params or {})


def _instance_hash() -> str:
    token = get_local_auth_token()
    if not token:
        return "no-local-auth-token"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compute_command_hash(command: str, params: dict | None, action_scope: str) -> str:
    payload = {
        "version": _HASH_VERSION,
        "command": str(command or ""),
        "params": _canonical_params(params),
        "action_scope": str(action_scope or ""),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iso_ts(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _cleanup_expired(now: float, *, keep: str | None = None) -> None:
    expired = [
        cid
        for cid, record in _store.items()
        if (record.expires_at <= now or record.used) and cid != keep
    ]
    for cid in expired:
        _store.pop(cid, None)


def create_confirmation(command: str, params: dict | None, action_scope: str, *, ttl_seconds: int = CONFIRMATION_TTL_SECONDS) -> dict:
    now = time.time()
    safe_params = _canonical_params(params)
    command_hash = compute_command_hash(command, safe_params, action_scope)
    confirmation_id = secrets.token_urlsafe(32)
    expires_at = now + max(1, int(ttl_seconds))
    record = ConfirmationRecord(
        confirmation_id=confirmation_id,
        command=str(command or ""),
        params=safe_params,
        command_hash=command_hash,
        action_scope=str(action_scope or ""),
        instance_hash=_instance_hash(),
        created_at=now,
        expires_at=expires_at,
    )
    with _lock:
        _cleanup_expired(now)
        _store[confirmation_id] = record

    param_keys = sorted(str(k) for k in safe_params.keys())
    return {
        "success": True,
        "requires_confirmation": True,
        "confirmation_id": confirmation_id,
        "command_hash": command_hash,
        "action_scope": record.action_scope,
        "created_at": _iso_ts(now),
        "expires_at": _iso_ts(expires_at),
        "ttl_seconds": int(expires_at - now),
        "summary": {
            "command": record.command,
            "action_scope": record.action_scope,
            "param_keys": param_keys,
            "command_hash_prefix": command_hash[:12],
        },
    }


def audit_details(record_or_payload: ConfirmationRecord | dict, status: str = "") -> str:
    if isinstance(record_or_payload, ConfirmationRecord):
        command_hash = record_or_payload.command_hash
        action_scope = record_or_payload.action_scope
        params = record_or_payload.params
        expires_at = _iso_ts(record_or_payload.expires_at)
    else:
        command_hash = str(record_or_payload.get("command_hash", ""))
        action_scope = str(record_or_payload.get("action_scope", ""))
        summary = record_or_payload.get("summary") or {}
        params = {key: True for key in summary.get("param_keys", [])}
        expires_at = str(record_or_payload.get("expires_at", ""))
    param_keys = ",".join(sorted(str(k) for k in params.keys()))
    pieces = [
        f"scope={action_scope}",
        f"hash={command_hash[:12]}",
        f"params=[{param_keys}]",
        f"expires_at={expires_at}",
    ]
    if status:
        pieces.insert(0, f"reason={status}")
    return " ".join(pieces)


def consume_confirmation(
    confirmation_id: str | None,
    *,
    command: str,
    params: dict | None,
    action_scope: str,
    command_hash: str | None = None,
) -> ConfirmationRecord:
    if not confirmation_id:
        raise ConfirmationError("confirmation_required", "Missing confirmation_id.", 403)

    now = time.time()
    cid = str(confirmation_id)
    with _lock:
        # Auch beim Konsumieren abgelaufene/verbrauchte Records aufräumen, damit der
        # _store bei prepare-Spam ohne folgendes create nicht unbegrenzt wächst.
        # Den angefragten Eintrag selbst ausnehmen, um seine spezifischen
        # Fehlercodes (expired/replay) unten zu erhalten.
        _cleanup_expired(now, keep=cid)
        record = _store.get(cid)
        if record is None:
            raise ConfirmationError("invalid_confirmation", "Invalid or expired confirmation_id.", 403)
        if record.used:
            raise ConfirmationError("confirmation_replay", "confirmation_id was already used.", 409)
        if record.expires_at <= now:
            _store.pop(record.confirmation_id, None)
            raise ConfirmationError("confirmation_expired", "confirmation_id expired.", 403)
        if record.instance_hash != _instance_hash():
            raise ConfirmationError("confirmation_instance_mismatch", "confirmation_id is not valid for this local instance.", 403)
        if record.command != str(command or ""):
            raise ConfirmationError("confirmation_command_mismatch", "confirmation_id does not match command.", 403)
        if record.action_scope != str(action_scope or ""):
            raise ConfirmationError("confirmation_scope_mismatch", "confirmation_id does not match action scope.", 403)

        expected_hash = compute_command_hash(command, _canonical_params(params), action_scope)
        if record.command_hash != expected_hash:
            raise ConfirmationError("confirmation_hash_mismatch", "confirmation_id does not match command payload.", 403)
        if command_hash and str(command_hash) != record.command_hash:
            raise ConfirmationError("confirmation_hash_mismatch", "Provided command_hash does not match confirmation.", 403)

        record.used = True
        return record


def clear_confirmations_for_tests() -> None:
    with _lock:
        _store.clear()
