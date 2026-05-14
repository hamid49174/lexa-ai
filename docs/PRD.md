# Product Requirements Document - Lexa AI

## Vision

Lexa ist ein lokaler KI-Assistent, der einen Windows-PC per Chat, Sprache und automatisierte Routinen steuert. Die App ist lokal-first, privacy-bewusst und nutzt Cloud-Provider nur optional fuer bessere KI-, Voice- oder Vision-Funktionen.

## Target Users

- Power-User, die ihren PC effizienter steuern wollen
- Entwickler, die Dev-Tools per Chat nutzen moechten
- Produktivitaetsnutzer mit Todos, Pomodoro, Habits und Zeiterfassung
- Privacy-bewusste User, die lokale Kontrolle bevorzugen

## Core Features

| Priority | Feature | Status |
|----------|---------|--------|
| P0 | Chat + KI Provider | Done |
| P0 | PC-Steuerung ueber Companion Commands | Done |
| P0 | Voice: STT, TTS, Wakeword | Done |
| P0 | Produktivitaet: Todos, Pomodoro, Habits, Time Tracking | Done |
| P0 | Memory: Conversations, Notes, Profile, Clipboard, Search | Done |
| P0 | Agent Loop, Tool Use, MCP, Vision, Calendar, Weather, Email | Done |
| P0 | Security: Whitelist, Rate Limits, Audit Log, Input Validation | In hardening |
| P0 | Electron Packaging | In validation |

## Next-Level Roadmap

Die aktive professionelle Roadmap liegt in `NEXT_LEVEL_APP_PLAN.md`. Kurzfassung:

| Priority | Workstream | Goal |
|----------|------------|------|
| P0 | Baseline & Repo-Hygiene | Sauberer, reviewbarer, releasefaehiger Arbeitsstand |
| P0 | Security & Trust Hardening | CSP ohne `unsafe-inline`, weniger `innerHTML`, sichere Tool-/Plugin-Ausfuehrung |
| P0 | Startup Reliability & Diagnostics | Klare Diagnose fuer Backend, Provider, Keys, Voice, Port und Dependencies |
| P1 | Frontend Engineering Upgrade | DOM-Builder, weniger globale Seiteneffekte, echte Frontend-Tests |
| P1 | Assistant Quality & Tool UX | Bessere Confirmation, Dry Run, Tool-History, Agent-Step-UX |
| P1 | Voice Reliability & UX | Verstaendlicher Voice-Status, Fallbacks, Latenz- und Fehleranzeigen |
| P1 | Data, Memory & Privacy | Memory Inspector, Forget-Flows, Backup/Restore-Reife |
| P2 | Testing & CI Gates | CI-Gates, Electron-Smoke-Test, Coverage fuer kritische Module |
| P2 | Packaging & Commercial Readiness | Reproduzierbarer Installer, Code Signing, Offline-Lizenzstrategie |

## Success Metrics

- Lokale Befehle reagieren in normalen Faellen unter 200ms.
- Kritische Aktionen sind auditiert und bestaetigungspflichtig.
- App startet auf einem frischen Windows 10/11 Profil ohne Entwicklungsumgebung.
- Backend-, Frontend-Rendering- und Electron-Smoke-Checks laufen vor Releases.
- 0 bekannte kritische Sicherheitsluecken.
- User kann jederzeit sehen, welche Provider, Voice-Engines und Tools aktiv sind.

## Constraints

- Windows-only fuer v1.x.
- Offline-faehiger Kernbetrieb, Cloud optional.
- Keine externen Dienste, wenn lokale Alternativen sinnvoll verfuegbar sind.
- Einzelentwickler-Projekt, daher kleine, reviewbare Sprints.

## Non-Goals fuer die naechsten Sprints

- Kein grosses neues Feature ohne Qualitaetsarbeit.
- Kein UI-Redesign ohne klares Produktproblem.
- Kein Remote Access vor abgeschlossener Security-Haertung.
- Keine weitere parallele Roadmap neben `NEXT_LEVEL_APP_PLAN.md`.
