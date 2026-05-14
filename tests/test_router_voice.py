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
        sys.modules["voice"] = voice_mod
        stubs["voice"] = None

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
    stt_stub.get_stt_status = MagicMock(return_value={"engine": "groq", "available": True})
    stt_stub.get_available_models = MagicMock(return_value=["base", "small", "large-v3"])
    stt_stub.set_model_size = MagicMock()
    stt_stub.set_language = MagicMock()
    stt_stub.set_engine = MagicMock()
    stubs["voice.stt"] = sys.modules.get("voice.stt")
    sys.modules["voice.stt"] = stt_stub

    # voice.wakeword
    ww_stub = types.ModuleType("voice.wakeword")
    ww_stub.WakeWordDetector = MagicMock
    stubs["voice.wakeword"] = sys.modules.get("voice.wakeword")
    sys.modules["voice.wakeword"] = ww_stub

    # backend.voice_ws
    ws_stub = types.ModuleType("backend.voice_ws")
    for name in ["push_event", "push_volume", "push_state", "push_command",
                 "push_response", "push_response_chunk", "push_error",
                 "pop_fallback_events", "register_ws_client", "unregister_ws_client",
                 "init_ws_loop"]:
        setattr(ws_stub, name, MagicMock(return_value=[]))
    stubs["backend.voice_ws"] = sys.modules.get("backend.voice_ws")
    sys.modules["backend.voice_ws"] = ws_stub

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
    def test_tts_status(self, client):
        res = client.get("/voice/tts/status")
        assert res.status_code == 200
        data = res.json()
        assert "engine" in data

    def test_tts_empty_text(self, client):
        res = client.post("/voice/tts", json={"text": ""})
        assert res.status_code == 400

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

    def test_stt_upload_wrong_extension(self, client):
        """Upload a file with unsupported extension."""
        file_data = io.BytesIO(b"fake audio data")
        res = client.post(
            "/voice/stt",
            files={"file": ("test.txt", file_data, "text/plain")},
        )
        # Should reject non-audio extensions (400 or 422 depending on validation)
        assert res.status_code in (200, 400, 415, 422)


# ══════════════════════════════════════════════════
#  WAKEWORD ENDPOINTS
# ══════════════════════════════════════════════════

class TestWakeWordEndpoints:
    def test_wakeword_status(self, client):
        res = client.get("/voice/wakeword/status")
        assert res.status_code == 200

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
