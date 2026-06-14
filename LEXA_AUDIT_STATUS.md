# Lexa Audit & Fix — Statusbericht (Stand 2026-06-12)

> Diese Datei sichert den kompletten Stand des Pre-Launch-Audits. Sie kann gelöscht werden, wenn der Audit abgeschlossen und alles berichtet ist.

## Workflow-Läufe (Run-IDs)

| Lauf | Run-ID | Zweck | Status |
|---|---|---|---|
| Audit Runde 1 | `wf_b96292e1-d2a` | Scan, 5 von 28 Bereichen fertig | erledigt (Findings unten) |
| Fix-Lauf | `wf_b7431a91-87c` | Behebung der 76 Findings | erledigt (Ergebnis unten) |
| Audit Fortsetzung | `wf_9a230a1b-bab` | restliche 23 Bereiche, Sub-Agents auf **Opus 4.8** | LÄUFT / fortsetzbar |

**Fortsetzen (nächste Session):**
```
Workflow({ scriptPath: "C:\\Users\\admin\\.claude\\projects\\C--Users-admin-OneDrive---Office-lexa\\8a2b321b-07ee-4e52-b8fb-f0c288515f14\\workflows\\scripts\\lexa-audit-rest.js", resumeFromRunId: "wf_9a230a1b-bab" })
```
Findings der Läufe liegen in `…\subagents\workflows\<run-id>\journal.jsonl`.

## Git-Stand
- Branch `codex/lexa-stabilization-review`. **20 Dateien geändert, NICHT committet.** Review per `git diff`.
- Tests: 1650 gesamt, grün bis auf 2 vorbestehende (`test_manual_prompt_probe` — hängen an bereits offener Doc-Änderung `docs/product/manual_lexa_prompt_suite.md`, NICHT von uns).
- `compileall` über backend/companion/voice = exit 0.

## Fix-Lauf: Ergebnis (~50 von 76 behoben)

**CRITICAL behoben:** PowerShell-Command-Injection/RCE in `companion/engine.py` (`file_search`/`_search_index`) — query/path/extension werden jetzt via SQL- + `_sanitize_ps_arg`-Escaping abgesichert.

**Weitere wichtige Fixes:** Vision/OCR (`screen_analyze` asyncio-Bug), MCP stderr-Deadlock + Orphan-Leak + env-Secret-Leak (`mcp_client.py`/`mcp_registry.py`), OS-Agent-Tasks hängen nicht mehr auf „running" (`os_agent_runtime.py`), Event-Loop-Stall bei Obsidian-Kontext (`personal_os_actions.py:517`), doppelte User-Nachricht im Agent-Prompt (`agent_loop.py:1143`), Secret-Redaction in SSE-Fehlern, Emoji/Surrogat-Eingabe (`desktop_control.py`), Trace-Sampling, async-sichere Plugin-Endpoints u.v.m.

**6 Auto-Fixes wieder REVERTIERT** (brachen getestetes Soll-Verhalten — bewusst zurückgenommen, NICHT erneut anwenden):
1. `router_agent.py:133` Pending-Block — Blockieren ist beabsichtigte Sicherheit (Finding war False Positive).
2. `ai_engine.py:86` Keyring-TTL-Cache — brach Test-Isolation + 30s-Staleness.
3. `plugin_manager.py:305` Trust-Modell — Architektur-/Security-Entscheidung nötig.
4. `plugin_manager.py:657` exec-Gate untrusted — AST-Sandbox IST der vorgesehene Schutz.
5+6. `plugin_loader.py:47/:154` AST statt Substring — brach Security-Test `globals(`. Datei via git checkout HEAD voll zurückgesetzt.

## OFFEN — braucht deine Entscheidung (needs_human)
- **Plugin-Trust-Modell**: Plugin kann sich per `trusted:true` selbst Rechte geben. Saubere Lösung braucht Trust-Allowlist + UI-Entscheidung.
- **MCP/Plugin-Tools ans LLM** (`mcp_registry.py:340`): aktuell totes Feature; Aktivieren = Security-Abwägung.
- `ai_engine.py`: Gesamt-Deadline für `chat()` (3780), Modell-Wahl über Neustart persistent (4403), Stream-Fehler sauber an Client (3918/3943 — braucht `router_chat.py`).
- `agent_loop.py:1453`: Step-Timeout stoppt laufende Tools (to_thread) nicht.
- `shared.py`/`agent_loop.py:399`: Pending-Confirmation-Race (kein Lock, ein Slot).
- `plugin_manager.py:248`: SSRF/DNS-Rebinding-Härtung.
- **partial:** `ai_engine.py:431` max_tokens (Anthropic/Groq auf 4096 erhöht; finish_reason-Auswertung offen).

## Nächste Schritte
1. Audit-Fortsetzung `wf_9a230a1b-bab` abwarten/resumen (Frontend, Electron/preload, Security-Layer, Website/Supabase-RLS, Memory, Chat, Voice).
2. Findings Runde 1 (76, oben) + neue Findings zu Gesamtbericht zusammenführen.
3. needs_human-Punkte mit dir durchgehen.
4. Kostenregel: Sub-Agents in Workflows auf `model:'opus'` (Opus 4.8) lassen — halbe Tokenkosten ggü. Fable 5.

## Manuelle Vorab-Prüfung: Website / Supabase (lexa-website/supabase-schema.sql)

RLS-Datenisolation ist solide: profiles/subscriptions SELECT nur eigene Zeilen (`auth.uid()=id` / `=user_id`); INSERT/UPDATE/DELETE auf subscriptions komplett auf service_role gesperrt; Profil-DELETE gesperrt. Kein „User A liest User B".

**ABER — 🔴 CRITICAL (Business-Logic / Privilege Escalation): Plan-Selbst-Upgrade möglich** — `supabase-schema.sql:174-204` (`protect_sensitive_profile_fields`)
- Der Schutz-Trigger ist `SECURITY DEFINER`. Darin liefert `current_user` den **Funktions-Eigentümer** (in Supabase i.d.R. `postgres`), NICHT den aufrufenden User. Damit ist `current_user != 'postgres'` praktisch immer FALSE → die `if`-Bedingung immer FALSE → **die Schutzprüfung greift NIE**.
- Kombiniert mit der UPDATE-Policy „Benutzer kann eigenes Profil aktualisieren" (Z. 323-327) kann ein authentifizierter User per direktem Supabase-Client `plan='ultra'`, `license_key` und `key_version` **selbst setzen** → kostenloses Upgrade auf Bezahltarif / Lizenz-Fälschung.
- **Fix:** Rolle nicht über `current_user` prüfen, sondern über das JWT: z.B. `if coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role','') <> 'service_role' then raise exception ...`. Zusätzlich `request.jwt.claim.role` (Singular, Z. 190) ist in neueren Supabase-Versionen deprecated/NULL — nicht darauf verlassen. Vor Launch unbedingt mit einem echten authenticated-Token testen (Update auf `plan` muss scheitern, Stripe-Webhook als service_role muss durchgehen).

**🟡 MEDIUM — vorhersehbare Lizenzschlüssel** — `generate_license_key` (Z. 24-55)
- Schlüssel = `sha256(user_id || '-' || version)`, gekürzt. Wer die User-UUID kennt, kann den Schlüssel berechnen. Unkritisch, WENN die Desktop-App die Lizenz serverseitig gegen das Konto prüft; **kritisch, falls die App den Schlüssel offline/alleinstehend als Aktivierungsnachweis akzeptiert** (dann fälschbar). Prüfen, wie `backend`/Desktop-App die Lizenz validiert.

> Hinweis: `supabase-schema.sql` wird vom laufenden Opus-Audit (Bereich `website`) ohnehin nochmal geprüft — diese manuelle Prüfung ist die abgesicherte Vorab-Version.

## Umstellung auf Gemini-only (2026-06-14)

Auf Wunsch: **nur noch Gemini, Hauptmodell Gemini 3.5 Flash.** Groq/OpenAI/Anthropic aus dem Produkt entfernt.
- **Recherche-Korrektur:** Gemini 3.5 Flash existiert (GA). Gemini **2.0 wurde am 01.06.2026 abgeschaltet**, 2.5 läuft aus → daher direkt auf 3.x-Modelle gestellt (nicht 2.5).
- **`backend/ai_engine.py`:** `AI_MODEL_REGISTRY` enthält nur noch Gemini 3.5 Flash / 3.1 Flash-Lite / 3.1 Pro; `_PROVIDER_LABELS`, `_PROVIDER_DEFAULT_MODEL_IDS`, `_PROVIDER_FALLBACK_ORDER` = nur `gemini`; `_active_model_id` = `gemini:gemini-3.5-flash`; `_get_model_meta`-Fallback auf gemini; `get_ai_status()` liefert nur noch den `gemini`-Key. Client-Funktionen `_get_groq_client`/`_get_openai_client`/`_get_anthropic_api_key` bleiben als toter Code (ungenutzt, kein Risiko).
- **`frontend/src/index.html`:** Groq/OpenAI/Anthropic API-Key-Zeilen entfernt, nur Gemini-Zeile bleibt (Beschreibung auf 3.x aktualisiert).
- **`frontend/src/settings.js`:** Readiness-Provider-Liste `["gemini"]`, Zähler „/4"→„/{providers.length}", AI-ready-State vereinfacht (ready bei 1 verfügbar).
- **Verifiziert:** `py_compile` ok; Import-Test → `get_ai_models().current = gemini:gemini-3.5-flash`, `get_ai_status()` ohne Crash; `node --check settings.js` ok.
- **Gemini-API-Key:** am 2026-06-14 im Windows Credential Manager gespeichert (service `lexa-ai`, name `gemini_api_key`) + **Live-Call mit `gemini-3.5-flash` erfolgreich** (Antwort „OK"). Key-Wert NICHT in Dateien. → **Backend neu starten**, damit neuer Gemini-only-Code + Key aktiv werden. (Key steht im Chat-Verlauf — bei Bedarf in AI Studio rotieren.)
- **Falls `gemini-3.5-flash` doch nicht akzeptiert wird:** in `ai_engine.py` `AI_MODEL_REGISTRY` den exakten Model-String anpassen (z.B. `gemini-3.1-pro`).
- Voice-STT/TTS (Groq Whisper / OpenAI Transcribe / Deepgram) wurde BEWUSST nicht angefasst (separates Subsystem).
- Nicht committet.
- **2026-06-14 angewendet:** Alter Backend-Prozess (PID 16972, lief seit 06-13 23:51 mit altem Code) zeigte im UI noch das volle Provider-Dropdown, weil Electron das Backend auf Port 8000 wiederverwendet statt neu zu starten (main.js getBackendPath/Reuse-Logik). Stale-Prozess gekillt → Electron hat frisches Backend (neuer Gemini-only-Code) auto-gestartet (läuft auf 8000 = Code lädt runtime-fehlerfrei). User muss App noch voll neu starten/Fenster reloaden, damit Frontend (index.html/settings.js) frisch lädt. KEIN gepacktes Backend vorhanden (backend-dist leer) → kein Rebuild nötig.
- **Bekannt (Audit-Finding 4403):** Modell-Auswahl wird nicht persistiert → frischer Start nutzt Default = gemini-3.5-flash. Falls User dauerhaft ein anderes Default will, in `_active_model_id` / `_PROVIDER_DEFAULT_MODEL_IDS` ändern.
