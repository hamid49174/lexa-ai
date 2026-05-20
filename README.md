# LEXA AI v1.0.0

**Dein lokaler KI-Desktop-Assistent fuer Windows.**

Lexa steuert deinen PC per Sprache und Chat - lokal-first, privat und mit optionalen Cloud-Providern.

---

## Quick Start

```bash
# 1. Repo klonen und Dependencies installieren
git clone https://github.com/alexsprogis/lexa-ai.git
cd lexa-ai
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 2. Frontend installieren
cd frontend && npm install && cd ..

# 3. Optional: AI-Provider hinterlegen
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'groq_api_key', 'DEIN_GROQ_KEY')"
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'openai_api_key', 'DEIN_OPENAI_KEY')"
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'gemini_api_key', 'DEIN_GEMINI_KEY')"

# 4. Starten
start.bat
```

---

## Features

- **138+ PC-Befehle** - Apps, Fenster, Prozesse, Netzwerk, Dienste, Autostart, Umgebungsvariablen
- **KI-Chat** - Groq, OpenAI, Gemini oder lokales Ollama
- **Sprache** - Deepgram Nova-3 STT + Groq/local fallback, Cartesia/ElevenLabs/SAPI TTS
- **Browser-Automation** - YouTube, Web-Scraping, PDFs, Screenshots (Playwright)
- **Produktivitaet** - Todos, Pomodoro-Timer, Gewohnheiten, Zeiterfassung, Fokus-Modus
- **Datei-Tools** - Archive, Backups, PDF merge/split, Bild-Konvertierung, Duplikat-Finder
- **Developer-Tools** - Git, Docker, API-Tester, Log-Analyse, JSON/Regex/Base64-Utilities
- **Kommunikation** - E-Mail (Gmail), Telegram, Discord
- **Gedaechtnis** - SQLite mit FTS5, Notizen, Routinen, Profil
- **Sicherheit** - 3-Tier Whitelist, Prompt-Injection-Defense, Rate Limiting, Audit Log
- **7 Views** - Dashboard, Chat, System, Commands, Productivity, Memory, Settings
- **Responsive UI** - Mobile-Breakpoints, ARIA Accessibility, Keyboard Shortcuts

---

## Voraussetzungen

- **Windows 10/11**
- **Python 3.11+**
- **Node.js 18+**
- **Git**

Optional: Ollama (lokale KI), ffmpeg (Media-Konvertierung)

---

## Installation

```bash
# Repository klonen
git clone https://github.com/alexsprogis/lexa-ai.git
cd lexa-ai

# Python Virtual Environment
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# Playwright Browser
venv\Scripts\playwright install chromium

# Frontend Dependencies
cd frontend && npm install && cd ..
```

### Cloud API Keys

Du kannst einen oder mehrere AI-Provider parallel hinterlegen:

```bash
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'groq_api_key', 'DEIN_GROQ_KEY')"
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'openai_api_key', 'DEIN_OPENAI_KEY')"
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'gemini_api_key', 'DEIN_GEMINI_KEY')"
```

Groq-Key: [console.groq.com](https://console.groq.com)  
OpenAI-Key: [platform.openai.com](https://platform.openai.com)  
Gemini-Key: [aistudio.google.com](https://aistudio.google.com)

Alternativ: kopiere `.env.example` nach `.env` und trage den Key dort ein.

### Voice Setup

Voice nutzt den Windows Credential Manager fuer optionale Cloud-Provider.

- **STT** - Deepgram Nova-3 (primaer), Groq Whisper (Fallback), lokales faster-whisper (offline)
- **TTS** - Cartesia Sonic (Cloud), ElevenLabs (optionale Premium-Stimmen), Windows SAPI (offline Fallback)

Beispiel fuer API-Keys:

```python
import keyring
keyring.set_password("lexa-ai", "deepgram_api_key", "DEIN_DEEPGRAM_KEY")
keyring.set_password("lexa-ai", "cartesia_api_key", "DEIN_CARTESIA_KEY")
keyring.set_password("lexa-ai", "elevenlabs_api_key", "DEIN_ELEVENLABS_KEY")
keyring.set_password("lexa-ai", "groq_api_key", "DEIN_GROQ_KEY")  # optionaler STT-Fallback
```

Deepgram Key: [deepgram.com](https://deepgram.com)  
Cartesia Key: [cartesia.ai](https://cartesia.ai)  
ElevenLabs Key: [elevenlabs.io](https://elevenlabs.io)

---

## Starten

**Ein-Klick-Start:**

```bash
start.bat
```

Oder manuell:

```bash
# Backend (Terminal 1)
venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend (Terminal 2)
cd frontend && npx electron .
```

### Personal OS Integration

Lexa exposes a narrow extraction endpoint for the local Personal OS:

```http
POST /personal-os/raw-inbox/extract
```

Request:

```json
{
  "sourcePath": "06_Inbox/Raw/example.txt",
  "body": "Raw inbox text"
}
```

Response:

```json
{
  "status": "ok",
  "summary": "...",
  "tags": ["inbox", "raw"],
  "provider": "groq",
  "model": "llama-3.3-70b-versatile"
}
```

This endpoint is intentionally separate from normal `/chat`: it does not use chat history or tool execution, and is meant for summary/tag extraction only.

---

## Tech-Stack

| Komponente | Technologie |
|------------|-------------|
| Frontend | Electron + Vanilla JS (modular) |
| Backend | Python FastAPI (Port 8000, localhost) |
| KI | Groq + OpenAI + Gemini + Ollama |
| STT | Deepgram Nova-3 + Groq Whisper + faster-whisper |
| TTS | Cartesia Sonic + ElevenLabs + Windows SAPI |
| Browser | Playwright + yt-dlp |
| Datenbank | SQLite mit FTS5 Volltextsuche |
| Security | keyring + 3-Tier Whitelist + Rate Limiting |

---

## Building from Source

Lexa nutzt `electron-builder` zum Erstellen des Windows-Installers:

```bash
cd frontend
npm run build
```

Das erzeugt einen NSIS-Installer unter `frontend/dist/`. Die Konfiguration liegt in `electron-builder.json`.

---

## Testing

```bash
# Optional: install local development/build tooling
venv\Scripts\pip install -r requirements-dev.txt

# Backend-Tests
venv\Scripts\python -m pytest -q

# Einzelne Test-Module
venv\Scripts\python -m pytest tests/test_memory.py -v
venv\Scripts\python -m pytest tests/test_security.py -v

# Frontend-Rendering-Checks
node tests/test_chat_rendering.js

# Python-Lint wie in CI
# Hinweis: derzeit Report-Gate bis zum Lint-Baseline-Cleanup
venv\Scripts\python -m flake8 backend companion voice --max-line-length=120 --ignore=E501,W503,E402
```

### Release Readiness

Lexa uses scripted release gates instead of ad hoc manual checks:

```powershell
scripts\run_quality_gates.ps1 -Mode Quick
scripts\run_quality_gates.ps1 -Mode Full
scripts\run_release_candidate_check.ps1 -Target InternalRC
scripts\check_remote_ci_readiness.ps1
scripts\generate_codex_context_pack.ps1 -Check
```

Release tiers:

- `InternalRC`: internal review candidate; warnings are allowed when documented.
- `PublicRC`: requires remote CI proof, signing, VM installer proof, reviewed OS cleanup risk, and clear website target.
- `PublicRelease`: requires PublicRC plus release/privacy readiness.

Read `AGENTS.md`, `docs/codex_context_pack.md`, and `docs/release/release_candidate_checklist.md` before release-hardening work.

Release-readiness gates:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Full
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode CI
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Mode StrictRC
```

The release-candidate check is local only. It does not deploy, upload, delete files, or commit build artifacts. For release proofing, also use clean-clone and packaging/installer smokes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install -RunQuickGate -KeepTemp
powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1 -Build
powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <artifact-dir>
```

`StrictRC` distinguishes `Ready` from `Needs Review` when remote CI, signing, or disposable-VM install/uninstall proof is still missing. See `docs/release/release_candidate_checklist.md` and the `docs/release/` runbooks.

PublicRC/PublicRelease remain blocked until remote GitHub Actions, signed installer, disposable VM install/uninstall, approved website release target, and OS cleanup review are proven. Phase 4F tracks these items in `docs/release/public_rc_blocker_matrix.md` and checks remote-CI readiness with `scripts\check_remote_ci_readiness.ps1`. The context-pack generator is safe-only and must not read Personal OS content, eval results, traces, memory databases, env files, or signing material.

Phase 5A adds a PublicRelease privacy/trace consent checklist and keeps unresolved PublicRC items explicit: no GitHub remote means remote CI is not yet proven, unsigned installers remain PublicRC-blocking, VM install/uninstall must be proven outside the productive machine, website release targeting stays external/static until approved, and OS cleanup remains a separate backup-first review project.

Phase 5B classifies every remaining PublicRC blocker as agent-solvable, user-decision, external-infrastructure, later, or proven. The release scripts and docs now make clear that GitHub Actions, VM installer proof, signing, website release target, OS cleanup review, and privacy/trace consent require user or external proof before PublicRC/PublicRelease.

---

## Sicherheit

- **Kein externer Zugriff** - API nur auf `127.0.0.1`
- **3-Tier Whitelist** - gefaehrliche Befehle blockiert oder brauchen Bestaetigung
- **Prompt Injection Defense** - Pattern-Matching plus Unicode-Normalisierung
- **Path/URL/Param Validation** - System-Verzeichnisse blockiert, SSRF-Schutz
- **Rate Limiting** - pro Endpoint
- **Audit Log** - jeder Befehl wird protokolliert
- **Keine Secrets im Code** - alles ueber Windows Credential Manager (`keyring`)

---

## Lizenz

MIT
