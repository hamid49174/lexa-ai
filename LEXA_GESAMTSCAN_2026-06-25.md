# Lexa — Gesamt-Scan & Reifegrad-Bericht (2026-06-25)

Vollständiger Multi-Agenten-Scan über das **gesamte** Codebase: 30 Bereiche, 51 Agenten,
~4,45 Mio. Token. Jeder Bereich wurde komplett gelesen (Reifegrad + Funde), kritische/hohe
Funde wurden adversarisch gegengeprüft.

## Bottom Line

**Lexa ist ein reifes, weitgehend fertiges Produkt — Durchschnitt 83 % Reifegrad, kein Bereich unter „mostly-complete".**
Die Substanz steht: Chat, Memory, Agent-Orchestrator, Companion, Voice, Personal-OS, Bezahlung sind
funktional und getestet. Was fehlt, sind Feinschliff, ein paar echte Bugs und vor allem
**rechtliche/Release-Hausaufgaben** (Website).

### Harte Fakten (selbst ausgeführt, kein Agenten-Urteil)
- **Python-Tests: 1765 / 1765 grün** (100 %, 101 s)
- **JS-Unit-Tests (node): 33 / 33 grün**
- Electron-Smoke-Tests (22 Dateien): brauchen echte Electron-Runtime — hier nicht ausführbar
  (laut Verlauf 5 davon vorbestehend rot, keine Regression)

### Fund-Bilanz
| Schwere | Anzahl gemeldet | Status nach Verifikation |
|---|---|---|
| 🔴 critical | 1 | **bestätigt** (→ als high eingestuft) |
| 🟠 high | 20 | 14 bestätigt, 5 widerlegt, 1 unsicher |
| 🟡 medium | 38 | nicht einzeln verifiziert |
| ⚪ low | 132 | nicht verifiziert |
| 💡 improvement | 25 | — |

---

## 🔴 Der eine kritische Fund (selbst am Code bestätigt)

**Workflow-`tool`-Steps sind zur Laufzeit komplett tot.**
`backend/main.py:458` ruft `await wf_engine.start_scheduler()` **ohne** `companion_execute_fn` auf.
Dadurch bleibt `WorkflowEngine._companion_execute = None`, und jeder `tool`-Step wirft
`RuntimeError("CompanionEngine nicht verfügbar")` (`workflows.py:771-775`).
4 von 5 mitgelieferten Templates (Morgen-Routine, Pomodoro-Auto, Backup …) nutzen `tool`-Steps.

Pikant: Zwei Zeilen vorher (`main.py:428`) wird `companion.execute` korrekt an den *anderen*
Scheduler übergeben — der companion ist also da, er wird der Workflow-Engine nur nicht durchgereicht.
**Fix:** `await wf_engine.start_scheduler(companion.execute if hasattr(companion, "execute") else None)`

---

## 🟠 Bestätigte hohe Funde (echte Defekte)

1. **Workflow Event-Trigger feuern nie** — `emit_event()` (`workflows.py:1196`) ist voll implementiert,
   wird aber intern **nirgends** aufgerufen (kein `system_start`/`high_cpu`-Producer). Event-basierte
   Templates lösen nie automatisch aus. Einziger Caller ist der externe HTTP-Endpoint.
2. **Light-Theme nur halb umgesetzt** — `toggleTheme()` setzt `data-theme=light`, aber nur `theme.css`
   definiert Light-Tokens. ~23 von 25 CSS-Dateien (Overrides + Views) hardcoden dunkle `rgba()`-Werte
   ohne `[data-theme=light]`-Pendant → Light-Modus ist optisch kaputt.
3. **Datenschutzerklärung nennt falsche KI-Provider** — `datenschutz.html:87-88` + `agb.html:125`
   listen Groq/ElevenLabs als Auftragsverarbeiter; real ist der Chat **Gemini-only**.
   DSGVO-Compliance-/Abmahnrisiko.
4. **Impressum unvollständig** — `impressum.html:49-74` enthält nur Platzhalter ([Name], [Straße], [USt-IdNr]).
   Bei kommerzieller DE-Seite mit Bezahlfunktion gesetzlich Pflicht (§5 TMG/DDG), abmahnfähig.

## 🟡 Bestätigte Funde, auf medium herabgestuft
- **Globale Pending-Confirmation & conversation_history** (`shared.py`) — ein einziger Modul-Global ohne
  Konversations-/Session-Bezug. Bei parallelen Chats theoretisch Fehlkontext („ja" in Chat B führt
  Aktion aus Chat A aus). Auf strikt sequentieller Single-User-Nutzung unkritisch, aber latent.
- **`file_move`/`file_copy` überschreiben Zieldateien kommentarlos** (`file_tools.py:996/1037`,
  `shutil.move`/`copy2` ohne Existenz-Check) → möglicher Datenverlust. `file_write`/`batch_rename`
  schützen korrekt — Inkonsistenz.
- **Voice-Chat sendet `conversation_id` aus nicht existentem State-Key** (`chat_voice.js:512`
  liest `activeConversationId`, gesetzt wird aber `currentConversationId`) → immer `undefined`.
- **OpenAI/Groq STT/TTS-Keys nur per `keyring`-CLI setzbar** — kein API/UI-Endpoint
  (`router_voice` bietet nur deepgram/cartesia/elevenlabs). Default `STT_ENGINE=openai`.
- **Eval-Suite prüft überwiegend die eigene Mock-Logik** — 5 von 8 Adaptern importieren keinen
  Backend-Code, sondern reimplementieren Keyword-Heuristiken. Eval-Gates geben falsche Sicherheit.
- **Stripe-Webhook-Signaturprüfung ohne Test** — `stripe_webhook` (Plan-/Lizenz-Mutationen) ist
  ungetestet (kein Test für fehlende/ungültige Signatur, fehlendes Secret).
- **Doku bewirbt Multi-Provider-Chat** (README/CHANGELOG/start.bat/AI_HANDOFF) — Code ist Gemini-only.
- **Widersprüchliche Eigentümer-Angaben** — `alexsprogis` (electron-builder appId, README-Clone-URL,
  docs/release) vs. echter Remote `hamid49174`.

## 🟠 Unsicher
- **Tippen ins falsche Fenster bei Fokus-Fehler** (`hermes_desktop.py:2281`) — `_focus_window_for_action`-
  Ergebnis wird beim `type`-Pfad nicht geprüft (anders als `scroll`). Auswirkung vom Verifizierer als
  überzeichnet eingestuft, aber Mechanik real.

## ✅ Als FALSE-POSITIVE widerlegt (kein Handlungsbedarf)
- Gemini-Modellnamen `3.5/3.1` — laut Live-API-Prüfung des Verifizierers akzeptiert (trotzdem beim
  Key-Setzen real gegenchecken).
- `validate_url` SSRF via Hostname — jeder Egress-Pfad löst DNS auf und prüft die aufgelöste IP.
- `screen_record` Datei-Überschreiben — `output_path` wird global über `PATH_PARAM_KEYS` validiert.
- Personal-OS Apply ohne Approval — die SDK erzwingt es.
- Presence-Challenge „No-Op" — Auswirkung falsch eingeschätzt.

---

## Reifegrad je Bereich

| % | Level | Bereich |
|---|---|---|
| 95 | complete | Hermes-Agent (extern, vendored) |
| 90 | mostly-complete | Backend: Infra/Main |
| 88 | mostly-complete | Backend: Memory · Orchestrator · Frontend Chat-Rendering · App-Shell |
| 86 | mostly-complete | Frontend: Personal-OS-View |
| 85 | mostly-complete | Backend: Intent/Tools · Security · Frontend Chat-Kern · Chat-Features |
| 82 | mostly-complete | Backend: Chat-Router · Hermes · Agent-Loop · Personal-OS · Companion (alle) · Frontend Views/CSS · Website |
| 80 | mostly-complete | Backend: Plugins/MCP · Voice/Vision · Docs/Release |
| 78 | mostly-complete | Backend: AI-Engine · Workflows/Produktivität · Bezahlung · Voice-Pipeline · Tests/Evals |

---

## Ehrliche Lücken / Unfertiges (für „wie weit ist Lexa")

**Bewusst unfertig / Stub (kein Bug):**
- Realtime-Speech-to-Speech: `voice/realtime.py` `REALTIME_RUNTIME_IMPLEMENTED=False`, `/voice/realtime/start` gibt 501. Orb-Konversation läuft über klassischen STT→Chat→TTS-Pfad.
- Plugin-Tools erreichen das Chat-LLM bewusst nicht (Sicherheitsgrenze) — nur über `/plugins`-Router nutzbar.
- Multi-Provider-Code (Groq/OpenAI/Anthropic in `ai_engine.py`, ~800 Z.): Legacy/Reserve, unerreichbar.
- Memory-View ist bewusst auf den Graph reduziert; alte Listen-Render-Pfade (`memory.js` ab Z.816) sind toter Code hinter `return;`.

**Echte Feature-Lücken:**
- Kalender: nur Lese-/Connect-Endpoints exponiert; `create/delete/search/next` aus `calendar_integration` haben keinen Router.
- MCP-Server nur per `mcp_servers.json`-Datei anlegbar (kein Add/Edit/Remove-API); Pfade hartkodiert auf `C:/Users/admin/...` (nicht portabel).
- `weather_will_it_rain` implementiert, aber nicht in der Command-Whitelist → unerreichbar.
- `customer.subscription.updated` SQLite-Pfad ruft nicht existentes `_sqlite_update_subscription`.
- Toter Code: `system.js createSystemView()`, diverse HTML-String-Helper neben aktiven DOM-Varianten, `components.css` (leer, wird aber geladen).

---

## Empfohlene nächste Schritte (nach Hebel)

1. **Kritisch zuerst:** `start_scheduler(companion.execute)` durchreichen → Workflow-Engine wieder live (1-Zeilen-Fix).
2. **Release-Blocker (rechtlich):** Impressum ausfüllen + Datenschutz/AGB auf Gemini-only korrigieren.
3. **Sichtbare Bugs:** Light-Theme in Override-/View-CSS nachziehen; `chat_voice.js` `currentConversationId`; `file_move/copy` Overwrite-Guard.
4. **Hygiene:** Doku auf Gemini-only; `alexsprogis`→`hamid49174` überall; Eval-Adapter an echten Backend-Code hängen; Stripe-Webhook-Test.
5. **Feature-Lücken:** Workflow-Event-Producer, Kalender-Schreib-Endpoints, OpenAI/Groq-Voice-Key-Endpoint.

---

## FIX-PHASE (2026-06-25) — „fix alles hochwertig"

7 Batches, lokal committet auf `main` (kein Push), jede Charge mit grüner Suite.
**Endstand: Python 1788/1788 grün · JS 34/34 grün.** Adversarisches Self-Review +
Inline-Review: keine Regressionen.

| # | Commit | Inhalt |
|---|---|---|
| 1 | `c91ea3d6` | 🔴 **Workflow-Engine live** — `companion.execute` an Scheduler durchgereicht; Event-Bridge (ContextMonitor→Workflow) + `system_start` |
| 2 | `4b1cf579` | Companion: `file_move/copy` Overwrite-Schutz; `weather_will_it_rain` erreichbar; Hermes type-Fokus-Guard |
| 3 | `390c8d46` | Voice-Chat `currentConversationId`-Fix; OpenAI/Groq-Key-Verwaltung (Endpunkte+Bridges+UI+i18n) |
| 4 | `b57b159b` | Light-Theme-Retrofit (additive `overrides_light_theme.css`, 0 Dark-Risiko) |
| 5 | `5ee46eed` | Doku: Chat=Gemini-only; Eigentümer `alexsprogis→hamid49174` |
| 6 | `61ed7261` | Stripe-Webhook-Tests (6); Eval-Security-Adapter nutzt echten `sanitize_input` |
| 7 | `f5fbbef5` | Pending-Confirmation an Konversation gebunden (kein Cross-Conversation-Leak) |

**Website (kein Git-Repo, Datei-Edits — du musst deployen):** `datenschutz.html` + `agb.html`
Provider Groq/ElevenLabs → Google Gemini korrigiert.

### Bewusst NICHT gemacht / offen (mit Begründung)
- **Impressum-Rechtsdaten** (`lexa-website/impressum.html`) + **Hosting-Anbieter** (`datenschutz.html`):
  reine Platzhalter — nur du kannst die echten Daten (Name/Anschrift/USt-IdNr/Hoster) eintragen.
  **Release-Blocker (§5 TMG).**
- **Dead-Code-Removal** (`createSystemView`, `composerCommandIconSvg` u.a.): verify-first ergab,
  dass diese durch Tests gepinnt sind → keine sichere Entfernung; Datei-Löschung braucht dein OK.
- **Kalender-Schreib-Endpoints** (create/delete/search/next): Feature-Gap, kein Defekt.
- **Voller Eval-Adapter-Rewrite**: die Suite ist szenario-basiert (eigenes Projekt); der
  Security-Adapter exerziert jetzt aber echten Backend-Code.
- **Gemini-API-Key** muss gesetzt sein, sonst ist der Chat blockiert (Gemini-only).

---
*Roh-Output des Scans: `tasks/wx7bw2ius.output` (temp). Scan-Workflow `wf_fe4f7fcf-4bb`, Self-Review `wf_43179cb0-4f6`.*
