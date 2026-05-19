"""Health and startup diagnostics routes."""
from __future__ import annotations

from fastapi import APIRouter, Query

from backend.startup_diagnostics import build_startup_diagnostics

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/startup")
async def health_startup(probeVoice: bool = Query(default=False)):
    """Return a compact startup/runtime reliability packet for Lexa."""
    return await build_startup_diagnostics(probe_voice=probeVoice)
