"""
Lexa AI -- Plugin Router
API Endpoints fuer das Plugin-System (async-safe via PluginManager).

Endpoints:
  GET    /plugins              -- Liste aller Plugins
  GET    /plugins/tools        -- Alle Plugin-Tools (fuer Tool-Registry Integration)
  POST   /plugins/scan         -- Plugin-Verzeichnis neu scannen
  GET    /plugins/{name}       -- Plugin-Details
  POST   /plugins/{name}/reload  -- Plugin neu laden
  POST   /plugins/{name}/enable  -- Plugin aktivieren
  POST   /plugins/{name}/disable -- Plugin deaktivieren
  POST   /plugins/execute      -- Plugin-Tool ausfuehren
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.plugin_manager import plugin_manager

logger = logging.getLogger("lexa.router_plugins")
router = APIRouter(prefix="/plugins", tags=["plugins"])


# ── Request/Response Models ──

class PluginExecuteRequest(BaseModel):
    """Request-Body fuer Plugin-Tool-Ausfuehrung."""
    plugin: str = Field(..., description="Name des Plugins")
    tool: str = Field(..., description="Name des Tools")
    args: dict = Field(default_factory=dict, description="Tool-Argumente")


class PluginExecuteResponse(BaseModel):
    """Response fuer Plugin-Tool-Ausfuehrung."""
    success: bool
    result: dict | list | str | None = None
    error: str | None = None


# ══════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════

@router.get("")
async def list_plugins():
    """Liste aller geladenen Plugins mit Status."""
    plugins = plugin_manager.list_plugins()
    return JSONResponse({
        "success": True,
        "plugins": plugins,
        "count": len(plugins),
    })


@router.get("/tools")
async def list_plugin_tools():
    """Alle Plugin-Tools im OpenAI function-calling Format.

    Kann direkt an die Tool-Registry angehaengt werden.
    """
    tools = plugin_manager.get_plugin_tools()
    return JSONResponse({
        "success": True,
        "tools": tools,
        "count": len(tools),
    })


@router.post("/scan")
async def scan_plugins():
    """Plugin-Verzeichnis neu scannen und Plugins laden.

    Findet neue Plugins und laedt sie. Bereits geladene werden nicht beeinflusst.
    """
    try:
        loaded = plugin_manager.discover_plugins()
        all_plugins = plugin_manager.list_plugins()
        return JSONResponse({
            "success": True,
            "loaded": loaded,
            "total_plugins": len(all_plugins),
            "message": f"{len(loaded)} Plugins geladen",
        })
    except Exception as e:
        logger.error(f"Plugin-Scan fehlgeschlagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Plugin-Scan fehlgeschlagen: {e}")


@router.get("/{name}")
async def get_plugin_details(name: str):
    """Detaillierte Informationen zu einem einzelnen Plugin."""
    info = plugin_manager.get_plugin(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' nicht gefunden")
    return JSONResponse({
        "success": True,
        "plugin": info,
    })


@router.post("/{name}/reload")
async def reload_plugin(name: str):
    """Plugin entladen und neu laden (Hot-Reload)."""
    success = plugin_manager.reload_plugin(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' konnte nicht neu geladen werden")
    info = plugin_manager.get_plugin(name)
    return JSONResponse({
        "success": True,
        "message": f"Plugin '{name}' neu geladen",
        "plugin": info,
    })


@router.post("/{name}/enable")
async def enable_plugin(name: str):
    """Plugin aktivieren (Tools werden an LLM geschickt)."""
    success = plugin_manager.enable_plugin(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' nicht gefunden")
    return JSONResponse({
        "success": True,
        "message": f"Plugin '{name}' aktiviert",
    })


@router.post("/{name}/disable")
async def disable_plugin(name: str):
    """Plugin deaktivieren (Tools werden nicht mehr an LLM geschickt)."""
    success = plugin_manager.disable_plugin(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' nicht gefunden")
    return JSONResponse({
        "success": True,
        "message": f"Plugin '{name}' deaktiviert",
    })


@router.post("/execute")
async def execute_plugin_tool(request: PluginExecuteRequest):
    """Fuehrt ein Plugin-Tool aus.

    Body:
        {
            "plugin": "Web Search",
            "tool": "web_search",
            "args": {"query": "FastAPI tutorial"}
        }
    """
    # Validierung
    if not request.plugin or not request.tool:
        raise HTTPException(status_code=400, detail="Plugin-Name und Tool-Name erforderlich")

    if len(request.args) > 50:
        raise HTTPException(status_code=400, detail="Zu viele Argumente (max 50)")

    result = await plugin_manager.execute_plugin_tool(
        plugin_name=request.plugin,
        tool_name=request.tool,
        args=request.args,
    )

    status_code = 200 if result.get("success") else 422
    return JSONResponse(content=result, status_code=status_code)
