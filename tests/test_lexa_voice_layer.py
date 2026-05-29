"""Regression tests for Lexa's central user-facing voice layer."""


def test_system_prompt_uses_central_lexa_voice_rules():
    from backend.ai_engine import SYSTEM_PROMPT_CORE
    from backend.lexa_voice import LEXA_SYSTEM_PROMPT_CORE

    assert SYSTEM_PROMPT_CORE == LEXA_SYSTEM_PROMPT_CORE
    assert "Deutsch, per du, kurz" in SYSTEM_PROMPT_CORE
    assert "Keine Modell-, Provider- oder Fallback-Namen" in SYSTEM_PROMPT_CORE
    assert "QUALITAETSSTANDARD" in SYSTEM_PROMPT_CORE
    assert "Fakten, Annahmen, Entscheidungen" in SYSTEM_PROMPT_CORE
    assert "Zeiten konsistent rechnen" in SYSTEM_PROMPT_CORE
    assert "keine nicht genannten Aufgaben erfinden" in SYSTEM_PROMPT_CORE
    assert "keine Schein-Komplexitaet" in SYSTEM_PROMPT_CORE
    assert "Sequenz-/Tensor-Shapes" in SYSTEM_PROMPT_CORE
    assert "technisch noch laeuft" in SYSTEM_PROMPT_CORE
    assert "Draft/Approval" in SYSTEM_PROMPT_CORE


def test_provider_failure_message_hides_provider_details():
    from backend.lexa_voice import lexa_user_error

    message = lexa_user_error("ai_unavailable")
    forbidden = ("Provider", "Modell", "Gemini", "OpenAI", "Claude", "Groq", "503")
    assert all(word.lower() not in message.lower() for word in forbidden)
    assert "Einstellungen" in message


def test_os_agent_worker_instructions_inherit_voice_boundary():
    from backend.os_agent_runtime import _build_worker_instructions

    prompt = _build_worker_instructions({
        "id": "task_1",
        "title": "Draft pruefen",
        "instructions": "Pruefe einen OS-Draft.",
    })

    assert "User-facing voice" in prompt
    assert "Vermeide Modell-/Provider-/Fallback-Gelaber" in prompt
    assert "OS-Aenderungen bleiben Draft/Approval-gebunden" in prompt
