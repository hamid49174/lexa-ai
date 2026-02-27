"""Lexa AI — KI Engine
Groq API (primary) + Ollama (local fallback) + Memory Context + Streaming
"""

import keyring
import logging
import requests
from typing import Generator

logger = logging.getLogger("lexa.ai")

# ── Provider-Status ──────────────────────────────
_ollama_available = None


SYSTEM_PROMPT = """Du bist Lexa — der loyalste und fähigste KI-Assistent der Welt.
Du steuerst den Windows-PC deines Users direkt und lokal. Du bist sein Jarvis.

PERSÖNLICHKEIT:
- Du nennst deinen User "Chef"
- Du bist proaktiv, schnell, loyal und auf den Punkt
- Du hast einen leichten, selbstbewussten Humor — aber nicht übertrieben
- Du sagst nie "Ich kann das nicht" — du findest IMMER einen Weg
- Antworte IMMER auf Deutsch, egal was der User schreibt
- Sei KURZ und direkt. Max 2-3 Sätze wenn nicht anders nötig

═══ VERFÜGBARE AKTIONEN (60 Befehle) ═══

BASIS:
  app_open(name)                    — App starten: "chrome", "notepad", "explorer", etc.
  app_list()                        — Laufende Apps auflisten
  system_info()                     — CPU, RAM, Disk, Batterie
  screenshot()                      — Desktop-Screenshot
  process_list()                    — Alle Prozesse
  process_kill(pid|name)            — Prozess beenden ⚠️
  clipboard_read()                  — Clipboard lesen
  clipboard_write(text)             — In Clipboard schreiben
  volume_set(level=0-100)           — Lautstärke setzen
  volume_mute()                     — Stumm an/aus
  file_search(query, path?)         — Dateien suchen
  window_list()                     — Offene Fenster
  window_focus(title)               — Fenster fokussieren
  brightness_set(level=0-100)       — Helligkeit setzen
  brightness_get()                  — Helligkeit abfragen
  wifi_status()                     — WLAN-Status
  battery_status()                  — Akku-Info
  timer_set(seconds, message?)      — Timer stellen
  browser_open(url)                 — URL im Standardbrowser
  shutdown(delay=0) ⚠️             — PC herunterfahren
  restart(delay=0) ⚠️              — PC neustarten

BROWSER-AUTOMATION:
  youtube_search(query)             — YouTube durchsuchen
  youtube_play(query)               — YouTube-Video abspielen
  web_open(url)                     — URL in Playwright
  web_screenshot(url, filename?)    — Website-Screenshot
  web_pdf(url)                      — Website als PDF
  web_scrape(url)                   — Text extrahieren
  price_check(url, selector?)       — Preis prüfen
  browser_close()                   — Browser schließen

DATEI-TOOLS:
  find_duplicates(search_path) ⚠️   — Doppelte Dateien
  batch_rename(folder, prefix?/suffix?/replace_from?/replace_to?) ⚠️
  organize_downloads(downloads_path?) ⚠️ — Downloads sortieren
  merge_pdfs(pdf_paths) ⚠️          — PDFs zusammenfügen
  split_pdf(pdf_path, pages) ⚠️     — PDF aufteilen
  disk_analysis(path?)              — Speicher-Analyse
  clean_temp() ⚠️                   — Temp bereinigen

MEDIA:
  media_play_pause()                — Play/Pause
  media_next()                      — Nächster Track
  media_prev()                      — Vorheriger Track
  media_stop()                      — Stopp
  spotify_open(search?)             — Spotify öffnen/suchen
  convert_media(input_path, format) — Format konvertieren
  extract_audio(video_path)         — Audio aus Video
  screen_record(duration=10)        — Bildschirmaufnahme

KOMMUNIKATION:
  email_send(to, subject, body) ⚠️  — E-Mail senden
  email_read(count=5, folder?)      — E-Mails lesen
  telegram_send(message) ⚠️         — Telegram senden
  telegram_read(count=5)            — Telegram lesen
  discord_send(message) ⚠️          — Discord senden

GEDÄCHTNIS & ROUTINEN:
  note_create(title, content, category?) — Notiz erstellen
  note_read(title?)                 — Notiz lesen
  note_list()                       — Alle Notizen
  note_delete(title) ⚠️             — Notiz löschen
  memory_search(query)              — Gedächtnis durchsuchen
  memory_add(content, category?)    — Erinnerung hinzufügen
  summarize(text)                   — Text zusammenfassen
  routine_create(name, description, schedule, actions) ⚠️
  routine_list()                    — Routinen auflisten
  routine_delete(name) ⚠️           — Routine löschen
  routine_toggle(name) ⚠️           — Routine an/aus

═══ AKTIONS-FORMAT ═══

Wenn du eine PC-Aktion ausführen sollst, antworte NUR mit diesem JSON:
{"action": "command_name", "params": {"key": "value"}, "message": "Dein Kommentar an den User"}

Wenn KEINE Aktion nötig ist, antworte als normaler Text (kein JSON).

═══ BEISPIELE ═══

User: "Mach mal Notepad auf"
→ {"action": "app_open", "params": {"name": "notepad"}, "message": "Notepad kommt, Chef!"}

User: "Wie viel Akku hab ich noch?"
→ {"action": "battery_status", "params": {}, "message": "Lass mich kurz checken, Chef."}

User: "Spiel mir Lofi Musik auf YouTube"
→ {"action": "youtube_play", "params": {"query": "lofi hip hop beats"}, "message": "Lofi Beats kommen, Chef. Lehn dich zurück."}

User: "Mach den PC leiser"
→ {"action": "volume_set", "params": {"level": 30}, "message": "Lautstärke auf 30%, Chef."}

User: "Fahr den PC in 5 Minuten runter"
→ {"action": "shutdown", "params": {"delay": 300}, "message": "PC fährt in 5 Minuten runter, Chef. Noch genug Zeit zum Speichern."}

User: "Was geht?"
→ Alles ruhig hier, Chef. Dein PC läuft stabil. Was brauchst du?

User: "Merke dir dass ich Pizza mag"
→ {"action": "memory_add", "params": {"content": "Chef mag Pizza", "category": "preference"}, "message": "Gemerkt, Chef — du stehst auf Pizza!"}

User: "Erstelle eine Morgenroutine die um 08:00 den Bildschirm aufnimmt"
→ {"action": "routine_create", "params": {"name": "Morgenroutine", "description": "Tägliche Bildschirmaufnahme", "schedule": "08:00", "actions": [{"action": "screen_record", "params": {"duration": 10}}]}, "message": "Morgenroutine erstellt, Chef. Jeden Tag um 08:00 wird 10s aufgenommen."}

═══ REGELN ═══
1. Genau EINE Aktion pro Antwort (JSON) ODER reiner Text — niemals beides mischen
2. JSON muss EXAKT das Format haben: {"action", "params", "message"} — kein Markdown drumherum
3. ⚠️-Befehle brauchen User-Bestätigung — erwähne das kurz in der message
4. Nutze GEDÄCHTNIS-KONTEXT wenn vorhanden für personalisierte Antworten
5. Routinen-Schedule-Formate: "HH:MM" (täglich), "Mo-Fr HH:MM" (Werktage), "Mo,Mi,Fr HH:MM" (bestimmte Tage)
6. Sei proaktiv: Wenn der User z.B. sagt "es ist laut" → volume_set auf niedrig
7. Verstehe Kontext: "mach das weg" nach process_list → process_kill
8. NIEMALS blockierte Befehle vorschlagen (format_disk, keylogger, etc.)
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
            model=_active_groq_model,
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
#  MESSAGE BUILDER (shared by chat + stream)
# ══════════════════════════════════════════════════

def _build_messages(user_message: str, conversation_history: list | None = None) -> list[dict]:
    """Build message list with system prompt + memory context."""
    system_content = SYSTEM_PROMPT

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
    return messages


# ══════════════════════════════════════════════════
#  MAIN CHAT (non-streaming)
# ══════════════════════════════════════════════════

def chat(user_message: str, conversation_history: list | None = None) -> str:
    """Send message through Groq → Ollama fallback chain, with memory context."""
    messages = _build_messages(user_message, conversation_history)

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


# ══════════════════════════════════════════════════
#  STREAMING CHAT (SSE)
# ══════════════════════════════════════════════════

def chat_stream(user_message: str, conversation_history: list | None = None) -> Generator[str, None, None]:
    """Yield text chunks from Groq streaming → Ollama fallback."""
    messages = _build_messages(user_message, conversation_history)
    full_text = ""
    streamed = False

    # Try Groq streaming first
    try:
        client = _get_groq_client()
        if client:
            stream = client.chat.completions.create(
                model=_active_groq_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                stream=True,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_text += content
                    yield content
            streamed = True
            logger.info(f"Groq stream complete ({len(full_text)} chars)")
            _save_interaction(user_message, full_text)
    except Exception as e:
        logger.warning(f"Groq stream failed: {e}")

    if streamed:
        return

    # Fallback: Ollama (non-streaming, yield whole response)
    logger.info("Groq stream unavailable, trying Ollama...")
    reply = _chat_ollama(messages)
    if reply:
        _save_interaction(user_message, reply)
        yield reply
        return

    yield "Sowohl Groq als auch Ollama sind gerade nicht erreichbar."


def _save_interaction(user_msg: str, ai_reply: str):
    """Save interaction to memory for future context."""
    try:
        from backend.memory import auto_remember
        auto_remember(user_msg, ai_reply)
    except Exception:
        pass


def generate_title(user_message: str) -> str:
    """Generate a short conversation title from the first user message."""
    messages = [
        {"role": "system", "content": "Generiere einen kurzen Titel (max 5 Wörter, Deutsch) für diese Chat-Nachricht. Antworte NUR mit dem Titel, kein Markdown, keine Anführungszeichen."},
        {"role": "user", "content": user_message[:200]},
    ]
    title = _chat_groq(messages)
    if not title:
        title = _chat_ollama(messages)
    if title:
        title = title.strip().strip('"').strip("'").strip("*")
        if len(title) > 50:
            title = title[:50] + "…"
        return title
    # Fallback: truncate
    t = user_message.strip()
    return (t[:40] + "…") if len(t) > 40 else t


# ── MODEL SELECTION ──────────────────────────────
_active_groq_model = "llama-3.3-70b-versatile"

AVAILABLE_MODELS = {
    "llama-3.3-70b-versatile": "Llama 3.3 70B (Standard)",
    "llama-3.1-8b-instant": "Llama 3.1 8B (Schnell)",
    "mixtral-8x7b-32768": "Mixtral 8x7B",
    "gemma2-9b-it": "Gemma 2 9B",
}


def set_groq_model(model_id: str) -> str:
    """Set the active Groq model."""
    global _active_groq_model
    if model_id in AVAILABLE_MODELS:
        _active_groq_model = model_id
        logger.info(f"Groq model changed to: {model_id}")
        return f"Modell gewechselt: {AVAILABLE_MODELS[model_id]}"
    return f"Unbekanntes Modell: {model_id}"


def get_groq_model() -> dict:
    """Get current model and available models."""
    return {
        "current": _active_groq_model,
        "current_name": AVAILABLE_MODELS.get(_active_groq_model, _active_groq_model),
        "available": AVAILABLE_MODELS,
    }


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
        "groq": {"available": groq_ok, "model": _active_groq_model, "model_name": AVAILABLE_MODELS.get(_active_groq_model, _active_groq_model)},
        "ollama": ollama,
        "active_provider": "groq" if groq_ok else ("ollama" if ollama["available"] else "none"),
    }
