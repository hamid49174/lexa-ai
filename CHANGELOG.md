# Changelog

Alle wichtigen Aenderungen an Lexa AI werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Added
- Multi-Agenten-Orchestrator (Planner -> parallele read-only Sub-Agenten -> adversarische Verifikation -> zitierte Synthese), eigene Agenten-Ansicht und `/orchestrate`-Chat-Integration
- Generische MCP-zu-Chat-Bruecke und lesende Coding-Bruecke (filesystem-MCP) fuer den Code-Agenten
- Live-Websuche/Grounding im Chat (Tavily/Brave/Exa mit DDG-Fallback) sowie Obsidian/Personal-OS-Grounding
- Voice: OpenAI- und Groq-Sprach-Keys (STT/TTS) ueber UI/API verwaltbar (vorher nur per keyring-CLI)
- Workflow-Event-Bruecke: ContextMonitor-Events (high_cpu, system_start, ...) loesen Event-Workflows wieder aus

### Fixed
- KRITISCH: Workflow-`tool`-Steps liefen ins Leere, weil die CompanionEngine nicht an den Scheduler durchgereicht wurde
- `file_move`/`file_copy` ueberschreiben bestehende Zieldateien nicht mehr kommentarlos (Datenverlust-Schutz)
- Light-Theme: dunkle Flaechen in Override-/View-CSS bekommen ein korrektes helles Pendant
- Voice-Chat sendete die Konversations-ID aus einem nicht existenten State-Key (immer `undefined`)
- Timer- und Pomodoro-Intents werden nicht mehr faelschlich als generisches `app_open` erkannt
- Voice-Konfigurationsrouten liefern bei ungueltigen Voice-IDs wieder korrekte `400`-Fehler
- Chat-Rendering im Frontend funktioniert auch in isolierten Tests ohne globale `t()`-Funktion

### Changed
- **Chat ist Gemini-only** (Google Gemini); die fruehere Groq/OpenAI/Anthropic/Ollama-Multi-Provider-Schicht fuer den Chat ist nur noch Legacy. Doku (README, start.bat, AI_HANDOFF) entsprechend korrigiert. Sprache (STT/TTS) nutzt weiterhin Deepgram/OpenAI/Groq/Cartesia/ElevenLabs.
- Eigentuemer-/Repo-Angaben vereinheitlicht auf `hamid49174` (electron-builder appId/Copyright, GitHub-Update-Owner, README, Release-Docs)
- `start.bat` und README auf den aktuellen 7-View- und Voice-Stack gebracht
- Runtime-Artefakte wie `audio_cache/`, `app_cache.json` und SQLite-WAL-Dateien per `.gitignore` aus dem Repo-Rauschen genommen

## [1.0.0] - 2026-03-14

### Added
- Deepgram Cloud STT als primaere Spracherkennung
- Zentrales State Management fuer Frontend-Module
- Zentrales `backend/config.py` fuer konfigurierbare Werte
- API-Versionierung mit `/v1` Rueckwaertskompatibilitaet
- Einheitliches API-Response-Format
- Code-Signing-Dokumentation und Infrastruktur

### Changed
- `main.py` in mehrere fokussierte Router-Module aufgeteilt
- `tools.js` in mehrere Frontend-Module zerlegt
- Silent `catch {}`-Bloecke durch Logging ersetzt
- Conversation-History auf SQLite als Single Source of Truth umgestellt
- Browser-, Datei-, Medien- und Entwickler-Views aus der UI entfernt

### Fixed
- Magic Numbers zentralisiert
- Chat-History-Limits zwischen Frontend und Backend abgeglichen
- Inkonsistente API-Responses vereinheitlicht

### Security
- API-Keys nur noch ueber `keyring`
- `.gitignore` fuer `.env` und Build-Artefakte erweitert
- Startup-Warnung fuer API-Keys in Umgebungsvariablen

## [0.20.0] - 2026-02-15

### Added
- FTS5 Volltextsuche fuer Notes und Memories
- Backup/Restore API fuer SQLite
- Windows SAPI als TTS-Fallback
- Electron-Builder Installer fuer Windows x64
- GitHub Actions fuer Tests, Linting, Build und Releases
- Responsive Layout, Accessibility und UI-States
- Onboarding Wizard und Auto-Updater

### Changed
- `app.js` in mehrere Module zerlegt
- Command Whitelist bereinigt
- Voice-Dependencies erweitert

### Fixed
- Pomodoro Thread-Safety
- Frontend Interval-Leaks bei View-Wechseln

## [0.19.0] - 2026-01-20

### Added
- Dashboard Weekly Chart
- Notification Center
- Zero-prompt Modal-System
- Inline-Todo-Editing und Todo-Export
- Focus Mode Banner
- Quick Notes, Habit-Visualisierung und Clipboard-History
- Code-Block Header mit Copy-Button
- Sidebar-Badge fuer offene Todos

### Changed
- View-Refreshes mit `Promise.allSettled` parallelisiert
- Inline-Handler durch `data-action` Events ersetzt
- XSS-Haertung ueber mehrere Views hinweg ausgebaut

### Security
- Shell-Injection, SSRF, ZIP Slip und URL-Validierung gehaertet
- Rate Limiting und Plugin-Sandbox erweitert

## [0.18.0] - 2025-12-15

### Added
- Batch-Befehlsausfuehrung
- Rotierende Chat-Placeholder
- Zeichenzaehler
- Conversation-Export mit Statistik

### Changed
- Groq-Modelle aktualisiert
- Datum und Uhrzeit in den System-Prompt integriert

## [0.17.0] - 2025-11-15

### Added
- Deduplizierte Chat-Logik ueber `action_parser.py`
- Robuste JSON-Extraktion mit mehrstufiger Strategie
- Dynamisches Plugin-System
- yt-dlp Fallback fuer YouTube

### Changed
- Clipboard und Session-State in SQLite persistiert
- Blockierende Calls auf `asyncio.to_thread()` umgestellt
- System-Prompt um komplette Befehlsliste erweitert

## [0.16.0] - 2025-10-15

### Added
- Clipboard History API
- Quick Text Snippets
- Onboarding Wizard
- Theme-System mit Dark/Light, Akzentfarben und Font-Size

## [0.15.0] - 2025-09-15

### Added
- AI-generierte Conversation-Titel
- Multi-Model-Auswahl in Settings
- Globale Suche fuer Conversations, Notes und Memories
- Chat-Export
- Drag and Drop mit File Intelligence

## [0.14.0] - 2025-08-15

### Added
- Multi-Conversation System
- SSE Streaming Chat
- Smart Suggestion Chips
- Dashboard mit mehreren Widgets
- Command Palette
- NeoAI UI Overhaul

## [0.13.0] - 2025-07-15

### Added
- 138 PC-Befehle
- Produktivitaets-Suite mit Todos, Pomodoro, Habits und Focus Mode
- System Tray, Notifications und Autostart
- Keyboard Shortcuts
- Routine Scheduler
- Erweiterte System- und Developer-Views

### Security
- 3-Tier Command Whitelist
- Injection-Erkennung
- Path Traversal Guards, SSRF Protection und PowerShell Sanitization
- Rate Limiting und Audit Logging

## [0.1.0] - 2025-05-15

### Added
- Initiales Release
- FastAPI Backend plus Electron Frontend
- Groq API plus Ollama Fallback
- faster-whisper STT plus Piper TTS
- Erste Basis-Befehle fuer App-Steuerung und Systeminfos
- SQLite Memory mit Notes, Memories, Profil und Routinen
- Voice Orb UI und Wake-Word Detection
