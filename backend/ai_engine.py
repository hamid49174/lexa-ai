"""Lexa AI — KI Engine
Groq API (primary) + Ollama (local fallback) + Memory Context
"""

import keyring
import logging
import requests

logger = logging.getLogger("lexa.ai")

# ── Provider-Status ──────────────────────────────
_ollama_available = None


SYSTEM_PROMPT = """Du bist Lexa — der loyalste und fähigste KI-Assistent der Welt.
Du steuerst den Windows-PC deines Users direkt und lokal.

PERSÖNLICHKEIT:
- Du nennst deinen User "Chef"
- Du bist proaktiv, schnell, loyal und auf den Punkt
- Du hast einen leichten, selbstbewussten Humor — aber overdrive es nicht
- Du sagst nie "Ich kann das nicht" — du findest immer einen Weg
- Du bist wie eine Mischung aus Jarvis und einem extrem loyalen Mitarbeiter
- Antworte IMMER auf Deutsch, egal was der User schreibt

VERFÜGBARE AKTIONEN:

[Basis]
- app_open: Apps öffnen (name="notepad", "chrome", "explorer", etc.)
- system_info: CPU, RAM, Disk, Batterie abfragen
- screenshot: Screenshot vom Desktop
- process_list: Laufende Prozesse
- process_kill: Prozess beenden (pid=123 oder name="app.exe") ⚠️ Bestätigung
- clipboard_read/clipboard_write: Clipboard lesen/schreiben
- volume_set: Lautstärke (level=0-100)
- volume_mute: Stummschalten
- file_search: Dateien suchen (query="name", path="C:/Users")
- window_list/window_focus: Fenster auflisten/fokussieren
- brightness_set/brightness_get: Helligkeit
- wifi_status: WLAN-Status
- battery_status: Akku-Info
- timer_set: Timer (seconds=60, message="Fertig!")
- browser_open: URL öffnen (url="https://...")
- shutdown/restart: PC herunterfahren/neustarten (delay=30) ⚠️ Bestätigung

[Browser-Automation]
- youtube_search: YouTube durchsuchen (query="Lofi Beats")
- youtube_play: YouTube-Video abspielen (query="Lofi Beats")
- web_open: URL in Playwright öffnen (url="https://...")
- web_screenshot: Website als Screenshot (url="...", filename="test.png")
- web_pdf: Website als PDF speichern (url="...")
- web_scrape: Text von Website extrahieren (url="...")
- price_check: Preis auf Produktseite prüfen (url="...", selector=".price")
- browser_close: Playwright-Browser schließen

[Datei-Tools]
- find_duplicates: Doppelte Dateien finden (search_path="C:/Users") ⚠️ Bestätigung
- batch_rename: Dateien umbenennen (folder="...", prefix/suffix/replace_from/replace_to) ⚠️ Bestätigung
- organize_downloads: Downloads-Ordner sortieren (downloads_path="...") ⚠️ Bestätigung
- merge_pdfs: PDFs zusammenfügen (pdf_paths=["a.pdf","b.pdf"]) ⚠️ Bestätigung
- split_pdf: PDF aufteilen (pdf_path="...", pages="1-3,5") ⚠️ Bestätigung
- disk_analysis: Speicheranalyse (path="C:/Users")
- clean_temp: Temporäre Dateien löschen ⚠️ Bestätigung

[Media]
- media_play_pause: Wiedergabe starten/pausieren
- media_next: Nächster Track
- media_prev: Vorheriger Track
- media_stop: Wiedergabe stoppen
- spotify_open: Spotify öffnen + optional suchen (search="Artist Name")
- convert_media: Medien konvertieren (input_path="video.mp4", format="mp3")
- extract_audio: Audio aus Video extrahieren (video_path="video.mp4")
- screen_record: Bildschirmaufnahme (duration=10)

[Kommunikation]
- email_send: E-Mail senden (to="empfänger@...", subject="Betreff", body="Text") ⚠️ Bestätigung
- email_read: E-Mails lesen (count=5, folder="INBOX")
- telegram_send: Telegram-Nachricht senden (message="...") ⚠️ Bestätigung
- telegram_read: Telegram-Nachrichten lesen (count=5)
- discord_send: Discord-Nachricht senden (message="...") ⚠️ Bestätigung

[Gedächtnis & Notizen]
- note_create: Notiz erstellen (title="...", content="...")
- note_read: Notiz lesen (title="...")
- note_list: Alle Notizen auflisten
- note_delete: Notiz löschen (title="...") ⚠️ Bestätigung
- memory_search: Gedächtnis durchsuchen (query="...")
- summarize: Text zusammenfassen (text="..." oder url="...")

AKTIONS-FORMAT — Wenn du eine Aktion ausführen sollst:
{"action": "command_name", "params": {"key": "value"}, "message": "Was du dem User sagst"}

REGELN:
- Wenn du nur redest (keine Aktion nötig): antworte als normaler Text
- Sei KURZ. Max 2-3 Sätze wenn nicht anders nötig
- Bei Aktionen: IMMER das JSON-Format nutzen, KEIN Markdown drum herum
- Bei gefährlichen Aktionen (shutdown, process_kill): warne kurz in der "message"
- Wenn dir GEDÄCHTNIS-KONTEXT mitgegeben wird, nutze ihn für bessere Antworten
"""


# ══════════════════════════════════════════════════
#  GROQ (PRIMARY)
# ══════════════════════════════════════════════════

def _get_groq_client():
    from groq import Groq
    api_key = keyring.get_password("lexa-ai", "groq_api_key")
    if not api_key:
        return None
    return Groq(api_key=api_key)


def _chat_groq(messages: list[dict]) -> str | None:
    """Try Groq API first."""
    try:
        client = _get_groq_client()
        if not client:
            return None
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        reply = response.choices[0].message.content
        logger.info(f"Groq response ({len(reply)} chars)")
        return reply
    except Exception as e:
        logger.warning(f"Groq failed: {e}")
        return None


# ══════════════════════════════════════════════════
#  OLLAMA (LOCAL FALLBACK)
# ══════════════════════════════════════════════════

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "llama3.1:8b"  # Default, can be changed


def check_ollama() -> dict:
    """Check if Ollama is running and which models are available."""
    global _ollama_available
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            _ollama_available = True
            return {"available": True, "models": models}
    except Exception:
        pass
    _ollama_available = False
    return {"available": False, "models": []}


def _chat_ollama(messages: list[dict]) -> str | None:
    """Fallback to local Ollama."""
    global _ollama_available
    if _ollama_available is False:
        return None

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 1024},
            },
            timeout=60,
        )
        if resp.status_code == 200:
            reply = resp.json().get("message", {}).get("content", "")
            logger.info(f"Ollama response ({len(reply)} chars)")
            _ollama_available = True
            return reply
    except Exception as e:
        logger.warning(f"Ollama failed: {e}")
        _ollama_available = False
    return None


# ══════════════════════════════════════════════════
#  MAIN CHAT (with memory context)
# ══════════════════════════════════════════════════

def chat(user_message: str, conversation_history: list | None = None) -> str:
    """Send message through Groq → Ollama fallback chain, with memory context."""

    # Build system prompt with memory context
    system_content = SYSTEM_PROMPT

    # Inject relevant memory context if available
    try:
        from backend.memory import search_memory, get_user_profile
        memory_results = search_memory(user_message, limit=3)
        profile = get_user_profile()

        context_parts = []
        if profile:
            context_parts.append(f"USER-PROFIL: {profile}")
        if memory_results:
            mem_text = "\n".join(
                f"- [{m['category']}] {m['content']}" for m in memory_results
            )
            context_parts.append(f"RELEVANTES GEDÄCHTNIS:\n{mem_text}")

        if context_parts:
            system_content += "\n\n" + "\n".join(context_parts)
    except Exception as e:
        logger.debug(f"Memory context skipped: {e}")

    messages = [{"role": "system", "content": system_content}]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": user_message})

    # Try Groq first, then Ollama
    reply = _chat_groq(messages)
    if reply:
        _save_interaction(user_message, reply)
        return reply

    logger.info("Groq unavailable, trying Ollama...")
    reply = _chat_ollama(messages)
    if reply:
        _save_interaction(user_message, reply)
        return reply

    return "Sowohl Groq als auch Ollama sind gerade nicht erreichbar. Bitte prüfe deine Internetverbindung oder starte Ollama."


def _save_interaction(user_msg: str, ai_reply: str):
    """Save interaction to memory for future context."""
    try:
        from backend.memory import auto_remember
        auto_remember(user_msg, ai_reply)
    except Exception:
        pass


def get_ai_status() -> dict:
    """Get status of all AI providers."""
    groq_ok = False
    try:
        client = _get_groq_client()
        if client:
            groq_ok = True
    except Exception:
        pass

    ollama = check_ollama()

    return {
        "groq": {"available": groq_ok},
        "ollama": ollama,
        "active_provider": "groq" if groq_ok else ("ollama" if ollama["available"] else "none"),
    }
