# Lexa AI Next-Level App Plan

Stand: 2026-05-03

Dieses Dokument ersetzt die alten Phase-, Upgrade- und Masterplan-Analysen. Es ist die neue Arbeitsgrundlage fuer die App `lexa-ai`: weniger Feature-Feuerwerk, mehr Produktqualitaet, Sicherheit, Wartbarkeit und Release-Faehigkeit.

## Zielbild

Lexa soll sich nicht wie ein schnell zusammengestecktes Demo-Projekt anfuehlen, sondern wie ein serioeses Windows-Produkt:

- stabiler Start und klare Fehlerdiagnose
- nachvollziehbare Tool-Ausfuehrung mit Sicherheitsgrenzen
- ruhiges, konsistentes UI ohne brittle DOM-Hacks
- belastbare Tests fuer Kernpfade
- reproduzierbarer Build und sauberer Release-Prozess
- klare Architekturgrenzen zwischen UI, API, Agent, Tools, Voice und Datenhaltung

## Aktueller Ist-Zustand

### Staerken

- FastAPI/Electron-Grundarchitektur ist funktionsfaehig.
- App ist lokal-first und Windows-fokussiert.
- Viele Kernfeatures sind vorhanden: Chat, Voice, Tool-Ausfuehrung, Memory, Productivity, Agent Loop, MCP, Vision, Kalender, Wetter, E-Mail, Datei- und Systemtools.
- Backend-Testbasis ist solide: `331 passed, 1 skipped` im letzten Lauf.
- Frontend-Smoke-Test fuer Chat-Rendering existiert und wurde auf `17 passed` erweitert.
- CSP-Regressionstest existiert und blockt neue Inline-Styles, Inline-Handler, `<style>` und `unsafe-inline`.
- Sicherheitsgrundlagen existieren: Whitelist, Rate Limits, Audit Log, Path/URL Validation, Keyring fuer Secrets.
- CSS ist modularisiert, Frontend ist in mehrere JS-Module gesplittet.

### Schwaechen

- Der Working Tree ist sehr gross und uncommitted. Das erschwert Reviews, Rollbacks und saubere Releases.
- Architektur und Produktplanung waren in mehreren alten, widerspruechlichen Analyse-Dateien verteilt.
- Frontend hat weiterhin viele `innerHTML`-Zuweisungen. Das bleibt der wichtigste DOM-Sicherheitsblock nach der CSP-Haertung.
- CSP ist ohne `unsafe-inline`; ein pytest-Regressionscheck schuetzt den Stand.
- Electron-UI hat wenig echte Unit-/Integrationstests.
- Es gibt keinen automatisierten Electron-Smoke-Test fuer Start, Backend-Verbindung und Chat.
- Der aktuelle `shell=True`-Scan fuer Backend, Companion, Voice und Tests ist leer; Plugin- und Command-Ausfuehrung muss trotzdem weiter gehaertet werden.
- Voice ist feature-reich, aber Diagnose-/Fallback-UX muss professioneller werden.
- Release-Prozess ist dokumentiert, aber nicht als reproduzierbare Checkliste mit automatischen Gates umgesetzt.
- Lizenzsystem hat Online-Validierung, aber noch keine robuste Offline-Signaturstrategie.

### Technische Kennzahlen

- Backend/Companion/Voice/Python: 87 Python-Dateien im betrachteten App-Bereich.
- Frontend: 15 JS-Dateien, 7 CSS-Module.
- API: ca. 167 Router-Endpunkte.
- Tests: 411 Testdefinitionen per statischer Suche, aktuell 331 pytest Tests plus 17 Chat-Rendering-Smoke-Checks erfolgreich.
- Frontend-Hotspots: ca. 79 `innerHTML`-Zuweisungen.
- Client-Persistenz: ca. 40 `localStorage`-Zugriffe.
- Prozessaufrufe: ca. 73 `subprocess`/Process-Aufrufe in Backend, Companion und Voice.

## Professioneller Arbeitsstandard

Ab jetzt gilt fuer neue Arbeit:

- Jede groessere Aenderung hat ein klares Problem, Scope und Akzeptanzkriterien.
- Keine neuen globalen HTML-String-Blobs fuer usernahe Inhalte.
- Keine neuen Shell-Ausfuehrungen ohne explizite Security-Tier-Bewertung.
- Keine neuen Features ohne mindestens einen passenden Test oder eine begruendete Testluecke.
- UI-Zustand wird ueber klare State- und Render-Funktionen gesteuert, nicht ueber verstreute Seiteneffekte.
- Fehlerzustaende sind Teil der UX, nicht nur Console Logs.
- Build-/Release-Checks werden als Gates behandelt, nicht als spaeteres Polieren.
- Python-Lint ist bis zum ersten Lint-Baseline-Cleanup nur ein Report-Gate, weil der aktuelle grosse Working Tree viele bestehende Flake8-Treffer enthaelt.

## Priorisierte Arbeitsblaecke

### P0. Baseline & Repo-Hygiene

Problem: Der aktuelle Arbeitsstand ist gross und schwer reviewbar.

Ziele:

- Working Tree in sinnvolle Changesets aufteilen.
- Runtime-Artefakte und grosse lokale Modelle sauber aus Git heraushalten.
- Version, README, Changelog und Docs synchronisieren.
- Einen stabilen Baseline-Commit herstellen.

Konkrete Aufgaben:

- `git status` in Kategorien sortieren: Architektur, Frontend, Backend, Voice, Tests, Docs, Runtime.
- Unerwuenschte lokale Artefakte entfernen oder ignorieren.
- `CHANGELOG.md` mit aktuellem Stand abgleichen.
- README auf tatsaechliche App-Faehigkeiten und Setup-Schritte reduzieren.
- Finaler Baseline-Check: `python -m pytest -q`, `node tests/test_chat_rendering.js`, JS-Syntaxchecks.

Akzeptanz:

- Sauberer Commit-Stack oder mindestens ein klarer Baseline-Commit.
- Keine Runtime-Dateien im Git-Status.
- Neue Entwickler koennen Setup und Start ohne alte Planungsdokumente verstehen.

### P0. Security & Trust Hardening

Problem: Lexa steuert den PC. Sicherheit ist Produktkern, nicht Nebenfeature.

Ziele:

- CSP haerten.
- User Content konsequent vom DOM trennen.
- Tool-Ausfuehrung auditierbar und vorhersehbar machen.
- Prozess- und Plugin-Ausfuehrung sicherer kapseln.

Konkrete Aufgaben:

- CSP ohne `unsafe-inline` erhalten und ueber `tests/test_csp_static.py` regressionssicher machen.
- CSP-Migration und Rest-Risiken ueber `docs/production/csp-hardening-plan.md` steuern.
- `innerHTML`-Hotspots priorisieren: Chat Search, Modals, Dashboard, Memory, Productivity, Commands.
- Gemeinsame DOM-Builder-Helfer fuer Empty States, Buttons, Cards, Status Rows.
- `backend/plugin_manager.py` `shell=True` pruefen und ersetzen oder streng begruenden.
- Security-Test fuer Plugin-Ausfuehrung und Command-Whitelist erweitern.
- Tool Execution History im UI sichtbar machen: Aktion, Parameter, Sicherheitsstufe, Resultat.

Akzeptanz:

- CSP ohne `unsafe-inline`.
- `tests/test_csp_static.py` bleibt gruen.
- Keine neuen userkontrollierten HTML-Strings.
- Security-Checklist ist gruener als vorher und mit Tests belegbar.

### P0. Startup Reliability & Diagnostics

Problem: Ein Desktop-Assistent muss beim Start glasklar sagen, was funktioniert und was nicht.

Ziele:

- Robustere Backend-Startdiagnose.
- Klare UI fuer fehlende Dependencies, belegten Port, fehlende Keys, Voice-Probleme.
- Reparaturpfade statt kryptischer Fehler.

Konkrete Aufgaben:

- Startup Health Panel im Settings/System-Bereich.
- Checks fuer Python/Backend, Port 8000, Playwright, ffmpeg, Keyring, Mikrofon, Speaker, AI Provider.
- Preload/API Bridge: standardisierte Fehlerobjekte statt uneinheitlicher Strings.
- Backend Health Endpoint erweitern: Feature Flags, Provider Status, Versionsinfo, Build Mode.
- Logs im UI oeffnen/exportieren.

Akzeptanz:

- Frischer Start ohne Keys zeigt klare, nicht-panische Diagnose.
- Port-belegt-Szenario ist verstaendlich.
- User sieht, welcher Provider aktiv ist und welcher Fallback greift.

### P1. Frontend Engineering Upgrade

Problem: Die UI ist umfangreich, aber noch zu string-/global-state-lastig.

Ziele:

- Stabilere Render-Funktionen.
- Weniger globale Seiteneffekte.
- Bessere Testbarkeit.
- Konsistente Komponentenmuster.

Konkrete Aufgaben:

- Kleine DOM-Builder-Library in Vanilla JS: `el()`, `button()`, `emptyState()`, `statusPill()`.
- Moduleweise Migration: Commands -> Memory -> Productivity -> Dashboard -> Modals.
- State-Zugriffe ueber `LexaState` konsequenter kapseln.
- Frontend Unit Tests mit Vitest oder Node-DOM-Stub fuer reine Render-Helfer.
- Snapshot-freie, verhaltensorientierte Tests fuer Rendering, Filters, Settings, License UI.

Akzeptanz:

- Neue UI-Elemente entstehen nicht mehr per grossem Template-String.
- Mindestens 30 Frontend-Unit-Tests fuer Kernmodule.
- UI-Fehler koennen isoliert getestet werden.

### P1. Assistant Quality & Tool UX

Problem: Viele Tools sind vorhanden, aber professionelle Assistenz entsteht durch Zuverlaessigkeit, Rueckfragen und transparente Ergebnisse.

Ziele:

- Bessere Tool-Auswahl.
- Bessere Confirmation-Flows.
- Bessere Resultat-Zusammenfassungen.
- Weniger "AI macht irgendwas"-Gefuehl.

Konkrete Aufgaben:

- Tool-Registry mit Kategorien, Risk Level, Parameter-Schema, Beispielausgabe dokumentieren.
- Confirmation UI mit Diff/Preview fuer Datei-, System- und Netzwerkaktionen.
- Dry Run standardisieren.
- Undo-Metadaten fuer reversible Aktionen definieren.
- Agent Loop: bessere Step-Titles, Abbruch, Retry, Teilresultate.
- Tests fuer Tool Selection, Confirmation, Blocked/Unknown Commands erweitern.

Akzeptanz:

- Kritische Aktionen sind vor Ausfuehrung nachvollziehbar.
- Tool-Ergebnisse sind nicht nur Toasts, sondern verwertbare Chat-/Panel-Resultate.
- Unknown Commands werden niemals still ausgefuehrt.

### P1. Voice Reliability & UX

Problem: Voice ist ein Kernmerkmal. Wenn es nicht klappt, muss die App trotzdem souveran wirken.

Ziele:

- Voice Status ist jederzeit klar.
- Fallbacks sind sichtbar.
- Fehler sind handhabbar.
- Latenz und Aufnahmezustand wirken kontrolliert.

Konkrete Aufgaben:

- Voice Diagnostics Panel: Mikrofon, STT Engine, TTS Engine, Keys, Latenz, letzter Fehler.
- Push-to-talk, Wakeword und Conversation Mode klar trennen.
- Offline-/Cloud-Fallbacks im UI anzeigen.
- Testbare Statusmodelle fuer STT/TTS/Wakeword.
- Smoke-Test fuer Voice-Router ohne echte Audio-Hardware erweitern.

Akzeptanz:

- User weiss immer, ob Lexa hoert, denkt oder spricht.
- Fehlende Keys/Audio Devices erzeugen klare UI-Hinweise.
- Voice-Settings sind nicht nur technisch, sondern entscheidungsfreundlich.

### P1. Data, Memory & Privacy

Problem: Memory ist stark, aber Vertrauen braucht Kontrollierbarkeit.

Ziele:

- Datenhaltung transparent machen.
- Export/Import/Backup robuster.
- Privacy-Kontrollen klar sichtbar.

Konkrete Aufgaben:

- Memory Inspector: welche Daten speichert Lexa, warum, wann zuletzt genutzt.
- "Forget" flows fuer Profil, Notizen, Clipboard, Conversations, Embeddings.
- Backup/Restore mit Preflight und Restore Preview.
- Optional: DB-Verschluesselung evaluieren, aber erst nach Backup-Reife.
- Retention Policies fuer Clipboard und Audit Logs.

Akzeptanz:

- User kann sehen und kontrollieren, was Lexa ueber ihn weiss.
- Backup/Restore ist testbar und dokumentiert.
- Keine sensiblen Daten versehentlich in localStorage.

### P2. Testing & CI Gates

Problem: Backend ist gut abgedeckt, Frontend/Packaging noch nicht genug.

Ziele:

- Automatische Gates fuer echte Release-Faehigkeit.
- Mehr Tests fuer UI und Electron.
- Coverage als Signal, nicht als Zahlenspiel.

Konkrete Aufgaben:

- CI: pytest, chat rendering test, JS syntax checks, dependency audit.
- Electron smoke test: App startet, Backend health ok, Chat view erreichbar.
- Router Contract Tests fuer neue Endpunkte.
- Frontend Render Tests fuer kritische Module.
- Coverage Report in CI mit Mindestschwellen fuer sicherheitskritische Module.

Akzeptanz:

- Jeder Release-Kandidat laeuft durch dieselben Checks.
- Fehlende Frontend-Coverage ist sichtbar.
- Installer wird mindestens smoke-getestet.

### P2. Packaging & Commercial Readiness

Problem: Ein installierbares Produkt braucht reproduzierbare Builds und saubere Update-/Lizenzpfade.

Ziele:

- Reproduzierbarer Windows-Build.
- Signierbarer Installer.
- Lizenzstatus robust online und offline.
- Release-Checkliste als operative Routine.

Konkrete Aufgaben:

- PyInstaller Backend Bundle validieren.
- Electron Builder Config pruefen.
- Code-Signing-Prozess praktisch testen.
- Offline License Token mit Signaturdesign entwerfen.
- Update-/Migration-Strategie fuer DB und Config.
- Installer auf frischem Windows-Profil testen.

Akzeptanz:

- Installer startet auf frischem Windows 10/11 ohne Dev-Tools.
- App kann auch ohne Internet in definiertem Umfang laufen.
- Lizenzstatus ist nachvollziehbar, nicht leicht manipulierbar.

## Empfohlene Reihenfolge

1. Baseline & Repo-Hygiene
2. Security & Trust Hardening
3. Startup Reliability & Diagnostics
4. Frontend Engineering Upgrade
5. Assistant Quality & Tool UX
6. Voice Reliability & UX
7. Data, Memory & Privacy
8. Testing & CI Gates
9. Packaging & Commercial Readiness

## Erste konkrete Sprint-Liste

### Sprint 1: Professionelle Basis

- Working Tree sortieren und Baseline-Commit vorbereiten.
- Runtime-Artefakte aus Git-Status entfernen.
- `docs/NEXT_LEVEL_APP_PLAN.md` als neue Source-of-Truth etablieren.
- Security-Hotspot-Liste erzeugen: `innerHTML`, CSP, `shell=True`, localStorage.
- Bestehende Tests als Pflichtgate dokumentieren.

### Sprint 2: Security/CSP

- `index.html` Inline-Style entfernen.
- Chat Search Overlay ohne Template-String neu bauen.
- Commands/Memory Empty States auf DOM Builder migrieren.
- `plugin_manager.py` `shell=True` ersetzen oder deaktivieren.
- Security-Tests fuer Plugin-Ausfuehrung ergaenzen.

### Sprint 3: Startup Diagnostics

- Health Endpoint erweitern.
- Settings/System Diagnosepanel bauen.
- Provider-/Voice-/Tool-Status normalisieren.
- Port-belegt- und Backend-fail-Szenarien testen.

### Sprint 4: Frontend Testbarkeit

- Minimalen DOM-Builder einfuehren.
- Vitest oder Node-DOM-Stub entscheiden.
- Tests fuer Settings, Commands und Chat Search schreiben.
- Electron-Smoke-Test vorbereiten.

## Nicht-Ziele fuer die naechsten Sprints

- Keine grossen neuen Features ohne Qualitaetsarbeit.
- Kein UI-Redesign nur aus Geschmack.
- Kein Provider-Wechsel als Ablenkung von Architekturproblemen.
- Keine weitere Roadmap-Datei neben diesem Dokument.

## Definition of Done fuer Next-Level-Arbeit

Eine Aufgabe ist erst fertig, wenn:

- der Scope klein genug fuer Review ist,
- relevante Tests laufen,
- Security-Auswirkungen bewertet sind,
- User-Fehlerzustaende sichtbar behandelt werden,
- Doku oder Changelog bei Produktverhalten aktualisiert sind,
- der Arbeitsstand commitfaehig bleibt.
