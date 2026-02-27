# LEXA AI

**Dein lokaler KI-Desktop-Assistent für Windows.**

Lexa steuert deinen PC per Sprache und Chat — komplett lokal, kostenlos, privat. Kein Cloud-Zwang, keine Abos, keine Datensammlung.

---

## Features

### 60+ PC-Befehle
- Apps starten, Fenster steuern, Prozesse verwalten
- Lautstärke, Helligkeit, Clipboard, Timer, Screenshot
- Herunterfahren, Neustarten (mit Bestätigung)

### Browser-Automation
- YouTube suchen & abspielen
- Websites scrapen, als PDF speichern, Screenshots
- Preise prüfen auf Produktseiten
- Playwright-basiert (Chromium)

### Datei-Tools
- Doppelte Dateien finden (MD5)
- Downloads automatisch nach Typ sortieren
- PDFs zusammenfügen & aufteilen
- Speicher-Analyse, Temp-Bereinigung
- Batch-Umbenennung

### Media-Steuerung
- Play/Pause, Nächster/Vorheriger Track, Stop
- Spotify öffnen & durchsuchen
- Medien konvertieren (ffmpeg)
- Audio aus Videos extrahieren
- Bildschirmaufnahme

### Kommunikation
- E-Mail lesen & senden (Gmail SMTP/IMAP)
- Telegram Nachrichten lesen & senden (Bot API)
- Discord Nachrichten senden (Webhooks)

### KI-Chat
- **Groq API** (Llama 3.3 70B) — schnelle Cloud-KI
- **Ollama Fallback** — komplett lokal wenn Groq offline
- Versteht natürliche Sprache und führt Aktionen aus
- Kontext-Injektion aus Gedächtnis

### Gedächtnis-System
- SQLite-Datenbank für Notizen, Erinnerungen, Profil
- Auto-Learning: Lexa merkt sich Vorlieben aus Gesprächen
- Routinen erstellen und verwalten
- Alle Daten bleiben lokal

### Sprache
- **faster-whisper** STT — Sprache zu Text (lokal, CPU)
- **Piper TTS** — Text zu Sprache (deutsche Stimme, lokal)
- Mikrofon-Button im Chat

### Sicherheit
- 3-Tier Command Whitelist (erlaubt / Bestätigung / blockiert)
- Prompt-Injection-Defense (17 Patterns)
- Path/URL/Param Validation
- Rate Limiting (30/min)
- Audit Logging
- API nur auf localhost — kein externer Zugriff
- Credentials im Windows Credential Manager (keyring)

### UI
- Electron Desktop-App
- Dark Professional Theme (#0a0a0f + #ff3b00 Accent)
- 8 Views: Chat, System, Commands, Browser, Files, Media, Memory, Settings
- Toast-Notifications
- Live System-Monitor (CPU, RAM, Disk)
- Connection Banner + Auto-Reconnect

---

## Voraussetzungen

- **Windows 10/11**
- **Python 3.11+** (getestet mit 3.14)
- **Node.js 18+** (getestet mit 24.x)
- **Git**

Optional:
- **Ollama** — für lokale KI ohne Internet
- **ffmpeg** — für Media-Konvertierung und Screen Recording
- **Piper TTS** Binary + deutsches Modell

---

## Installation

```bash
# 1. Repository klonen
git clone https://github.com/yourusername/lexa-ai.git
cd lexa-ai

# 2. Python Virtual Environment
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 3. Playwright Browser installieren
venv\Scripts\playwright install chromium

# 4. Frontend Dependencies
cd frontend
npm install
cd ..

# 5. Groq API Key setzen (einmalig)
venv\Scripts\python -c "import keyring; keyring.set_password('lexa-ai', 'groq-api-key', 'DEIN_KEY_HIER')"
```

---

## Starten

**Ein-Klick-Start:**
```
start.bat
```

Oder manuell:
```bash
# Backend
venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend (neues Terminal)
cd frontend && npx electron .
```

---

## Projektstruktur

```
lexa-ai/
├── CLAUDE.md               # Projektdokumentation
├── command_whitelist.json   # Sicherheits-Whitelist
├── requirements.txt         # Python Dependencies
├── start.bat               # Ein-Klick-Launcher
├── backend/
│   ├── main.py             # FastAPI Server
│   ├── ai_engine.py        # Groq + Ollama KI
│   ├── memory.py           # SQLite Gedächtnis
│   ├── security.py         # Security Module
│   ├── router_companion.py # Companion API
│   └── router_voice.py     # Voice API
├── companion/
│   ├── engine.py           # 60 PC-Befehle
│   ├── browser.py          # Playwright Automation
│   ├── file_tools.py       # Datei-Werkzeuge
│   ├── media.py            # Media-Steuerung
│   └── communication.py    # E-Mail, Telegram, Discord
├── voice/
│   ├── stt.py              # Spracherkennung
│   ├── tts.py              # Sprachausgabe
│   └── piper/              # TTS Engine + Modell
└── frontend/
    ├── main.js             # Electron
    ├── preload.js          # Secure Bridge
    └── src/
        ├── index.html      # 8-View UI
        ├── styles.css      # Dark Theme
        └── app.js          # Frontend Logic
```

---

## Tech-Stack

| Komponente | Technologie |
|------------|-------------|
| Frontend | Electron + Vanilla JS |
| Backend | Python FastAPI |
| KI | Groq API + Ollama |
| STT | faster-whisper |
| TTS | Piper |
| Browser | Playwright |
| Datenbank | SQLite |
| Security | keyring + Whitelist |

---

## API Endpoints

| Method | Endpoint | Beschreibung |
|--------|----------|-------------|
| GET | /health | Server Status |
| POST | /chat | KI-Chat |
| POST | /companion/execute | Befehl ausführen |
| GET | /companion/commands | Alle Befehle |
| POST | /voice/stt | Sprache → Text |
| POST | /voice/tts | Text → Sprache |
| GET | /ai/status | KI-Provider Status |
| GET | /memory/stats | Gedächtnis-Stats |
| GET | /memory/notes | Notizen |
| POST | /memory/profile | Profil setzen |

---

## Sicherheit

Lexa nimmt Sicherheit ernst:

- **Kein externer Zugriff** — API nur auf 127.0.0.1
- **3-Tier Whitelist** — gefährliche Befehle blockiert oder brauchen Bestätigung
- **Prompt Injection Defense** — KI-Input wird auf 17 Patterns gefiltert
- **Path Traversal Schutz** — System-Verzeichnisse blockiert
- **Rate Limiting** — max 30 Befehle pro Minute
- **Audit Log** — jeder Befehl wird protokolliert
- **Keine Secrets im Code** — alles via Windows Credential Manager

---

## Lizenz

MIT

---

*Built with Claude Code*
