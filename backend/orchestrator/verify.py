"""Verifier-Schicht (Phase 48 B): LLM-as-Judge + adversarische Verifikation.

Im Modus "gruendlich" bewertet ein separater Judge jedes Sub-Agenten-Ergebnis gegen eine
Rubrik (Relevanz, Faktentreue/Belegtheit, Vollstaendigkeit). Bei niedrigem Score oder
high-risk folgt eine adversarische Runde (Skeptiker versuchen zu widerlegen; Mehrheit
entscheidet). Provider-agnostisch ueber den injizierten chat_fn (Default = ai_engine.chat
ohne Tools). Faellt bei LLM-Fehlern wohlwollend auf "bestanden" zurueck (blockiert nie hart).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from backend.orchestrator.core import (
    ChatFn,
    _default_chat_fn,
    _extract_json,
    _invoke,
    _safe,
)

logger = logging.getLogger("lexa.orchestrator.verify")

_PASS_THRESHOLD = 0.5
_ADVERSARIAL_ROUNDS = 2

_JUDGE_PERSONA = (
    "Du bist ein strenger QUALITAETS-PRUEFER (LLM-as-Judge) in einem Multi-Agenten-System. "
    "Du bewertest, ob das Ergebnis eines Sub-Agenten seine Teilaufgabe korrekt, belegt und "
    "vollstaendig erfuellt. Sei kritisch. Du gibst AUSSCHLIESSLICH gueltiges JSON zurueck."
)
_REFUTE_PERSONA = (
    "Du bist ein SKEPTIKER in einem Multi-Agenten-System. Versuche aktiv, das Ergebnis zu "
    "WIDERLEGEN: finde Fehler, unbelegte Behauptungen, Halluzinationen, Luecken. Im Zweifel "
    "refuted=true. Du gibst AUSSCHLIESSLICH gueltiges JSON zurueck."
)


def _judge_prompt(task: str, result: dict, sources_block: str = "") -> str:
    base = (
        "Bewerte das folgende Sub-Agenten-Ergebnis gegen seine Teilaufgabe. Kriterien: "
        "Relevanz, Faktentreue/Belegtheit, Vollstaendigkeit. Gib JSON: "
        '{"score": 0.0-1.0, "passed": true|false, "reasons": ["..."]'
    )
    if sources_block:
        base += (
            ', "claims": [{"claim": "...", "source_ids": [1,2], "supported": true|false}], '
            '"unsupported_count": 0'
        )
    base += (
        "}. passed=false wenn unbelegt, off-topic, leer oder widerspruechlich."
    )
    if sources_block:
        base += (
            " Pruefe ZUSAETZLICH jede zentrale Tatsachenbehauptung des Ergebnisses gegen die "
            "Quellenliste: trage sie in 'claims' ein, verweise mit 'source_ids' auf die "
            "stuetzenden Quellennummern und setze 'supported'=false, wenn KEINE Quelle die "
            "Behauptung belegt (= moegliche Halluzination). 'unsupported_count' = Anzahl der "
            "nicht belegten claims. Senke den Score deutlich bei unbelegten Behauptungen."
        )
    parts = [
        base,
        "",
        f"GESAMTAUFGABE: {task}",
        f"TEILAUFGABE: {result.get('objective', '')}",
        f"ERGEBNIS:\n{result.get('summary', '')}",
    ]
    if sources_block:
        parts += ["", "QUELLEN (Nummern fuer source_ids):", sources_block]
    return "\n".join(parts)


def _refute_prompt(task: str, result: dict) -> str:
    return (
        "Versuche zu widerlegen, dass dieses Ergebnis die Teilaufgabe korrekt erfuellt. "
        'Gib JSON: {"refuted": true|false, "reason": "..."}.\n\n'
        f"TEILAUFGABE: {result.get('objective', '')}\n"
        f"ERGEBNIS:\n{result.get('summary', '')}"
    )


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, score))


def _parse_claims(raw: Any, max_source_id: int) -> tuple[list[dict], int]:
    """Normalisiere die claim-level Bewertung des Judges. Filtert erfundene source_ids."""
    if not isinstance(raw, list):
        return [], 0
    claims: list[dict] = []
    unsupported = 0
    for c in raw:
        if not isinstance(c, dict):
            continue
        ids = c.get("source_ids")
        clean_ids: list[int] = []
        if isinstance(ids, list):
            for x in ids:
                try:
                    n = int(x)
                except (TypeError, ValueError):
                    continue
                if 1 <= n <= max_source_id and n not in clean_ids:
                    clean_ids.append(n)
        supported = bool(c.get("supported")) and bool(clean_ids)
        claims.append({
            "claim": _safe(c.get("claim"), 240),
            "source_ids": clean_ids,
            "supported": supported,
        })
        if not supported:
            unsupported += 1
        if len(claims) >= 12:
            break
    return claims, unsupported


async def judge_result(
    task: str,
    result: dict,
    *,
    chat_fn: Optional[ChatFn] = None,
    step_timeout: Optional[float] = None,
    sources_block: str = "",
    max_source_id: int = 0,
) -> dict:
    """LLM-as-Judge fuer EIN Sub-Agenten-Ergebnis. Gibt einen Verdict-Dict zurueck.
    Faellt wohlwollend auf bestanden zurueck (judge darf nie hart blockieren)."""
    chat_fn = chat_fn or _default_chat_fn
    agent_id = result.get("agent_id")
    # Fehlgeschlagene Sub-Agenten gar nicht erst bewerten.
    if result.get("status") in {"error", "failed", "timeout"}:
        return {"agent_id": agent_id, "passed": False, "score": 0.0,
                "reasons": [f"Sub-Agent-Status: {result.get('status')}"], "adversarial": None,
                "claims": [], "unsupported_count": 0}
    try:
        res = await _invoke(
            chat_fn,
            [{"role": "user", "content": _judge_prompt(task, result, sources_block)}],
            _JUDGE_PERSONA,
            [],
            timeout=step_timeout,
        )
        data = _extract_json(res.get("content", "") if isinstance(res, dict) else "")
        if isinstance(data, dict):
            score = _coerce_score(data.get("score"))
            passed = bool(data.get("passed", score >= _PASS_THRESHOLD))
            reasons = data.get("reasons") if isinstance(data.get("reasons"), list) else []
            reasons = [_safe(r, 200) for r in reasons][:6]
            claims, unsupported = _parse_claims(data.get("claims"), max_source_id) if sources_block else ([], 0)
            if unsupported:
                reasons = ([f"{unsupported} unbelegte Behauptung(en)"] + reasons)[:6]
            return {"agent_id": agent_id, "passed": passed, "score": score, "reasons": reasons,
                    "adversarial": None, "claims": claims, "unsupported_count": unsupported}
    except Exception as exc:
        logger.warning("orchestrator judge failed: %s", _safe(exc))
    # Wohlwollender Fallback: nicht blockieren, aber markieren.
    return {"agent_id": agent_id, "passed": True, "score": 0.5, "reasons": ["Judge nicht verfuegbar"],
            "adversarial": None, "claims": [], "unsupported_count": 0}


async def adversarial_judge(
    task: str,
    result: dict,
    *,
    chat_fn: Optional[ChatFn] = None,
    rounds: int = _ADVERSARIAL_ROUNDS,
    step_timeout: Optional[float] = None,
) -> dict:
    """Mehrere Skeptiker versuchen zu widerlegen; Mehrheit entscheidet (refuted)."""
    chat_fn = chat_fn or _default_chat_fn
    rounds = max(1, int(rounds))
    refute_votes = 0
    reasons: list[str] = []
    for _ in range(rounds):
        try:
            res = await _invoke(
                chat_fn,
                [{"role": "user", "content": _refute_prompt(task, result)}],
                _REFUTE_PERSONA,
                [],
                timeout=step_timeout,
            )
            data = _extract_json(res.get("content", "") if isinstance(res, dict) else "")
            if isinstance(data, dict) and bool(data.get("refuted")):
                refute_votes += 1
                if data.get("reason"):
                    reasons.append(_safe(data.get("reason"), 200))
        except Exception as exc:
            logger.warning("orchestrator adversarial judge failed: %s", _safe(exc))
    refuted = refute_votes * 2 > rounds  # echte Mehrheit
    return {"refuted": refuted, "refute_votes": refute_votes, "rounds": rounds, "reasons": reasons}


async def verify_results(
    task: str,
    results: list[dict],
    *,
    mode: str,
    chat_fn: Optional[ChatFn] = None,
    step_timeout: Optional[float] = None,
    high_risk: bool = False,
    adversarial_rounds: int = _ADVERSARIAL_ROUNDS,
    sources_block: str = "",
    max_source_id: int = 0,
) -> list[dict]:
    """Verifiziere alle Sub-Agenten-Ergebnisse (nur Modus 'gruendlich'). Judges laufen
    parallel; bei niedrigem Score, high_risk ODER unbelegten Behauptungen folgt eine
    adversarische Runde."""
    if str(mode).strip().lower() != "thorough" or not results:
        return []
    chat_fn = chat_fn or _default_chat_fn
    verdicts = await asyncio.gather(
        *[judge_result(task, r, chat_fn=chat_fn, step_timeout=step_timeout,
                       sources_block=sources_block, max_source_id=max_source_id) for r in results]
    )
    out: list[dict] = []
    for result, verdict in zip(results, verdicts):
        needs_adv = (
            high_risk
            or verdict.get("score", 1.0) < _PASS_THRESHOLD
            or verdict.get("unsupported_count", 0) > 0
        )
        if needs_adv and result.get("status") not in {"error", "failed", "timeout"}:
            adv = await adversarial_judge(
                task, result, chat_fn=chat_fn, rounds=adversarial_rounds, step_timeout=step_timeout
            )
            verdict = {**verdict, "adversarial": adv, "passed": bool(verdict.get("passed")) and not adv.get("refuted")}
        out.append(verdict)
    return out
