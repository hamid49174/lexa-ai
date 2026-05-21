"""Lexa AI — Tool Registry (Phase 40)
Central registry of all 138+ companion commands as native LLM tool definitions.
Supports: Groq, OpenAI, Gemini (all use OpenAI-compatible function calling format).

Instead of listing commands in the system prompt and hoping the LLM produces
correct JSON, we register each command as a typed tool definition. The LLM
provider validates parameters automatically — no more JSON-parsing hacks.
"""

import logging
from typing import Any

logger = logging.getLogger("lexa.tool_registry")

# ── Storage ──
TOOL_DEFINITIONS: list[dict] = []
_TOOL_MAP: dict[str, dict] = {}  # name -> full tool definition
_DANGEROUS_ARGUMENT_KEYS: frozenset[str] = frozenset({
    "__proto__",
    "constructor",
    "prototype",
})


class ToolSchemaValidationError(ValueError):
    """Raised when LLM-supplied tool arguments do not match registry schema."""


# ══════════════════════════════════════════════════
#  BUILDER HELPERS
# ══════════════════════════════════════════════════

def _param(
    name: str,
    type_: str,
    description: str,
    required: bool = False,
    enum: list[str] | None = None,
    default: Any = None,
    items_type: str | None = None,
) -> dict:
    """Build a JSON-Schema parameter descriptor."""
    schema: dict[str, Any] = {"type": type_, "description": description}
    if enum:
        schema["enum"] = enum
    if default is not None:
        schema["default"] = default
    if type_ == "array" and items_type:
        schema["items"] = {"type": items_type}
    return {"name": name, "schema": schema, "required": required}


def _tool(
    name: str,
    description: str,
    params: list[dict] | None = None,
    confirmation_required: bool = False,
) -> dict:
    """Build a complete tool definition in OpenAI function-calling format."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in (params or []):
        properties[p["name"]] = p["schema"]
        if p.get("required"):
            required.append(p["name"])

    desc = description
    if confirmation_required:
        desc += " ⚠️ Braucht User-Bestätigung."

    tool_def = {
        "type": "function",
        "confirmation_required": bool(confirmation_required),
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": properties,
            },
        },
    }
    if required:
        tool_def["function"]["parameters"]["required"] = required
    return tool_def


# ══════════════════════════════════════════════════
#  TOOL REGISTRATION
# ══════════════════════════════════════════════════

def _register_basis_tools() -> list[dict]:
    """Basis-Tools (22): Apps, System, Clipboard, Volume, etc."""
    return [
        _tool("app_open", "Startet eine beliebige Anwendung auf dem PC. Erkennt automatisch installierte Programme per Smart Discovery mit Fuzzy-Matching. Funktioniert mit deutschen und englischen Namen, Abkürzungen und Spitznamen (z.B. 'chrome', 'vscode', 'rechner', 'word', 'spotify', 'discord', 'steam', 'einstellungen'). Kann jede installierte App finden und öffnen.", [
            _param("name", "string", "Name der App — deutsch oder englisch, auch Abkürzungen (z.B. 'chrome', 'vscode', 'word', 'rechner', 'spotify', 'terminal', 'discord', 'steam', 'obs', 'vlc')", required=True),
            _param("path", "string", "Optionaler direkter Pfad zur .exe Datei (nur wenn Name nicht reicht)"),
        ]),
        _tool("app_search", "Sucht nach installierten Apps auf dem PC — zeigt die besten Treffer per Fuzzy-Matching", [
            _param("query", "string", "Suchbegriff (Name oder Teil davon)", required=True),
        ]),
        _tool("app_list_installed", "Listet alle auf dem PC installierten Programme auf (aus Start Menu, Registry, PATH)", [
            _param("limit", "integer", "Max. Anzahl der Ergebnisse (Standard: 50)"),
        ]),
        _tool("app_list", "Listet alle aktuell laufenden Anwendungen/Prozesse auf mit CPU- und RAM-Verbrauch"),
        _tool("system_info", "Zeigt CPU, RAM, Disk und Batterie Informationen"),
        _tool("screenshot", "Erstellt einen Screenshot des Desktops"),
        _tool("process_list", "Listet alle laufenden Prozesse auf"),
        _tool("process_kill", "Beendet einen Prozess anhand PID oder Name", [
            _param("pid", "integer", "Prozess-ID"),
            _param("name", "string", "Prozessname"),
        ], confirmation_required=True),
        _tool("clipboard_read", "Liest den aktuellen Inhalt der Zwischenablage"),
        _tool("clipboard_write", "Schreibt Text in die Zwischenablage", [
            _param("text", "string", "Text der in die Zwischenablage geschrieben wird", required=True),
        ]),
        _tool("volume_set", "Setzt die System-Lautstärke auf einen bestimmten Prozentsatz (präzise via Windows Core Audio API)", [
            _param("level", "integer", "Lautstärke von 0 bis 100", required=True),
        ]),
        _tool("volume_mute", "Schaltet den Ton stumm oder wieder an (mit Statusmeldung ob stumm/laut)"),
        _tool("file_search", "Sucht Dateien auf dem PC — nutzt Windows Search Index (sofortige Ergebnisse) mit os.walk Fallback", [
            _param("query", "string", "Suchbegriff oder Dateiname", required=True),
            _param("path", "string", "Suchpfad — wenn nicht angegeben wird im Home-Verzeichnis gesucht"),
            _param("extension", "string", "Dateiendung-Filter z.B. '.pdf', '.docx', '.jpg'"),
            _param("max_results", "integer", "Max. Anzahl Ergebnisse (Standard: 50, Max: 100)"),
        ]),
        _tool("window_list", "Listet alle offenen Fenster mit Titel und PID (instant via ctypes, kein PowerShell)"),
        _tool("window_focus", "Bringt ein bestimmtes Fenster in den Vordergrund", [
            _param("title", "string", "Fenstertitel oder Teil davon", required=True),
        ]),
        _tool("brightness_set", "Setzt die Bildschirmhelligkeit (Laptop/DDC-CI Monitor). Gibt klare Fehlermeldung wenn nicht verfügbar.", [
            _param("level", "integer", "Helligkeit von 0 bis 100", required=True),
        ]),
        _tool("brightness_get", "Fragt die aktuelle Bildschirmhelligkeit ab (mit Hardware-Erkennung)"),
        _tool("wifi_status", "Zeigt WLAN/Netzwerk-Status: SSID, Signalstärke, IP, Geschwindigkeit, Verbindungstyp"),
        _tool("battery_status", "Zeigt Akku-Stand, Ladestatus und geschätzte Restlaufzeit"),
        _tool("timer_set", "Stellt einen Timer der nach Ablauf benachrichtigt", [
            _param("seconds", "integer", "Timer-Dauer in Sekunden", required=True),
            _param("message", "string", "Nachricht die bei Timer-Ablauf angezeigt wird"),
        ]),
        _tool("browser_open", "Öffnet eine URL im Standardbrowser", [
            _param("url", "string", "Die zu öffnende URL", required=True),
        ]),
        _tool("shutdown", "Fährt den PC herunter", [
            _param("delay", "integer", "Verzögerung in Sekunden vor dem Herunterfahren (Standard: 0)"),
        ], confirmation_required=True),
        _tool("restart", "Startet den PC neu", [
            _param("delay", "integer", "Verzögerung in Sekunden vor dem Neustart (Standard: 0)"),
        ], confirmation_required=True),
    ]


def _register_browser_tools() -> list[dict]:
    """Browser-Automation (8): YouTube, Web, Scraping."""
    return [
        _tool("youtube_search", "Durchsucht YouTube nach Videos", [
            _param("query", "string", "Suchbegriff", required=True),
        ]),
        _tool("youtube_play", "Spielt ein YouTube-Video ab", [
            _param("query", "string", "Video-Suchbegriff oder YouTube-URL", required=True),
        ]),
        _tool("web_open", "Oeffnet eine URL im automatisierten Browser (Playwright). Nur fuer explizite Browser-Automation nutzen; fuer normales Oeffnen oder Google-Suche browser_open verwenden.", [
            _param("url", "string", "URL der Website", required=True),
        ]),
        _tool("web_screenshot", "Erstellt einen Screenshot einer Website", [
            _param("url", "string", "URL der Website", required=True),
            _param("filename", "string", "Dateiname für den Screenshot"),
        ]),
        _tool("web_pdf", "Speichert eine Website als PDF-Datei", [
            _param("url", "string", "URL der Website", required=True),
        ]),
        _tool("web_scrape", "Extrahiert den Haupttext einer Website — 3 Strategien: trafilatura (schnell, kein Browser), Mozilla Readability.js (wie Firefox Reader Mode), DOM-Scoring (Fallback). Erkennt Titel, Autor, Datum automatisch.", [
            _param("url", "string", "URL der Website", required=True),
            _param("max_chars", "integer", "Max. Zeichenanzahl (Standard: 5000, Max: 50000)"),
            _param("use_browser", "boolean", "Browser erzwingen für JS-gerenderte Seiten (SPAs)"),
        ]),
        _tool("price_check", "Erkennt Preise auf jeder Shop-Seite weltweit (JSON-LD, Meta-Tags, CSS, Regex-Scan)", [
            _param("url", "string", "URL der Produktseite", required=True),
            _param("selector", "string", "Optionaler CSS-Selector für das Preis-Element"),
        ]),
        _tool("browser_close", "Schließt den automatisierten Browser"),
    ]


def _register_file_tools() -> list[dict]:
    """Datei-Tools (19): Archive, Backup, Bilder, PDF."""
    return [
        _tool("find_duplicates", "Findet doppelte Dateien mit 3-Phasen-Hashing (Size → Quick-Hash → Full SHA-256, keine False Positives)", [
            _param("search_path", "string", "Pfad zum Durchsuchen", required=True),
            _param("max_files", "integer", "Max. Dateien zum Scannen (Standard: 1000, Max: 10000)"),
        ], confirmation_required=True),
        _tool("batch_rename", "Benennt mehrere Dateien nach einem Muster um", [
            _param("folder", "string", "Ordner-Pfad", required=True),
            _param("pattern", "string", "Suchmuster (Regex oder Wildcard)", required=True),
            _param("replacement", "string", "Ersetzungstext", required=True),
        ], confirmation_required=True),
        _tool("organize_downloads", "Sortiert den Downloads-Ordner nach Dateitypen", [
            _param("path", "string", "Pfad zum Downloads-Ordner (Standard: ~/Downloads)"),
        ], confirmation_required=True),
        _tool("merge_pdfs", "Fügt mehrere PDF-Dateien zu einer zusammen", [
            _param("pdf_paths", "array", "Liste der PDF-Dateipfade", required=True, items_type="string"),
        ], confirmation_required=True),
        _tool("split_pdf", "Teilt eine PDF-Datei nach Seitenangabe auf", [
            _param("pdf_path", "string", "Pfad zur PDF-Datei", required=True),
            _param("pages", "string", "Seitenangabe z.B. '1-3,5,7-9'", required=True),
        ], confirmation_required=True),
        _tool("disk_analysis", "Analysiert den Speicherverbrauch eines Verzeichnisses (mit Timeout-Schutz)", [
            _param("path", "string", "Pfad zum Analysieren (Standard: Home-Verzeichnis)"),
            _param("timeout_sec", "integer", "Timeout in Sekunden (Standard: 30)"),
        ]),
        _tool("clean_temp", "Bereinigt temporäre Dateien und Caches (mit Bericht über gesperrte/fehlgeschlagene Dateien)", [], confirmation_required=True),
        _tool("archive_create", "Erstellt ein ZIP-Archiv aus Dateien oder Ordnern", [
            _param("path", "string", "Quellpfad (Datei oder Ordner)", required=True),
            _param("format", "string", "Archiv-Format", enum=["zip", "7z", "tar"]),
        ], confirmation_required=True),
        _tool("archive_extract", "Entpackt ein Archiv (ZIP, 7z, TAR, RAR)", [
            _param("path", "string", "Pfad zum Archiv", required=True),
            _param("dest", "string", "Zielverzeichnis (optional)"),
        ], confirmation_required=True),
        _tool("archive_list", "Zeigt den Inhalt eines Archivs an ohne zu entpacken", [
            _param("path", "string", "Pfad zum Archiv", required=True),
        ]),
        _tool("backup_create", "Erstellt ein Backup als ZIP-Datei mit Zeitstempel", [
            _param("source", "string", "Quellpfad zum Sichern", required=True),
            _param("dest", "string", "Zielverzeichnis für das Backup"),
        ], confirmation_required=True),
        _tool("backup_list", "Listet vorhandene Backups auf", [
            _param("dest", "string", "Backup-Verzeichnis (optional)"),
        ]),
        _tool("backup_restore", "Stellt ein Backup wieder her", [
            _param("backup_path", "string", "Pfad zur Backup-Datei", required=True),
        ], confirmation_required=True),
        _tool("image_convert", "Konvertiert ein Bild in ein anderes Format", [
            _param("path", "string", "Pfad zum Quellbild", required=True),
            _param("format", "string", "Zielformat", required=True, enum=["png", "jpg", "webp", "bmp", "gif"]),
        ]),
        _tool("image_resize", "Ändert die Größe eines Bildes", [
            _param("path", "string", "Pfad zum Bild", required=True),
            _param("width", "integer", "Neue Breite in Pixeln", required=True),
            _param("height", "integer", "Neue Höhe in Pixeln (optional — behält Seitenverhältnis bei)"),
        ]),
        _tool("image_batch_resize", "Ändert die Größe aller Bilder in einem Ordner", [
            _param("folder", "string", "Ordner mit den Bildern", required=True),
            _param("width", "integer", "Neue Breite in Pixeln", required=True),
            _param("height", "integer", "Neue Höhe in Pixeln (optional)"),
        ], confirmation_required=True),
        _tool("image_info", "Zeigt Informationen zu einem Bild (Größe, Format, DPI)", [
            _param("path", "string", "Pfad zum Bild", required=True),
        ]),
        _tool("file_info", "Zeigt Details zu einer Datei (Größe, Typ, Erstelldatum)", [
            _param("path", "string", "Dateipfad", required=True),
        ]),
        _tool("folder_size", "Berechnet die Gesamtgröße eines Ordners", [
            _param("path", "string", "Ordner-Pfad", required=True),
        ]),
        _tool("file_move", "Verschiebt eine Datei oder einen Ordner von Quelle nach Ziel", [
            _param("source", "string", "Quellpfad (Datei oder Ordner)", required=True),
            _param("destination", "string", "Zielpfad oder Zielordner", required=True),
        ], confirmation_required=True),
        _tool("file_copy", "Kopiert eine Datei oder einen Ordner (rekursiv bei Ordnern)", [
            _param("source", "string", "Quellpfad (Datei oder Ordner)", required=True),
            _param("destination", "string", "Zielpfad oder Zielordner", required=True),
        ], confirmation_required=True),
        _tool("file_delete", "Löscht eine Datei oder einen leeren Ordner (kein rekursives Löschen)", [
            _param("path", "string", "Pfad zur Datei oder zum leeren Ordner", required=True),
        ], confirmation_required=True),
        _tool("file_open", "Öffnet eine Datei mit der Standard-Anwendung (blockiert .exe/.bat/.cmd/.ps1/.vbs)", [
            _param("path", "string", "Pfad zur Datei", required=True),
        ]),
        _tool("file_recent_downloads", "Listet die neuesten Dateien im Downloads-Ordner auf", [
            _param("count", "integer", "Anzahl der Dateien (Standard: 5, Max: 50)"),
        ]),
        _tool("folder_create", "Erstellt einen neuen Ordner (inkl. übergeordneter Ordner falls nötig)", [
            _param("path", "string", "Pfad des neuen Ordners", required=True),
        ]),
    ]


def _register_media_tools() -> list[dict]:
    """Media-Tools (8): Playback, Spotify, Konvertierung, Aufnahme."""
    return [
        _tool("media_play_pause", "Spielt Medien ab oder pausiert die Wiedergabe (funktioniert mit jedem Player: Spotify, VLC, YouTube, etc.)"),
        _tool("media_next", "Springt zum nächsten Track/Song (OS-Level, funktioniert mit jedem Player)"),
        _tool("media_prev", "Springt zum vorherigen Track/Song (OS-Level, funktioniert mit jedem Player)"),
        _tool("media_stop", "Stoppt die Medienwiedergabe komplett (OS-Level, funktioniert mit jedem Player)"),
        _tool("spotify_open", "Öffnet Spotify und spielt Musik ab — funktioniert sofort ohne Konfiguration. Nutze IMMER den search-Parameter wenn der User einen Song, Künstler oder Playlist hören will. Beispiel: User sagt 'spiel Mero' → search='Mero'. Spotify wird geöffnet, der Song/Künstler gesucht und automatisch abgespielt.", [
            _param("search", "string", "Song-Name, Künstler oder Playlist — z.B. 'Mero', 'Blinding Lights', 'Chill Playlist'"),
            _param("auto_play", "boolean", "Automatisch abspielen nach Suche (Standard: true)"),
        ]),
        _tool("convert_media", "Konvertiert eine Mediendatei in ein anderes Format", [
            _param("path", "string", "Pfad zur Quelldatei", required=True),
            _param("format", "string", "Zielformat (mp3, mp4, wav, ogg, flac, avi, mkv)", required=True),
        ]),
        _tool("extract_audio", "Extrahiert die Audiospur aus einer Videodatei", [
            _param("video_path", "string", "Pfad zur Videodatei", required=True),
        ]),
        _tool("screen_record", "Nimmt den Bildschirm als Video auf", [
            _param("duration", "integer", "Aufnahmedauer in Sekunden (Standard: 10, Max: 3600)"),
        ]),
    ]


def _register_communication_tools() -> list[dict]:
    """Kommunikation (7): E-Mail (send/read/search/summarize), Telegram, Discord."""
    return [
        _tool("email_send", "Sendet eine E-Mail — unterstützt alle Anbieter: Gmail, Outlook, Yahoo, GMX, web.de, iCloud, Protonmail, etc. Provider wird automatisch aus der E-Mail-Adresse erkannt. Optional mit Dateianhang (max 25MB).", [
            _param("to", "string", "Empfänger E-Mail-Adresse", required=True),
            _param("subject", "string", "Betreff der E-Mail", required=True),
            _param("body", "string", "Nachrichtentext", required=True),
            _param("attachment_path", "string", "Optionaler Pfad zu einer Datei als Anhang (max 25MB, keine .exe/.bat etc.)"),
        ], confirmation_required=True),
        _tool("email_read", "Liest die neuesten E-Mails aus dem Posteingang (alle Provider: Gmail, Outlook, Yahoo, GMX, etc.). Kann nach ungelesenen oder nach Absender filtern.", [
            _param("count", "integer", "Anzahl der zu lesenden E-Mails (Standard: 10, max 50)"),
            _param("folder", "string", "E-Mail-Ordner (Standard: INBOX)"),
            _param("unread_only", "boolean", "Nur ungelesene E-Mails anzeigen (Standard: false)"),
            _param("sender", "string", "Filter nach Absender (E-Mail-Adresse oder Name, teilweise Übereinstimmung)"),
        ]),
        _tool("email_search", "Durchsucht E-Mails nach Stichworten in Betreff und Inhalt. Unterstützt Zeitraum- und Absender-Filter.", [
            _param("query", "string", "Suchbegriff (wird in Betreff und Inhalt gesucht)", required=True),
            _param("sender", "string", "Optionaler Absender-Filter"),
            _param("days", "integer", "Zeitraum in Tagen (Standard: 7, max 365)"),
        ]),
        _tool("email_summarize", "Liest die letzten ungelesenen E-Mails und gibt strukturierte Daten zurück, die für eine Zusammenfassung genutzt werden können.", [
            _param("count", "integer", "Anzahl ungelesener E-Mails zum Zusammenfassen (Standard: 5, max 20)"),
        ]),
        _tool("telegram_send", "Sendet eine Nachricht über Telegram", [
            _param("message", "string", "Nachrichtentext", required=True),
        ], confirmation_required=True),
        _tool("telegram_read", "Liest neue Telegram-Nachrichten (mit Offset-Tracking, keine Duplikate zwischen Aufrufen)", [
            _param("count", "integer", "Anzahl der zu lesenden Nachrichten (Standard: 5)"),
        ]),
        _tool("discord_send", "Sendet eine Nachricht über Discord Webhook", [
            _param("message", "string", "Nachrichtentext", required=True),
        ], confirmation_required=True),
    ]


def _register_memory_tools() -> list[dict]:
    """Gedächtnis & Routinen (11): Notes, Memory, Routines."""
    return [
        _tool("note_create", "Erstellt eine neue Notiz", [
            _param("title", "string", "Titel der Notiz", required=True),
            _param("content", "string", "Inhalt der Notiz", required=True),
            _param("category", "string", "Kategorie (z.B. 'arbeit', 'privat', 'idee')"),
        ]),
        _tool("note_read", "Liest den Inhalt einer bestimmten Notiz", [
            _param("title", "string", "Titel der gesuchten Notiz"),
        ]),
        _tool("note_list", "Listet alle gespeicherten Notizen auf"),
        _tool("note_delete", "Löscht eine Notiz permanent", [
            _param("title", "string", "Titel der zu löschenden Notiz", required=True),
        ], confirmation_required=True),
        _tool("memory_search", "Durchsucht das Langzeitgedächtnis nach relevanten Einträgen", [
            _param("query", "string", "Suchbegriff oder Frage", required=True),
        ]),
        _tool("memory_add", "Speichert eine neue Erinnerung im Langzeitgedächtnis", [
            _param("content", "string", "Inhalt der Erinnerung", required=True),
            _param("category", "string", "Kategorie: preference, fact, task, person, event"),
        ]),
        _tool("summarize", "Fasst einen langen Text zusammen", [
            _param("text", "string", "Text der zusammengefasst werden soll", required=True),
        ]),
        _tool("routine_create", "Erstellt eine automatische Routine mit Zeitplan", [
            _param("name", "string", "Name der Routine", required=True),
            _param("description", "string", "Beschreibung", required=True),
            _param("schedule", "string", "Zeitplan: 'HH:MM' (täglich), 'Mo-Fr HH:MM', 'Mo,Mi,Fr HH:MM'", required=True),
            _param("actions", "array", "Liste von Aktionen die ausgeführt werden", required=True, items_type="object"),
        ], confirmation_required=True),
        _tool("routine_list", "Listet alle konfigurierten Routinen auf"),
        _tool("routine_delete", "Löscht eine Routine", [
            _param("name", "string", "Name der Routine", required=True),
        ], confirmation_required=True),
        _tool("routine_toggle", "Aktiviert oder deaktiviert eine Routine", [
            _param("name", "string", "Name der Routine", required=True),
        ], confirmation_required=True),
    ]


def _register_personal_os_tools() -> list[dict]:
    """Personal OS read tools routed through the MCP/SDK boundary."""
    return [
        _tool("personal_os_diagnostics", "Prueft read-only den Personal OS MCP/SDK-Zustand, Capabilities und Draft-Queue-Counts.", [
            _param("hideSmoke", "boolean", "Smoke-Test-Drafts ausblenden, Standard: true"),
            _param("maxDrafts", "integer", "Maximale Draft-Anzahl fuer Diagnose-Counts, Standard: 200"),
        ]),
        _tool("personal_os_raw_inbox_status", "Prueft read-only den lokalen Personal OS Raw-Inbox-Worker, verfuegbare Prozessoren und Failure-State."),
        _tool("personal_os_query", "Liest einen Personal OS Area-Index oder sucht Dateien nach exakt passendem Frontmatter-Tag. Read-only.", [
            _param("areaPath", "string", "OS-relativer Bereich, z.B. '00_System' oder '.', Standard: '.'"),
            _param("tag", "string", "Optionaler exakter Tag-Filter, z.B. 'lexa', '#lexa' oder 'tag:lexa'"),
            _param("maxMatches", "integer", "Maximale Trefferanzahl fuer Tag-Suche, Standard: 50"),
        ]),
        _tool("personal_os_read_file", "Liest eine einzelne Personal OS Markdown-Datei ueber MCP und gibt Frontmatter plus Body zurueck. Read-only.", [
            _param("filepath", "string", "OS-relativer Markdown-Pfad, z.B. 'OS_MANIFEST.md'", required=True),
        ]),
        _tool("personal_os_graph", "Erzeugt eine read-only Personal OS Context Map aus Frontmatter, related Links und Tags.", [
            _param("areaPath", "string", "OS-relativer Bereich fuer die Context Map, Standard: '.'"),
            _param("maxFiles", "integer", "Maximale Markdown-Dateien in der Context Map, Standard: 80"),
            _param("includeTags", "boolean", "Tags als Context-Map-Knoten einbeziehen, Standard: true"),
            _param("hideSmoke", "boolean", "Smoke-Test-Artefakte ausblenden, Standard: true"),
        ]),
        _tool("personal_os_context_pack", "Baut ein kompaktes read-only Personal OS Kontextpaket aus Query, begrenzten Datei-Previews und optionaler Context-Map-Summary.", [
            _param("areaPath", "string", "OS-relativer Bereich, z.B. '00_System' oder '.', Standard: '.'"),
            _param("tag", "string", "Optionaler exakter Tag-Filter, z.B. 'lexa'; '#lexa' und 'tag:lexa' werden normalisiert"),
            _param("maxFiles", "integer", "Maximale Dateien im Kontextpaket, Standard: 5"),
            _param("bodyChars", "integer", "Maximale Body-Zeichen pro Datei, Standard: 700"),
            _param("includeGraph", "boolean", "Context-Map-Summary einbeziehen, Standard: true"),
            _param("hideSmoke", "boolean", "Smoke-Test-Artefakte ausblenden, Standard: true"),
        ]),
        _tool("personal_os_obsidian_context", "Baut einen bounded Obsidian-/Personal-OS-Kontext-Bootstrap fuer Lexa und Hermes. Read-only, laedt nie den ganzen Vault.", [
            _param("topic", "string", "Optionaler Fokus, z.B. 'lexa hermes obsidian context'"),
            _param("maxFiles", "integer", "Maximale Bootstrap-Dateien, Standard: 8"),
            _param("bodyChars", "integer", "Maximale Preview-Zeichen pro Datei, Standard: 800"),
            _param("includePreviews", "boolean", "Datei-Previews einbeziehen, Standard: true"),
        ]),
        _tool("personal_os_lexa_code_loop", "Baut einen read-only Personal-OS-Briefing-Prompt fuer den naechsten kleinen Lexa-Code-Verbesserungsschritt.", [
            _param("areaPath", "string", "OS-relativer Bereich fuer Lexa-Kontext, Standard: '00_System'"),
            _param("tag", "string", "Optionaler exakter Tag-Filter, Standard: 'lexa'; '#lexa' und 'tag:lexa' werden normalisiert"),
            _param("maxFiles", "integer", "Maximale Kontextdateien, Standard: 5"),
            _param("bodyChars", "integer", "Maximale Body-Zeichen pro Datei, Standard: 650"),
            _param("includeGraph", "boolean", "Context-Map-Summary einbeziehen, Standard: true"),
            _param("hideSmoke", "boolean", "Smoke-Test-Artefakte ausblenden, Standard: true"),
        ]),
        _tool("personal_os_list_drafts", "Listet Personal OS Review-Drafts ohne volle Bodies. Read-only.", [
            _param("approval", "string", "Filter: pending, approved, rejected, conflict, missing oder all"),
            _param("query", "string", "Optionaler lokaler Filter ueber Titel, Pfad, Approval, Tags, Source und Memory-Level"),
            _param("hideSmoke", "boolean", "Smoke-Test-Drafts ausblenden, Standard: true"),
            _param("maxDrafts", "integer", "Maximale Draft-Anzahl, Standard: 20"),
        ]),
        _tool("personal_os_view_draft", "Liest einen einzelnen Personal OS Draft mit Frontmatter und Body. Read-only. Akzeptiert exakten Draft-Pfad oder eindeutigen Titel-/Pfad-Suchbegriff.", [
            _param("draftPath", "string", "OS-relativer Draft-Pfad unter 06_Inbox/Drafts"),
            _param("query", "string", "Optionaler eindeutiger Draft-Titel oder Pfad-Teil, falls draftPath nicht bekannt ist"),
            _param("hideSmoke", "boolean", "Smoke-Test-Drafts beim Query-Resolve ausblenden, Standard: true"),
        ]),
        _tool("personal_os_review_draft", "Baut ein read-only Review-Packet fuer einen Personal OS Draft mit deterministic Review Assist, Related Context, Audit History und Apply-Hinweis. Akzeptiert exakten Draft-Pfad oder eindeutigen Titel-/Pfad-Suchbegriff.", [
            _param("draftPath", "string", "OS-relativer Draft-Pfad unter 06_Inbox/Drafts"),
            _param("query", "string", "Optionaler eindeutiger Draft-Titel oder Pfad-Teil, falls draftPath nicht bekannt ist"),
            _param("hideSmoke", "boolean", "Smoke-Test-Drafts beim Query-Resolve ausblenden, Standard: true"),
        ]),
        _tool("personal_os_draft_history", "Liest die Audit-History fuer einen einzelnen Personal OS Draft aus dem Event-Log. Read-only. Akzeptiert exakten Draft-Pfad oder eindeutigen Titel-/Pfad-Suchbegriff.", [
            _param("draftPath", "string", "OS-relativer Draft-Pfad unter 06_Inbox/Drafts"),
            _param("query", "string", "Optionaler eindeutiger Draft-Titel oder Pfad-Teil, falls draftPath nicht bekannt ist"),
            _param("hideSmoke", "boolean", "Smoke-Test-Drafts beim Query-Resolve ausblenden, Standard: true"),
            _param("maxEvents", "integer", "Maximale Event-Anzahl, Standard: 50"),
        ]),
    ]

def _register_hermes_tools() -> list[dict]:
    """Hermes Agent bridge tools."""
    return [
        _tool("hermes_status", "Prueft, ob Hermes Agent lokal in Lexa verfuegbar ist und welche Lexa-/OS-/Workspace-Pfade genutzt werden."),
        _tool("hermes_telegram_status", "Prueft, ob Hermes Telegram lokal vorbereitet ist, welche Werte fehlen und welcher lokale Hermes-Home-Pfad genutzt wird."),
        _tool("hermes_gateway_autostart_status", "Prueft read-only, ob der Hermes Telegram Gateway beim Windows-Login automatisch startet."),
        _tool("hermes_telegram_configure", "Speichert Telegram-Bot-Token und optionale Chat-ID lokal in Lexas Hermes-Config. Tokens werden nicht ausgegeben.", [
            _param("botToken", "string", "BotFather-Token fuer den Telegram-Bot", required=True),
            _param("homeChannel", "string", "Optionale Telegram Chat-ID/User-ID fuer Antworten"),
            _param("homeChannelName", "string", "Anzeigename fuer den Home-Chat, Standard: Lexa"),
        ], confirmation_required=True),
        _tool("hermes_gateway_autostart_set", "Aktiviert oder deaktiviert den Hermes Telegram Gateway im Windows-Startup-Ordner.", [
            _param("enabled", "boolean", "true aktiviert Autostart, false deaktiviert ihn", required=True),
        ], confirmation_required=True),
        _tool("hermes_run", "Startet Hermes Agent fuer eine kontrollierte Hintergrundaufgabe im Lexa-Workspace. OS bleibt draft-geschuetzt.", [
            _param("message", "string", "Aufgabe fuer Hermes", required=True),
            _param("mode", "string", "Modus: general, lexa_improve oder os_context", enum=["general", "lexa_improve", "os_context"]),
            _param("timeout", "integer", "Timeout in Sekunden, Standard: 120"),
        ], confirmation_required=True),
        _tool("hermes_improve_lexa", "Laesst Hermes eine fokussierte Lexa-Verbesserung vorbereiten oder ausfuehren, mit OS-Draft-Grenze und Verifikation.", [
            _param("focus", "string", "Optionaler Fokus, z.B. Backend, OS, Tests oder UX"),
            _param("timeout", "integer", "Timeout in Sekunden, Standard: 180"),
        ], confirmation_required=True),
    ]


def _register_os_agent_tools() -> list[dict]:
    """Lexa OS agent runtime tools."""
    return [
        _tool("os_agent_status", "Zeigt Lexas OS-Agent-Runtime: Lexa als Kontrollschicht, Personal OS als Kontext/Approval und Hermes als Worker."),
        _tool("os_agent_list_tasks", "Listet Lexa OS-Agent-Aufgaben mit Status, Evidence und Review-Drafts.", [
            _param("limit", "integer", "Maximale Anzahl Aufgaben, Standard: 30"),
            _param("status", "string", "Optionaler Status-Filter: queued, running, completed, failed oder blocked"),
        ]),
        _tool("os_agent_task_status", "Zeigt eine einzelne Lexa OS-Agent-Aufgabe mit Evidence und Ergebnis.", [
            _param("task_id", "string", "Task-ID der OS-Agent-Aufgabe", required=True),
        ]),
        _tool("os_agent_start_task", "Startet eine kontrollierte Lexa OS-Agent-Aufgabe. Lexa bleibt Kontrollschicht, Hermes arbeitet als Worker, OS-Aenderungen nur als Draft.", [
            _param("title", "string", "Kurzer Titel der Aufgabe", required=True),
            _param("instructions", "string", "Konkrete Aufgabe fuer den OS-Agent-Worker", required=True),
            _param("agent", "string", "Worker-Agent, aktuell hermes", enum=["hermes"]),
            _param("mode", "string", "Modus: general, lexa_improve oder os_context", enum=["general", "lexa_improve", "os_context"]),
            _param("timeout", "integer", "Timeout in Sekunden, Standard: 180"),
            _param("createReviewDraft", "boolean", "Nach erfolgreicher Aufgabe Review-Draft im Personal OS erzeugen"),
        ], confirmation_required=True),
        _tool("os_agent_create_review_draft", "Erstellt fuer eine vorhandene OS-Agent-Aufgabe einen Review-Draft im Personal OS.", [
            _param("task_id", "string", "Task-ID der OS-Agent-Aufgabe", required=True),
        ], confirmation_required=True),
    ]


def _register_productivity_tools() -> list[dict]:
    """Produktivität (17): Todos, Pomodoro, Habits, Time Tracking, Focus."""
    return [
        _tool("todo_create", "Erstellt ein neues To-Do", [
            _param("title", "string", "Titel der Aufgabe", required=True),
            _param("priority", "string", "Priorität", enum=["high", "normal", "low"]),
            _param("category", "string", "Kategorie (z.B. 'arbeit', 'privat')"),
            _param("due_date", "string", "Fälligkeitsdatum im Format YYYY-MM-DD"),
            _param("description", "string", "Detaillierte Beschreibung"),
        ]),
        _tool("todo_list", "Listet To-Dos auf (mit optionalem Filter)", [
            _param("status", "string", "Filter nach Status", enum=["open", "done", "all"]),
            _param("category", "string", "Filter nach Kategorie"),
        ]),
        _tool("todo_update", "Aktualisiert ein bestehendes To-Do", [
            _param("id", "integer", "ID des To-Dos", required=True),
            _param("title", "string", "Neuer Titel"),
            _param("status", "string", "Neuer Status", enum=["open", "done"]),
            _param("priority", "string", "Neue Priorität", enum=["high", "normal", "low"]),
        ]),
        _tool("todo_complete", "Markiert ein To-Do als erledigt", [
            _param("id", "integer", "ID des To-Dos", required=True),
        ]),
        _tool("todo_delete", "Löscht ein To-Do permanent", [
            _param("id", "integer", "ID des To-Dos", required=True),
        ], confirmation_required=True),
        _tool("pomodoro_start", "Startet einen Pomodoro-Fokus-Timer", [
            _param("task", "string", "Aufgabe an der gearbeitet wird"),
            _param("duration", "integer", "Dauer in Minuten (Standard: 25)"),
        ]),
        _tool("pomodoro_stop", "Stoppt den laufenden Pomodoro-Timer"),
        _tool("pomodoro_status", "Zeigt den aktuellen Pomodoro-Status (läuft/pausiert/fertig)"),
        _tool("habit_create", "Erstellt eine neue Gewohnheit zum Tracken", [
            _param("name", "string", "Name der Gewohnheit", required=True),
            _param("description", "string", "Beschreibung"),
            _param("frequency", "string", "Häufigkeit", enum=["daily", "weekly"]),
            _param("target", "integer", "Tagesziel (Standard: 1)"),
        ]),
        _tool("habit_log", "Loggt eine Gewohnheit als erledigt", [
            _param("name", "string", "Name der Gewohnheit", required=True),
            _param("count", "integer", "Anzahl (Standard: 1)"),
        ]),
        _tool("habit_list", "Listet alle Gewohnheiten mit Streaks und Fortschritt"),
        _tool("habit_delete", "Löscht eine Gewohnheit", [
            _param("name", "string", "Name der Gewohnheit", required=True),
        ], confirmation_required=True),
        _tool("time_tracking_start", "Startet die Zeiterfassung für eine Aufgabe", [
            _param("task", "string", "Name der Aufgabe"),
        ]),
        _tool("time_tracking_stop", "Stoppt die laufende Zeiterfassung"),
        _tool("time_tracking_report", "Zeigt einen Zeiterfassungs-Bericht", [
            _param("days", "integer", "Zeitraum in Tagen (Standard: 1)"),
        ]),
        _tool("focus_mode_on", "Aktiviert den Fokus-Modus (blockiert ablenkende Websites)", [
            _param("sites", "array", "Zusätzliche Websites die blockiert werden sollen", items_type="string"),
        ], confirmation_required=True),
        _tool("focus_mode_off", "Deaktiviert den Fokus-Modus", [], confirmation_required=True),
    ]


def _register_pc_control_tools() -> list[dict]:
    """PC-Kontrolle erweitert (24): Fenster, Autostart, Dienste, Netzwerk."""
    return [
        _tool("window_move", "Verschiebt ein Fenster an eine bestimmte Position", [
            _param("title", "string", "Fenstertitel", required=True),
            _param("x", "integer", "X-Position in Pixeln", required=True),
            _param("y", "integer", "Y-Position in Pixeln", required=True),
        ]),
        _tool("window_resize", "Ändert die Größe eines Fensters", [
            _param("title", "string", "Fenstertitel", required=True),
            _param("width", "integer", "Neue Breite in Pixeln", required=True),
            _param("height", "integer", "Neue Höhe in Pixeln", required=True),
        ]),
        _tool("window_minimize", "Minimiert ein Fenster in die Taskleiste", [
            _param("title", "string", "Fenstertitel", required=True),
        ]),
        _tool("window_maximize", "Maximiert ein Fenster auf volle Bildschirmgröße", [
            _param("title", "string", "Fenstertitel", required=True),
        ]),
        _tool("window_layout", "Ordnet alle Fenster in einem vordefinierten Layout an", [
            _param("layout", "string", "Layout-Typ", required=True, enum=["split", "quad", "stack"]),
        ]),
        _tool("autostart_list", "Listet alle Programme die beim Windows-Start automatisch starten"),
        _tool("autostart_add", "Fügt ein Programm zum Windows-Autostart hinzu", [
            _param("name", "string", "Name des Eintrags", required=True),
            _param("path", "string", "Pfad zur Anwendung", required=True),
        ], confirmation_required=True),
        _tool("autostart_remove", "Entfernt ein Programm aus dem Windows-Autostart", [
            _param("name", "string", "Name des Autostart-Eintrags", required=True),
        ], confirmation_required=True),
        _tool("service_list", "Listet alle Windows-Dienste auf"),
        _tool("service_info", "Zeigt detaillierte Informationen zu einem Windows-Dienst", [
            _param("name", "string", "Dienstname", required=True),
        ]),
        _tool("service_start", "Startet einen Windows-Dienst (mit Admin-Erkennung und klarer Fehlermeldung)", [
            _param("name", "string", "Dienstname", required=True),
        ], confirmation_required=True),
        _tool("service_stop", "Stoppt einen Windows-Dienst (mit Admin-Erkennung und klarer Fehlermeldung)", [
            _param("name", "string", "Dienstname", required=True),
        ], confirmation_required=True),
        _tool("env_list", "Listet alle Umgebungsvariablen auf"),
        _tool("env_get", "Liest den Wert einer bestimmten Umgebungsvariable", [
            _param("name", "string", "Name der Umgebungsvariable", required=True),
        ]),
        _tool("env_set", "Setzt eine Umgebungsvariable", [
            _param("name", "string", "Name der Umgebungsvariable", required=True),
            _param("value", "string", "Neuer Wert", required=True),
        ], confirmation_required=True),
        _tool("system_uptime", "Zeigt wie lange der PC seit dem letzten Start läuft"),
        _tool("installed_apps", "Listet alle auf dem PC installierten Programme"),
        _tool("ping", "Sendet Ping-Pakete an einen Host und zeigt Antwortzeiten", [
            _param("host", "string", "Hostname oder IP-Adresse", required=True),
        ]),
        _tool("dns_lookup", "Führt eine DNS-Abfrage für eine Domain durch", [
            _param("domain", "string", "Domain-Name", required=True),
        ]),
        _tool("port_check", "Prüft ob ein bestimmter Port auf einem Host offen ist", [
            _param("host", "string", "Hostname oder IP-Adresse", required=True),
            _param("port", "integer", "Port-Nummer", required=True),
        ]),
        _tool("network_info", "Zeigt Netzwerk-Adapter, IP-Adressen und Gateway-Informationen"),
        _tool("public_ip", "Zeigt die öffentliche IP-Adresse des PCs"),
        _tool("traceroute", "Zeigt den Netzwerkpfad zu einem Host (Traceroute)", [
            _param("host", "string", "Ziel-Hostname oder IP-Adresse", required=True),
        ]),
        _tool("flush_dns", "Leert den lokalen DNS-Cache", [], confirmation_required=True),
    ]


def _register_dev_tools() -> list[dict]:
    """Entwickler-Tools (25): Git, Docker, API, Utilities."""
    return [
        _tool("git_status", "Zeigt den Git-Status eines Repositories", [
            _param("path", "string", "Pfad zum Repository"),
        ]),
        _tool("git_log", "Zeigt die Git-Commit-Historie", [
            _param("path", "string", "Pfad zum Repository"),
            _param("count", "integer", "Anzahl der anzuzeigenden Commits (Standard: 10)"),
        ]),
        _tool("git_diff", "Zeigt Git-Diff: Statistik + tatsächlicher Code-Diff (nicht nur --stat)", [
            _param("path", "string", "Pfad zum Repository"),
            _param("staged", "boolean", "Nur gestagete Änderungen zeigen"),
            _param("full", "boolean", "Nur Code-Diff ohne Statistik"),
        ]),
        _tool("git_branch_list", "Listet alle Git-Branches auf", [
            _param("path", "string", "Pfad zum Repository"),
        ]),
        _tool("git_add", "Staged Dateien für den nächsten Commit (git add)", [
            _param("path", "string", "Pfad zum Repository", required=True),
            _param("files", "string", "Dateien zum Stagen (Standard: '.')"),
        ], confirmation_required=True),
        _tool("git_commit", "Erstellt einen Git-Commit mit Nachricht", [
            _param("path", "string", "Pfad zum Repository", required=True),
            _param("message", "string", "Commit-Nachricht", required=True),
        ], confirmation_required=True),
        _tool("git_pull", "Git Pull mit Merge-Konflikt-Erkennung und Lösungsvorschlägen", [
            _param("path", "string", "Pfad zum Repository", required=True),
        ], confirmation_required=True),
        _tool("git_push", "Git Push mit Rejection-Erkennung und Upstream-Hilfe", [
            _param("path", "string", "Pfad zum Repository", required=True),
        ], confirmation_required=True),
        _tool("docker_ps", "Listet laufende Docker-Container auf"),
        _tool("docker_images", "Listet alle lokalen Docker-Images auf"),
        _tool("docker_stats", "Zeigt CPU/RAM-Verbrauch der Docker-Container"),
        _tool("docker_logs", "Zeigt die Logs eines Docker-Containers", [
            _param("name", "string", "Container-Name oder ID", required=True),
        ]),
        _tool("docker_start", "Startet einen gestoppten Docker-Container", [
            _param("name", "string", "Container-Name oder ID", required=True),
        ], confirmation_required=True),
        _tool("docker_stop", "Stoppt einen laufenden Docker-Container", [
            _param("name", "string", "Container-Name oder ID", required=True),
        ], confirmation_required=True),
        _tool("http_request", "Führt einen HTTP-Request aus und zeigt die Antwort", [
            _param("url", "string", "Ziel-URL", required=True),
            _param("method", "string", "HTTP-Methode", enum=["GET", "POST", "PUT", "DELETE"]),
            _param("body", "string", "Request-Body (für POST/PUT)"),
        ]),
        _tool("log_analyze", "Analysiert eine Log-Datei und filtert nach Pattern oder Level", [
            _param("path", "string", "Pfad zur Log-Datei", required=True),
            _param("pattern", "string", "Suchmuster (Regex)"),
            _param("level", "string", "Log-Level Filter", enum=["ERROR", "WARN", "INFO", "DEBUG"]),
        ]),
        _tool("server_check", "Prüft ob ein Server/URL erreichbar ist und zeigt Antwortzeit", [
            _param("url", "string", "Server-URL", required=True),
        ]),
        _tool("multi_server_check", "Prüft mehrere Server gleichzeitig auf Erreichbarkeit", [
            _param("urls", "array", "Liste von Server-URLs", required=True, items_type="string"),
        ]),
        _tool("json_format", "Formatiert und validiert einen JSON-String", [
            _param("text", "string", "JSON-String zum Formatieren", required=True),
        ]),
        _tool("regex_test", "Testet einen regulären Ausdruck gegen einen Text", [
            _param("pattern", "string", "Regex-Pattern", required=True),
            _param("text", "string", "Text zum Testen", required=True),
        ]),
        _tool("base64_encode", "Kodiert Text als Base64", [
            _param("text", "string", "Text zum Kodieren", required=True),
        ]),
        _tool("base64_decode", "Dekodiert einen Base64-String zu Text", [
            _param("text", "string", "Base64-String zum Dekodieren", required=True),
        ]),
        _tool("hash_text", "Berechnet einen kryptographischen Hash eines Textes", [
            _param("text", "string", "Text zum Hashen", required=True),
            _param("algorithm", "string", "Hash-Algorithmus", enum=["md5", "sha1", "sha256", "sha512"]),
        ]),
        _tool("generate_uuid", "Generiert eine zufällige UUID (v4)"),
        _tool("timestamp_convert", "Konvertiert zwischen Unix-Timestamp und lesbarem Datum", [
            _param("timestamp", "string", "Unix-Timestamp oder ISO-Datum (leer = aktuelle Zeit)"),
        ]),
    ]


def _register_reminder_tools() -> list[dict]:
    """Reminder-Tools (3): Smart persistent reminders."""
    return [
        _tool("reminder_create", "Erstellt eine Erinnerung mit natuerlicher Zeitangabe. Unterstuetzt: 'morgen um 9', 'in 2 Stunden', 'jeden Montag um 8', 'taeglich um 22 Uhr', 'naechsten Freitag 14:30'. Wiederkehrend moeglich (taeglich, woechentlich, monatlich, werktags).", [
            _param("message", "string", "Woran erinnert werden soll", required=True),
            _param("time", "string", "Wann? z.B. 'morgen um 9', 'in 2 Stunden', 'jeden Montag 8 Uhr'", required=True),
            _param("repeat", "string", "Wiederholung", enum=["daily", "weekly", "monthly", "weekdays"]),
        ]),
        _tool("reminder_list", "Zeigt alle aktiven Erinnerungen an, sortiert nach Zeit"),
        _tool("reminder_delete", "Loescht eine Erinnerung anhand der ID", [
            _param("id", "integer", "ID der Erinnerung", required=True),
        ], confirmation_required=True),
    ]


def _register_calendar_tools() -> list[dict]:
    """Calendar-Tools (6): Google Calendar Integration."""
    return [
        _tool("calendar_today", "Zeigt alle heutigen Google Kalender-Termine an"),
        _tool("calendar_week", "Zeigt alle Termine dieser Woche aus dem Google Kalender"),
        _tool("calendar_next", "Zeigt den nächsten anstehenden Kalender-Termin"),
        _tool("calendar_create", "Erstellt einen neuen Termin im Google Kalender. Unterstützt natürliche Zeitangaben wie 'morgen um 14 Uhr'.", [
            _param("title", "string", "Titel des Termins", required=True),
            _param("start", "string", "Startzeit als ISO-String oder natürliche Sprache (z.B. 'morgen um 14 Uhr', '2026-03-20T10:00:00')", required=True),
            _param("end", "string", "Endzeit (optional, Standard: 1 Stunde nach Start)"),
            _param("description", "string", "Beschreibung des Termins"),
            _param("location", "string", "Ort des Termins"),
        ], confirmation_required=True),
        _tool("calendar_delete", "Löscht einen Termin aus dem Google Kalender anhand der Event-ID", [
            _param("event_id", "string", "ID des zu löschenden Kalender-Events", required=True),
        ], confirmation_required=True),
        _tool("calendar_search", "Durchsucht den Google Kalender nach Terminen mit einem Stichwort", [
            _param("query", "string", "Suchbegriff", required=True),
            _param("days", "integer", "Anzahl Tage voraus suchen (Standard: 30, Max: 365)"),
        ]),
    ]


def _register_weather_tools() -> list[dict]:
    """Weather-Tools (2): Aktuelles Wetter, Vorhersage."""
    return [
        _tool("weather_current", "Zeigt das aktuelle Wetter: Temperatur, Gefühlt, Beschreibung, Luftfeuchtigkeit, Wind. Nutzt OpenWeatherMap.", [
            _param("city", "string", "Stadt. Wenn leer, wird gespeicherte Stadt oder IP-Standort verwendet."),
        ]),
        _tool("weather_forecast", "Zeigt die Wettervorhersage für die nächsten Tage mit Hoch/Tief-Temperaturen, Beschreibung und Regenwahrscheinlichkeit.", [
            _param("city", "string", "Stadt. Wenn leer, wird gespeicherte Stadt oder IP-Standort verwendet."),
            _param("days", "integer", "Anzahl der Vorhersage-Tage (1-5, Standard: 3)"),
        ]),
    ]


def _register_vision_tools() -> list[dict]:
    """Vision/OCR-Tools (3): Screenshot analysieren, Text lesen, OCR."""
    return [
        _tool("screen_analyze", "Screenshot machen und mit KI analysieren (Groq/Gemini/OpenAI Vision). Beschreibt was auf dem Bildschirm zu sehen ist.", [
            _param("prompt", "string", "Was soll analysiert werden? Frage oder Anweisung zum Screenshot."),
            _param("window", "string", "Optional: Fenstertitel fuer gezielten Screenshot (z.B. 'Chrome', 'VS Code')"),
        ]),
        _tool("screen_read_text", "Text vom Bildschirm lesen via lokalem OCR (schnell, offline, ~150ms). Extrahiert allen sichtbaren Text ohne Cloud-API.", [
            _param("window", "string", "Optional: Nur Text aus bestimmtem Fenster lesen"),
        ]),
        _tool("screen_ocr", "Alias fuer screen_read_text — OCR vom Bildschirm. Schnelle lokale Texterkennung ohne Cloud.", [
            _param("window", "string", "Optional: Nur Text aus bestimmtem Fenster lesen"),
        ]),
    ]


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

def register_all_tools() -> None:
    """Register all 140+ Lexa commands as tool definitions. Called once at startup."""
    global TOOL_DEFINITIONS, _TOOL_MAP

    tools: list[dict] = []
    tools.extend(_register_basis_tools())        # 22
    tools.extend(_register_browser_tools())       # 8
    tools.extend(_register_file_tools())          # 19
    tools.extend(_register_media_tools())         # 8
    tools.extend(_register_communication_tools()) # 5
    tools.extend(_register_memory_tools())        # 11
    tools.extend(_register_personal_os_tools())   # 11
    tools.extend(_register_hermes_tools())        # 5
    tools.extend(_register_os_agent_tools())      # 5
    tools.extend(_register_productivity_tools())  # 17
    tools.extend(_register_pc_control_tools())    # 24
    tools.extend(_register_dev_tools())           # 25
    tools.extend(_register_reminder_tools())       # 3
    tools.extend(_register_calendar_tools())      # 6
    tools.extend(_register_weather_tools())       # 2
    tools.extend(_register_vision_tools())        # 3

    TOOL_DEFINITIONS = tools
    _TOOL_MAP = {t["function"]["name"]: t for t in tools}
    logger.info(f"Tool Registry: {len(tools)} tools registered")


def get_all_tools() -> list[dict]:
    """Return all tool definitions (for LLM API calls)."""
    if not TOOL_DEFINITIONS:
        register_all_tools()
    return TOOL_DEFINITIONS


def get_tool(name: str) -> dict | None:
    """Return a single tool definition by name."""
    if not _TOOL_MAP:
        register_all_tools()
    return _TOOL_MAP.get(name)


def get_tool_names() -> list[str]:
    """Return all registered tool names."""
    if not _TOOL_MAP:
        register_all_tools()
    return list(_TOOL_MAP.keys())


def get_tool_count() -> int:
    """Return the number of registered tools."""
    if not TOOL_DEFINITIONS:
        register_all_tools()
    return len(TOOL_DEFINITIONS)


def is_confirmation_tool(name: str) -> bool:
    """Check if a tool requires user confirmation."""
    tool = get_tool(name)
    if not tool:
        return True  # Unknown tools require confirmation by default
    return bool(tool.get("confirmation_required"))


def validate_tool_arguments(name: str, arguments: dict) -> dict:
    """Validate LLM tool-call arguments against the registry JSON schema.

    This intentionally validates only the schema subset emitted by this registry:
    object properties, required fields, additional-property rejection, primitive
    types, arrays with simple item schemas, and enums. Runtime safety checks such
    as path and URL policy still happen later in `backend.security.validate_params`.
    """
    tool = get_tool(name)
    if not tool:
        raise ToolSchemaValidationError(f"unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ToolSchemaValidationError("arguments must be an object")

    _validate_no_dangerous_argument_keys(arguments)
    parameters = tool.get("function", {}).get("parameters") or {
        "type": "object",
        "properties": {},
    }
    _validate_schema_object(parameters, arguments, path="arguments", reject_unknown=True)
    return dict(arguments)


def _validate_no_dangerous_argument_keys(value: Any, path: str = "arguments") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in _DANGEROUS_ARGUMENT_KEYS:
                raise ToolSchemaValidationError(f"{path}.{key_text} is not allowed")
            _validate_no_dangerous_argument_keys(item, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_dangerous_argument_keys(item, f"{path}[{index}]")


def _validate_schema_object(schema: dict, value: dict, path: str, reject_unknown: bool) -> None:
    if schema.get("type", "object") != "object":
        raise ToolSchemaValidationError(f"{path} schema must be an object")

    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        raise ToolSchemaValidationError(f"{path} schema properties must be an object")

    required = schema.get("required") or []
    for key in required:
        if key not in value:
            raise ToolSchemaValidationError(f"{path}.{key} is required")

    unknown = sorted(str(key) for key in value.keys() if key not in properties)
    if reject_unknown and unknown:
        raise ToolSchemaValidationError(f"{path} has unknown parameter(s): {', '.join(unknown)}")

    for key, item in value.items():
        if key not in properties:
            continue
        _validate_schema_value(properties[key], item, f"{path}.{key}")


def _validate_schema_value(schema: dict, value: Any, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type is None:
        return

    valid = False
    if expected_type == "string":
        valid = isinstance(value, str)
    elif expected_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected_type == "boolean":
        valid = isinstance(value, bool)
    elif expected_type == "array":
        valid = isinstance(value, list)
    elif expected_type == "object":
        valid = isinstance(value, dict)
    else:
        raise ToolSchemaValidationError(f"{path} has unsupported schema type: {expected_type}")

    if not valid:
        raise ToolSchemaValidationError(f"{path} must be {expected_type}")

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise ToolSchemaValidationError(f"{path} must be one of: {', '.join(map(str, enum))}")

    if expected_type == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema_value(schema["items"], item, f"{path}[{index}]")

    if expected_type == "object" and isinstance(value, dict):
        _validate_schema_object(schema, value, path=path, reject_unknown=bool(schema.get("properties")))


# ══════════════════════════════════════════════════
#  CONTEXT-AWARE TOOL SELECTION
# ══════════════════════════════════════════════════

# Category keywords for smart filtering (reuses concept from old COMMAND_CATEGORIES)
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "basis": ["app", "öffne", "starte", "open", "launch", "programm",
              "screenshot", "prozess", "clipboard", "installiert", "suche",
              "timer", "lautstärke", "leiser", "lauter", "stumm", "mute",
              "helligkeit", "wifi", "wlan", "batterie", "akku", "fenster",
              "shutdown", "neustart", "restart", "herunterfahren"],
    "browser": ["youtube", "browser", "seite", "website", "web", "url",
                "suche", "google", "scrape", "preis", "price", "online",
                "research", "recherche", "recherchiere", "quellen",
                "quellenrecherche", "source", "sources", "citation",
                "citations", "zitat", "zitate", "fundstelle",
                "fundstellen", "belege", "evidence", "report"],
    "dateien": ["datei", "file", "zip", "archiv", "backup", "ordner", "pdf",
                "bild", "image", "duplikat", "umbenennen", "rename", "download",
                "temp", "entpack", "konvertier", "resize", "skalier", "disk"],
    "media": ["musik", "music", "spotify", "media", "abspielen", "play",
              "pause", "stop", "song", "track", "video", "aufnahme",
              "record", "screen", "audio", "konvertier",
              "spiel", "spiele", "hör", "höre", "hören", "lied", "artist",
              "künstler", "album", "playlist", "rap", "rock", "pop",
              "nächster", "vorheriger", "skip", "weiter", "zurück"],
    "kommunikation": ["email", "mail", "telegram", "discord", "nachricht",
                      "senden", "inbox", "postfach"],
    "gedaechtnis": ["notiz", "note", "erinner", "merke", "gedächtnis",
                    "memory", "vergiss", "routine", "zusammenfass",
                    "reminder", "erinnerung", "weck"],
    "personal_os": ["personal", "os", "markdown", "frontmatter", "graph",
                    "draft", "drafts", "index", "lexa", "kontext",
                    "context", "tag", "tags", "manifest", "workspace",
                    "arbeitsentwurf", "arbeitsdokument", "arbeitsbereich",
                    "artifact", "artefakt", "canvas", "obsidian", "vault", "contextpack",
                    "kontextpaket", "briefing", "projektbriefing",
                    "entwurf", "entwuerfe", "review", "approval",
                    "freigabe", "pruefung", "pruefe", "ueberpruefe",
                    "genehmigen", "ablehnen", "skill", "skills", "gem",
                    "gems", "customassistant", "customgpt", "assistentenprofil",
                    "spezialist", "template", "vorlage", "instructions",
                    "instruktionen", "decision", "entscheidung",
                    "entscheidungsbrief", "entscheiden", "tradeoff",
                    "tradeoffs", "abwägen", "abwaegen", "risiko", "risiken",
                    "optionen", "alternativen", "reversibilitaet",
                    "ship", "shipping", "release", "launch", "publish",
                    "veroeffentlichen", "produktreif", "readiness"],
    "hermes": ["hermes", "agent", "agents", "agenten", "worker",
               "background", "hintergrund", "selfimprove", "self-improve",
               "nousresearch", "nous", "telegram", "botfather", "gateway"],
    "os_agent": ["osagent", "agentruntime", "agent-runtime", "runtime",
                 "worker", "agenten", "subagent", "subagents",
                 "hintergrundaufgabe", "hintergrundaufgaben",
                 "taskqueue", "task-queue"],
    "produktivitaet": ["todo", "aufgabe", "task", "pomodoro", "gewohnheit",
                       "habit", "fokus", "focus", "zeiterfassung", "tracking",
                       "produktiv", "erledigt"],
    "pc_kontrolle": ["fenster", "window", "layout", "split", "autostart",
                     "dienst", "service", "umgebungsvariable", "env",
                     "uptime", "installiert", "netzwerk", "ping", "dns",
                     "port", "ip", "traceroute", "flush"],
    "entwickler": ["git", "commit", "push", "pull", "branch", "diff",
                   "docker", "container", "image", "api", "http", "request",
                   "server", "log", "json", "regex", "base64", "hash",
                   "uuid", "timestamp", "deploy", "code", "debug",
                   "release", "ship", "shipping", "launch", "publish",
                   "qa", "test", "tests", "regression", "rollback",
                   "produktreif", "veroeffentlichen", "readiness",
                   "privacy", "security", "accessibility", "a11y",
                   "performance"],
    "kalender": ["kalender", "calendar", "termin", "termine", "event",
                 "meeting", "besprechung", "verabredung", "agenda",
                 "woche", "heute", "morgen", "übermorgen"],
    "wetter": ["wetter", "weather", "temperatur", "temperature", "regen",
               "rain", "sonnig", "sunny", "bewölkt", "cloudy", "schnee",
               "snow", "wind", "vorhersage", "forecast", "grad", "degrees"],
    "vision": ["screenshot", "bildschirm", "screen", "ocr", "text lesen",
               "sehe ich", "was siehst", "analysiere", "vision", "bild",
               "erkennung", "lesen", "anzeige"],
}

# Map category -> tool name prefixes
_CATEGORY_TOOL_PREFIXES: dict[str, list[str]] = {
    "basis": ["app_", "system_", "screenshot", "process_", "clipboard_",
              "volume_", "file_search", "window_list", "window_focus",
              "brightness_", "wifi_", "battery_", "timer_", "browser_open",
              "shutdown", "restart", "installed_apps"],
    "browser": ["youtube_", "web_", "price_", "browser_close"],
    "dateien": ["find_duplicates", "batch_rename", "organize_", "merge_",
                "split_", "disk_", "clean_", "archive_", "backup_",
                "image_", "file_info", "folder_size"],
    "media": ["media_", "spotify_", "convert_media", "extract_audio", "screen_record"],
    "kommunikation": ["email_", "telegram_", "discord_"],
    "gedaechtnis": ["note_", "memory_", "summarize", "routine_", "reminder_"],
    "personal_os": ["personal_os_"],
    "hermes": ["hermes_"],
    "os_agent": ["os_agent_"],
    "produktivitaet": ["todo_", "pomodoro_", "habit_", "time_tracking_", "focus_mode_"],
    "pc_kontrolle": ["window_move", "window_resize", "window_min", "window_max",
                     "window_layout", "autostart_", "service_", "env_",
                     "system_uptime", "installed_apps", "ping", "dns_",
                     "port_", "network_", "public_ip", "traceroute", "flush_dns"],
    "entwickler": ["git_", "docker_", "http_request", "log_analyze",
                   "server_check", "multi_server", "json_format", "regex_",
                   "base64_", "hash_text", "generate_uuid", "timestamp_"],
    "kalender": ["calendar_"],
    "wetter": ["weather_"],
    "vision": ["screen_analyze", "screen_read_text", "screen_ocr"],
}

_CATEGORY_SELECTION_PRIORITY: dict[str, int] = {
    "os_agent": 0,
    "hermes": 1,
    "personal_os": 2,
    "entwickler": 3,
    "browser": 4,
    "dateien": 5,
    "media": 6,
    "kommunikation": 7,
    "gedaechtnis": 8,
    "produktivitaet": 9,
    "pc_kontrolle": 10,
    "kalender": 11,
    "wetter": 12,
    "vision": 13,
}


def get_tools_for_context(user_message: str, max_tools: int = 45) -> list[dict]:
    """Return context-relevant tools based on the user message.

    Uses keyword matching to select only relevant tool categories,
    keeping the tool list lean for providers with tool-count limits.

    Falls back to all tools if no specific category matches,
    or if the total after filtering is below max_tools anyway.
    """
    all_tools = get_all_tools()
    import re
    msg_lower = user_message.lower()
    msg_compact = re.sub(r"[\s_\-]+", " ", msg_lower)

    no_tool_meta_terms = (
        "tool regeln",
        "tool regel",
        "tool rules",
        "system prompt",
        "szenen prompt",
        "developer prompt",
        "interne regeln",
        "interne anweisungen",
    )
    if any(term in msg_compact for term in no_tool_meta_terms):
        return []
    if "regel" in msg_compact and any(q in msg_compact for q in ("welche", "was", "zeig", "zeige", "brauch", "erklaer", "erklär")):
        return []

    # If total tools fit within limit, send all
    if len(all_tools) <= max_tools:
        return all_tools
    msg_words = set(re.findall(r'[a-zäöüß]{3,}', msg_lower))

    matched_categories: list[str] = []
    for cat_name, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_words or any(w.startswith(kw) for w in msg_words):
                if cat_name not in matched_categories:
                    matched_categories.append(cat_name)
                break

    if not matched_categories:
        # No match — return top tools by general usefulness
        # Always include: basis + the first N tools
        return all_tools[:max_tools]

    specific_categories = [cat for cat in matched_categories if cat != "basis"]
    specific_categories.sort(
        key=lambda cat: (_CATEGORY_SELECTION_PRIORITY.get(cat, 50), matched_categories.index(cat))
    )
    selected_categories = specific_categories[:4]

    # Basis tools (always included, but lower priority than matched)
    basis_names: set[str] = set()
    for tool_def in all_tools:
        fname = tool_def["function"]["name"]
        for prefix in _CATEGORY_TOOL_PREFIXES.get("basis", []):
            if fname.startswith(prefix) or fname == prefix:
                basis_names.add(fname)
                break

    # Build prioritized list: matched category tools FIRST, then basis
    seen: set[str] = set()
    filtered: list[dict] = []

    # 1. Specific matched categories first (what the user actually asked about).
    for cat in selected_categories:
        prefixes = _CATEGORY_TOOL_PREFIXES.get(cat, [])
        for t in all_tools:
            fname = t["function"]["name"]
            for prefix in prefixes:
                if (fname.startswith(prefix) or fname == prefix) and fname not in seen:
                    seen.add(fname)
                    filtered.append(t)
                    break

    # 2. Basis tools (core functionality)
    for t in all_tools:
        fname = t["function"]["name"]
        if fname in basis_names and fname not in seen:
            seen.add(fname)
            filtered.append(t)

    # 3. If still too few, pad with remaining tools
    if len(filtered) < 15:
        for t in all_tools:
            fname = t["function"]["name"]
            if fname not in seen:
                seen.add(fname)
                filtered.append(t)
                if len(filtered) >= max_tools:
                    break

    return filtered[:max_tools]


# Auto-register on module import
register_all_tools()
