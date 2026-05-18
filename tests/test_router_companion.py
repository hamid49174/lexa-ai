"""Tests for backend/router_companion.py — Command execution API endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────

@pytest.fixture
def mock_companion():
    """Create a mock companion engine."""
    mock = MagicMock()
    mock.commands = {
        "system_info": lambda: None,
        "app_open": lambda name="": None,
        "screenshot": lambda: None,
        "process_kill": lambda name="": None,
        "shutdown": lambda: None,
        "format_disk": lambda: None,
    }
    mock.execute.return_value = {"success": True, "data": "Executed successfully"}
    mock.get_plugin_info.return_value = []
    mock._loaded_plugins = {}
    mock.get_pending_timers.return_value = []
    mock.acknowledge_timers.return_value = "OK"
    return mock


@pytest.fixture
def client(mock_companion, disable_rate_limit):
    """Create test client with mocked companion and security."""
    with patch("backend.router_companion.companion", mock_companion), \
         patch("backend.router_companion.is_command_allowed") as mock_allowed, \
         patch("backend.router_companion.audit_log"), \
         patch("backend.router_companion.validate_params", side_effect=lambda cmd, params: params):

        # Default: always_allowed
        mock_allowed.return_value = "always_allowed"

        from backend.router_companion import router
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app), mock_companion, mock_allowed


# ══════════════════════════════════════════════════
#  EXECUTE ENDPOINT
# ══════════════════════════════════════════════════

class TestExecuteCommand:
    def test_execute_allowed_command(self, client):
        tc, mock_comp, _ = client
        res = tc.post("/companion/execute", json={"command": "system_info"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        mock_comp.execute.assert_called_once()

    def test_execute_blocked_command(self, client):
        tc, mock_comp, mock_allowed = client
        mock_allowed.return_value = "blocked"
        res = tc.post("/companion/execute", json={"command": "format_disk"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "blockiert" in data["error"].lower()
        mock_comp.execute.assert_not_called()

    def test_execute_confirmation_required_without_confirm(self, client):
        tc, mock_comp, mock_allowed = client
        mock_allowed.return_value = "confirmation_required"
        res = tc.post("/companion/execute", json={"command": "shutdown"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["requires_confirmation"] is True
        mock_comp.execute.assert_not_called()

    def test_execute_confirmation_required_with_confirm(self, client):
        tc, mock_comp, mock_allowed = client
        mock_allowed.return_value = "confirmation_required"
        res = tc.post("/companion/execute", json={
            "command": "shutdown",
            "confirmed": True,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        mock_comp.execute.assert_called_once()

    def test_execute_unknown_requires_confirmation(self, client):
        tc, mock_comp, mock_allowed = client
        mock_allowed.return_value = "unknown"
        res = tc.post("/companion/execute", json={"command": "mystery_cmd"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["requires_confirmation"] is True

    def test_execute_unknown_with_confirm(self, client):
        tc, mock_comp, mock_allowed = client
        mock_allowed.return_value = "unknown"
        res = tc.post("/companion/execute", json={
            "command": "mystery_cmd",
            "confirmed": True,
        })
        assert res.status_code == 200
        assert res.json()["success"] is True

    def test_dry_run(self, client):
        tc, mock_comp, _ = client
        res = tc.post("/companion/execute", json={
            "command": "system_info",
            "dry_run": True,
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["dry_run"] is True
        mock_comp.execute.assert_not_called()

    def test_execute_with_params(self, client):
        tc, mock_comp, _ = client
        res = tc.post("/companion/execute", json={
            "command": "app_open",
            "params": {"name": "notepad"},
        })
        assert res.status_code == 200
        mock_comp.execute.assert_called_once_with("app_open", {"name": "notepad"})

    def test_execute_personal_os_action_routes_without_companion(self, client, monkeypatch):
        tc, mock_comp, _ = client
        calls = []

        async def fake_personal_os_action(command, params):
            calls.append((command, params))
            return {"success": True, "data": "Personal OS result"}

        monkeypatch.setattr(
            "backend.router_companion.execute_personal_os_action",
            fake_personal_os_action,
        )

        res = tc.post("/companion/execute", json={
            "command": "personal_os_query",
            "params": {"areaPath": "00_System"},
        })

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"] == "Personal OS result"
        assert calls == [("personal_os_query", {"areaPath": "00_System"})]
        mock_comp.execute.assert_not_called()

    def test_execute_exception_handling(self, client):
        tc, mock_comp, _ = client
        mock_comp.execute.side_effect = RuntimeError("Kaboom")
        res = tc.post("/companion/execute", json={"command": "system_info"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "Kaboom" in data["error"]


# ══════════════════════════════════════════════════
#  COMMANDS LIST
# ══════════════════════════════════════════════════

class TestCommandsList:
    def test_list_commands(self, client):
        tc, _, _ = client
        res = tc.get("/companion/commands")
        assert res.status_code == 200
        data = res.json()
        assert "commands" in data
        assert "total" in data
        assert data["total"] == len(data["commands"])


# ══════════════════════════════════════════════════
#  PLUGINS
# ══════════════════════════════════════════════════

class TestAuditRecent:
    def test_recent_audit_endpoint_is_read_only(self, client, monkeypatch):
        tc, mock_comp, _ = client
        calls = []
        rate_buckets = []

        def fake_read(limit, hide_noise=False):
            calls.append((limit, hide_noise))
            return {
                "ok": True,
                "source": "audit.log",
                "limit": limit,
                "count": 1,
                "entries": [{
                    "timestamp": "2026-05-17T07:02:00",
                    "command": "system_info",
                    "status": "executed",
                    "details": "params=[]",
                }],
            }

        def fake_check_rate_limit(bucket):
            rate_buckets.append(bucket)
            return True

        monkeypatch.setattr("backend.router_companion.read_recent_audit_entries", fake_read)
        monkeypatch.setattr("backend.router_companion.check_rate_limit", fake_check_rate_limit)

        res = tc.get("/companion/audit/recent?limit=12&hideNoise=true")

        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["entries"][0]["command"] == "system_info"
        assert calls == [(12, True)]
        assert rate_buckets == ["audit_read"]
        mock_comp.execute.assert_not_called()

    def test_recent_audit_endpoint_rate_limits_without_reading_log(self, client, monkeypatch):
        tc, mock_comp, _ = client
        read_calls = []

        def fake_read(limit, hide_noise=False):
            read_calls.append((limit, hide_noise))
            return {"ok": True, "entries": []}

        monkeypatch.setattr("backend.router_companion.read_recent_audit_entries", fake_read)
        monkeypatch.setattr("backend.router_companion.check_rate_limit", lambda bucket: False)

        res = tc.get("/companion/audit/recent?limit=12&hideNoise=true")

        assert res.status_code == 429
        assert read_calls == []
        mock_comp.execute.assert_not_called()


class TestPlugins:
    def test_list_plugins(self, client):
        tc, _, _ = client
        res = tc.get("/companion/plugins")
        assert res.status_code == 200
        data = res.json()
        assert "plugins" in data
        assert "plugin_commands" in data


# ══════════════════════════════════════════════════
#  TIMERS
# ══════════════════════════════════════════════════

class TestTimers:
    def test_pending_timers(self, client):
        tc, _, _ = client
        res = tc.get("/companion/timers")
        assert res.status_code == 200
        assert "timers" in res.json()

    def test_acknowledge_timers(self, client):
        tc, _, _ = client
        res = tc.post("/companion/timers/acknowledge")
        assert res.status_code == 200
        assert "status" in res.json()


# ══════════════════════════════════════════════════
#  BATCH EXECUTION
# ══════════════════════════════════════════════════

class TestBatchExecution:
    def test_batch_basic(self, client):
        tc, mock_comp, _ = client
        res = tc.post("/companion/execute/batch", json={
            "commands": [
                {"command": "system_info"},
                {"command": "screenshot"},
            ],
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["results"]) == 2

    def test_batch_max_limit(self, client):
        tc, _, _ = client
        cmds = [{"command": "system_info"} for _ in range(11)]
        res = tc.post("/companion/execute/batch", json={"commands": cmds})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert "10" in data["error"]

    def test_batch_blocked_command_skipped(self, client):
        tc, mock_comp, mock_allowed = client

        def _side_effect(cmd):
            if cmd == "format_disk":
                return "blocked"
            return "always_allowed"

        mock_allowed.side_effect = _side_effect
        res = tc.post("/companion/execute/batch", json={
            "commands": [
                {"command": "format_disk"},
                {"command": "system_info"},
            ],
            "stop_on_error": False,
        })
        assert res.status_code == 200
        data = res.json()
        assert len(data["results"]) == 2
        assert data["results"][0]["success"] is False

    def test_batch_stop_on_error(self, client):
        tc, mock_comp, mock_allowed = client

        def _side_effect(cmd):
            if cmd == "format_disk":
                return "blocked"
            return "always_allowed"

        mock_allowed.side_effect = _side_effect
        res = tc.post("/companion/execute/batch", json={
            "commands": [
                {"command": "format_disk"},
                {"command": "system_info"},
            ],
            "stop_on_error": True,
        })
        assert res.status_code == 200
        data = res.json()
        # Should stop after first blocked command
        assert len(data["results"]) == 1

    def test_batch_empty(self, client):
        tc, _, _ = client
        res = tc.post("/companion/execute/batch", json={"commands": []})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["results"]) == 0


# ══════════════════════════════════════════════════
#  VALIDATE RESULT HELPER
# ══════════════════════════════════════════════════

class TestValidateResult:
    def test_valid_result(self):
        from backend.router_companion import _validate_result
        result = _validate_result({"success": True, "data": "ok"})
        assert result["success"] is True
        assert result["data"] == "ok"

    def test_non_dict_result(self):
        from backend.router_companion import _validate_result
        result = _validate_result("string result")
        assert result["success"] is False
        assert "Unerwartetes" in result["error"]

    def test_missing_keys_defaults(self):
        from backend.router_companion import _validate_result
        result = _validate_result({})
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] is None

    def test_requires_confirmation_passthrough(self):
        from backend.router_companion import _validate_result
        result = _validate_result({"success": False, "requires_confirmation": True})
        assert result["requires_confirmation"] is True
