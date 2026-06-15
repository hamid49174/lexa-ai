"""Lexa Multi-Agenten-Orchestrator (Phase 48).

Claude-ultracode-artiges Orchestrator-Worker-System: ein Planner zerlegt eine Aufgabe,
startet spezialisierte Sub-Agenten parallel (read-only, eigener Kontext + Budget),
verifiziert adversarisch und synthetisiert das Ergebnis. Provider-agnostisch ueber
backend.ai_engine.chat (heute Gemini). Siehe docs/agents/ORCHESTRATOR_DESIGN.md.
"""
from backend.orchestrator.core import (
    OrchestratorError,
    plan_task,
    run_orchestration,
    synthesize_results,
)
from backend.orchestrator.roles import (
    ORCHESTRATOR_ROLES,
    normalize_role,
    role_persona,
    role_tool_defs,
)
from backend.orchestrator.verify import (
    adversarial_judge,
    judge_result,
    verify_results,
)

__all__ = [
    "OrchestratorError",
    "plan_task",
    "run_orchestration",
    "synthesize_results",
    "ORCHESTRATOR_ROLES",
    "normalize_role",
    "role_persona",
    "role_tool_defs",
    "judge_result",
    "adversarial_judge",
    "verify_results",
]
