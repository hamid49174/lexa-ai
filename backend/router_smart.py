"""Lexa AI — Smart Memory & Proactive Suggestions Router
API Endpoints fuer User-Profil, Vorschlaege, Lern-Statistiken, Insights.
"""

import asyncio
import json
import logging
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend import smart_memory as sm
from backend import proactive
from backend.security import check_rate_limit

logger = logging.getLogger("lexa.router_smart")

router = APIRouter(prefix="/smart", tags=["smart"])


# ══════════════════════════════════════════════════
#  USER PROFILE
# ══════════════════════════════════════════════════

@router.get("/profile")
async def get_profile():
    """Komplettes User-Profil anzeigen."""
    profile = await asyncio.to_thread(sm.profile_get_all)
    return {"profile": profile}


@router.put("/profile")
async def update_profile(req: Request):
    """Profil manuell anpassen. Body: {"key": "...", "value": ..., "confidence": 0.8}"""
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit ueberschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": "Ungueltiges JSON."}, status_code=400)

    key = data.get("key", "").strip()
    if not key:
        return JSONResponse({"error": "Key darf nicht leer sein."}, status_code=400)
    if len(key) > 200:
        return JSONResponse({"error": "Key zu lang (max 200 Zeichen)."}, status_code=400)

    value = data.get("value")
    if value is None:
        return JSONResponse({"error": "Value fehlt."}, status_code=400)

    confidence = data.get("confidence", 0.8)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.8

    result = await asyncio.to_thread(sm.profile_set, key, value, confidence)
    return {"status": result}


@router.delete("/profile/{key:path}")
async def delete_profile_entry(key: str):
    """Gelerntes vergessen — Profil-Eintrag loeschen."""
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit ueberschritten."}, status_code=429)

    key = key.strip()
    if not key:
        return JSONResponse({"error": "Key darf nicht leer sein."}, status_code=400)
    if len(key) > 200:
        return JSONResponse({"error": "Key zu lang (max 200 Zeichen)."}, status_code=400)

    result = await asyncio.to_thread(sm.profile_delete, key)

    if "nicht gefunden" in result.lower():
        return JSONResponse({"status": result}, status_code=404)
    return {"status": result}


# ══════════════════════════════════════════════════
#  PROACTIVE SUGGESTIONS
# ══════════════════════════════════════════════════

@router.get("/suggestions")
async def get_suggestions(current_app: str = ""):
    """Aktuelle Vorschlaege abrufen. Optional: ?current_app=chrome"""
    context = {}
    if current_app:
        context["current_app"] = current_app[:200]

    suggestions = await asyncio.to_thread(proactive.get_suggestions, context or None)
    return {"suggestions": suggestions, "count": len(suggestions)}


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str):
    """Vorschlag wegklicken / ignorieren."""
    if not suggestion_id or len(suggestion_id) > 50:
        return JSONResponse({"error": "Ungueltige Suggestion-ID."}, status_code=400)

    result = await asyncio.to_thread(proactive.dismiss_suggestion, suggestion_id)
    return {"status": "dismissed" if result else "not_found"}


@router.post("/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: str):
    """Vorschlag akzeptieren — gibt die Action zurueck."""
    if not suggestion_id or len(suggestion_id) > 50:
        return JSONResponse({"error": "Ungueltige Suggestion-ID."}, status_code=400)

    action = await asyncio.to_thread(proactive.accept_suggestion, suggestion_id)
    if action is None:
        return JSONResponse(
            {"status": "not_found", "action": None},
            status_code=404,
        )
    return {"status": "accepted", "action": action}


# ══════════════════════════════════════════════════
#  STATISTICS & LEARNING
# ══════════════════════════════════════════════════

@router.get("/stats")
async def get_stats():
    """Lern-Statistiken: Interaktionen, gelernte Patterns etc."""
    stats = await asyncio.to_thread(sm.get_stats)
    return {"stats": stats}


@router.post("/learn")
async def manual_learn(req: Request):
    """Manuell etwas beibringen: {"key": "favorite_editor", "value": "VS Code"}"""
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit ueberschritten."}, status_code=429)

    try:
        data = await req.json()
    except Exception:
        return JSONResponse({"error": "Ungueltiges JSON."}, status_code=400)

    key = data.get("key", "").strip()
    if not key:
        return JSONResponse({"error": "Key darf nicht leer sein."}, status_code=400)
    if len(key) > 200:
        return JSONResponse({"error": "Key zu lang (max 200 Zeichen)."}, status_code=400)

    value = data.get("value")
    if value is None:
        return JSONResponse({"error": "Value fehlt."}, status_code=400)

    # Manuelles Lernen = hohe Confidence
    result = await asyncio.to_thread(sm.profile_set, key, value, confidence=0.9)
    return {"status": result}


@router.get("/activity/hours")
async def activity_by_hour():
    """Aktivitaetsverteilung pro Stunde (0-23)."""
    data = await asyncio.to_thread(sm.get_activity_by_hour)
    return {"hours": data}


@router.get("/activity/days")
async def activity_by_day():
    """Aktivitaetsverteilung pro Wochentag."""
    data = await asyncio.to_thread(sm.get_activity_by_day)
    return {"days": data}


@router.get("/commands")
async def common_commands(limit: int = 20):
    """Haeufigste Commands."""
    limit = max(1, min(100, limit))
    commands = await asyncio.to_thread(sm.get_common_commands, limit)
    return {"commands": commands}


@router.get("/apps")
async def common_apps(limit: int = 20):
    """Meistgenutzte Apps (letzte 30 Tage)."""
    limit = max(1, min(100, limit))
    apps = await asyncio.to_thread(sm.get_common_apps, limit)
    return {"apps": apps}


# ══════════════════════════════════════════════════
#  AI-GENERIERTE INSIGHTS
# ══════════════════════════════════════════════════

# Kurzzeit-Cache fuer /insights: Insights aendern sich nicht im Sekundentakt,
# daher werden die teure Daten-Aggregation und der AI-Call fuer eine kurze
# TTL wiederverwendet, statt sie bei jedem Aufruf erneut auszufuehren.
_INSIGHTS_CACHE_TTL = 120.0  # Sekunden
_insights_cache: dict | None = None
_insights_cache_ts: float = 0.0


@router.get("/insights")
async def get_insights():
    """AI-generierte Insights ueber User-Verhalten.
    Nutzt die AI-Engine fuer eine Zusammenfassung der gesammelten Daten.
    Ergebnisse werden kurz gecacht, um teure AI-Calls zu vermeiden.
    """
    if not check_rate_limit("chat"):
        return JSONResponse({"error": "Rate limit ueberschritten."}, status_code=429)

    global _insights_cache, _insights_cache_ts

    # Gecachtes Ergebnis innerhalb der TTL zurueckgeben
    if _insights_cache is not None and (time.monotonic() - _insights_cache_ts) < _INSIGHTS_CACHE_TTL:
        return _insights_cache

    def _cache(payload: dict) -> dict:
        """Ergebnis fuer die TTL merken und zurueckgeben."""
        global _insights_cache, _insights_cache_ts
        _insights_cache = payload
        _insights_cache_ts = time.monotonic()
        return payload

    # Daten sammeln
    insights_data = await asyncio.to_thread(sm.get_insights_data)

    # Pruefen ob genug Daten vorhanden
    total_interactions = insights_data.get("stats", {}).get("total_interactions", 0)
    if total_interactions < 5:
        return _cache({
            "insights": "Noch nicht genug Daten fuer Insights. Nutze Lexa ein paar Tage, damit ich deine Muster erkennen kann.",
            "data_points": total_interactions,
            "ai_generated": False,
        })

    # AI-Insights generieren
    try:
        from backend.ai_engine import chat as ai_chat

        prompt = _build_insights_prompt(insights_data)
        result = await asyncio.to_thread(ai_chat, prompt)

        content = result.get("content", "")
        if result.get("type") == "error" or not content:
            # Fallback: Regelbasierte Insights
            content = _generate_fallback_insights(insights_data)
            return _cache({
                "insights": content,
                "data_points": total_interactions,
                "ai_generated": False,
            })

        return _cache({
            "insights": content,
            "data_points": total_interactions,
            "ai_generated": True,
        })
    except Exception as e:
        logger.error(f"AI Insights fehlgeschlagen: {e}", exc_info=True)
        content = _generate_fallback_insights(insights_data)
        return _cache({
            "insights": content,
            "data_points": total_interactions,
            "ai_generated": False,
        })


def _build_insights_prompt(data: dict) -> str:
    """Baut den Prompt fuer AI-generierte Insights."""
    stats = data.get("stats", {})
    activity_hours = data.get("activity_by_hour", [])
    activity_days = data.get("activity_by_day", [])
    commands = data.get("common_commands", [])
    apps = data.get("common_apps", [])
    profile = data.get("profile", {})

    # Peak-Hours berechnen
    peak_hours = sorted(activity_hours, key=lambda x: x.get("count", 0), reverse=True)[:3]
    peak_str = ", ".join(f"{h.get('hour', '?')}:00 ({h.get('count', 0)}x)" for h in peak_hours) if peak_hours else "keine Daten"

    # Peak-Days berechnen
    peak_days = sorted(activity_days, key=lambda x: x.get("count", 0), reverse=True)[:3]
    days_str = ", ".join(f"{d.get('name', '?')} ({d.get('count', 0)}x)" for d in peak_days) if peak_days else "keine Daten"

    # Top Commands
    cmd_str = ", ".join(f"'{c.get('command', '?')}' ({c.get('count', 0)}x)" for c in commands[:5]) if commands else "keine"

    # Top Apps
    app_str = ", ".join(f"{a.get('name', '?')} ({a.get('frequency', 0)}x)" for a in apps[:5]) if apps else "keine"

    # Profil-Info
    prefs = {}
    for k, v in profile.items():
        if k.startswith("preferences."):
            prefs[k.replace("preferences.", "")] = v.get("value", "")

    prompt = f"""Analysiere folgende Nutzungsdaten und gib kurze, hilfreiche Insights auf Deutsch:

STATISTIKEN:
- Gesamte Interaktionen: {stats.get('total_interactions', 0)}
- Gelernte Profil-Eintraege: {stats.get('profile_entries', 0)}
- Einzigartige Commands: {stats.get('unique_commands', 0)}
- Tracking seit: {stats.get('tracking_since', 'unbekannt')}

AKTIVITAET:
- Peak-Stunden: {peak_str}
- Aktivste Tage: {days_str}

TOP COMMANDS: {cmd_str}
TOP APPS: {app_str}
PRAEFERENZEN: {json.dumps(prefs, ensure_ascii=False) if prefs else 'noch keine'}

Gib 3-5 kurze, actionable Insights. Fokus auf:
1. Produktivitaetsmuster (wann ist der User am aktivsten?)
2. Nutzungsgewohnheiten (welche Tools/Commands werden am meisten genutzt?)
3. Verbesserungsvorschlaege (basierend auf den Mustern)

Format: Aufzaehlung mit Emoji-Bullets. Kurz und praegnant, maximal 2 Saetze pro Punkt."""

    return prompt


def _generate_fallback_insights(data: dict) -> str:
    """Regelbasierte Insights als Fallback wenn AI nicht verfuegbar."""
    stats = data.get("stats", {})
    activity_hours = data.get("activity_by_hour", [])
    commands = data.get("common_commands", [])
    apps = data.get("common_apps", [])

    lines = []

    # Peak-Hour Insight
    if activity_hours:
        peak = max(activity_hours, key=lambda x: x["count"])
        if peak["count"] > 0:
            lines.append(
                f"Deine aktivste Stunde ist {peak['hour']}:00 Uhr "
                f"mit {peak['count']} Interaktionen."
            )

    # Top Command
    if commands:
        top = commands[0]
        lines.append(
            f"Dein haeufigster Befehl ist '{top['command']}' "
            f"({top['count']}x verwendet)."
        )

    # Top App
    if apps:
        top_app = apps[0]
        lines.append(
            f"Deine meistgenutzte App ist {top_app['name']} "
            f"({top_app['frequency']}x in den letzten 30 Tagen)."
        )

    # Gesamt-Stats
    total = stats.get("total_interactions", 0)
    if total > 0:
        lines.append(f"Insgesamt habe ich {total} Interaktionen von dir gelernt.")

    if not lines:
        return "Noch nicht genug Daten fuer Insights. Nutze Lexa weiter!"

    return "\n".join(f"- {line}" for line in lines)
