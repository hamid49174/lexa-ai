"""LLM-Triage fuer den Orchestrator (Phase 49 #2).

Ersetzt die billige Keyword-Regex-Entscheidung: ein dedizierter, guenstiger LLM-Call
entscheidet — wie Claude ultracode — OB eine Aufgabe von einem Multi-Agenten-Lauf
profitiert und WIE BREIT (Effort-Scaling), BEVOR der teure Lauf startet. Strukturiertes
JSON, kein Fliesstext. Faellt bei Fehler wohlwollend auf "kein Multi-Agent" zurueck
(dann laeuft normaler Chat) — blockiert nie.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.config import ORCHESTRATOR_MAX_SUBAGENTS
from backend.orchestrator.core import ChatFn, _default_chat_fn, _extract_json, _invoke, _safe

logger = logging.getLogger("lexa.orchestrator.triage")

_TRIAGE_PERSONA = (
    "Du bist ein TRIAGE-Router fuer ein KI-Assistenzsystem. Du entscheidest, ob eine "
    "Nutzer-Aufgabe von einem MULTI-AGENTEN-Lauf (Planung + parallele Recherche/Analyse + "
    "Synthese) echt profitiert, oder ob ein normaler Chat reicht. Du antwortest "
    "AUSSCHLIESSLICH mit gueltigem JSON, kein Fliesstext."
)


def _triage_prompt(task: str) -> str:
    return (
        "Aufgabe des Nutzers:\n" + task.strip() + "\n\n"
        "Gib JSON: {\"needs_agents\": true|false, \"subagents\": 1-5, "
        "\"mode\": \"fast\"|\"thorough\", \"reason\": \"kurz\"}.\n"
        "needs_agents=true NUR wenn die Aufgabe von Zerlegung + paralleler Recherche/Analyse "
        "wirklich profitiert: Vergleiche, breite/aktuelle Recherche, mehrteilige Aufgaben, "
        "Pro/Contra, 'analysiere X und Y und Z'. needs_agents=false bei Smalltalk, kurzen "
        "Faktenfragen, einfachen Anweisungen, Code-Schnipseln. subagents = sinnvolle Anzahl "
        "(1 fuer einfach, 3-5 fuer breit). mode=thorough nur bei hohem Genauigkeits-/Risiko-Bedarf."
    )


def _fallback(reason: str) -> dict:
    return {"needs_agents": False, "subagents": 1, "mode": "fast", "reason": reason, "source": "fallback"}


async def triage_task(
    task: str,
    *,
    chat_fn: Optional[ChatFn] = None,
    step_timeout: Optional[float] = 20,
) -> dict:
    """Entscheide per LLM, ob/wie ein Multi-Agenten-Lauf sinnvoll ist. Nie blockierend."""
    if not task or not str(task).strip():
        return _fallback("leere Aufgabe")
    chat_fn = chat_fn or _default_chat_fn
    try:
        res = await _invoke(
            chat_fn,
            [{"role": "user", "content": _triage_prompt(task)}],
            _TRIAGE_PERSONA,
            [],  # keine Tools -> reines, billiges Text/JSON
            timeout=step_timeout,
        )
        data = _extract_json(res.get("content", "") if isinstance(res, dict) else "")
        if isinstance(data, dict) and "needs_agents" in data:
            try:
                subs = max(1, min(int(data.get("subagents") or 3), int(ORCHESTRATOR_MAX_SUBAGENTS)))
            except (TypeError, ValueError):
                subs = 3
            mode = "thorough" if str(data.get("mode", "")).strip().lower() == "thorough" else "fast"
            return {
                "needs_agents": bool(data.get("needs_agents")),
                "subagents": subs,
                "mode": mode,
                "reason": _safe(data.get("reason"), 200),
                "source": "llm",
            }
    except Exception as exc:
        logger.warning("orchestrator triage failed: %s", _safe(exc))
    return _fallback("Triage nicht verfuegbar")
