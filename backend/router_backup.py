"""Lexa AI — Backup Router
Backup endpoints: /backup, /backup/restore and settings backup management.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.shared import parse_json_body
from backend import memory
from backend.security import check_rate_limit

logger = logging.getLogger("lexa.backup")

router = APIRouter(tags=["backup"])
_BACKUP_FILENAME_PREFIX = "lexa-backup-"
_BACKUP_FILENAME_SUFFIX = ".json"
_RESTORE_INTENT_HEADER = "X-Lexa-Restore-Intent"
_RESTORE_INTENT_VALUE = "confirmed"


def _get_backup_dir() -> Path:
    raw = os.environ.get("LEXA_BACKUP_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".lexa" / "backups").resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _backup_metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "filename": path.name,
        "path": str(path),
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _resolve_backup_path(raw_path: str) -> Path:
    if not raw_path:
        raise HTTPException(status_code=400, detail="Backup path is required")
    backup_dir = _get_backup_dir()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = backup_dir / candidate
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, backup_dir):
        raise HTTPException(status_code=403, detail="Backup path is outside the Lexa backup directory")
    if not resolved.name.startswith(_BACKUP_FILENAME_PREFIX) or resolved.suffix.lower() != _BACKUP_FILENAME_SUFFIX:
        raise HTTPException(status_code=400, detail="Unsupported backup file name")
    return resolved


def _require_restore_intent(req: Request) -> None:
    if req.headers.get(_RESTORE_INTENT_HEADER, "").strip().lower() != _RESTORE_INTENT_VALUE:
        raise HTTPException(status_code=403, detail="Restore requires explicit restore intent.")


@router.get("/backup")
async def create_backup():
    """Create a full JSON backup of all data."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte kurz warten.")
    data = await asyncio.to_thread(memory.backup_database)
    if isinstance(data, dict):
        data["status"] = data.get("status", "ok")
    return data


@router.post("/backup/restore")
async def restore_backup(req: Request):
    """Restore data from a JSON backup."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte kurz warten.")
    _require_restore_intent(req)
    data = await parse_json_body(req)
    result = await asyncio.to_thread(memory.restore_database, data)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Restore failed"))
    result["status"] = result.get("status", "ok")
    return result


@router.post("/backup/create")
async def create_backup_file():
    """Create a JSON backup file for the Settings backup UI."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte kurz warten.")

    backup_dir = _get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"{_BACKUP_FILENAME_PREFIX}{timestamp}{_BACKUP_FILENAME_SUFFIX}"

    data = await asyncio.to_thread(memory.backup_database, str(path))
    if not path.exists():
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = _backup_metadata(path)
    return {"status": "ok", "success": True, **meta}


@router.get("/backup/list")
async def list_backup_files():
    """List JSON backup files created by Lexa."""
    backup_dir = _get_backup_dir()
    if not backup_dir.exists():
        return {"status": "ok", "backups": []}
    backups = sorted(
        backup_dir.glob(f"{_BACKUP_FILENAME_PREFIX}*{_BACKUP_FILENAME_SUFFIX}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return {"status": "ok", "backups": [_backup_metadata(path) for path in backups]}


@router.post("/backup/restore-db")
async def restore_backup_file(req: Request):
    """Restore a JSON backup selected from the Settings backup UI."""
    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte kurz warten.")
    _require_restore_intent(req)

    body = await parse_json_body(req)
    path = _resolve_backup_path(str(body.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Backup file is not valid JSON: {exc}") from exc

    result = await asyncio.to_thread(memory.restore_database, data)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Restore failed"))
    return {
        "status": "ok",
        "success": True,
        "result": "Backup restored",
        "restored": result.get("restored", {}),
        "path": str(path),
    }
