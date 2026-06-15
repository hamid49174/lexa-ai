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
        assert "desktop_engine_status" in names
        assert "desktop_engine_observe" in names
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

    def test_detect_quality_mode_for_plain_lexa_improvement_goal(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel: Lexa verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system
        assert "High-Impact-Schritte" in system
        assert "User-Aenderungen" in system
        assert "fokussiert mit passenden Tests" in system

    def test_detect_quality_mode_for_lexa_tests_and_guardrails(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa Tests und Guardrails verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_reliability_improvement(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa reliability, stability und Robustheit verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_accessibility_improvement(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa Barrierefreiheit, Bedienbarkeit und a11y verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_performance_improvement(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa speed, latency, Ladezeit und Reaktionszeit verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_memory_context_improvement(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa Memory, Kontext und Personalisierung verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_conversation_intelligence(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa conversation flow, follow-up questions und Intent-Erkennung verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_normalizes_real_umlauts(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel ist Lexa Qualit\u00e4t und Architektur professionell verbessern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system

    def test_detect_quality_mode_for_lexa_chat_intelligence_features(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Verbessere Lexa Chat-Intelligenz, Features und allgemeine Funktionen.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_typo_heavy_lexa_feature_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("will lexa intilegnz futeres autoamtion verbessern")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_lexa_development_wording(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel: Lexa weiterentwickeln.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system
        assert "High-Impact-Schritte" in system

    def test_detect_quality_mode_for_lexa_expand_wording(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Ziel: Lexa ausbauen.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system
        assert "High-Impact-Schritte" in system

    def test_detect_quality_mode_for_source_backed_fact_check(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a source-backed fact-check brief with claims and citations.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_matches_separator_variants(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Lexa answer-quality and user-experience polish.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_build_messages_keeps_simple_assistant_quality_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("what is assistant quality?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_detect_quality_mode_ignores_markers_inside_words(self):
        from backend.ai_engine import _build_messages

        applet_messages = _build_messages("Ziel: applet quality kurz erklaeren.")
        resource_messages = _build_messages("List resources that mention claim verification.")

        assert "[QUALITAETSMODUS]" not in applet_messages[0]["content"]
        assert "[QUALITAETSMODUS]" not in resource_messages[0]["content"]

    def test_detect_quality_mode_for_source_claim_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Bitte pruefe die Quellen und markiere unbelegte Claims.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Fakten/Annahmen/Entscheidungen" in system

    def test_detect_quality_mode_for_direct_answer_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Verify this answer.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_direct_claim_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Check this claim.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_direct_statement_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Verify this statement.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_double_check_statement(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Double-check this statement.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_personal_answer_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Verify my answer.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_german_factcheck_answer_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Faktencheck meine Antwort.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_german_direct_answer_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Prüf die Antwort.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "checkbare Claims" in system
        assert "ungepruefte Aussagen" in system

    def test_detect_quality_mode_for_inflected_source_verification(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Bitte verifiziere die Quellen und Belege.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_validation_and_cross_check(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Validate the sources and cross-check the evidence.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_research_reference_validation(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Bitte validiere die Studien, Papers und Referenzen.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Top-tier Assistant Quality" in system

    def test_detect_quality_mode_for_decision_brief_planning(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Erstelle einen Entscheidungsbrief mit Optionen und Risiken fuer Lexa.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Tradeoffs/Risiken" in system
        assert "Confidence" in system
        assert "Chain-of-Thought" in system

    def test_detect_quality_mode_for_strategy_tradeoff_question(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Soll ich fuer Lexa Performance oder Memory zuerst priorisieren? "
            "Vergleiche Optionen, Risiken und naechste Schritte."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Reversibilitaet" in system
        assert "offene Fragen" in system

    def test_detect_quality_mode_for_natural_should_i_comparison(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Soll ich Lexa Performance oder Memory zuerst verbessern?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Confidence" in system

    def test_detect_quality_mode_for_natural_which_is_better_comparison(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist besser fuer Lexa: Performance oder Memory?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Reversibilitaet" in system

    def test_detect_quality_mode_for_option_choice_followup(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Welche Option ist besser?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system

    def test_detect_quality_mode_for_help_me_decide_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Hilf mir entscheiden.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Confidence" in system

    def test_detect_quality_mode_for_make_the_call_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Make the call.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system

    def test_detect_quality_mode_for_which_option_should_i_pick(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Which option should I pick?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "offene Fragen" in system

    def test_detect_quality_mode_for_rank_options_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Rank these options: Performance, Memory, UX.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Tradeoffs/Risiken" in system

    def test_detect_quality_mode_for_prioritize_choices_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Prioritize these choices: speed, memory, UX.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system

    def test_detect_quality_mode_for_pros_and_cons_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Give me pros and cons of improving Lexa memory.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Tradeoffs/Risiken" in system

    def test_detect_quality_mode_for_tradeoffs_between_options(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Tradeoffs between Lexa Performance and Memory.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system

    def test_detect_quality_mode_for_decision_matrix_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a decision matrix for options: Performance, Memory, UX.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Optionen" in system
        assert "Kriterien-/Score-Tabelle" in system
        assert "Gewichtung" in system

    def test_detect_quality_mode_for_criteria_scoring_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Bewerte die Optionen nach Kriterien: Performance, Memory, UX.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Confidence" in system
        assert "Kriterien-/Score-Tabelle" in system

    def test_detect_quality_mode_for_roadmap_milestones_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Erstelle eine Roadmap fuer Lexa mit Meilensteinen und Timeline.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "naechste Schritte" in system
        assert "Phasen/Meilensteinen" in system
        assert "Review-Punkten" in system

    def test_detect_quality_mode_for_execution_plan_phases_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create an execution plan with phases and owners for Lexa memory.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "offene Fragen" in system
        assert "Ownern" in system
        assert "Abhaengigkeiten" in system

    def test_detect_quality_mode_for_deadline_budget_plan(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Plane Lexa Memory mit Deadline Freitag und 2 Stunden Budget.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Deadline/Budget/Ressourcen-Constraints" in system
        assert "realistische Minimalversion" in system

    def test_detect_quality_mode_for_limited_rollout_plan(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a rollout plan for Lexa voice with limited resources.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Scope-Kuerzungen" in system

    def test_detect_quality_mode_for_release_risk_assessment(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a risk assessment for Lexa release.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Failure Modes" in system
        assert "Rollback-/Abort-Kriterien" in system

    def test_detect_quality_mode_for_rollback_plan(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Rollback plan for Lexa voice launch.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Early-Warning-Signale" in system

    def test_detect_quality_mode_for_threat_model_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a threat model for Lexa memory tools.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Threat-/Privacy-Review" in system
        assert "Trust Boundaries" in system
        assert "Exfiltration-Risiken" in system

    def test_detect_quality_mode_for_privacy_review_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Privacy review for Lexa agent permissions.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Permissions" in system
        assert "Verifikationsschritte" in system

    def test_detect_quality_mode_for_accessibility_review_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Accessibility review for Lexa chat keyboard navigation and screen reader labels.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Accessibility-Review" in system
        assert "Tastaturfluss" in system
        assert "Screenreader-/ARIA-Labels" in system

    def test_detect_quality_mode_for_contrast_audit_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Check contrast and focus order for Lexa settings UI.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Kontrast" in system
        assert "Fokusreihenfolge" in system
        assert "Verifikationstests" in system

    def test_detect_quality_mode_for_performance_review_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Performance review for Lexa chat latency and startup time.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Performance-Review" in system
        assert "Baseline/Metrik" in system
        assert "Performance-Budget" in system

    def test_detect_quality_mode_for_latency_budget_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a latency budget for Lexa streaming.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Bottleneck-Hypothesen" in system
        assert "Regressionstest" in system

    def test_detect_quality_mode_for_test_plan_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a test plan for Lexa release with acceptance criteria.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Teststrategie" in system
        assert "Akzeptanzkriterien" in system
        assert "Testmatrix" in system

    def test_detect_quality_mode_for_regression_test_plan_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Regression test plan for Lexa streaming workflow.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "kritische Regressionen" in system
        assert "Verifikationsbefehle" in system

    def test_detect_quality_mode_for_memory_review_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Memory review for Lexa chat: what should stay stable vs draft?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Memory-/Kontext-Aufgaben" in system
        assert "stabile Fakten" in system
        assert "Draft- statt Stable-Memory-Writes" in system
        assert "Privacy-/Consent-Risiken" in system

    def test_detect_quality_mode_for_context_pack_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Build a context pack for Lexa project decisions and tasks.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Memory-/Kontext-Aufgaben" in system
        assert "Verifikationsfragen" in system

    def test_detect_quality_mode_for_tool_execution_plan_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Create a tool execution plan for Lexa workspace automation with permissions and rollback."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Tool-Execution-Review" in system
        assert "erlaubte Tools/Kontext" in system
        assert "Stop-/Approval-Kriterien" in system
        assert "Rollback/Recovery" in system

    def test_detect_quality_mode_for_agent_run_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Plan an agent run for Lexa repository cleanup and verification.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Agent-/Tool-Aufgaben" in system
        assert "Verifikationssignal" in system

    def test_detect_quality_mode_for_ship_check_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Run a production Ship Check for Lexa before publish with launch blockers."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Ship-Readiness-Review" in system
        assert "Must-fix vor Publish" in system
        assert "Go/No-go-Empfehlung" in system

    def test_detect_quality_mode_for_release_readiness_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Check Lexa release readiness: tests, rollback, docs, security.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Launch-Blocker" in system
        assert "Verifikationsbefehle" in system

    def test_detect_quality_mode_for_destructive_memory_cleanup_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Delete old memories for Lexa after backup and dry run.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Data-Safety-Review" in system
        assert "Backup/Snapshot" in system
        assert "Dry-run-/Read-only-Vorcheck" in system
        assert "Restore/Rollback" in system

    def test_detect_quality_mode_for_backup_restore_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Restore backup for Lexa database after migration.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "datenveraendernden oder destruktiven Aktionen" in system
        assert "Nachpruefung" in system

    def test_detect_quality_mode_for_debug_triage_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Debug Lexa startup error: collect logs, reproduce, find root cause.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Bug-/Incident-/Debugging-Aufgaben" in system
        assert "Repro-Schritte" in system
        assert "Hypothesen nach Wahrscheinlichkeit" in system
        assert "Regressionstest" in system

    def test_detect_quality_mode_for_incident_triage_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Incident triage for Lexa chat outage with logs and rollback.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Impact" in system
        assert "Verifikationssignal" in system

    def test_detect_quality_mode_for_status_handoff_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Wie weit sind wir mit Lexa? Zeig erledigt, verifiziert und offen.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Status-/Handoff-Aufgaben" in system
        assert "erledigt" in system
        assert "verifiziert" in system
        assert "Risiken/Blocker" in system

    def test_detect_quality_mode_for_handoff_summary_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a handoff summary for Lexa project changes, tests, next steps, and risks.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Arbeitsuebergabe" in system
        assert "gesicherte Fakten" in system

    def test_detect_quality_mode_for_clarification_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Before building this Lexa feature, ask clarifying questions and state assumptions.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "unklaren Anforderungen" in system
        assert "Annahmen von Fakten" in system
        assert "maximal drei konkrete Rueckfragen" in system

    def test_detect_quality_mode_for_missing_context_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("List missing context for this Lexa implementation plan before proceeding.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "fehlenden Kontext" in system
        assert "sichere Defaults" in system

    def test_detect_quality_mode_for_feature_spec_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Draft a feature spec for Lexa voice memory with user stories and edge cases.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Feature-/Requirements-Spezifikationen" in system
        assert "Akzeptanzkriterien" in system
        assert "kleinster MVP" in system

    def test_detect_quality_mode_for_prd_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create a PRD for Lexa agent handoff with success metrics and non-goals.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Zielnutzer" in system
        assert "Nicht-Ziele" in system
        assert "Erfolgsmessung" in system

    def test_detect_quality_mode_for_eval_rubric_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Create an answer quality eval rubric for Lexa vs GPT, Claude, and Gemini.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Eval-/Benchmark-Aufgaben" in system
        assert "Testset/Golden Set" in system
        assert "Kriterien mit Gewichtung" in system

    def test_detect_quality_mode_for_assistant_benchmark_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Benchmark Lexa assistant answers with a golden set and hallucination eval.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Baseline/Vergleichsmodelle" in system
        assert "Regression-Gate" in system

    def test_detect_quality_mode_for_meeting_summary_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Summarize meeting notes for Lexa: extract action items, owners, deadlines, and decisions."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Meeting-/Notizen-/Transcript-Zusammenfassungen" in system
        assert "Action Items mit Owner/Deadline" in system
        assert "unklare Sprecher" in system

    def test_detect_quality_mode_for_transcript_action_items_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Turn transcript into action items for Lexa planning with open questions.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "offene Fragen" in system
        assert "Follow-ups" in system

    def test_detect_quality_mode_for_monthly_cost_calculation(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Calculate monthly cost: 120000 tokens per day at 0.15 USD per 1M tokens."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Rechen-/Zahlenanalyse-Aufgaben" in system
        assert "Einheiten/Waehrung" in system
        assert "Formel/Rechenschritte" in system
        assert "Plausibilitaetscheck" in system

    def test_detect_quality_mode_for_percentage_change_calculation(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Berechne prozentuale Aenderung von 80 auf 92 Nutzern.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Zwischenergebnisse" in system
        assert "Rundung" in system
        assert "unsichere Eingaben" in system

    def test_detect_quality_mode_for_customer_email_reply_draft(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Draft a customer email reply about the Lexa refund delay with a warm tone and clear CTA."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Kommunikations-/Antwortentwurfs-Aufgaben" in system
        assert "Empfaenger/Audience" in system
        assert "CTA/naechster Schritt" in system
        assert "Tonvariante" in system

    def test_detect_quality_mode_for_german_announcement_draft(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Schreibe eine Ankuendigung an das Lexa Team mit Betreff, kurzem Ton und naechstem Schritt."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Kernbotschaft" in system
        assert "Betreff/Opening" in system
        assert "Laenge" in system

    def test_detect_quality_mode_for_step_by_step_learning_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Teach me Lexa architecture step by step with examples and a quick check."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Lern-/Erklaer-Aufgaben" in system
        assert "Wissensstand" in system
        assert "mentalen Modell" in system
        assert "Checkfrage" in system

    def test_detect_quality_mode_for_beginner_explanation_request(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages(
            "Explain async API workflows for beginners with examples and common mistakes."
        )
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "konkreten Beispiel" in system
        assert "Fehlannahmen" in system
        assert "naechsten Lernschritt" in system

    def test_detect_quality_mode_for_plain_compare_vs_question(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Vergleiche Lexa Performance vs Memory.")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system
        assert "Tradeoffs/Risiken" in system

    def test_detect_quality_mode_for_what_would_you_do_comparison(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was wuerdest du machen: Performance oder Memory?")
        system = messages[0]["content"]

        assert "[QUALITAETSMODUS]" in system
        assert "Decision Brief" in system

    def test_build_messages_keeps_simple_source_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("was ist eine quelle")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_factcheck_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist ein Faktencheck?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_decision_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist eine Entscheidung?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_roadmap_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist eine Roadmap?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_should_i_question_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Soll ich Wasser trinken?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_vague_better_question_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist besser?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_comparison_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was bedeutet Vergleich?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_plain_source_comparison_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Vergleiche die Quellen.")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_vague_what_would_you_do_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was wuerdest du machen?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_simple_ranking_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is ranking?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_pros_cons_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What does pros and cons mean?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_decision_matrix_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a decision matrix?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_execution_plan_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an execution plan?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_deadline_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("Was ist eine Deadline?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_budget_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a budget?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_risk_assessment_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a risk assessment?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_threat_model_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a threat model?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_privacy_review_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a privacy review?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_accessibility_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is accessibility?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_screen_reader_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a screen reader?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_latency_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is latency?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_profiling_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is profiling?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_test_plan_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a test plan?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_acceptance_criteria_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What are acceptance criteria?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_memory_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is memory?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_context_pack_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a context pack?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_agent_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an agent?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_tool_workflow_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a tool workflow?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_release_readiness_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is release readiness?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_ship_check_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a ship check?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_backup_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a backup?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_data_loss_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is data loss risk?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_debugging_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is debugging?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_root_cause_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is root cause analysis?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_status_update_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a status update?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_handoff_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a handoff?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_clarification_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a clarifying question?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_assumption_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an assumption?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_prd_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a PRD?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_user_story_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a user story?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_rubric_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a rubric?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_eval_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an eval?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_meeting_minutes_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What are meeting minutes?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_action_items_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What are action items?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_percentage_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a percentage?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_roi_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is ROI?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_cta_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a CTA?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_email_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an email?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_tutorial_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is a tutorial?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

    def test_build_messages_keeps_example_definition_light(self):
        from backend.ai_engine import _build_messages

        messages = _build_messages("What is an example?")

        assert "[QUALITAETSMODUS]" not in messages[0]["content"]

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
            result = ai_engine.set_ai_model("gemini:gemini-3.1-pro")
            current = ai_engine.get_ai_models()
            assert "Gemini" in result
            assert current["current"] == "gemini:gemini-3.1-pro"
            assert current["current_provider"] == "gemini"
        finally:
            ai_engine.set_ai_model(original)

    def test_set_ai_model_accepts_legacy_raw_ids(self):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            ai_engine.set_ai_model("gemini-3.1-flash-lite")
            current = ai_engine.get_ai_models()
            assert current["current"] == "gemini:gemini-3.1-flash-lite"
            assert current["current_provider"] == "gemini"
        finally:
            ai_engine.set_ai_model(original)

    def test_set_ai_model_rejects_unknown_provider_ids(self):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            result = ai_engine.set_ai_model("anthropic:claude-sonnet-4-20250514")
            current = ai_engine.get_ai_models()
            assert "Unbekanntes Modell" in result
            # Selection stays on the previously active model.
            assert current["current"] == original
        finally:
            ai_engine.set_ai_model(original)

    def test_get_ai_models_returns_grouped_provider_data(self):
        from backend.ai_engine import get_ai_models

        models = get_ai_models()
        assert "grouped" in models
        assert "gemini" in models["grouped"]
        assert models["grouped"]["gemini"]["models"]


class TestProviderStatus:
    def test_groq_client_uses_env_key_without_keyring(self, monkeypatch):
        from backend import ai_engine

        created_keys = []

        class FakeGroq:
            def __init__(self, api_key):
                self.api_key = api_key
                created_keys.append(api_key)

        monkeypatch.setattr(ai_engine, "_Groq", FakeGroq)
        monkeypatch.setattr(ai_engine, "keyring", None)
        monkeypatch.setattr(ai_engine, "_groq_client", None)
        monkeypatch.setattr(ai_engine, "_groq_client_key_hash", None)
        monkeypatch.setenv("GROQ_API_KEY", "env-groq-key")

        client = ai_engine._get_groq_client()

        assert isinstance(client, FakeGroq)
        assert client.api_key == "env-groq-key"
        assert created_keys == ["env-groq-key"]

    def test_groq_client_prefers_keyring_over_env_key(self, monkeypatch):
        from backend import ai_engine

        class FakeKeyring:
            @staticmethod
            def get_password(service_name, secret_name):
                assert service_name == "lexa-ai"
                assert secret_name == "groq_api_key"
                return "keyring-groq-key"

        class FakeGroq:
            def __init__(self, api_key):
                self.api_key = api_key

        monkeypatch.setattr(ai_engine, "_Groq", FakeGroq)
        monkeypatch.setattr(ai_engine, "keyring", FakeKeyring())
        monkeypatch.setattr(ai_engine, "_groq_client", None)
        monkeypatch.setattr(ai_engine, "_groq_client_key_hash", None)
        monkeypatch.setenv("GROQ_API_KEY", "env-groq-key")

        client = ai_engine._get_groq_client()

        assert isinstance(client, FakeGroq)
        assert client.api_key == "keyring-groq-key"

    def test_get_ai_status_reports_gemini_provider(self, monkeypatch):
        from backend import ai_engine

        original = ai_engine.get_ai_models()["current"]
        try:
            ai_engine.set_ai_model("gemini:gemini-3.5-flash")
            monkeypatch.setattr(ai_engine, "_get_gemini_client", lambda: object())

            status = ai_engine.get_ai_status()
            # Phase 40+: Gemini-only registry — groq/openai/anthropic/ollama
            # are no longer separate status entries.
            assert status["gemini"]["available"] is True
            assert "groq" not in status
            assert "openai" not in status
            assert "anthropic" not in status
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

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-3.1-pro"]
        calls = []

        def fake_chat(messages, selected_model=None, tools=None):
            calls.append(selected_model["id"])
            if selected_model["id"] == "gemini:gemini-3.5-flash":
                return {"type": "text", "content": "Fallback antwortet."}
            return None

        monkeypatch.setattr(ai_engine, "_provider_available_for_fallback", lambda provider: provider == "gemini")
        monkeypatch.setattr(ai_engine, "_chat_with_selected_provider", fake_chat)

        result = ai_engine._chat_with_provider_fallbacks(
            [{"role": "user", "content": "ping"}],
            selected,
            tools=None,
        )

        assert result == {"type": "text", "content": "Fallback antwortet."}
        assert calls == ["gemini:gemini-3.5-flash"]

    def test_stream_fallback_returns_first_configured_stream(self, monkeypatch):
        from backend import ai_engine

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-3.1-pro"]

        def fake_stream(messages, selected_model=None, tools=None):
            if selected_model["id"] == "gemini:gemini-3.5-flash":
                return iter(["ok"])
            return None

        monkeypatch.setattr(ai_engine, "_provider_available_for_fallback", lambda provider: provider == "gemini")
        monkeypatch.setattr(ai_engine, "_stream_with_selected_provider", fake_stream)

        stream, meta = ai_engine._stream_with_provider_fallbacks(
            [{"role": "user", "content": "ping"}],
            selected,
            tools=None,
        )

        assert meta["id"] == "gemini:gemini-3.5-flash"
        assert list(stream) == ["ok"]

    def test_chat_stream_falls_back_after_empty_primary_stream(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config

        class Delta:
            def __init__(self, content):
                self.content = content
                self.tool_calls = None

        class Choice:
            def __init__(self, content):
                self.delta = Delta(content)

        class Chunk:
            def __init__(self, content):
                self.choices = [Choice(content)]

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-3.5-flash"]
        fallback = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-3.1-pro"]
        calls = []

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", False)
        monkeypatch.setattr(ai_engine, "_get_selected_model_meta", lambda: selected)
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_interaction", lambda *args, **kwargs: None)

        def fake_primary_stream(messages, selected_model=None, tools=None):
            calls.append(("primary", selected_model["id"], tools))
            return iter([])

        def fake_provider_fallbacks(messages, selected_model=None, tools=None):
            calls.append(("fallback", selected_model["id"], tools))
            return iter([Chunk("Fallback antwortet.")]), fallback

        monkeypatch.setattr(ai_engine, "_stream_with_selected_provider", fake_primary_stream)
        monkeypatch.setattr(ai_engine, "_stream_with_provider_fallbacks", fake_provider_fallbacks)

        result = list(ai_engine.chat_stream("ping"))

        assert result == ["Fallback antwortet."]
        assert calls == [
            ("primary", "gemini:gemini-3.5-flash", None),
            ("fallback", "gemini:gemini-3.5-flash", None),
        ]

    def test_chat_stream_accepts_tool_delta_without_function_payload(self, monkeypatch):
        from backend import ai_engine
        import backend.config as config

        class Delta:
            content = None

            def __init__(self, tool_calls):
                self.tool_calls = tool_calls

        class Choice:
            def __init__(self, tool_calls):
                self.delta = Delta(tool_calls)

        class Chunk:
            def __init__(self, tool_calls):
                self.choices = [Choice(tool_calls)]

        class IdOnlyToolDelta:
            index = 0
            id = "call-1"

        class FunctionPayload:
            name = "timer_set"
            arguments = '{"minutes": 5}'

        class FunctionToolDelta:
            index = 0
            id = None
            function = FunctionPayload()

        selected = ai_engine.AI_MODEL_REGISTRY["gemini:gemini-3.5-flash"]

        monkeypatch.setattr(config, "TOOL_USE_ENABLED", False)
        monkeypatch.setattr(ai_engine, "_get_selected_model_meta", lambda: selected)
        monkeypatch.setattr(
            ai_engine,
            "_build_messages",
            lambda user_message, conversation_history=None, system_extra=None: [
                {"role": "user", "content": user_message or ""}
            ],
        )
        monkeypatch.setattr(ai_engine, "_save_interaction", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            ai_engine,
            "_stream_with_selected_provider",
            lambda messages, selected_model=None, tools=None: iter([
                Chunk([IdOnlyToolDelta()]),
                Chunk([FunctionToolDelta()]),
            ]),
        )
        monkeypatch.setattr(
            ai_engine,
            "_stream_with_provider_fallbacks",
            lambda messages, selected_model=None, tools=None: (None, None),
        )

        result = list(ai_engine.chat_stream("stelle einen Timer auf 5 Minuten"))

        assert result == [{
            "type": "tool_call",
            "tool_calls": [{
                "id": "call-1",
                "name": "timer_set",
                "arguments": {"minutes": 5},
            }],
        }]


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
