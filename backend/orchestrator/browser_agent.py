"""Browser-Agent-Faehigkeit (Phase 48 D, optional).

Bindet browser-use (https://github.com/browser-use/browser-use, MIT) an, das einem LLM
einen echten Browser steuern laesst — provider-agnostisch, Gemini nativ ueber ChatGoogle.

BEWUSSTE SICHERHEITS-/RESSOURCEN-ENTSCHEIDUNG:
- browser-use startet einen echten Chromium-Prozess (RAM/CPU-intensiv) und kann fremde
  Webseiten lesen/anklicken (indirekte Prompt-Injection, Anti-Bot). Daher ist der
  Browser-Agent NICHT Teil des autonomen Parallel-Orchestrators und laeuft NICHT
  automatisch. Er ist explizit opt-in (LEXA_ORCHESTRATOR_BROWSER_ENABLED=1) und nur
  verfuegbar, wenn das Paket installiert ist (lazy import, optionale Dependency).
- Aktivierung braucht: `uv pip install browser-use` + Chromium (`uvx browser-use install`
  bzw. `playwright install chromium`); im PyInstaller-Deploy muessen die Browser-Binaries
  mitgebuendelt werden (haeufigste Deploy-Huerde).

Diese Datei kapselt Erkennung (browser_status) + einen sicheren, getimeouteten Lauf
(run_browser_task). Sie wird vom restlichen System nur defensiv genutzt.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.config import ORCHESTRATOR_BROWSER_ENABLED, ORCHESTRATOR_RUN_TIMEOUT

logger = logging.getLogger("lexa.orchestrator.browser")


def browser_use_installed() -> bool:
    """True, wenn das browser-use Paket importierbar ist (ohne es zu starten)."""
    try:
        import importlib.util
        return importlib.util.find_spec("browser_use") is not None
    except Exception:  # pragma: no cover - defensive
        return False


def browser_status() -> dict:
    """Verfuegbarkeits-Status fuer UI/Diagnose. Startet nichts."""
    installed = browser_use_installed()
    enabled = bool(ORCHESTRATOR_BROWSER_ENABLED)
    available = installed and enabled
    if available:
        reason = "bereit"
    elif not enabled:
        reason = "deaktiviert (LEXA_ORCHESTRATOR_BROWSER_ENABLED=1 zum Aktivieren)"
    else:
        reason = "browser-use nicht installiert (uv pip install browser-use + Chromium)"
    return {"available": available, "installed": installed, "enabled": enabled, "reason": reason}


async def run_browser_task(
    task: str,
    *,
    timeout: Optional[float] = None,
    max_steps: int = 25,
) -> dict:
    """Fuehre EINE Browser-Aufgabe via browser-use aus (Gemini). Read-/Recherche-orientiert.

    Gibt {success, data|error} zurueck. Laeuft NUR wenn aktiviert + installiert; sonst
    sauberer, nicht-blockierender Fehler. Nie Teil des autonomen Parallel-Orchestrators.
    """
    status = browser_status()
    if not status["available"]:
        return {"success": False, "error": f"Browser-Agent nicht verfuegbar: {status['reason']}"}
    if not task or not str(task).strip():
        return {"success": False, "error": "Leere Browser-Aufgabe."}

    timeout = float(timeout if timeout is not None else ORCHESTRATOR_RUN_TIMEOUT)
    try:
        import asyncio

        from browser_use import Agent, ChatGoogle  # type: ignore

        # Gemini-Key best-effort aus ai_engine holen (Funktionsname kann variieren); sonst
        # faellt browser-use auf die GOOGLE_API_KEY/GEMINI_API_KEY Umgebungsvariable zurueck.
        api_key = None
        try:
            import backend.ai_engine as _aie
            for _fn in ("_get_gemini_api_key", "get_gemini_api_key", "_gemini_api_key"):
                _f = getattr(_aie, _fn, None)
                if callable(_f):
                    api_key = _f()
                    break
        except Exception:
            api_key = None

        llm = ChatGoogle(model="gemini-2.5-flash", api_key=api_key) if api_key else ChatGoogle(model="gemini-2.5-flash")
        agent = Agent(task=str(task), llm=llm)

        async def _run():
            history = await agent.run(max_steps=max_steps)
            try:
                return history.final_result()
            except Exception:
                return str(history)

        result = await asyncio.wait_for(_run(), timeout=timeout)
        return {"success": True, "data": result}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Browser-Agent: Zeitlimit erreicht."}
    except Exception as exc:
        logger.warning("browser agent failed: %s", exc)
        return {"success": False, "error": "Browser-Agent fehlgeschlagen."}
