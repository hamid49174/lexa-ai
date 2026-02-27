# CLAUDE.md — Das Lexa AI Projektgehirn

## Was ist Lexa
Lexa ist ein lokaler KI-Assistent der meinen Windows-PC vollständig steuert.
Läuft als Electron Desktop-App mit Python FastAPI Backend auf Port 8000.
Companion-Engine steuert Windows direkt via psutil/subprocess.
Voice: faster-whisper STT + Piper TTS — komplett lokal.
Browser-Automation via Playwright. Kommunikation via SMTP/IMAP, Telegram, Discord.
KI: Groq API (primary) + Ollama (local fallback). SQLite-Gedächtnis für Kontext.

## Sicherheitsregeln (NIEMALS brechen)
- Alle Befehle durch command_whitelist.json validieren
- Keine externen APIs wenn lokal möglich
- Credentials nur via python-keyring — NIE im Code
- Jede file_delete / email_send / shutdown braucht User-Bestätigung
- API nur auf localhost (127.0.0.1) — kein externer Zugriff
- KI-Output immer parsen & validieren — niemals raw als System-Befehl ausführen
- Prompt Injection Defense: Jeder User-Input wird sanitized (17 Patterns)
- Rate Limiting: Max 30 Befehle pro Minute
- Audit Log: Jeder Befehl lokal geloggt mit Timestamp und Ergebnis
- Path Validation: System32/SysWOW64 blockiert, keine Path Traversal
- URL Validation: Nur http/https, Cloud Metadata IPs blockiert
- Param Validation: Alle path/url Parameter werden geprüft
- Dangerous Command Detection: 15 gefährliche Patterns in KI-Output erkannt

## Tech-Stack
- Frontend: Electron + Vanilla JS + Custom CSS (Purple/Violet Glassmorphism Theme)
- Backend: Python FastAPI (Port 8000, nur localhost)
- KI: Groq API (Llama 3.3 70B) → Ollama Fallback (lokal)
- STT: faster-whisper (lokal, base model, CPU int8)
- TTS: Piper TTS mit Thorsten-Medium Stimme (lokal)
- Wake-Word: Custom VAD + STT Loop (lokal)
- PC-Kontrolle: psutil, subprocess, pyperclip, netsh, PowerShell
- Browser: Playwright (Chromium)
- PDF: pypdf (merge/split)
- Kommunikation: smtplib/imaplib (Gmail), requests (Telegram/Discord)
- Gedächtnis: SQLite (lexa_memory.db)

## Projektstruktur
```
lexa-ai/
├── CLAUDE.md               # Projektgehirn
├── command_whitelist.json   # Sicherheits-Whitelist (3 Tiers)
├── lexa_memory.db          # SQLite Gedächtnis-DB
├── requirements.txt
├── start.bat               # Ein-Klick-Start (mit Health-Check)
├── backend/
│   ├── main.py             # FastAPI Server v0.8.0 + Router + Memory Endpoints
│   ├── ai_engine.py        # Groq API + Ollama Fallback + Memory Context
│   ├── memory.py           # SQLite: Notes, Memories, Profil, Routinen
│   ├── security.py         # Whitelist, Rate Limit, Sanitize, Path/URL/Param Validation, Audit
│   ├── router_companion.py # /companion/* Endpoints + Param Validation
│   ├── router_voice.py     # /voice/* Endpoints (STT/TTS)
│   └── scheduler.py        # Routine Scheduler (cron-like, 60s Intervall)
├── companion/
│   ├── engine.py           # CompanionEngine (60 Befehle)
│   ├── browser.py          # Playwright: YouTube, Scraping, PDF, Screenshots
│   ├── file_tools.py       # Duplikate, Batch-Rename, PDF merge/split, Cleanup
│   ├── media.py            # Media-Keys, Spotify, ffmpeg Convert, Screen Record
│   └── communication.py    # E-Mail (SMTP/IMAP), Telegram Bot, Discord Webhook
├── voice/
│   ├── stt.py              # faster-whisper STT
│   ├── tts.py              # Piper TTS
│   ├── wakeword.py         # Wake-Word Detection
│   └── piper/              # Piper Binary + Deutsche Stimme
├── frontend/
│   ├── package.json
│   ├── main.js             # Electron Main Process
│   ├── preload.js          # Secure Bridge (chat, execute, tts, stt, memory, ai)
│   └── src/
│       ├── index.html      # NeoAI UI mit 9 Views + Dashboard + Voice Orb + Toast System
│       ├── styles.css      # Purple/Violet Glassmorphism Theme + Voice Orb + Dashboard CSS
│       └── app.js          # v0.8 Chat, Voice, Dashboard, Command Palette, Voice Orb
└── tests/
```

## Verfügbare Befehle (60 total)

### Basis (immer erlaubt):
app_open, app_list, system_info, screenshot, process_list, clipboard_read,
clipboard_write, volume_set, volume_mute, file_search, window_list, window_focus,
brightness_set, brightness_get, wifi_status, battery_status, timer_set, browser_open

### Browser-Automation (immer erlaubt):
youtube_search, youtube_play, web_open, web_screenshot, web_pdf, web_scrape,
price_check, browser_close

### Media (immer erlaubt):
media_play_pause, media_next, media_prev, media_stop, spotify_open,
convert_media, extract_audio, screen_record

### Gedächtnis & Notizen (immer erlaubt):
note_create, note_read, note_list, memory_search, memory_add, summarize, routine_list

### Datei-Tools (Bestätigung nötig):
find_duplicates, batch_rename, organize_downloads, merge_pdfs, split_pdf,
disk_analysis (erlaubt), clean_temp

### Kommunikation:
email_read (erlaubt), email_send (Bestätigung), telegram_read (erlaubt),
telegram_send (Bestätigung), discord_send (Bestätigung)

### System (Bestätigung nötig):
process_kill, shutdown, restart, note_delete, routine_create, routine_delete, routine_toggle

### Blockiert (hardcoded):
format_disk, mass_delete, password_read, keylogger, screen_spy, credential_dump,
registry_delete_tree, disable_firewall, disable_antivirus, crypto_mine, network_sniff

## API Endpoints
- GET  /health — Server-Status + Version
- POST /chat — KI-Chat (Groq → Ollama)
- POST /companion/execute — PC-Befehle ausführen
- GET  /companion/commands — Alle Befehle listen
- POST /voice/stt — Audio → Text (faster-whisper)
- POST /voice/tts — Text → Audio (Piper)
- GET  /voice/tts/status — Piper-Status
- GET  /voice/stt/status — Whisper-Status
- GET  /ai/status — KI-Provider Status (Groq + Ollama)
- GET  /memory/stats — Gedächtnis-Statistiken
- GET  /memory/notes — Alle Notizen
- GET  /memory/profile — User-Profil
- POST /memory/profile — Profil setzen
- GET  /memory/routines — Alle Routinen
- GET  /scheduler/status — Scheduler-Status (running, active routines)

## Frontend Features
- 9 Views: Dashboard, Chat, System, Commands, Browser, Files, Media, Memory, Settings
- NeoAI-inspiriertes Design: Purple/Violet (#8b5cf6) Glassmorphism mit Gradient Borders
- Animated Voice Orb: Pulsiert/leuchtet bei Spracheingabe, klickbar für Recording
- Dashboard: 6 Widgets (System Stats, KI Status, Quick Actions, Routinen, Memory, Greeting)
- Command Palette: Ctrl+P Overlay mit Fuzzy-Search über Views + Commands
- Enhanced Chat: Code-Blocks, Inline-Code, Bold, Italic, Links, Timestamps, Copy-Button
- Toast-Notification-System (success, error, warning, info)
- Connection Banner bei Backend-Verlust + Auto-Reconnect
- View-Transitions mit Fade-In Animation
- Card-Hover-Glow-Effekt, Sidebar Active-Indicator
- Error Handling: Offline-Checks vor API-Calls
- Keyboard Shortcuts: Ctrl+1-9 Views, Ctrl+P Palette, Esc Chat, Ctrl+L Clear, Ctrl+B Sidebar, Ctrl+M Mic
- Chat-History Persistenz via localStorage (letzte 50 Nachrichten)
- Command-Suche mit Live-Filter und Highlighting
- Collapsible Sidebar mit State-Persistenz
- System Tray: Minimize-to-Tray, Tray-Kontextmenü (Open, System, Commands, Autostart, Quit)
- Windows Native Notifications bei Befehl-Ausführung + Verbindungsverlust
- Autostart mit Windows (Toggle in Settings)
- Desktop-Benachrichtigungen Toggle in Settings
- Routine Scheduler: Cron-ähnliche Ausführung (HH:MM, Mo-Fr HH:MM, Mo,Mi,Fr HH:MM)

## Aktueller Status
- [x] Phase 0: Setup — Git Repo, CLAUDE.md, Projektstruktur
- [x] Phase 1: Lebendiges Skelett — FastAPI + Electron + Companion (10 Befehle)
- [x] Phase 2: Voice & Persönlichkeit — STT, TTS, Wake-Word, 21 Befehle, Voice-UI
- [x] Phase 3: Features stapeln — 49 Befehle, Browser, Dateien, Media, Kommunikation, 6 Views
- [x] Phase 4: KI-Features — 60 Befehle, Ollama Fallback, SQLite Memory, Notes, Routinen, 7 Views
- [x] Phase 5: Polish & Security — Toast System, Animationen, Error Handling, Security Hardening, Settings View, 8 Views
- [x] Phase 6: Launch — Git Init, README.md, .gitignore, Dependency Cleanup, Initial Commit (29 files, 6032 LOC)
- [x] Phase 7: Quality of Life — Keyboard Shortcuts, Chat-Persistenz, Command-Suche, Sidebar-Toggle, LICENSE
- [x] Phase 8: Desktop Integration — System Tray, Notifications, Autostart, Routine Scheduler
- [x] Phase 9: Intelligence & Dashboard — Enhanced AI Prompt, Dashboard, Command Palette, NeoAI UI Overhaul, Voice Orb, Chat Upgrades
