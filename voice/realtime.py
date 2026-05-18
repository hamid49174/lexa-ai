"""Realtime voice architecture status for Lexa.

This is the capability boundary for ChatGPT/Gemini-style speech-to-speech.
It intentionally reports readiness separately from the older STT -> LLM -> TTS
fallback so the UI can show what is genuinely modern and what is legacy.
"""

from __future__ import annotations

import importlib.util
import os

from voice.config import OPENAI_REALTIME_MODEL


GEMINI_LIVE_MODEL = os.environ.get("LEXA_GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
REALTIME_RUNTIME_ENABLED = os.environ.get("LEXA_REALTIME_VOICE_ENABLED", "").strip().lower() in {
    "1", "true", "yes", "on",
}
REALTIME_RUNTIME_IMPLEMENTED = False


def _get_secret(secret_name: str, env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    try:
        import keyring

        return keyring.get_password("lexa-ai", secret_name)
    except Exception:
        return None


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def get_realtime_voice_status() -> dict:
    openai_key = _get_secret("openai_api_key", "OPENAI_API_KEY")
    gemini_key = _get_secret("gemini_api_key", "GEMINI_API_KEY")
    websockets_available = _module_available("websockets")
    google_genai_available = _module_available("google.genai")

    openai_configured = bool(openai_key and websockets_available)
    gemini_configured = bool(gemini_key and google_genai_available)
    provider_configured = openai_configured or gemini_configured
    runtime_requested = bool(REALTIME_RUNTIME_ENABLED)
    runtime_implemented = bool(REALTIME_RUNTIME_IMPLEMENTED)
    runtime_active = bool(runtime_requested and runtime_implemented and provider_configured)
    preferred = "openai_realtime" if openai_configured else ("gemini_live" if gemini_configured else "cascaded_fallback")
    active_path = preferred if runtime_active else "cascaded_stt_llm_tts"
    provider_state = "runtime_active" if runtime_active else (
        "provider_configured_runtime_unimplemented" if provider_configured and runtime_requested and not runtime_implemented
        else "provider_configured_runtime_disabled" if provider_configured
        else "provider_not_configured"
    )

    if runtime_active:
        next_action = "Realtime audio runtime is active."
    elif provider_configured and runtime_requested and not runtime_implemented:
        next_action = "Implement the realtime audio transport before enabling runtime."
    elif provider_configured:
        next_action = "Keep using cascaded voice or enable realtime after transport implementation."
    else:
        next_action = "Configure an OpenAI Realtime or Gemini Live provider."

    return {
        "version": "voice-stack-v3",
        "target": "speech_to_speech_realtime_with_vad_and_barge_in",
        "preferred": preferred,
        "active_path": active_path,
        "runtime_requested": runtime_requested,
        "runtime_implemented": runtime_implemented,
        "runtime_active": runtime_active,
        "provider_configured": provider_configured,
        "provider_state": provider_state,
        "runtime_gate": "LEXA_REALTIME_VOICE_ENABLED",
        "next_action": next_action,
        "ready": runtime_active,
        "configured": provider_configured,
        "fallback_ready": True,
        "openai": {
            "available": bool(openai_key),
            "transport_ready": websockets_available,
            "configured": openai_configured,
            "runtime_active": bool(runtime_active and preferred == "openai_realtime"),
            "model": OPENAI_REALTIME_MODEL,
            "vad": "server_vad_or_semantic_vad",
            "barge_in": True,
            "state": (
                "runtime_active" if runtime_active and preferred == "openai_realtime"
                else "configured_runtime_unimplemented" if openai_configured and runtime_requested and not runtime_implemented
                else "configured_runtime_disabled" if openai_configured
                else "missing_key_or_transport"
            ),
        },
        "gemini": {
            "available": bool(gemini_key),
            "transport_ready": google_genai_available,
            "configured": gemini_configured,
            "runtime_active": bool(runtime_active and preferred == "gemini_live"),
            "model": GEMINI_LIVE_MODEL,
            "vad": "automatic_activity_detection",
            "barge_in": True,
            "state": (
                "runtime_active" if runtime_active and preferred == "gemini_live"
                else "configured_runtime_unimplemented" if gemini_configured and runtime_requested and not runtime_implemented
                else "configured_runtime_disabled" if gemini_configured
                else "missing_key_or_google_genai"
            ),
        },
        "legacy": {
            "name": "cascaded_stt_llm_tts",
            "kept_as_fallback": True,
            "active": not runtime_active,
            "reason": "Keeps Lexa usable until realtime audio runtime is implemented and explicitly enabled.",
        },
    }


def get_realtime_session_preflight() -> dict:
    """Return whether a realtime audio session may start right now.

    This deliberately stays separate from provider readiness: a key and model can
    be configured before Lexa has a safe audio transport wired into the app.
    """
    status = get_realtime_voice_status()
    blockers: list[str] = []
    warnings: list[str] = []

    if not status.get("provider_configured"):
        blockers.append("No realtime provider is configured.")
    if not status.get("runtime_implemented"):
        blockers.append("Realtime audio transport is not implemented yet.")
    if status.get("runtime_implemented") and not status.get("runtime_requested"):
        blockers.append("Realtime runtime is disabled by LEXA_REALTIME_VOICE_ENABLED.")
    if status.get("runtime_requested") and not status.get("runtime_implemented"):
        warnings.append("Runtime was requested, but Lexa is still using the cascaded fallback.")

    can_start = bool(status.get("runtime_active") and not blockers)
    return {
        "ok": can_start,
        "can_start": can_start,
        "status": status,
        "provider": status.get("preferred"),
        "active_path": status.get("active_path"),
        "blockers": blockers,
        "warnings": warnings,
        "next_action": (
            "Start realtime session." if can_start
            else status.get("next_action") or "Keep using cascaded voice fallback."
        ),
    }
