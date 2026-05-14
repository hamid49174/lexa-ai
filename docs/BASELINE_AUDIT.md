# Lexa AI Baseline Audit

Stand: 2026-05-03

Dieses Dokument ist der Startpunkt fuer `LEXA-001: Baseline & Repo-Hygiene`. Ziel ist, den grossen aktuellen Arbeitsstand in reviewbare, commitfaehige Einheiten zu bringen.

## Ergebnis der ersten Bestandsaufnahme

Der letzte Git-Commit ist `db252d7` vom 2026-02-27 (`Lexa AI v0.13.0`). Seitdem ist die App stark gewachsen. Der aktuelle Working Tree enthaelt nicht nur kleine Fixes, sondern praktisch mehrere Releases an Architektur, Features, Tests und Doku.

Der Root-Commit-Stand trackt nur einen kleinen historischen Kern. Viele aktuelle App-Dateien sind noch untracked. Deshalb ist der naechste Schritt kein Feature, sondern saubere Baseline-Arbeit.

## Status-Kategorien

### Geaenderte getrackte Dateien

- Repo/Docs: `.gitignore`, `README.md`, `requirements.txt`, `start.bat`
- Backend-Kern: `backend/ai_engine.py`, `backend/main.py`, `backend/memory.py`, `backend/security.py`, `backend/scheduler.py`
- Bestehende Router: `backend/router_companion.py`, `backend/router_voice.py`
- Companion: `companion/browser.py`, `companion/communication.py`, `companion/engine.py`, `companion/file_tools.py`, `companion/media.py`
- Frontend: `frontend/main.js`, `frontend/package.json`, `frontend/preload.js`, `frontend/src/app.js`, `frontend/src/index.html`
- Voice: `voice/stt.py`, `voice/tts.py`, `voice/wakeword.py`
- Whitelist: `command_whitelist.json`

### Getrackte Loeschungen

- `CLAUDE.md` wurde aus dem Repo entfernt.
- `frontend/src/styles.css` wurde durch CSS-Module ersetzt.

### Neue App-Module

- Backend-Router: Chat, Memory, Conversations, Search, Backup, Productivity, Stripe, Agent, MCP, Plugins, Vision, Workflows, Calendar, Context, Smart, Embeddings.
- Backend-Services: Tool Registry, Agent Loop, Action Parser/Executor, Config, Context Tools, Embeddings, Integrations, Plugin Loader/Manager, Proactive, Reminders, Vision, Workflows, Voice WS.
- Companion-Tools: App Discovery, Calendar, Dev Tools, OCR, System Tools, Tool Health, Weather.
- Frontend-Module: Chat, Commands, Dashboard, Devtools, Memory, Modals, Productivity, Settings, State, System, Orb3D, i18n, CSS modules, icons.
- Voice-Module: Config, Conversation, Playback, VAD.
- Tests: Backend tests, router tests, security tests, intent tests, rendering smoke tests.
- Build/Release: `.github`, `electron-builder.json`, `lexa-backend.spec`, `build_backend.py`, `pytest.ini`.

### Lokale oder Runtime-Artefakte

Diese sollen nicht in Commits landen:

- `audit.log`
- `lexa_memory.db`
- `app_cache.json`
- `.coverage`
- `.pytest_cache/`
- `.pytest_tmp*/`
- `.test-tmp/`
- `backend-dist/`
- `build/`
- `dist/`
- `frontend/node_modules/`
- `frontend/package-lock.json`
- `venv/`
- `voice/piper/`
- `voice/test_output.wav`
- `App-Ausf*` Windows/Python-Alias-Diagnose

`.gitignore` wurde korrigiert:

- `.env.example` ist nicht mehr versehentlich ignoriert.
- `App-Ausf*` wird als lokales Windows-Diagnoseartefakt ignoriert.
- Pytest-Temp-Verzeichnisse werden ignoriert, weil Windows/Python ACLs lokale Testlaeufe sonst in `git status --ignored` stoeren koennen.

## Kennzahlen

- API-Router-Endpunkte: ca. 167
- Pytest-Tests: 331 gesammelt
- Aktueller kompletter Testlauf: `331 passed, 1 skipped`
- Chat-Rendering-Smoke-Test: `17 passed`
- Frontend-Hotspots aus vorheriger Analyse: ca. 79 `innerHTML`-Zuweisungen
- Client-Persistenz-Hotspots: ca. 40 `localStorage`-Zugriffe
- Prozessaufrufe in Backend/Companion/Voice: ca. 73
- Bekannter Shell-Hotspot: behoben; `rg -n "shell=True" backend companion voice tests -S` liefert keine Treffer

## Security-Hardening seit Audit

- `backend/plugin_manager.py` startet YAML-Prozessaktionen jetzt ohne Shell.
- YAML-Plugin-Aktionen unterstuetzen explizite `argv`-Listen fuer sichere Argumentuebergabe.
- Shell-Operatoren wie `&&`, `|`, `;`, `<` und `>` werden fuer Legacy-`command`-Strings blockiert.
- `backend/plugins_builtin/system_shortcuts.yaml` nutzt fuer System-Shortcuts explizite `argv`-Definitionen.
- `tests/test_plugin_manager.py` deckt Shell-Verzicht, `argv`-Templates, Shell-Operator-Blocking fuer `command` und `argv` sowie bestehende Dangerous-Pattern-Checks ab.
- `backend/workflows.py` uebergibt Notification-Text per Base64 an PowerShell, statt User-/Workflow-Text direkt in den `-Command`-String zu interpolieren.
- `tests/test_workflows.py` prueft, dass potenziell gefaehrlicher Notification-Text nicht roh im PowerShell-Skript landet.

## Commitfaehige Changeset-Reihenfolge

### Changeset 1: Baseline Documentation & Repo Hygiene

Inhalt:

- Neue Planungsdokumente: `docs/NEXT_LEVEL_APP_PLAN.md`, `docs/BASELINE_AUDIT.md`
- Aktualisierte Doku-Indexe: `docs/README.md`, `docs/PRD.md`, `features/INDEX.md`
- Entfernte alte Analyse-Artefakte: ehemaliges `docs/alt/*`
- `.gitignore`-Korrektur fuer `.env.example` und `App-Ausf*`

Akzeptanz:

- `git status --short --ignored` zeigt lokale Runtime-Artefakte nur als ignored.
- `.env.example` erscheint als absichtlich trackbare Platzhalterdatei.
- Keine alten `docs/alt`-Roadmaps bleiben uebrig.

### Changeset 2: Architecture & Backend Expansion

Inhalt:

- Neue Router und Backend-Services
- Refactor von `backend/main.py`
- Config, shared helpers, action parser/executor, tool registry
- Memory, embeddings, workflows, proactive, reminders, MCP, vision

Akzeptanz:

- `python -m pytest -q` ist gruen.
- Router-Registration und `/v1`-Kompatibilitaet sind dokumentiert.
- Security-Tier fuer neue Commands ist in `command_whitelist.json` nachvollziehbar.

### Changeset 3: Frontend Modularization & UI

Inhalt:

- CSS-Modularisierung
- neue Frontend-Module
- Preload/Main IPC-Erweiterungen
- Chat-Rendering-Fix und Vision-Message-Fix

Akzeptanz:

- `node --check frontend/src/app.js`
- `node --check frontend/src/chat.js`
- `node tests/test_chat_rendering.js`
- Keine regressiven inline event handlers in `index.html`

### Changeset 4: Voice & Companion Tooling

Inhalt:

- Voice-Konfiguration, STT/TTS/Wakeword-Erweiterungen
- Companion Tools fuer System, App Discovery, OCR, Dev Tools, Weather, Calendar
- Setup-Script fuer Voice

Akzeptanz:

- Router-Voice-Tests gruen.
- Tool Health kann fehlende externe Dependencies melden.
- Kein neuer unsicherer Prozessaufruf ohne Security-Bewertung.

### Changeset 5: Tests, CI & Packaging

Inhalt:

- `tests/`, `pytest.ini`, `.github`
- Electron Builder Config
- PyInstaller Spec und Backend Build Script
- Changelog/README Synchronisierung

Akzeptanz:

- Test-Suite gruen.
- CI-Jobs referenzieren existierende Pfade und Befehle.
- Build-Doku und Build-Konfig passen zusammen.

## Naechste konkrete Arbeit

1. Changeset 1 final reviewen und commitbereit schneiden.
2. Security & Trust fortsetzen: restliche Prozessaufrufe nach Risiko klassifizieren und Tool-Confirmation-Flows pruefen.
3. Startup Reliability beginnen: Healthcheck fuer Backend, Voice, Model Keys, lokale Dependencies und Port-Konflikte definieren.
4. Frontend Engineering Upgrade fortsetzen: verbleibende `innerHTML`-Hotspots und globale State-/Storage-Zugriffe reduzieren.

## Baseline-Gates

Letzter Lauf am 2026-05-14:

```text
node --check frontend\src\app.js        OK
node --check frontend\src\chat.js       OK
node tests\test_chat_rendering.js       17 passed, 0 failed
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
                                           331 passed, 1 skipped
rg -n "shell=True" backend companion voice tests -S
                                           NO_MATCHES
```

Damit ist der aktuelle App-Stand nach Repo-Hygiene- und erstem Security-Hardening weiterhin testgruen.
