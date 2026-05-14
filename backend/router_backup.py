"""Lexa AI — Backup Router
Backup endpoints: /backup, /backup/restore
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from backend.shared import parse_json_body
from backend import memory
from backend.security import check_rate_limit

logger = logging.getLogger("lexa.backup")

router = APIRouter(tags=["backup"])


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
    data = await parse_json_body(req)
    result = await asyncio.to_thread(memory.restore_database, data)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Restore failed"))
    result["status"] = result.get("status", "ok")
    return result


# NOTE: /backup/create, /backup/list, /backup/restore-db endpoints were removed
# because they called nonexistent functions (memory.create_backup, memory.list_backups,
# memory.restore_backup). Use GET /backup and POST /backup/restore instead.
