"""Tests for backend/ai_engine.py — keyword extraction, command selection,
token estimation, and conversation summarization."""

import pytest


# ---------------------------------------------------------------------------
#  Token Estimation (Fix #1)
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    def test_estimate_tokens_accepts_int(self):
        """_estimate_tokens must accept an int (char count), not a string."""
        from backend.ai_engine import _estimate_tokens
        result = _estimate_tokens(400)
        assert result == 100

    def test_estimate_tokens_zero(self):
        from backend.ai_engine import _estimate_tokens
        assert _estimate_tokens(0) == 0

    def test_check_token_budget_does_not_crash(self):
        """_check_token_budget should run without TypeError."""
        from backend.ai_engine import _check_token_budget
        # Should not raise — previously crashed with len(int)
        _check_token_budget("System prompt text", [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ])


# ---------------------------------------------------------------------------
#  Keyword Extraction
# ---------------------------------------------------------------------------

class TestKeywordExtraction:
    def test_stop_words_removed(self):
        """German stop words like 'kannst', 'mir', 'bitte' should be removed."""
        from backend.ai_engine import _extract_keywords
        keywords = _extract_keywords("Hey Lexa kannst du mir bitte die Lautstärke auf 50 setzen")
        assert "kannst" not in keywords
        assert "bitte" not in keywords
        assert "lautstärke" in keywords or "setzen" in keywords

    def test_short_words_removed(self):
        """Words shorter than 3 chars should be filtered."""
        from backend.ai_engine import _extract_keywords
        keywords = _extract_keywords("du da es so am um")
        assert len(keywords) == 0

    def test_dedup_keywords(self):
        """Duplicate words should only appear once."""
        from backend.ai_engine import _extract_keywords
        keywords = _extract_keywords("test test test andere")
        assert keywords.count("test") == 1

    def test_max_keywords_limit(self):
        """Should return at most max_keywords results."""
        from backend.ai_engine import _extract_keywords
        keywords = _extract_keywords(
            "python java rust golang typescript kotlin swift ruby elixir",
            max_keywords=3,
        )
        assert len(keywords) <= 3

    def test_empty_input(self):
        from backend.ai_engine import _extract_keywords
        assert _extract_keywords("") == []


# ---------------------------------------------------------------------------
#  Tool Context Selection (Phase 40 — replaced _select_relevant_commands)
# ---------------------------------------------------------------------------

class TestToolContextSelection:
    def test_youtube_selects_browser_tools(self):
        """A YouTube request should include youtube/browser tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("spiele Musik auf YouTube")
        names = [t["function"]["name"] for t in tools]
        assert any("youtube" in n for n in names)

    def test_todo_selects_productivity_tools(self):
        """A todo request should include productivity tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("zeig mir meine todos")
        names = [t["function"]["name"] for t in tools]
        assert any("todo" in n for n in names)

    def test_git_selects_dev_tools(self):
        """A git request should include git tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("zeig mir den git status")
        names = [t["function"]["name"] for t in tools]
        assert any("git" in n for n in names)

    def test_personal_os_selects_os_tools(self):
        """A Personal OS request should include read-only OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("lies das Personal OS Manifest und zeig mir den Graph")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_diagnostics" in names
        assert "personal_os_raw_inbox_status" in names
        assert "personal_os_read_file" in names
        assert "personal_os_graph" in names
        assert "personal_os_context_pack" in names
        assert "personal_os_lexa_code_loop" in names
        assert "personal_os_review_draft" in names
        assert "personal_os_draft_history" in names

    def test_max_tools_limit(self):
        """Context selection should not exceed TOOL_USE_MAX_TOOLS + padding allowance."""
        from backend.tool_registry import get_tools_for_context
        from backend.config import TOOL_USE_MAX_TOOLS
        tools = get_tools_for_context(
            "oeffne youtube, erstelle todo, git status, docker ps, screenshot"
        )
        # Context-aware selection may slightly exceed the soft limit due to
        # padding with basis tools. Hard cap is TOOL_USE_MAX_TOOLS + 10.
        assert len(tools) <= TOOL_USE_MAX_TOOLS + 10

    def test_generic_question_returns_tools(self):
        """A generic question should still return some tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("was ist der Sinn des Lebens")
        assert len(tools) > 0

    def test_internal_prompt_questions_return_no_tools(self):
        """Prompt/tool-rule meta questions should stay conversational."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("ich brauche die Tool-Regeln fuer die App")
        assert tools == []


# ---------------------------------------------------------------------------
#  Conversation Summarization
# ---------------------------------------------------------------------------

class TestConversationSummarization:
    def test_summarize_empty_returns_empty(self):
        """Summarizing empty messages should return something sensible."""
        from backend.ai_engine import _summarize_messages_local
        result = _summarize_messages_local([])
        assert isinstance(result, str)

    def test_summarize_extracts_topics(self):
        """Summarization should extract discussed topics."""
        from backend.ai_engine import _summarize_messages_local
        messages = [
            {"role": "user", "content": "Wie wird das Wetter morgen?"},
            {"role": "assistant", "content": "Morgen wird es sonnig mit 22 Grad."},
            {"role": "user", "content": "Starte einen Pomodoro Timer"},
            {"role": "assistant", "content": '{"action": "pomodoro_start", "params": {"duration": 25}}'},
        ]
        result = _summarize_messages_local(messages)
        assert isinstance(result, str)
        assert len(result) > 10  # Should have some content

    def test_summarize_detects_actions(self):
        """Summarization should detect executed actions."""
        from backend.ai_engine import _summarize_messages_local
        messages = [
            {"role": "assistant", "content": '{"action": "volume_set", "params": {"level": 50}}'},
            {"role": "assistant", "content": '{"action": "app_open", "params": {"name": "Chrome"}}'},
        ]
        result = _summarize_messages_local(messages)
        # Should mention the actions
        assert "volume_set" in result or "app_open" in result or "Aktionen" in result


# ---------------------------------------------------------------------------
#  Multi-Provider Model Selection
# ---------------------------------------------------------------------------

class TestModelSelection:
    def test_set_ai_model_accepts_provider_prefixed_ids(self):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            result = ai_engine.set_ai_model("openai:gpt-4o")
            current = ai_engine.get_ai_models()
            assert "OpenAI" in result
            assert current["current"] == "openai:gpt-4o"
            assert current["current_provider"] == "openai"
        finally:
            ai_engine.set_ai_model(original)

    def test_set_ai_model_accepts_legacy_groq_ids(self):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            ai_engine.set_ai_model("llama-3.1-8b-instant")
            current = ai_engine.get_ai_models()
            assert current["current"] == "groq:llama-3.1-8b-instant"
            assert current["current_provider"] == "groq"
        finally:
            ai_engine.set_ai_model(original)

    def test_get_ai_models_returns_grouped_provider_data(self):
        from backend.ai_engine import get_ai_models

        models = get_ai_models()
        assert "grouped" in models
        assert "openai" in models["grouped"]
        assert "gemini" in models["grouped"]
        assert models["grouped"]["openai"]["models"]


class TestProviderStatus:
    def test_get_ai_status_reports_all_providers(self, monkeypatch):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            ai_engine.set_ai_model("gemini:gemini-2.5-flash")
            monkeypatch.setattr(ai_engine, "_get_groq_client", lambda: object())
            monkeypatch.setattr(ai_engine, "_get_openai_client", lambda: object())
            monkeypatch.setattr(ai_engine, "_get_gemini_client", lambda: object())

            status = ai_engine.get_ai_status()
            assert status["groq"]["available"] is True
            assert status["openai"]["available"] is True
            assert status["gemini"]["available"] is True
            # ollama removed in Phase 40+ (no longer a separate status entry)
            assert status["selected_provider"] == "gemini"
            assert status["active_provider"] == "gemini"
        finally:
            ai_engine.set_ai_model(original)
