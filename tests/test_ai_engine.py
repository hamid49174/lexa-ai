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

    def test_research_selects_browser_tools(self):
        """A source-backed research request should include web tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("erstelle einen quellenbasierten research brief")
        names = [t["function"]["name"] for t in tools]
        assert any(n.startswith("web_") for n in names)

    def test_citation_analysis_selects_browser_tools(self):
        """Citation/source analysis requests should include web tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("create an analysis with citations and evidence")
        names = [t["function"]["name"] for t in tools]
        assert any(n.startswith("web_") for n in names)

    def test_workspace_draft_selects_personal_os_tools(self):
        """Workspace-draft requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("baue einen workspace draft als markdown kontext")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_context_pack" in names
        assert "personal_os_review_draft" in names

    def test_working_document_selects_personal_os_tools(self):
        """Lexa working-document requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("baue ein arbeitsdokument fuer Lexa")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_context_pack" in names
        assert "personal_os_review_draft" in names

    def test_context_pack_selects_personal_os_tools(self):
        """Context-pack requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("erstelle ein kontextpaket briefing fuer Lexa")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_context_pack" in names
        assert "personal_os_review_draft" in names

    def test_draft_review_selects_personal_os_tools(self):
        """Draft-review requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("pruefe die pending drafts zur freigabe")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_list_drafts" in names
        assert "personal_os_review_draft" in names

    def test_skill_draft_selects_personal_os_tools(self):
        """Skill-draft requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("entwirf einen Lexa Skill als Markdown Vorlage")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_context_pack" in names
        assert "personal_os_review_draft" in names

    def test_decision_brief_selects_personal_os_tools(self):
        """Decision-brief requests should include read-only Personal OS tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("erstelle einen entscheidungsbrief mit optionen und risiken")
        names = [t["function"]["name"] for t in tools]
        assert "personal_os_context_pack" in names
        assert "personal_os_review_draft" in names

    def test_ship_check_selects_dev_and_personal_os_tools(self):
        """Ship-check requests should include code and context review tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("release check fuer Lexa vor dem publish")
        names = [t["function"]["name"] for t in tools]
        assert "git_status" in names
        assert "personal_os_context_pack" in names

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

    def test_hermes_selects_hermes_tools(self):
        """Hermes requests should include the Hermes Agent bridge tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("nutze hermes agent um lexa im hintergrund zu verbessern")
        names = [t["function"]["name"] for t in tools]
        assert "hermes_status" in names
        assert "hermes_improve_lexa" in names
        assert "hermes_telegram_status" in names

    def test_hermes_pc_worker_file_request_selects_file_tools(self):
        """Hermes PC-worker requests should include file creation tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("Hermes oeffne VS Code und erstelle drei Dateien mit Code")
        names = [t["function"]["name"] for t in tools]
        assert "app_open" in names
        assert "folder_create" in names
        assert "file_write" in names

    def test_hermes_pc_worker_desktop_request_selects_desktop_tools(self):
        """Hermes PC-worker requests should include controlled desktop tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("Hermes klick auf den Button und tippe Hallo, aber aendere sonst nichts")
        names = [t["function"]["name"] for t in tools]
        assert "window_focus" in names
        assert "ui_tree" in names
        assert "ui_find" in names
        assert "ui_click" in names
        assert "screen_read_text" in names
        assert "desktop_position" in names
        assert "desktop_click" in names
        assert "desktop_click_text" in names
        assert "desktop_type" in names

    def test_os_agent_runtime_selects_os_agent_tools(self):
        """OS agent-runtime requests should include Lexa OS worker tools."""
        from backend.tool_registry import get_tools_for_context
        tools = get_tools_for_context("starte eine os agent runtime hintergrundaufgabe fuer lexa")
        names = [t["function"]["name"] for t in tools]
        assert "os_agent_status" in names
        assert "os_agent_start_task" in names

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


class TestQualityMode:
    def test_detect_quality_mode_for_top_tier_lexa_goal(self):
        from backend.ai_engine import _detect_quality_mode

        hint = _detect_quality_mode("mach bitte ziel ist lexa auf chagbt claude niviu+")

        assert "Top-tier Assistant Quality" in hint
        assert "kleinsten sinnvollen naechsten Schritt" in hint

    def test_build_messages_injects_quality_mode_for_complex_product_work(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel ist Lexa auf ChatGPT Claude Niveau+ verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Fakten/Annahmen/Entscheidungen" in system

    def test_detect_quality_mode_normalizes_real_umlauts(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel ist Lexa Qualit\u00e4t und Architektur professionell verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system

    def test_build_messages_skips_quality_mode_for_simple_greeting(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("hi")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_injects_senior_code_quality_for_python_generation(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "schreibe mir sehr komplexen Python Code wie von einem Senior mit 10 Jahren Erfahrung"
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Senior-Code-Antwort" in system
        assert "keine unbenutzten Imports/Parameter" in system
        assert "deprecated APIs" in system

    def test_build_messages_injects_ml_timeseries_guardrails(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "verbessere diesen Python Code fuer ein LSTM Zeitreihenmodell"
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "zeitliche Splits" in system
        assert "Scaler-Fit" in system
        assert "Tensor-Shapes" in system


class TestToolGatingForGeneration:
    @pytest.mark.parametrize("message", [
        "schriebe mir ein sehr sher komplexses python code was nur programiere mit 10 jahre erfrahrung koennene",
        "schreibe mir komplexen Python Code",
        "generiere ein async backend script in python",
        "implementiere eine REST API klasse",
    ])
    def test_disables_tools_for_direct_code_generation(self, message):
        from backend.ai_engine import _should_disable_tools_for_text_generation

        assert _should_disable_tools_for_text_generation(message) is True

    @pytest.mark.parametrize("message", [
        "spiel mir musik",
        "oeffne spotify",
        "wie ist wetter in hamburg",
        "git status",
        "suche python tutorial auf youtube",
        "erstelle einen quellenbasierten research brief",
    ])
    def test_keeps_tools_for_tool_backed_requests(self, message):
        from backend.ai_engine import _should_disable_tools_for_text_generation

        assert _should_disable_tools_for_text_generation(message) is False

    def test_chat_skips_tool_registry_for_code_generation(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config
        import backend.tool_registry as tool_registry

        tool_registry_calls = []
        received_tools = []

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", True)
        monkeypatch.setattr(
            ai_engine,
            "_get_selected_model_meta",
            lambda: {"id": "groq:test", "provider": "groq", "model": "test"},
        )
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_chat_result", lambda *args, **kwargs: None)

        def fake_get_tools(context, max_tools=45):
            tool_registry_calls.append((context, max_tools))
            raise AssertionError("tool registry should be skipped for code generation")

        def fake_chat(messages, selected_model, tools=None):
            received_tools.append(tools)
            return {"type": "text", "content": "ok"}

        monkeypatch.setattr(tool_registry, "get_tools_for_context", fake_get_tools)
        monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", fake_chat)

        result = ai_engine.chat("schreibe mir komplexen Python Code")

        assert result == {"type": "text", "content": "ok"}
        assert tool_registry_calls == []
        assert received_tools == [None]

    def test_chat_keeps_tool_registry_for_local_actions(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config
        import backend.tool_registry as tool_registry

        fake_tools = [{
            "type": "function",
            "function": {
                "name": "spotify_open",
                "description": "Open Spotify",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        tool_registry_calls = []
        received_tools = []

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", True)
        monkeypatch.setattr(
            ai_engine,
            "_get_selected_model_meta",
            lambda: {"id": "groq:test", "provider": "groq", "model": "test"},
        )
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_chat_result", lambda *args, **kwargs: None)

        def fake_get_tools(context, max_tools=45):
            tool_registry_calls.append((context, max_tools))
            return fake_tools

        def fake_chat(messages, selected_model, tools=None):
            received_tools.append(tools)
            return {"type": "text", "content": "ok"}

        monkeypatch.setattr(tool_registry, "get_tools_for_context", fake_get_tools)
        monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", fake_chat)

        result = ai_engine.chat("spiel mir musik")

        assert result == {"type": "text", "content": "ok"}
        assert tool_registry_calls == [("spiel mir musik", 45)]
        assert received_tools == [fake_tools]

    def test_agent_system_extra_keeps_tools_for_code_file_work(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config
        import backend.tool_registry as tool_registry

        fake_tools = [{
            "type": "function",
            "function": {
                "name": "file_write",
                "description": "Write file",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        tool_registry_calls = []
        received_tools = []

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", True)
        monkeypatch.setattr(
            ai_engine,
            "_get_selected_model_meta",
            lambda: {"id": "groq:test", "provider": "groq", "model": "test"},
        )
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_chat_result", lambda *args, **kwargs: None)

        def fake_get_tools(context, max_tools=45):
            tool_registry_calls.append((context, max_tools))
            return fake_tools

        def fake_chat(messages, selected_model, tools=None):
            received_tools.append(tools)
            return {"type": "text", "content": "ok"}

        monkeypatch.setattr(tool_registry, "get_tools_for_context", fake_get_tools)
        monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", fake_chat)

        result = ai_engine.chat(
            "schreibe drei Python Dateien in meinem Projekt",
            system_extra="Du bist im AGENT-MODUS. HERMES-WORKER-MODUS. Nutze Lexa-Tools.",
        )

        assert result == {"type": "text", "content": "ok"}
        assert tool_registry_calls == [("schreibe drei Python Dateien in meinem Projekt", 45)]
        assert received_tools == [fake_tools]

    def test_chat_stream_skips_tool_registry_for_code_generation(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config
        import backend.tool_registry as tool_registry

        class Delta:
            content = "ok"
            tool_calls = None

        class Choice:
            delta = Delta()

        class Chunk:
            choices = [Choice()]

        tool_registry_calls = []
        received_tools = []

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", True)
        monkeypatch.setattr(
            ai_engine,
            "_get_selected_model_meta",
            lambda: {"id": "groq:test", "provider": "groq", "model": "test"},
        )
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_interaction", lambda *args, **kwargs: None)

        def fake_get_tools(context, max_tools=45):
            tool_registry_calls.append((context, max_tools))
            raise AssertionError("tool registry should be skipped for code generation")

        def fake_stream(messages, selected_model, tools=None):
            received_tools.append(tools)
            return iter([Chunk()])

        monkeypatch.setattr(tool_registry, "get_tools_for_context", fake_get_tools)
        monkeypatch.setattr(ai_engine, "_stream_with_selected_provider", fake_stream)

        result = list(ai_engine.chat_stream("schreibe mir komplexen Python Code"))

        assert result == ["ok"]
        assert tool_registry_calls == []
        assert received_tools == [None]


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

    def test_set_ai_model_accepts_anthropic_ids(self):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            result = ai_engine.set_ai_model("anthropic:claude-sonnet-4-20250514")
            current = ai_engine.get_ai_models()
            assert "Claude" in result
            assert current["current"] == "anthropic:claude-sonnet-4-20250514"
            assert current["current_provider"] == "anthropic"
        finally:
            ai_engine.set_ai_model(original)

    def test_get_ai_models_returns_grouped_provider_data(self):
        from backend.ai_engine import get_ai_models

        models = get_ai_models()
        assert "grouped" in models
        assert "openai" in models["grouped"]
        assert "gemini" in models["grouped"]
        assert "anthropic" in models["grouped"]
        assert models["grouped"]["openai"]["models"]
        assert models["grouped"]["anthropic"]["models"]


class TestProviderStatus:
    def test_get_ai_status_reports_all_providers(self, monkeypatch):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            ai_engine.set_ai_model("gemini:gemini-2.5-flash")
            monkeypatch.setattr(ai_engine, "_get_groq_client", lambda: object())
            monkeypatch.setattr(ai_engine, "_get_openai_client", lambda: object())
            monkeypatch.setattr(ai_engine, "_get_gemini_client", lambda: object())
            monkeypatch.setattr(ai_engine, "_get_anthropic_api_key", lambda: "anthropic-key")

            status = ai_engine.get_ai_status()
            assert status["groq"]["available"] is True
            assert status["openai"]["available"] is True
            assert status["gemini"]["available"] is True
            assert status["anthropic"]["available"] is True
            # ollama removed in Phase 40+ (no longer a separate status entry)
            assert status["selected_provider"] == "gemini"
            assert status["active_provider"] == "gemini"
            assert status["fallback_enabled"] is True
            assert "fallback_order" in status
        finally:
            ai_engine.set_ai_model(original)


class TestProviderFallback:
    def test_503_is_temporary_model_error(self):
        from backend import ai_engine

        err = RuntimeError("503 Service Unavailable: model overloaded")

        assert ai_engine._categorize_error(err) == ai_engine._ErrorCategory.MODEL_ERROR

    def test_chat_fallback_tries_configured_provider_after_selected_failure(self, monkeypatch):
        from backend import ai_engine

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-2.5-flash"]
        calls = []

        def fake_chat(messages, selected_model=None, tools=None):
            calls.append(selected_model["id"])
            if selected_model["provider"] == "openai":
                return {"type": "text", "content": "Fallback antwortet."}
            return None

        monkeypatch.setattr(ai_engine, "_provider_available_for_fallback", lambda provider: provider == "openai")
        monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", fake_chat)

        result = ai_engine._chat_with_provider_fallbacks(
            [{"role": "user", "content": "ping"}],
            selected,
            tools=None,
        )

        assert result == {"type": "text", "content": "Fallback antwortet."}
        assert calls == ["openai:gpt-4o"]

    def test_stream_fallback_returns_first_configured_stream(self, monkeypatch):
        from backend import ai_engine

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-2.5-flash"]

        def fake_stream(messages, selected_model=None, tools=None):
            if selected_model["provider"] == "openai":
                return iter(["ok"])
            return None

        monkeypatch.setattr(ai_engine, "_provider_available_for_fallback", lambda provider: provider == "openai")
        monkeypatch.setattr(ai_engine, "_stream_with_selected_provider", fake_stream)

        stream, meta = ai_engine._stream_with_provider_fallbacks(
            [{"role": "user", "content": "ping"}],
            selected,
            tools=None,
        )

        assert meta["id"] == "openai:gpt-4o"
        assert list(stream) == ["ok"]


class TestAnthropicProvider:
    def test_anthropic_message_conversion_splits_system_and_messages(self):
        from backend.ai_engine import _anthropic_convert_messages

        system, messages = _anthropic_convert_messages([
            {"role": "system", "content": "Du bist Lexa."},
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Was kannst du?"},
        ])

        assert system == "Du bist Lexa."
        assert messages == [
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Was kannst du?"},
        ]

    def test_anthropic_tool_conversion_uses_input_schema(self):
        from backend.ai_engine import _anthropic_convert_tools

        tools = _anthropic_convert_tools([
            {
                "type": "function",
                "function": {
                    "name": "timer_set",
                    "description": "Set a timer",
                    "parameters": {
                        "type": "object",
                        "properties": {"minutes": {"type": "number"}},
                        "required": ["minutes"],
                    },
                },
            }
        ])

        assert tools == [
            {
                "name": "timer_set",
                "description": "Set a timer",
                "input_schema": {
                    "type": "object",
                    "properties": {"minutes": {"type": "number"}},
                    "required": ["minutes"],
                },
            }
        ]

    def test_anthropic_response_processing_supports_text_and_tools(self):
        from backend.ai_engine import _process_anthropic_response

        text = _process_anthropic_response({
            "content": [{"type": "text", "text": "Hallo von Claude"}]
        })
        tool = _process_anthropic_response({
            "content": [
                {"type": "text", "text": "Ich stelle den Timer."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "timer_set",
                    "input": {"minutes": 25},
                },
            ]
        })

        assert text == {"type": "text", "content": "Hallo von Claude"}
        assert tool["type"] == "tool_call"
        assert tool["tool_calls"][0] == {
            "id": "toolu_1",
            "name": "timer_set",
            "arguments": {"minutes": 25},
        }

    def test_openai_tool_argument_parse_preserves_malformed_args_for_schema_rejection(self):
        from backend.ai_engine import _parse_tool_calls_from_message

        class Fn:
            name = "system_info"
            arguments = '{"unexpected":'

        class ToolCall:
            id = "call_1"
            function = Fn()

        class Message:
            tool_calls = [ToolCall()]

        parsed = _parse_tool_calls_from_message(Message())

        assert parsed == [{
            "id": "call_1",
            "name": "system_info",
            "arguments": '{"unexpected":',
        }]

    def test_openai_tool_argument_parse_preserves_non_object_args_for_schema_rejection(self):
        from backend.ai_engine import _parse_tool_calls_from_message

        class Fn:
            name = "system_info"
            arguments = '["not", "an", "object"]'

        class ToolCall:
            id = "call_1"
            function = Fn()

        class Message:
            tool_calls = [ToolCall()]

        parsed = _parse_tool_calls_from_message(Message())

        assert parsed[0]["arguments"] == ["not", "an", "object"]

    def test_anthropic_chat_routes_through_unified_provider(self, monkeypatch):
        from backend import ai_engine

        monkeypatch.setattr(
            ai_engine,
            "_anthropic_with_retry",
            lambda messages, model, stream=False, tools=None: {
                "content": [{"type": "text", "text": "Claude ist verbunden."}]
            },
        )

        result = ai_engine._chat_with_selected_provider(
            [{"role": "user", "content": "ping"}],
            {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            tools=None,
        )

        assert result == {"type": "text", "content": "Claude ist verbunden."}

    def test_anthropic_stream_adapter_yields_text_and_tool_chunks(self):
        from backend.ai_engine import _anthropic_stream_to_openai_chunks

        lines = [
            'event: content_block_delta',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}',
            'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu_1","name":"timer_set","input":{}}}',
            'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"minutes\\":25}"}}',
        ]

        chunks = list(_anthropic_stream_to_openai_chunks(lines))
        assert chunks[0].choices[0].delta.content == "Hi"
        tool_delta = chunks[1].choices[0].delta.tool_calls[0]
        assert tool_delta.id == "toolu_1"
        assert tool_delta.function.name == "timer_set"
        assert chunks[2].choices[0].delta.tool_calls[0].function.arguments == '{"minutes":25}'
