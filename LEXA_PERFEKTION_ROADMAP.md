# Lexa — Perfektions-Fahrplan (Ziel: jede Funktion wirklich 100%, Claude/GPT-Niveau)

Stand 2026-06-26. Grundlage: Komplett-Scan (649 Einzelfunktionen über 30 Scan-Bereiche)
+ die Fixes/Features dieser Woche. Konsolidiert in **10 Bereiche**. Pro Bereich wird
ein eigener Zyklus gefahren: **Tiefen-Audit → Lücken schließen → adversarisch verifizieren
→ getestet committen**. „100%" heißt: tut wirklich was es verspricht, robust, getestet,
ehrlich dokumentiert — kein Fassaden-Feature.

Legende Ist-Zustand: 🟢 weitgehend echt · 🟡 läuft, aber Lücken · 🔴 kaputt/Fake/fehlt.

---

## A. Ehrlichkeit & Bezahlung (Credibility-Fundament)  🔴
**Warum zuerst:** Genau hier liegt das Kernproblem — verkauft wird mehr, als der Code deckt.
Das untergräbt die einzige echte Stärke (lokal & privat). Ohne das ist alles andere wertlos.
**Scope:** Website-Claims, Stripe/Plan-Durchsetzung, Lizenz, Supabase, Legal.
**Ist-Zustand:**
- 🔴 Website behauptet „eigene deutsche Server" — Code ruft Google direkt (Gemini-Key des Nutzers).
- 🔴 „Lexa Core/Advanced/Max" = umetikettiertes Gemini.
- 🔴 Bezahl-Tiers (Free/Pro/Ultra mit Limits) im Backend NICHT durchgesetzt (kein Plan-/Limit-/Auth-Gate in router_chat).
- 🔴 Erfundene Testimonials + Platzhalter-Impressum (§5 TMG).
- 🟡 Supabase Self-Upgrade-Schutz (.sql, muss gegen DB laufen).
**100% =** Jede öffentliche Aussage stimmt mit dem Code überein ODER ist entfernt; Plan-Limits
serverseitig erzwungen + getestet; Lizenz/Impressum/Legal sauber; Self-Upgrade dicht.

## B. PC-Steuerung & Desktop-Automation (der Kern-Differenzierer)  🟡
**Scope:** Companion (Desktop/UIA, Dateien, System/Apps, Medien/Kommunikation) + Hermes-Adapter. ~80 Tools.
**Ist-Zustand:** 🟢 echt gebaut (pywinauto/UIA, OCR, mss). 🟡 Fokus-/Fenster-Robustheit, Datei-Overwrite
(diese Woche teils gefixt), App-Launcher nur Notepad fest, einige Provider-Stubs (sikulix/ufo).
**100% =** jede Aktion zuverlässig + bestätigungs-gegated + verifiziert (Vorher/Nachher-Check),
keine „tippt ins falsche Fenster"-Klasse mehr, alle Tools erreichbar + getestet.

## C. Chat & KI-Kern  🟡
**Scope:** ai_engine, router_chat (Streaming, Tool-Loop, Web-/Obsidian-Grounding), Intent/Tool-Registry,
Frontend Chat (Rendering/Eingabe/Features), Vision (multimodal).
**Ist-Zustand:** 🟢 Streaming/Markdown/Tools/Grounding funktionieren. 🔴 ai_engine.py 4483 Z. mit
~2700 Z. Quality-Mode-String-Heuristik + ~390–800 Z. totem Provider-Code. 🟡 Server-seitige Turn-Persistenz.
**100% =** entrümpelter, wartbarer Kern (toter Code weg, Quality-Mode durch sauberen Prompt ersetzt),
Antwortqualität/Tool-Routing auf GPT/Claude-Niveau, Vision robust.

## D. Voice & Sprache  🟡
**Scope:** STT (Deepgram/OpenAI/Groq/lokal), TTS (Cartesia/ElevenLabs/OpenAI/SAPI), Wakeword, VAD,
Conversation-Loop, Realtime.
**Ist-Zustand:** 🟢 Cascaded STT→Chat→TTS läuft, Key-Verwaltung (diese Woche). 🟡 Realtime nur Gerüst
(diese Woche gebaut, Audio-Transport fehlt). 🟡 WS ohne Auth-Check.
**100% =** robuste Cascaded-Pipeline + echtes Realtime-Speech-to-Speech (braucht Live-Audio-Test),
sauberes Barge-in, klare Provider-Fehlerbehandlung.

## E. Multi-Agenten-Orchestrator  🟢
**Scope:** orchestrator/* (Planner→parallele read-only Sub-Agenten→Verifikation→zitierte Synthese), Agent-Loop.
**Ist-Zustand:** 🟢 echtes Hub-and-Spoke, Quellen-Registry, Triage, MCP-Read-Brücke. 🟡 Browser-Agent opt-in,
History im Lauf ungenutzt.
**100% =** verlässliche Planqualität, harte Budgets/Timeouts, sichtbare Live-UI, reproduzierbare Quellen.

## F. Gedächtnis & Wissen  🟡
**Scope:** Memory (SQLite/Embeddings/Smart-Memory), Personal-OS/Obsidian-Grounding, Memory-View.
**Ist-Zustand:** 🟢 Speicher/Suche/Grounding funktionieren. 🟡 O(n)-Embedding-Suche (kein Vektorindex),
auto_remember-Heuristik brüchig (nur DE), Memory-View bewusst auf Graph reduziert (toter Listen-Code).
**100% =** schnelle/robuste semantische Suche, verlässliche Extraktion, vollständige Verwaltungs-UI.

## G. Produktivität  🟡
**Scope:** Todos/Pomodoro/Habits/Zeiterfassung/Reminders, Kalender, Workflow-Engine, proaktive Vorschläge.
**Ist-Zustand:** 🟢 CRUD + Pomodoro/Habits. 🟢 Workflow-Engine + Event-Bridge (diese Woche gefixt — war tot),
Kalender-REST (diese Woche ergänzt). 🟡 proactive.accept_suggestion ohne Ausführer.
**100% =** Workflows laufen end-to-end (Schedule+Event), Kalender voll, proaktive Aktionen real ausführbar.

## H. Erweiterbarkeit (Plugins & MCP)  🟡
**Scope:** Plugin-System (AST-Sandbox), MCP-Client/Registry/Bridge/Verwaltung.
**Ist-Zustand:** 🟢 MCP-Verwaltung end-to-end (diese Woche gebaut), MCP-Read-Brücke im Orchestrator.
🟡 Plugin-Tools erreichen das Chat-LLM bewusst nicht (Sicherheitsgrenze — Entscheidung nötig).
**100% =** klare, sichere Plugin→LLM-Strategie (oder bewusst dokumentiert), MCP voll nutzbar inkl. Tools.

## I. Security & Härtung (Querschnitt)  🟡
**Scope:** security.py, Whitelist, Sandbox, presence/bridge, Redaction, SSRF.
**Ist-Zustand:** 🟢 fail-closed Tool-Loop, Whitelist+Nonce-Confirmation, AST-Sandbox, gehärtetes Electron.
🔴 „presence gating" verifiziert keine Anwesenheit (irreführend); TOCTOU-SSRF in always_allowed http_request;
stille Exfil-Kette in always_allowed.
**100% =** die 3 Löcher geschlossen, presence ehrlich benannt/echt, Injection-Filter ehrlich als Nicht-Gate dokumentiert.

## J. Qualität: Tests, Evals & Release  🟡
**Scope:** Test-Suite, Eval-Adapter, CI, Packaging/Installer, Docs.
**Ist-Zustand:** 🟡 1811 Python-Tests grün, aber 5–6/8 Eval-Adapter testen die EIGENE Mock-Heuristik
(Schein-Sicherheit; 1 diese Woche an echten Code gehängt). 🔴 kein CI-Proof, kein signierter Installer.
**100% =** Evals gegen echten Backend-Code, ehrliche Baseline, CI-Run-Beweis, signierter Installer, VM-Smoke.

---

## Vorgehen pro Bereich (Zyklus)
1. Tiefen-Audit des Bereichs (jede Funktion: Anspruch vs. Realität, file:line).
2. Lücken schließen (echt funktionsfähig machen, kein Fake).
3. Adversarisch verifizieren (unabhängige Skeptiker).
4. Getestet committen (volle Suite grün) + Roadmap-Haken setzen.

## Fortschritt
- [x] **A. Ehrlichkeit & Bezahlung** (2026-06-26) — Website auf die Wahrheit umgeschrieben (lokal + eigener Gemini-Key), „deutsche Server"-Lüge raus, Fake-Tiers → eine kostenlose „Lexa"-Karte (BYO-Key), Fake-Testimonials entfernt, Modell „powered by Google Gemini" offengelegt, Pricing-Toggle/„Wähle dein Level" → „Kostenlos. Für immer.", Dashboard-Upgrade-Button ausgeblendet + Limits „Unbegrenzt", config.js/i18n.js Fake-Preise entfernt. Im Browser verifiziert (1 Karte, 0 Testimonials, FAQ ehrlich, keine Konsolenfehler). Backend setzt ohnehin keine Pläne durch (passt). **OFFEN nur für dich (kann ich nicht erfinden): Impressum-Rechtsdaten + Hosting-Anbieter in datenschutz.html (§5 TMG).** Website = KEIN Git-Repo → du musst sie deployen.
- [ ] B. PC-Steuerung & Desktop-Automation
- [ ] C. Chat & KI-Kern
- [ ] D. Voice & Sprache
- [ ] E. Multi-Agenten-Orchestrator
- [ ] F. Gedächtnis & Wissen
- [ ] G. Produktivität
- [ ] H. Erweiterbarkeit (Plugins & MCP)
- [ ] I. Security & Härtung
- [ ] J. Qualität: Tests, Evals & Release
