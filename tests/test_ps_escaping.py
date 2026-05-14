"""
Smoke tests for PowerShell argument sanitization in system_tools.py.
Run with: python -m pytest tests/test_ps_escaping.py -v
"""
import types, pathlib, importlib.util, unittest

spec = importlib.util.spec_from_file_location(
    "companion.system_tools",
    pathlib.Path(__file__).parent.parent / "companion" / "system_tools.py",
)
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

# Keep this smoke test hermetic without poisoning sys.modules for the rest of pytest.
st.subprocess.run = lambda *a, **kw: types.SimpleNamespace(returncode=0, stdout="", stderr="")


class TestSanitizePsArg(unittest.TestCase):
    """
    Verify _sanitize_ps_arg() correctly escapes for PowerShell double-quoted strings.

    The function uses PS double-quoted string escaping rules:
      - backtick (`) → doubled (``)   — backtick is the PS escape char
      - double-quote (") → `"         — escaped with backtick
      - dollar sign ($) → `$          — prevents variable expansion
      - newline / carriage-return     — stripped entirely
    Single quotes and semicolons are NOT injection vectors inside double-quoted
    PS strings and are intentionally left as-is.
    """

    def sanitize(self, s: str) -> str:
        return st._sanitize_ps_arg(s)

    def test_plain_string_unchanged(self):
        self.assertEqual(self.sanitize("notepad"), "notepad")

    def test_backtick_doubled(self):
        # backtick → `` (doubled) so it becomes literal backtick in PS
        result = self.sanitize("foo`bar")
        self.assertEqual(result, "foo``bar", "Backtick must be doubled for PS escaping")

    def test_dollar_sign_escaped_with_backtick(self):
        # $var → `$var — in PS double-quoted strings `$ is a literal $, not a variable
        result = self.sanitize("$env:PATH")
        # Every $ must be preceded by a backtick
        import re
        unescaped = re.search(r'(?<!`)\$', result)
        self.assertIsNone(unescaped, f"Unescaped $ found in: {result!r}")

    def test_dollar_paren_injection_neutralised(self):
        # $(calc) — $ must be escaped so $( is not a subexpression in PS
        payload = "$(calc)"
        result = self.sanitize(payload)
        # Every $ must be preceded by a backtick → `$(calc) is safe (literal $)
        self.assertIn("`$", result, "$ must be escaped with backtick")
        # Confirm no unescaped $ remains
        import re
        unescaped = re.search(r'(?<!`)\$', result)
        self.assertIsNone(unescaped, f"Unescaped $ found in: {result!r}")

    def test_double_quote_escaped(self):
        result = self.sanitize('say "hello"')
        self.assertNotIn('"hello"', result, "Raw double-quotes must be escaped")
        self.assertIn('`"', result)

    def test_newline_stripped(self):
        result = self.sanitize("notepad\nrm -rf /")
        self.assertNotIn("\n", result)

    def test_carriage_return_stripped(self):
        result = self.sanitize("notepad\rrm")
        self.assertNotIn("\r", result)

    def test_empty_string(self):
        self.assertEqual(self.sanitize(""), "")

    def test_unicode_safe(self):
        result = self.sanitize("Präsentation")
        self.assertIn("sentation", result)


class TestWindowLayoutAssemblyOrder(unittest.TestCase):
    """Verify window_layout returns an error when PowerShell fails."""

    def test_ps_failure_returns_error_string(self):
        import types as _types
        failing_run = lambda *a, **kw: _types.SimpleNamespace(
            returncode=1, stdout="", stderr="Assembly load error"
        )
        # Patch subprocess.run inside the module
        original = st.subprocess.run
        st.subprocess.run = failing_run
        try:
            result = st.window_layout("left-half")
            self.assertIn("Fehler", result, "Should report error when PS exits non-zero")
        finally:
            st.subprocess.run = original

    def test_ps_success_returns_confirmation(self):
        import types as _types
        ok_run = lambda *a, **kw: _types.SimpleNamespace(
            returncode=0, stdout="OK", stderr=""
        )
        original = st.subprocess.run
        st.subprocess.run = ok_run
        try:
            result = st.window_layout("left-half")
            # Result is now an i18n key or localized string
            self.assertTrue(
                "left-half" in result or "layoutApplied" in result,
                f"Expected layout confirmation, got: {result}"
            )
            self.assertNotIn("Fehler", result)
        finally:
            st.subprocess.run = original


if __name__ == "__main__":
    unittest.main()
