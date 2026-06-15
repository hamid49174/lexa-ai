# Lexa Multi-Agenten-Orchestrator — Design

Status: in Bau (2026-06). Branch `codex/lexa-stabilization-review`.

Ziel: Lexa arbeitet wie Claude ultracode — ein **Orchestrator** zerlegt eine Aufgabe,
startet mehrere spezialisierte **Sub-Agenten parallel**, verifiziert adversarisch und
**synthetisiert** das Ergebnis. Provider-agnostisch (heute Gemini, später Claude/GPT),
verbunden mit Lexas Backend, Obsidian/Personal OS, Gedächtnis, Hermes und MCP-Coding.

## Architektur (Anthropic Orchestrator-Worker, Hub-and-Spoke)

```
User-Task
   │
   ▼
[PLANNER]  ── ai_engine.chat (tools off) → JSON-Plan: subtasks[{role, objective}]
   │           (Effort-Scaling: 1 Agent für Faktenfrage … 3-5 für breite Recherche)
   ▼
[SUB-AGENTEN]  N parallel (asyncio, Semaphore-Cap) — reden NIE miteinander
   ├─ research   (web_search, memory)
   ├─ knowledge  (Obsidian/Personal-OS-Reads, memory)
   ├─ code       (read-only Code/Repo-Reads)        [Phase D]
   ├─ browser    (browser-use, optional dep)        [Phase D]
   └─ planning   (Tag/Todos/Kalender/Mail)          [Phase D]
   │   jeder: eigener Kontext + eigenes Budget, READ-ONLY erzwungen
   ▼
[VERIFIER]  (Modus „gründlich") LLM-as-Judge mit Rubrik je Ergebnis;     [Phase B]
   │         adversarisch (Pro/Contra + Judge) nur für high-risk
   ▼
[SYNTHESE]  ai_engine.chat (tools off) → finale, zitierte Antwort
   ▼
done (Ledger + Ergebnis)
```

Sub-Agenten sind **read-only** (parallelisiert sicher; kein Schreib-Race auf den
globalen `set_pending_confirmation`/`companion`-Singleton/SQLite). Mutationen laufen
NUR seriell über die Synthese-Stufe bzw. den bestehenden Bestätigungs-Pfad des Chats.

## Wiederverwendung (NICHT neu bauen)
- `backend/agent_protocol.py` — Plan/Action/Verification/Review/AgentRunLedger + Policy + Budgets + Redaction + Trace. Datenmodell + Guardrails des Orchestrators.
- `backend/agent_loop._execute_tool` — abgesicherte Tool-Ausführung (Schema→reflect→whitelist→validate_params→rate-limit→audit). Sub-Agenten rufen NUR hierüber Tools auf.
- `backend/ai_engine.chat` — EINZIGER LLM-Eintrag, provider-agnostisch. `system_extra` = Rollen-Persona; neuer Param `tools_override` = exakte (read-only) Tool-Liste bzw. `[]` = keine Tools (Planner/Synthese/Judge).
- `backend/tool_registry` — Tool-Definitionen + `is_read_only_action`.
- `backend/os_agent_runtime`-Muster — JSON-File-Run-Persistenz (Phase C; KEINE parallelen SQLite-Writes).
- Frontend `agentRun`/`agentStreamRead`/`agentStreamCancel` (preload) + `chat_agent_runs.js` — SSE-Transport + Step-Rendering (Phase E/F).

## Kern-Constraints
- **Kosten:** Multi-Agent ≈ 15× Tokens eines Chats. Harte Caps: `ORCHESTRATOR_MAX_SUBAGENTS`, `ORCHESTRATOR_MAX_CONCURRENCY`, pro-Sub-Agent `budget_steps`. NICHT Default für jede Chat-Nachricht — nur explizit (/orchestrate) oder bei breiten Recherche-/Vergleichs-Aufgaben.
- **Model-Tiering:** Worker = schnelles Modell (Gemini Flash), Orchestrator/Judge = stärkeres (Gemini Pro) — über `_get_selected_model_meta` heute einheitlich, Hook für später.
- **Provider-agnostisch:** ausschließlich über `ai_engine.chat`. Kein direktes Gemini-SDK, kein LangGraph/Temporal (PyInstaller-Packaging).
- **Sicherheit:** alle Tool-Calls über `_execute_tool`; Sub-Agenten read-only erzwungen (doppelt: nur read-only Tools sichtbar + Ausführungs-Gate). Untrusted Tool-Output bleibt Daten, keine Anweisung.

## SSE-Event-Schema (Orchestrator → UI)
`orchestrator_start` · `plan` · `subagent_start` · `subagent_step` · `subagent_done` ·
`verification` · `synthesis` · `done` · `error`. Wiederverwendet den bestehenden
`/agent`-Stream-Transport; Frontend gruppiert Steps nach `agent_id`.

## Phasen
- **A (Kern):** Planner → parallele read-only Sub-Agenten (research/knowledge) → Synthese. Feature-Flag `ORCHESTRATOR_ENABLED`. Budget + Circuit-Breaker. Tests. ← *aktuell*
- **B:** Verifier-Schicht (LLM-as-Judge + adversarisch high-risk).
- **C:** `router_orchestrator.py` (/orchestrator/run SSE, /runs, /runs/{id}) + JSON-Run-Persistenz.
- **D:** Agententypen code (MCP-Brücke), browser (browser-use optional), planning (todos/kalender/mail).
- **E:** Chat-Integration (/orchestrate + neue Event-Typen im Rendering).
- **F:** Eigene Agenten-Ansicht (Live-Baum, CORE_VIEWS-Eintrag).
- **G:** Anbindung Obsidian/OS/Hermes/MCP + Modus „gründlich/schnell".
- **H:** Adversarisches Self-Review + Voll-Suite.
