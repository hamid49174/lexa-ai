"""Realtime-Voice-Session-Geruest (Speech-to-Speech).

Liefert die protokoll-korrekten Verbindungs-/Konfigurations-Bausteine fuer
OpenAI Realtime bzw. Gemini Live sowie einen Session-Manager mit Lebenszyklus
(plan/start/stop/get). Der eigentliche Audio-Transport (Mikrofon-PCM rein,
TTS-PCM raus ueber die WebSocket-Sitzung) ist die EINZIGE Stelle, die echte
Audio-Hardware + Live-Provider braucht und daher hier bewusst NICHT scharf
geschaltet ist: ``voice.realtime.REALTIME_RUNTIME_IMPLEMENTED`` bleibt False, der
Manager startet erst, wenn das Gate nach einem Live-Test gesetzt wird.

Damit ist alles testbar/lieferbar, was ohne Audio-Hardware verifizierbar ist
(URL-/Config-Builder, Plan-Ableitung, Session-Zustandsmaschine), ohne eine nicht
verifizierte Funktion vorzutaeuschen.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from voice.config import OPENAI_REALTIME_MODEL, OPENAI_TTS_VOICE, SAMPLE_RATE
from voice import realtime as _rt

OPENAI_REALTIME_WS_BASE = "wss://api.openai.com/v1/realtime"
# OpenAI Realtime liefert/erwartet pcm16; Ausgabe 24 kHz, Eingabe darf 16 kHz sein.
REALTIME_OUTPUT_SAMPLE_RATE = 24000

_DEFAULT_INSTRUCTIONS = (
    "Du bist Lexa, ein hilfreicher, knapper deutschsprachiger Sprachassistent. "
    "Antworte natuerlich und unterbrechbar."
)


def openai_realtime_url(model: Optional[str] = None) -> str:
    """WebSocket-URL fuer die OpenAI-Realtime-Sitzung."""
    return f"{OPENAI_REALTIME_WS_BASE}?model={model or OPENAI_REALTIME_MODEL}"


def build_openai_session_config(
    model: Optional[str] = None,
    voice: Optional[str] = None,
    instructions: str = "",
) -> dict:
    """``session.update``-Payload fuer OpenAI Realtime (server-VAD + barge-in)."""
    return {
        "type": "session.update",
        "session": {
            "model": model or OPENAI_REALTIME_MODEL,
            "modalities": ["audio", "text"],
            "voice": voice or OPENAI_TTS_VOICE,
            "instructions": instructions or _DEFAULT_INSTRUCTIONS,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            # Server-seitige Sprachaktivitaetserkennung erlaubt Barge-in.
            "turn_detection": {"type": "server_vad", "silence_duration_ms": 500},
        },
    }


def build_gemini_live_setup(model: Optional[str] = None) -> dict:
    """``setup``-Payload fuer die Gemini-Live-WebSocket-Sitzung."""
    return {
        "setup": {
            "model": f"models/{model or getattr(_rt, "GEMINI_LIVE_MODEL", "gemini-live")}",
            "generation_config": {"response_modalities": ["AUDIO"]},
            "system_instruction": {"parts": [{"text": _DEFAULT_INSTRUCTIONS}]},
        },
    }


def build_session_plan(status: dict) -> dict:
    """Leitet aus dem Realtime-Status den konkreten Verbindungsplan ab.

    Beschreibt exakt, was eine Sitzung verwenden WUERDE (Provider, Modell,
    Transport, Konfig, Audioformat) — unabhaengig davon, ob das Gate scharf ist.
    """
    provider = (status or {}).get("preferred")
    audio = {
        "format": "pcm16",
        "input_sample_rate_hz": SAMPLE_RATE,
        "output_sample_rate_hz": REALTIME_OUTPUT_SAMPLE_RATE,
        "barge_in": True,
    }
    if provider == "openai_realtime":
        return {
            "provider": "openai_realtime",
            "model": OPENAI_REALTIME_MODEL,
            "transport": "websocket",
            "url": openai_realtime_url(),
            "session_config": build_openai_session_config(),
            "audio": audio,
        }
    if provider == "gemini_live":
        return {
            "provider": "gemini_live",
            "model": getattr(_rt, "GEMINI_LIVE_MODEL", "gemini-live"),
            "transport": "websocket_google_genai",
            "setup": build_gemini_live_setup(),
            "audio": audio,
        }
    return {"provider": "cascaded_fallback", "transport": "none", "audio": None}


class RealtimeSessionManager:
    """In-Memory-Lebenszyklus fuer EINE Realtime-Sitzung.

    start() startet nur, wenn der Preflight ``can_start`` meldet (was das
    Laufzeit-Gate ``LEXA_REALTIME_VOICE_ENABLED`` + ``REALTIME_RUNTIME_IMPLEMENTED``
    voraussetzt). Solange der Audio-Transport nicht live verifiziert/freigegeben
    ist, liefert start() die Preflight-Blocker zurueck — ehrlich, keine
    Schein-Sitzung.
    """

    def __init__(
        self,
        preflight_fn: Optional[Callable[[], dict]] = None,
        status_fn: Optional[Callable[[], dict]] = None,
    ):
        self._preflight_fn = preflight_fn
        self._status_fn = status_fn
        self._session: Optional[dict] = None
        self._counter = 0
        self._lock = threading.Lock()

    def _preflight(self) -> dict:
        if self._preflight_fn:
            return self._preflight_fn()
        # Direkt-Import aus dem Submodul -> nutzt sys.modules["voice.realtime"]
        # (respektiert Stubs; ein Package-Attribut koennte veraltet sein).
        from voice.realtime import get_realtime_session_preflight
        return get_realtime_session_preflight()

    def _status(self) -> dict:
        if self._status_fn:
            return self._status_fn()
        from voice.realtime import get_realtime_voice_status
        return get_realtime_voice_status()

    def plan(self) -> dict:
        return {"preflight": self._preflight(), "plan": build_session_plan(self._status())}

    def get(self) -> Optional[dict]:
        with self._lock:
            return dict(self._session) if self._session else None

    def start(self) -> dict:
        pre = self._preflight() or {}
        if not pre.get("can_start"):
            return {
                "ok": False,
                "can_start": False,
                "session_state": "blocked",
                "blockers": list(pre.get("blockers") or []),
                "warnings": list(pre.get("warnings") or []),
                "next_action": pre.get("next_action"),
                "plan": build_session_plan(self._status()),
            }
        with self._lock:
            self._counter += 1
            session = {
                "id": f"rt-{self._counter}",
                "session_state": "active",
                "provider": pre.get("provider"),
                "plan": build_session_plan(self._status()),
            }
            self._session = session
            return {"ok": True, "session_state": "active", "session": dict(session)}

    def stop(self) -> dict:
        with self._lock:
            was_active = self._session is not None
            self._session = None
        status = self._status() or {}
        return {
            "ok": True,
            "session_state": "stopped",
            "active": False,
            "was_active": was_active,
            "provider": status.get("preferred"),
            "active_path": status.get("active_path"),
        }


# ── Singleton ─────────────────────────────────
realtime_session_manager = RealtimeSessionManager()
