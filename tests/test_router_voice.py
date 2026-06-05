"""Tests for backend/router_voice.py — Voice API endpoint tests.
Tests focus on HTTP endpoints (not WebSocket) with mocked voice modules.
"""

import io
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Stub voice modules before importing router ───

def _setup_voice_stubs():
    """Stub voice.tts, voice.stt, voice.wakeword so router_voice can import."""
    stubs = {}

    # voice package
    if "voice" not in sys.modules:
        voice_mod = types.ModuleType("voice")
        voice_mod.__path__ = []
        sys.modules["voice"] = voice_mod
        stubs["voice"] = None

    config_stub = types.ModuleType("voice.config")
    config_stub.WAKE_ENGINE = "openwakeword"
    config_stub.WAKE_PHRASES = ["lexa"]
    config_stub.WAKE_OPENWAKEWORD_MODELS = "alexa"
    config_stub.WAKE_OPENWAKEWORD_THRESHOLD = 0.55
    config_stub.WAKE_OPENWAKEWORD_PATIENCE = 2
    config_stub.WAKE_OPENWAKEWORD_VAD_THRESHOLD = 0.05
    config_stub.WAKE_OPENWAKEWORD_AUTO_DOWNLOAD = True
    config_stub.MAX_TTS_TEXT_CHARS = 2000
    config_stub.WAKE_FALLBACK_STT_MIN_INTERVAL_S = 0.75
    config_stub.WAKE_FALLBACK_STT_MAX_INTERVAL_S = 1.5
    config_stub.WAKE_FALLBACK_STT_BACKOFF_STEP_S = 0.25
    stubs["voice.config"] = sys.modules.get("voice.config")
    sys.modules["voice.config"] = config_stub

    # voice.tts — function names must match exactly what router_voice imports
    tts_stub = types.ModuleType("voice.tts")
    tts_stub.speak = MagicMock(return_value="/tmp/test.mp3")
    tts_stub.speak_async = AsyncMock(return_value="/tmp/test.mp3")
    tts_stub.get_tts_status = MagicMock(return_value={
        "engine": "elevenlabs", "available": True,
        "elevenlabs_available": True, "elevenlabs_has_key": True,
        "elevenlabs_voice_id": "test_voice", "elevenlabs_model": "eleven_multilingual_v2",
        "elevenlabs_enabled": True,
    })
    tts_stub.get_elevenlabs_voices = MagicMock(return_value=[{"voice_id": "abc", "name": "Test"}])
    tts_stub.set_elevenlabs_key = MagicMock()
    tts_stub.delete_elevenlabs_key = MagicMock()
    tts_stub.set_elevenlabs_voice = MagicMock()
    tts_stub.set_elevenlabs_model = MagicMock()
    tts_stub.set_elevenlabs_settings = MagicMock()
    tts_stub.set_elevenlabs_enabled = MagicMock()
    stubs["voice.tts"] = sys.modules.get("voice.tts")
    sys.modules["voice.tts"] = tts_stub

    # voice.stt — function names must match exactly
    stt_stub = types.ModuleType("voice.stt")
    stt_stub.transcribe_file = MagicMock(return_value={"text": "Hallo Lexa", "language": "de"})
    stt_stub.get_stt_status = MagicMock(return_value={
        "engine": "openai", "available": True, "openai_available": True,
    })
    stt_stub.get_available_models = MagicMock(return_value=["base", "small", "large-v3"])
    stt_stub.set_model_size = MagicMock()
    stt_stub.set_language = MagicMock()
    stt_stub.set_engine = MagicMock()
    stubs["voice.stt"] = sys.modules.get("voice.stt")
    sys.modules["voice.stt"] = stt_stub

    # voice.wakeword
    ww_stub = types.ModuleType("voice.wakeword")

    class FakeWakeWordDetector:
        start_error = ""
        start_active = True
        start_ready = True
        instances = []

        def __init__(self, *args, **kwargs):
            self.is_listening = False
            self._ready = False
            self._error = ""
            self.sensitivity = 0.015
            self.wake_phrases = ["lexa"]
            FakeWakeWordDetector.instances.append(self)

        def start(self, wait_ready_s=0.0):
            self._error = FakeWakeWordDetector.start_error
            self.is_listening = FakeWakeWordDetector.start_active and not self._error
            self._ready = FakeWakeWordDetector.start_ready and self.is_listening
            return self.status

        def start_direct(self, wait_ready_s=0.0):
            return self.start(wait_ready_s=wait_ready_s)

        def stop(self):
            self.is_listening = False
            self._ready = False

        @property
        def status(self):
            return {
                "active": self.is_listening,
                "ready": self._ready,
                "in_conversation": False,
                "phrases": self.wake_phrases,
                "sensitivity": self.sensitivity,
                "thread_alive": self.is_listening,
                "error": self._error,
                "wake_engine": {
                    "name": "openwakeword",
                    "ready": True,
                    "local": True,
                    "uses_stt": False,
                },
                "skipped_stt_checks": 0,
                "fallback_stt_min_interval_s": 2.0,
                "fallback_stt_max_interval_s": 6.0,
                "fallback_stt_interval_s": 2.0,
                "non_wake_transcripts": 0,
            }

    ww_stub.WakeWordDetector = FakeWakeWordDetector
    stubs["voice.wakeword"] = sys.modules.get("voice.wakeword")
    sys.modules["voice.wakeword"] = ww_stub

    realtime_stub = types.ModuleType("voice.realtime")
    realtime_stub.get_realtime_voice_status = MagicMock(return_value={
        "version": "voice-stack-v3",
        "target": "speech_to_speech_realtime_with_vad_and_barge_in",
        "preferred": "openai_realtime",
        "active_path": "cascaded_stt_llm_tts",
        "runtime_requested": False,
        "runtime_implemented": False,
        "runtime_active": False,
        "provider_configured": True,
        "provider_state": "provider_configured_runtime_disabled",
        "runtime_gate": "LEXA_REALTIME_VOICE_ENABLED",
        "next_action": "Keep using cascaded voice or enable realtime after transport implementation.",
        "configured": True,
        "ready": False,
    })
    realtime_stub.get_realtime_session_preflight = MagicMock(return_value={
        "ok": False,
        "can_start": False,
        "provider": "openai_realtime",
        "active_path": "cascaded_stt_llm_tts",
        "blockers": ["Realtime audio transport is not implemented yet."],
        "warnings": [],
        "next_action": "Keep using cascaded voice or enable realtime after transport implementation.",
    })
    stubs["voice.realtime"] = sys.modules.get("voice.realtime")
    sys.modules["voice.realtime"] = realtime_stub

    wake_engines_stub = types.ModuleType("voice.wakeword_engines")
    wake_engines_stub.get_wakeword_engine_capabilities = MagicMock(return_value={
        "target": "siri_style_local_keyword_spotting",
        "configured_mode": "auto",
    })
    stubs["voice.wakeword_engines"] = sys.modules.get("voice.wakeword_engines")
    sys.modules["voice.wakeword_engines"] = wake_engines_stub

    # backend.voice_ws
    ws_stub = types.ModuleType("backend.voice_ws")
    for name in ["push_event", "push_volume", "push_state", "push_command",
                 "push_response", "push_response_chunk", "push_error",
                 "pop_fallback_events", "register_ws_client", "unregister_ws_client",
                 "init_ws_loop"]:
        setattr(ws_stub, name, MagicMock(return_value=[]))
    stubs["backend.voice_ws"] = sys.modules.get("backend.voice_ws")
    sys.modules["backend.voice_ws"] = ws_stub

    # sounddevice
    sd_stub = types.ModuleType("sounddevice")
    sd_stub.default = types.SimpleNamespace(device=[1, 2])

    def query_devices(kind=None):
        if kind == "input":
            return {
                "name": "Test Microphone",
                "index": 1,
                "max_input_channels": 1,
                "max_output_channels": 0,
                "default_samplerate": 16000,
            }
        if kind == "output":
            return {
                "name": "Test Speakers",
                "index": 2,
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000,
            }
        return []

    sd_stub.query_devices = MagicMock(side_effect=query_devices)
    stubs["sounddevice"] = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = sd_stub

    return stubs


def _restore_stubs(stubs):
    """Restore original modules."""
    for key, original in stubs.items():
        if original is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = original


@pytest.fixture
def client(disable_rate_limit):
    """Create test client with stubbed voice modules."""
    stubs = _setup_voice_stubs()
    try:
        # Force reimport of router_voice with stubs in place
        if "backend.router_voice" in sys.modules:
            del sys.modules["backend.router_voice"]

        from backend.router_voice import router
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app)
    finally:
        # Clean up
        sys.modules.pop("backend.router_voice", None)
        _restore_stubs(stubs)


# ══════════════════════════════════════════════════
#  TTS ENDPOINTS
# ══════════════════════════════════════════════════

class TestTTSEndpoints:
    def test_voice_diagnostics_reports_stack(self, client):
        res = client.get("/voice/diagnostics")
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "attention"
        assert data["audio"]["available"] is True
        assert data["audio"]["input"]["name"] == "Test Microphone"
        assert data["stt"]["available"] is True
        assert data["tts"]["available"] is True
        assert data["wakeword"]["active"] is False
        assert any(check["id"] == "wakeword" and check["state"] == "warn" for check in data["checks"])

    def test_voice_status_alias_reports_same_shape(self, client):
        res = client.get("/voice/status")
        assert res.status_code == 200
        data = res.json()
        assert "checks" in data
        assert "audio" in data
        assert "nextAction" in data
        assert "realtime" in data
        assert "realtime_preflight" in data
        assert data["realtime_preflight"]["can_start"] is False
        assert "not implemented" in data["realtime_preflight"]["blockers"][0]

    def test_voice_architecture_reports_modern_stack(self, client):
        res = client.get("/voice/architecture")
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "voice-stack-v3"
        assert data["realtime"]["target"] == "speech_to_speech_realtime_with_vad_and_barge_in"
        assert data["realtime"]["configured"] is True
        assert data["realtime"]["ready"] is False
        assert data["realtime"]["active_path"] == "cascaded_stt_llm_tts"
        assert data["wakeword"]["target"] == "siri_style_local_keyword_spotting"

    def test_voice_realtime_preflight_reports_blockers(self, client):
        res = client.get("/voice/realtime/preflight")
        assert res.status_code == 200
        data = res.json()
        assert data["can_start"] is False
        assert data["provider"] == "openai_realtime"
        assert "not implemented" in data["blockers"][0]

    def test_voice_realtime_start_blocks_until_transport_exists(self, client):
        res = client.post("/voice/realtime/start")
        assert res.status_code == 409
        data = res.json()
        assert data["ok"] is False
        assert data["can_start"] is False
        assert data["session_state"] == "blocked"
        assert "not implemented" in data["blockers"][0]

    def test_voice_realtime_stop_is_safe_without_active_session(self, client):
        res = client.post("/voice/realtime/stop")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["session_state"] == "stopped"
        assert data["active"] is False
        assert data["active_path"] == "cascaded_stt_llm_tts"

    def test_voice_diagnostics_ready_next_action(self, client):
        start = client.post("/voice/wakeword/start")
        assert start.status_code == 200

        res = client.get("/voice/diagnostics")
        assert res.status_code == 200
        data = res.json()
        assert data["state"] == "ready"
        assert data["nextAction"] == "Voice stack is ready."

    def test_voice_diagnostics_redacts_internal_errors(self, client):
        local_path = r"C:\Users\admin\secret\voice.txt"
        sys.modules["voice.stt"].get_stt_status.side_effect = RuntimeError(
            f"failed at {local_path} token=supersecretvalue"
        )
        sys.modules["voice.realtime"].get_realtime_session_preflight.side_effect = RuntimeError(
            f"realtime failed at {local_path} api_key=sk-testsecret12345"
        )

        res = client.get("/voice/diagnostics")

        assert res.status_code == 200
        payload_text = str(res.json())
        assert "[local-path-redacted]" in payload_text
        assert "[REDACTED]" in payload_text
        assert local_path not in payload_text
        assert "supersecretvalue" not in payload_text
        assert "sk-testsecret12345" not in payload_text

    def test_tts_status(self, client):
        res = client.get("/voice/tts/status")
        assert res.status_code == 200
        data = res.json()
        assert "engine" in data

    def test_tts_empty_text(self, client):
        res = client.post("/voice/tts", json={"text": ""})
        assert res.status_code == 400

    def test_tts_text_too_long(self, client):
        res = client.post("/voice/tts", json={"text": "x" * 2001})
        assert res.status_code == 413
        assert sys.modules["voice.tts"].speak_async.await_count == 0

    def test_tts_audit_does_not_store_spoken_text(self, client, monkeypatch, tmp_path):
        import backend.router_voice as router_voice

        audio_path = tmp_path / "tts.mp3"
        audio_path.write_bytes(b"mp3")
        secret_text = "Sprich meinen geheimen API key sk-testsecret12345"
        seen = []
        monkeypatch.setattr(router_voice, "audit_log", lambda *args, **kwargs: seen.append(args))
        sys.modules["voice.tts"].speak_async = AsyncMock(return_value=str(audio_path))

        res = client.post("/voice/tts", json={"text": secret_text})

        assert res.status_code == 200
        audit_text = str(seen)
        assert "textChars=" in audit_text
        assert "Sprich meinen" not in audit_text
        assert "sk-testsecret12345" not in audit_text

    def test_tts_voices_list(self, client):
        res = client.get("/voice/tts/voices")
        assert res.status_code == 200

    def test_elevenlabs_key_empty(self, client):
        res = client.post("/voice/tts/elevenlabs/key", json={"api_key": ""})
        assert res.status_code == 400

    def test_elevenlabs_key_delete(self, client):
        res = client.delete("/voice/tts/elevenlabs/key")
        assert res.status_code == 200

    def test_elevenlabs_voice_empty(self, client):
        res = client.post("/voice/tts/elevenlabs/voice", json={"voice_id": ""})
        assert res.status_code == 400

    def test_elevenlabs_model(self, client):
        res = client.post("/voice/tts/elevenlabs/model", json={"model": "eleven_turbo_v2_5"})
        assert res.status_code == 200

    def test_elevenlabs_settings(self, client):
        res = client.post("/voice/tts/elevenlabs/settings", json={
            "stability": 0.5,
            "similarity": 0.8,
        })
        assert res.status_code == 200

    def test_elevenlabs_toggle(self, client):
        res = client.post("/voice/tts/elevenlabs/toggle", json={"enabled": False})
        assert res.status_code == 200


# ══════════════════════════════════════════════════
#  STT ENDPOINTS
# ══════════════════════════════════════════════════

class TestSTTEndpoints:
    def test_stt_status(self, client):
        res = client.get("/voice/stt/status")
        assert res.status_code == 200

    def test_stt_models(self, client):
        res = client.get("/voice/stt/models")
        assert res.status_code == 200

    def test_stt_set_model(self, client):
        res = client.post("/voice/stt/model", json={"model": "large-v3"})
        assert res.status_code == 200

    def test_stt_set_language(self, client):
        res = client.post("/voice/stt/language", json={"language": "en"})
        assert res.status_code == 200

    def test_stt_set_engine(self, client):
        res = client.post("/voice/stt/engine", json={"engine": "local"})
        assert res.status_code == 200

    def test_stt_upload_accepts_dict_result(self, client):
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("test.webm", file_data, "audio/webm")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["text"] == "Hallo Lexa"
        assert data["language"] == "de"

    def test_stt_upload_accepts_string_result(self, client):
        sys.modules["voice.stt"].transcribe_file.return_value = "Hallo String"
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("test.webm", file_data, "audio/webm")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["text"] == "Hallo String"

    def test_stt_upload_empty_result_is_not_success(self, client):
        sys.modules["voice.stt"].transcribe_file.return_value = {"text": "", "language": "de"}
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("test.webm", file_data, "audio/webm")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["text"] == ""
        assert "error" in data

    def test_stt_upload_wrong_extension(self, client):
        """Upload a file with unsupported extension."""
        sys.modules["voice.stt"].transcribe_file.reset_mock()
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("test.txt", file_data, "text/plain")},
        )
        assert res.status_code == 415
        assert sys.modules["voice.stt"].transcribe_file.call_count == 0

    def test_stt_upload_wrong_mime_type(self, client):
        sys.modules["voice.stt"].transcribe_file.reset_mock()
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("test.webm", file_data, "text/plain")},
        )
        assert res.status_code == 415
        assert sys.modules["voice.stt"].transcribe_file.call_count == 0

    def test_stt_upload_accepts_browser_webm_mime(self, client):
        sys.modules["voice.stt"].transcribe_file.return_value = "Hallo WebM"
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("recording.webm", file_data, "video/webm")},
        )
        assert res.status_code == 200
        assert res.json()["text"] == "Hallo WebM"

    def test_stt_upload_accepts_octet_stream_with_audio_extension(self, client):
        sys.modules["voice.stt"].transcribe_file.return_value = "Hallo Blob"
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"audio": ("recording.webm", file_data, "application/octet-stream")},
        )
        assert res.status_code == 200
        assert res.json()["text"] == "Hallo Blob"

    def test_stt_audit_does_not_store_transcript_text(self, client, monkeypatch):
        import backend.router_voice as router_voice

        secret_text = "Mein API key ist sk-testsecret12345 und token=supersecretvalue"
        seen = []
        monkeypatch.setattr(router_voice, "audit_log", lambda *args, **kwargs: seen.append(args))
        sys.modules["voice.stt"].transcribe_file.return_value = {"text": secret_text, "language": "de"}
        file_data = io.BytesIO(b"fake audio data")

        res = client.post(
            "/voice/stt",
            files={"audio": ("recording.webm", file_data, "audio/webm")},
        )

        assert res.status_code == 200
        assert res.json()["text"] == secret_text
        audit_text = str(seen)
        assert "textChars=" in audit_text
        assert "language=de" in audit_text
        assert "Mein API key" not in audit_text
        assert "sk-testsecret12345" not in audit_text
        assert "supersecretvalue" not in audit_text


# ══════════════════════════════════════════════════
#  WAKEWORD ENDPOINTS
# ══════════════════════════════════════════════════

class TestWakeWordEndpoints:
    def test_wakeword_status(self, client):
        res = client.get("/voice/wakeword/status")
        assert res.status_code == 200
        data = res.json()
        assert data["active"] is False
        assert data["ready"] is False
        assert "error" in data

    def test_wakeword_start_returns_ready_status(self, client):
        res = client.post("/voice/wakeword/start")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "started"
        assert data["active"] is True
        assert data["ready"] is True

    def test_wakeword_start_failure_is_reported(self, client):
        sys.modules["voice.wakeword"].WakeWordDetector.start_error = "microphone unavailable"
        res = client.post("/voice/wakeword/start")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "failed"
        assert data["active"] is False
        assert data["ready"] is False
        assert data["error"] == "microphone unavailable"

    def test_wakeword_start_failure_redacts_internal_error(self, client):
        local_path = r"C:\Users\admin\voice\model.onnx"
        sys.modules["voice.wakeword"].WakeWordDetector.start_error = (
            f"load failed at {local_path} token=supersecretvalue"
        )

        res = client.post("/voice/wakeword/start")

        assert res.status_code == 503
        data = res.json()
        assert "[local-path-redacted]" in data["error"]
        assert "[REDACTED]" in data["error"]
        assert local_path not in data["error"]
        assert "supersecretvalue" not in data["error"]

    def test_wakeword_start_not_ready_is_rejected(self, client):
        sys.modules["voice.wakeword"].WakeWordDetector.start_ready = False
        res = client.post("/voice/wakeword/start")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "failed"
        assert data["active"] is False
        assert data["ready"] is False
        assert "bereit" in data["error"]

    def test_wakeword_status_normalizes_numpy_scalars(self, client):
        import numpy as np
        from backend.router_voice import _wakeword_status_payload

        class Detector:
            @property
            def status(self):
                return {
                    "sensitivity": np.float32(0.007),
                    "last_window_rms": np.float32(0.004),
                    "wake_checks": np.int64(3),
                    "stt_checks": np.int64(2),
                    "skipped_stt_checks": np.int64(1),
                    "non_wake_transcripts": np.int64(4),
                    "fallback_stt_interval_s": np.float32(3.5),
                }

        payload = _wakeword_status_payload(Detector())
        assert payload["sensitivity"] == pytest.approx(0.007)
        assert payload["last_window_rms"] == pytest.approx(0.004)
        assert payload["wake_checks"] == 3
        assert payload["stt_checks"] == 2
        assert payload["skipped_stt_checks"] == 1
        assert payload["non_wake_transcripts"] == 4
        assert payload["fallback_stt_interval_s"] == pytest.approx(3.5)

    def test_wakeword_sensitivity_get(self, client):
        res = client.get("/voice/wakeword/sensitivity")
        assert res.status_code == 200

    def test_wakeword_sensitivity_set_invalid(self, client):
        res = client.post("/voice/wakeword/sensitivity", json={"sensitivity": 5.0})
        # Should reject out-of-range values
        assert res.status_code in (400, 409)

    def test_wakeword_events_fallback(self, client):
        res = client.get("/voice/wakeword/events", params={"client_id": "test123"})
        assert res.status_code == 200


# ══════════════════════════════════════════════════
#  REQUEST MODEL VALIDATION
# ══════════════════════════════════════════════════

class TestRequestModels:
    def test_tts_request_defaults(self):
        from backend.router_voice import TTSRequest
        req = TTSRequest()
        assert req.text == ""

    def test_sensitivity_request_default(self):
        from backend.router_voice import SensitivityRequest
        req = SensitivityRequest()
        assert req.sensitivity == 0.015

    def test_stt_engine_request_default(self):
        from backend.router_voice import STTEngineRequest
        req = STTEngineRequest()
        assert req.engine == "deepgram"
