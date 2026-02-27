"""Lexa AI — Companion Router
API Endpoints für PC-Kontrolle
"""

from fastapi import APIRouter
from pydantic import BaseModel

from companion.engine import companion
from backend.security import is_command_allowed, check_rate_limit, audit_log, validate_params

router = APIRouter(prefix="/companion", tags=["companion"])


class CommandRequest(BaseModel):
    command: str
    params: dict = {}
    confirmed: bool = False


class CommandResponse(BaseModel):
    success: bool
    data: str | dict | list | None = None
    error: str | None = None
    requires_confirmation: bool = False


@router.post("/execute", response_model=CommandResponse)
async def execute_command(req: CommandRequest):
    if not check_rate_limit():
        return CommandResponse(success=False, error="Rate limit erreicht.")

    permission = is_command_allowed(req.command)

    if permission == "blocked":
        audit_log(req.command, "blocked")
        return CommandResponse(success=False, error=f"Befehl '{req.command}' ist blockiert.")

    if permission == "confirmation_required" and not req.confirmed:
        audit_log(req.command, "awaiting_confirmation")
        return CommandResponse(
            success=False,
            requires_confirmation=True,
            error=f"Befehl '{req.command}' braucht deine Bestätigung.",
        )

    # Validate params for safety
    try:
        safe_params = validate_params(req.command, req.params)
    except ValueError as e:
        audit_log(req.command, "param_blocked", str(e))
        return CommandResponse(success=False, error=str(e))

    result = companion.execute(req.command, safe_params)
    return CommandResponse(**result)


@router.get("/commands")
async def list_commands():
    """Alle verfügbaren Befehle auflisten."""
    return {
        "commands": list(companion.commands.keys()),
        "total": len(companion.commands),
    }
