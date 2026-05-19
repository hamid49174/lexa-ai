"""
Smoke tests for action_parser.py — permission handling and JSON extraction.
Run with: python -m pytest tests/test_action_parser.py -v
"""
import sys
import types
import importlib
import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Load action_parser in isolation without polluting sys.modules for other tests.
# We use importlib.util to load the module from file and supply a stub for
# backend.security *only inside this module's namespace*, not in sys.modules.
# ---------------------------------------------------------------------------

def _load_action_parser():
    """Load action_parser.py with stubbed dependencies, no sys.modules pollution."""
    import importlib.util
    import pathlib

    # Create a minimal backend.security stub
    security_stub = types.ModuleType("backend.security")
    security_stub.is_command_allowed = lambda cmd: "allowed"
    security_stub.audit_log = lambda *a, **kw: None
    security_stub.validate_command_output = lambda cmd: None
    security_stub.sanitize_input = lambda t: t

    # Create a minimal backend.i18n stub
    i18n_stub = types.ModuleType("backend.i18n")
    i18n_stub.t = lambda key, **kw: key  # return the key as-is

    # Save any existing modules we'll temporarily override
    saved = {}
    keys_to_stub = ["backend", "backend.security", "backend.i18n"]
    for key in keys_to_stub:
        if key in sys.modules:
            saved[key] = sys.modules[key]

    try:
        # Temporarily inject stubs
        if "backend" not in sys.modules:
            sys.modules["backend"] = types.ModuleType("backend")
        sys.modules["backend.security"] = security_stub
        sys.modules["backend.i18n"] = i18n_stub

        spec = importlib.util.spec_from_file_location(
            "backend.action_parser",
            pathlib.Path(__file__).parent.parent / "backend" / "action_parser.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        # Restore original sys.modules state — clean up after ourselves
        for key in keys_to_stub:
            if key in saved:
                sys.modules[key] = saved[key]
            elif key in sys.modules:
                del sys.modules[key]


ap = _load_action_parser()


class TestPermissionHandling(unittest.TestCase):
    """Verify that 'unknown' commands require confirmation, never auto-execute."""

    def _call(self, permission: str, action_name: str = "test_cmd"):
        """Call process_ai_response with a faked is_command_allowed return."""
        ai_resp = f'{{"action": "{action_name}", "params": {{}}, "message": "ok"}}'
        with patch.object(ap, "is_command_allowed", return_value=permission), \
             patch.object(ap, "validate_command_output", return_value=None), \
             patch.object(ap, "audit_log"):
            return ap.process_ai_response(ai_resp, source="chat")

    def test_allowed_executes_without_confirmation(self):
        reply, action, requires_conf = self._call("allowed")
        self.assertIsNotNone(action)
        self.assertFalse(requires_conf)

    def test_blocked_returns_no_action(self):
        reply, action, requires_conf = self._call("blocked")
        self.assertIsNone(action)
        self.assertFalse(requires_conf)

    def test_confirmation_required_sets_flag(self):
        reply, action, requires_conf = self._call("confirmation_required")
        self.assertIsNotNone(action)
        self.assertTrue(requires_conf)

    def test_unknown_requires_confirmation_not_autoexecute(self):
        """THE KEY FIX: 'unknown' permission must never silently execute."""
        reply, action, requires_conf = self._call("unknown")
        # action is returned (so the user can confirm it)
        self.assertIsNotNone(action)
        # but it MUST require confirmation
        self.assertTrue(
            requires_conf,
            "'unknown' commands must require user confirmation before execution",
        )

    def test_unknown_reply_mentions_unknown(self):
        """Reply for unknown commands should indicate it needs approval."""
        reply, _, _ = self._call("unknown")
        self.assertTrue(
            "unbekannt" in reply.lower()
            or "ausführen" in reply.lower()
            or "unknown" in reply.lower()  # i18n key fallback in test env
            or "command" in reply.lower(),
            f"Expected warning in reply, got: {reply}",
        )

    def test_json_action_null_params_becomes_empty_dict(self):
        """Providers can emit null params; execution code expects a dict."""
        ai_resp = '{"action": "system_info", "params": null, "message": "ok"}'
        with patch.object(ap, "is_command_allowed", return_value="allowed"), \
             patch.object(ap, "validate_command_output", return_value=None), \
             patch.object(ap, "audit_log"):
            _, action, requires_conf = ap.process_ai_response(ai_resp, source="chat")
        self.assertIsNotNone(action)
        self.assertFalse(requires_conf)
        self.assertEqual(action["params"], {})

    def test_native_tool_call_null_arguments_becomes_empty_dict(self):
        """Native tool calls can carry null arguments; keep parser defensive."""
        with patch.object(ap, "is_command_allowed", return_value="allowed"), \
             patch.object(ap, "validate_command_output", return_value=None), \
             patch.object(ap, "audit_log"):
            _, action, requires_conf = ap.process_tool_call(
                [{"id": "x", "name": "system_info", "arguments": None}],
                ai_message="",
                source="chat_stream",
            )
        self.assertIsNotNone(action)
        self.assertFalse(requires_conf)
        self.assertEqual(action["params"], {})


class TestJsonExtraction(unittest.TestCase):
    """Verify robust JSON extraction from various AI response formats."""

    def _extract(self, text: str):
        return ap.extract_json_action(text)

    def test_plain_json(self):
        r = self._extract('{"action":"app_open","params":{"name":"notepad"}}')
        self.assertEqual(r["action"], "app_open")

    def test_markdown_code_block(self):
        r = self._extract('Sure!\n```json\n{"action":"screenshot","params":{}}\n```')
        self.assertEqual(r["action"], "screenshot")

    def test_json_with_surrounding_text(self):
        r = self._extract('I will do this: {"action":"system_info","params":{}} Done.')
        self.assertIsNotNone(r)
        self.assertEqual(r["action"], "system_info")

    def test_no_json_returns_none(self):
        r = self._extract("Just a plain text response without any JSON.")
        self.assertIsNone(r)

    def test_non_action_json_returns_none(self):
        r = self._extract('{"message": "hello", "status": "ok"}')
        self.assertIsNone(r)


if __name__ == "__main__":
    unittest.main()
