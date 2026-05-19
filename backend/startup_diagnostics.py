"""Startup and runtime diagnostics for Lexa backend reliability.

This module builds one compact, provider-neutral packet for the app/backend
surfaces. It checks availability, not secret values.
"""
from __future__ import annotations

import asyncio
import importlib.util
import time
from typing import Any

from backend import shared as _shared
from backend.ai_engine import get_ai_status
from backend.config import BACKEND_HOST, BACKEND_PORT, VERSION
from backend.hermes_adapter import (
    get_hermes_gateway_autostart_status,
    get_hermes_gateway_log_summary,
    get_hermes_status,
)


_PROVIDERS = ("groq", "openai", "gemini", "anthropic")
_IMPORTANT_TOOLS = ("ffmpeg", "playwright", "playwright_browser")


def _clip(value: Any, limit: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _check(
    check_id: str,
    label: str,
    state: str,
    detail: str,
    *,
    required: bool = False,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "state": state,
        "detail": _clip(detail),
        "required": required,
        "nextAction": _clip(next_action, 180),
    }


async def _safe_to_thread(fn, *args) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(fn, *args)
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        return {"error": str(exc)}


def _keyring_status() -> dict[str, Any]:
    available = importlib.util.find_spec("keyring") is not None
    return {
        "available": available,
        "summary": "keyring importable" if available else "keyring package missing",
    }


def _tool_health_summary() -> dict[str, Any]:
    try:
        from companion.tool_health import get_health_summary

        result = get_health_summary()
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        return {"error": str(exc), "tools": {}, "available_count": 0, "total_count": 0, "health_pct": 0}


async def _voice_status(probe_voice: bool = False) -> dict[str, Any]:
    try:
        from backend.router_voice import _build_voice_diagnostics

        payload = await _build_voice_diagnostics(probe_audio=probe_voice)
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {
            "ok": False,
            "state": "attention",
            "summary": "Voice diagnostics unavailable.",
            "checks": [],
            "error": str(exc),
        }


def _provider_checks(ai: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = [name for name in _PROVIDERS if (ai.get(name) or {}).get("available")]
    selected = str(ai.get("selected_provider") or "none")
    selected_ok = bool((ai.get(selected) or {}).get("available"))
    fallback_enabled = bool(ai.get("fallback_enabled"))
    fallback_available = ai.get("fallback_available") if isinstance(ai.get("fallback_available"), list) else []

    if selected_ok:
        provider_state = "ok"
        provider_detail = f"{selected} ready; {len(available)}/{len(_PROVIDERS)} providers configured."
        provider_next = ""
    elif available:
        provider_state = "warn"
        provider_detail = f"Selected provider {selected} unavailable; {len(available)} provider(s) available."
        provider_next = "Switch to an available provider or rely on fallback."
    else:
        provider_state = "blocked"
        provider_detail = "No AI provider is configured."
        provider_next = "Configure at least one provider key in Windows keyring."

    fallback_state = "ok" if fallback_enabled and fallback_available else ("warn" if fallback_enabled else "blocked")
    fallback_detail = (
        f"{len(fallback_available)} fallback model(s) available."
        if fallback_available
        else "No configured fallback model is currently available."
    )

    checks = [
        _check("providers", "AI providers", provider_state, provider_detail, required=True, next_action=provider_next),
        _check(
            "provider-fallback",
            "Provider fallback",
            fallback_state,
            fallback_detail,
            next_action="Configure a second provider for overload fallback." if fallback_state != "ok" else "",
        ),
    ]
    return checks, {
        "selected": selected,
        "active": ai.get("active_provider") or "none",
        "available": available,
        "fallbackAvailable": fallback_available,
    }


def _tool_checks(tool_health: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tools = tool_health.get("tools") if isinstance(tool_health.get("tools"), dict) else {}
    missing = [name for name in _IMPORTANT_TOOLS if not (tools.get(name) or {}).get("available")]
    checks = [
        _check(
            "runtime-tools",
            "Runtime tools",
            "warn" if missing else "ok",
            f"Missing: {', '.join(missing)}" if missing else "ffmpeg and Playwright runtime checks are ready.",
            next_action="Install missing runtime tools for browser/media workflows." if missing else "",
        )
    ]
    return checks, {
        "available": int(tool_health.get("available_count") or 0),
        "total": int(tool_health.get("total_count") or 0),
        "healthPct": int(tool_health.get("health_pct") or 0),
        "missingImportant": missing,
    }


def _voice_checks(voice: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks = voice.get("checks") if isinstance(voice.get("checks"), list) else []
    audio = next((check for check in checks if isinstance(check, dict) and check.get("id") == "audio-input"), {})
    audio_state = str(audio.get("state") or "warn")
    if audio_state == "blocked":
        audio_state = "warn"
    return [
        _check(
            "audio-input",
            "Audio input",
            "ok" if audio_state == "ok" else "warn",
            audio.get("detail") or voice.get("summary") or "Audio input not confirmed.",
            next_action="Check microphone permissions/device if voice input is needed." if audio_state != "ok" else "",
        )
    ], {
        "state": voice.get("state") or "unknown",
        "summary": voice.get("summary") or "",
    }


def _summarize(checks: list[dict[str, Any]]) -> tuple[str, str, str]:
    required_blocked = [check for check in checks if check.get("required") and check.get("state") == "blocked"]
    blocked = required_blocked or [check for check in checks if check.get("state") == "blocked"]
    warnings = [check for check in checks if check.get("state") == "warn"]
    if blocked:
        first = blocked[0]
        return "blocked", f"Startup blockiert: {first.get('label')} braucht Arbeit.", first.get("nextAction") or first.get("detail")
    if warnings:
        first = warnings[0]
        return "attention", f"Startup nutzbar, aber {first.get('label')} braucht Aufmerksamkeit.", first.get("nextAction") or first.get("detail")
    return "ready", "Startup und Runtime-Basis sind bereit.", "Keep backend health visible in Lexa."


async def build_startup_diagnostics(*, probe_voice: bool = False) -> dict[str, Any]:
    """Build a compact startup reliability packet for backend and UI callers."""
    ai_task = _safe_to_thread(get_ai_status)
    tools_task = _safe_to_thread(_tool_health_summary)
    hermes_task = _safe_to_thread(get_hermes_status)
    autostart_task = _safe_to_thread(get_hermes_gateway_autostart_status)
    logs_task = _safe_to_thread(get_hermes_gateway_log_summary, 80)
    voice_task = _voice_status(probe_voice)
    keyring_task = asyncio.to_thread(_keyring_status)

    ai, tool_health, hermes, autostart, logs, voice, keyring = await asyncio.gather(
        ai_task,
        tools_task,
        hermes_task,
        autostart_task,
        logs_task,
        voice_task,
        keyring_task,
    )

    uptime_seconds = int(time.time() - _shared.startup_time) if _shared.startup_time else 0
    provider_checks, provider_group = _provider_checks(ai)
    tool_checks, tool_group = _tool_checks(tool_health)
    voice_checks, voice_group = _voice_checks(voice)

    hermes_ready = hermes.get("health_state") == "ready"
    obsidian = hermes.get("obsidian_context") if isinstance(hermes.get("obsidian_context"), dict) else {}
    obsidian_ok = bool(obsidian.get("ok")) or bool(hermes.get("personal_os_root"))
    autostart_on = bool(autostart.get("enabled"))
    logs_ok = logs.get("status") == "ok" and logs.get("health_state") == "ok"

    checks = [
        _check("backend", "Lexa backend", "ok", f"Backend route is live; uptime {uptime_seconds}s.", required=True),
        _check("backend-port", "Backend port", "ok", f"{BACKEND_HOST}:{BACKEND_PORT} is serving this request.", required=True),
        *provider_checks,
        _check(
            "keyring",
            "Windows keyring",
            "ok" if keyring.get("available") else "warn",
            keyring.get("summary") or "keyring status unknown",
            next_action="Install/configure keyring so provider keys stay out of files." if not keyring.get("available") else "",
        ),
        *tool_checks,
        _check("hermes", "Hermes", "ok" if hermes_ready else "warn", hermes.get("summary") or hermes.get("health_state") or "unknown"),
        _check("obsidian", "Obsidian/Personal OS", "ok" if obsidian_ok else "warn", obsidian.get("summary") or "Personal OS context not confirmed."),
        _check(
            "gateway-autostart",
            "Gateway autostart",
            "ok" if autostart_on else "warn",
            "enabled" if autostart_on else "disabled",
            next_action="Enable Hermes gateway autostart for Telegram reliability." if not autostart_on else "",
        ),
        _check(
            "gateway-logs",
            "Gateway logs",
            "ok" if logs_ok else "warn",
            logs.get("summary") or "No gateway log summary.",
            next_action="Check Hermes gateway logs." if not logs_ok else "",
        ),
        *voice_checks,
    ]

    state, summary, next_action = _summarize(checks)
    issue_counts = {
        "ok": sum(1 for check in checks if check.get("state") == "ok"),
        "warn": sum(1 for check in checks if check.get("state") == "warn"),
        "blocked": sum(1 for check in checks if check.get("state") == "blocked"),
    }

    return {
        "ok": state != "blocked",
        "status": "ok",
        "state": state,
        "summary": summary,
        "nextAction": next_action,
        "version": VERSION,
        "uptimeSeconds": uptime_seconds,
        "checks": checks,
        "counts": issue_counts,
        "groups": {
            "providers": provider_group,
            "tools": tool_group,
            "hermes": {
                "state": hermes.get("health_state") or "unknown",
                "autostart": "enabled" if autostart_on else "disabled",
                "logs": logs.get("health_state") or "unknown",
            },
            "voice": voice_group,
        },
        "safeForCockpit": True,
    }
