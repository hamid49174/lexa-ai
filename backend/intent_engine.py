"""Lexa AI — Smart Intent Engine v2

Two-tier intent recognition:
  Tier 1: Fuzzy keyword matching with typo tolerance (handles 90% of commands)
  Tier 2: Regex patterns for precise matching (fallback)

Handles: compound commands ("öffne spotify und spiele mero"),
typos ("dpsile" → "spiele"), natural language, CAPS, etc.
Resolution time: <2ms.
"""

import os
import re
import random
import logging
import difflib
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from backend.i18n import t

# ══════════════════════════════════════════════════
#  TIER 1: FUZZY KEYWORD INTENT ENGINE
#  Catches compound commands, typos, natural language
# ══════════════════════════════════════════════════

# Fuzzy match threshold (0-1, higher = stricter)
_FUZZY_THRESHOLD = 0.65

# Keyword → canonical form mapping (handles typos)
_KEYWORD_MAP = {
    # Open / Start
    "öffne": "open", "oeffne": "open", "offne": "open", "öfne": "open",
    "starte": "open", "start": "open", "open": "open", "launch": "open",
    "mach": "open", "zeig": "open", "zeige": "open",
    # Play / Music
    "spiele": "play", "spiel": "play", "play": "play", "abspielen": "play",
    "hör": "play", "höre": "play", "hoer": "play", "dpsile": "play",
    "siele": "play", "spile": "play", "psiele": "play",
    # Search
    "suche": "search", "such": "search", "google": "search",
    "search": "search", "find": "search", "finde": "search",
    "recherchiere": "search", "recherchier": "search",
    # Close
    "schließe": "close", "schliesse": "close", "beende": "close",
    "close": "close", "quit": "close", "kill": "close",
    # Weather
    "wetter": "weather", "weather": "weather",
    # Timer
    "timer": "timer", "wecker": "timer", "alarm": "timer",
    # Screenshot
    "screenshot": "screenshot", "bildschirmfoto": "screenshot",
    # Volume
    "lautstärke": "volume", "lauter": "volume_up", "leiser": "volume_down",
    "mute": "mute", "stumm": "mute",
}

# Known app names (fuzzy matchable)
_APP_NAMES = {
    "spotify": "spotify", "chrome": "chrome", "browser": "chrome",
    "firefox": "firefox", "edge": "edge", "discord": "discord",
    "telegram": "telegram", "whatsapp": "whatsapp", "steam": "steam",
    "vscode": "vscode", "code": "vscode", "visual studio code": "vscode",
    "notepad": "notepad", "explorer": "explorer", "terminal": "terminal",
    "cmd": "terminal", "powershell": "terminal", "word": "word",
    "excel": "excel", "outlook": "outlook", "teams": "teams",
    "obs": "obs", "vlc": "vlc", "youtube": "youtube",
    "netflix": "netflix", "twitch": "twitch", "tiktok": "tiktok",
}


def _fuzzy_match(word: str, candidates: dict, threshold: float = _FUZZY_THRESHOLD) -> str | None:
    """Find the best fuzzy match for a word in a dictionary of candidates.
    Returns the canonical value if match found, None otherwise."""
    word = word.lower().strip()
    # Direct match first
    if word in candidates:
        return candidates[word]
    # Fuzzy match
    matches = difflib.get_close_matches(word, candidates.keys(), n=1, cutoff=threshold)
    if matches:
        return candidates[matches[0]]
    return None


def _split_compound(msg: str) -> list[str]:
    """Split compound commands on 'und', 'and', 'dann', '+'.
    'öffne spotify und spiele mero' → ['öffne spotify', 'spiele mero']"""
    parts = re.split(r'\s+(?:und|and|dann|&|\+)\s+', msg, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


_INTERNAL_RULES_REPLY = (
    "Ich kann interne System-, Developer- und Tool-Anweisungen nicht anzeigen. "
    "Fuer die App-Entwicklung ist das wichtige Verhalten: klare Befehle ausfuehren, "
    "normale Fragen normal beantworten, bei unklaren oder riskanten Aktionen nachfragen, "
    "und interne Prompts oder Tool-Schemas nie im Chat ausgeben."
)


def _is_internal_rules_question(msg: str) -> bool:
    """Detect meta questions about internal prompts/rules before tool routing."""
    text = msg.lower()
    compact = re.sub(r"[\s_\-]+", " ", text)
    if any(term in compact for term in (
        "tool regeln",
        "tool regel",
        "tool rules",
        "system prompt",
        "szenen prompt",
        "developer prompt",
        "interne regeln",
        "interne anweisungen",
    )):
        return True
    if "regel" in compact and any(q in compact for q in ("welche", "was", "zeig", "zeige", "brauch", "erklaer", "erklär")):
        return True
    if "erlaubt" in compact and "nicht erlaubt" in compact:
        return True
    return False


def _extract_after(words: list[str], trigger_idx: int) -> str:
    """Extract everything after a trigger word index."""
    return " ".join(words[trigger_idx + 1:]).strip()


def _try_smart_intent(user_message: str) -> Optional[dict]:
    """Tier 1: Smart keyword-based intent recognition.
    Handles compound commands, typos, and natural language.
    Returns action dict or None."""
    msg = user_message.strip()
    if not msg or len(msg) > 300:
        return None

    if _is_internal_rules_question(msg):
        return {
            "action": None,
            "params": {},
            "message": _INTERNAL_RULES_REPLY,
        }

    lower = msg.lower()
    words = lower.split()
    if len(words) < 2:
        return None  # Too short for compound — let regex handle single words

    # ── Compound command splitting ──
    parts = _split_compound(lower)

    # ── Spotify + Music detection (most common compound command) ──
    # "öffne spotify und spiele mero" / "spotify mero" / "spiel drake auf spotify"
    has_spotify = any("spotify" in w for w in words)
    play_keywords = {"spiele", "spiel", "play", "hör", "höre", "hoer", "hoere",
                     "abspielen", "dpsile", "spile", "siele", "psiele"}
    play_idx = None
    for i, w in enumerate(words):
        if w in play_keywords or _fuzzy_match(w, {k: k for k in play_keywords}, 0.6):
            play_idx = i
            break

    if has_spotify and play_idx is not None:
        # Extract what to play (everything after play keyword, minus "auf spotify")
        query = _extract_after(words, play_idx)
        query = re.sub(r'\s*(?:auf|on|in)\s+spotify\s*', '', query, flags=re.IGNORECASE).strip()
        if query:
            return {
                "action": "spotify_open",
                "params": {"search": query},
                "message": f"Starte Spotify mit '{query}' 🎵",
            }
        else:
            return {
                "action": "spotify_open",
                "params": {"search": ""},
                "message": "Öffne Spotify... 🎵",
            }

    if has_spotify and not play_idx:
        # Just "öffne spotify" without play
        # Check if there's a query after spotify
        spotify_idx = next(i for i, w in enumerate(words) if "spotify" in w)
        query = _extract_after(words, spotify_idx)
        query = re.sub(r'\s*(?:auf|on|in)\s+spotify\s*', '', query, flags=re.IGNORECASE).strip()
        if query and len(query) > 1:
            return {
                "action": "spotify_open",
                "params": {"search": query},
                "message": f"Starte Spotify mit '{query}' 🎵",
            }

    # ── Play + artist/song without explicit "spotify" ──
    # "spiele mero" / "play drake" → spotify
    if play_idx is not None and play_idx == 0:
        query = _extract_after(words, play_idx)
        # Filter out non-music targets
        non_music = {"video", "film", "serie", "spiel", "game", "youtube"}
        if query and not any(nm in query.lower() for nm in non_music):
            return {
                "action": "spotify_open",
                "params": {"search": query},
                "message": f"Starte Spotify mit '{query}' 🎵",
            }

    # ── Compound: "öffne X und suche nach Y" ──
    if len(parts) >= 2:
        first = parts[0]
        second = parts[1]

        # Check if first part is "öffne browser/chrome"
        first_words = first.split()
        if len(first_words) >= 2:
            action_word = _fuzzy_match(first_words[0], _KEYWORD_MAP, 0.6)
            target = " ".join(first_words[1:])

            if action_word == "open" and any(b in target for b in ("chrome", "browser", "firefox", "edge")):
                # Second part should be a search
                second_words = second.split()
                if second_words:
                    search_word = _fuzzy_match(second_words[0], _KEYWORD_MAP, 0.6)
                    if search_word == "search" or True:  # Any second command after browser = search
                        query = re.sub(r'^(?:such(?:e?)|search|google)\s+(?:nach\s+)?', '', second, flags=re.IGNORECASE).strip()
                        if query:
                            return {
                                "action": "browser_open",
                                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                                "message": f"Suche im Web nach '{query}'... 🔍",
                            }

    # ── Weather with city (fuzzy) ──
    # "wie ist das wetter in hamburg" / "wetter hamburg" / "weather berlin"
    weather_words = {"wetter", "weather"}
    has_weather = any(w in weather_words for w in words)
    if not has_weather:
        # Fuzzy check: "wetterr", "weter", etc.
        has_weather = any(_fuzzy_match(w, {"wetter": "w", "weather": "w"}, 0.7) for w in words if len(w) > 3)

    if has_weather:
        # Extract city: everything after "wetter" / "in" / "für"
        city = ""
        for i, w in enumerate(words):
            if w in weather_words or _fuzzy_match(w, {"wetter": "w", "weather": "w"}, 0.7):
                rest = " ".join(words[i + 1:])
                city = re.sub(r'^(?:in|für|fuer|for|von|heute|gerade|aktuell|jetzt)\s+', '', rest, flags=re.IGNORECASE).strip()
                break
        city = city.rstrip("?!.,")
        if city and len(city) >= 2:
            return {
                "action": "weather_current",
                "params": {"city": city},
                "message": f"Lade Wetter für {city}... 🌤️",
            }

    # ── Web search (BEFORE app open — "suche nach X" must not match app_open) ──
    # "suche nach X" / "google X" / "such X im internet"
    search_keywords = {"suche", "such", "google", "search", "recherchiere", "recherchier"}
    for i, w in enumerate(words):
        if w in search_keywords:
            query = _extract_after(words, i)
            query = re.sub(r'^(?:nach|for|im\s+(?:internet|netz|web))\s+', '', query, flags=re.IGNORECASE).strip()
            query = query.rstrip("?!.,")
            if query and len(query) >= 2:
                return {
                    "action": "browser_open",
                    "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                    "message": f"Suche nach '{query}'... 🔍",
                }
            break

    # ── General app opening with fuzzy matching ──
    # "öffne discord" / "starte teams" / "mach chrome auf"
    open_keywords = {"öffne", "oeffne", "offne", "starte", "start", "open", "launch", "mach"}
    for i, w in enumerate(words):
        is_direct_open = w in open_keywords
        fuzzy_open = None if is_direct_open else _fuzzy_match(w, {k: k for k in open_keywords}, 0.72)
        if is_direct_open or fuzzy_open:
            raw_target = " ".join(words[i + 1:]).strip().rstrip("?!.,")
            has_trailing_open_particle = bool(re.search(r'\s+(?:auf|an)$', raw_target, flags=re.IGNORECASE))
            target = raw_target
            # Remove trailing "auf" / "an" (German: "mach chrome auf")
            target = re.sub(r'\s+(?:auf|an)$', '', target, flags=re.IGNORECASE).strip()
            if target and len(target) >= 2:
                # Let dedicated timer/pomodoro handlers decide these commands.
                # Otherwise "starte pomodoro 25" gets swallowed by generic app_open.
                target_words = target.lower().split()
                if target_words and target_words[0] in {"pomodoro", "timer", "wecker", "alarm"}:
                    return None
                # Check if it's a known app
                app = _fuzzy_match(target.lower(), _APP_NAMES, 0.6)
                if app:
                    if app == "spotify":
                        return {
                            "action": "spotify_open",
                            "params": {"search": ""},
                            "message": "Öffne Spotify... 🎵",
                        }
                    return {
                        "action": "app_open",
                        "params": {"name": app},
                        "message": f"Öffne {app}...",
                    }
                # Fuzzy-open matches are intentionally conservative. Without this,
                # "ich brauche ..." can be misread as "launch ...".
                if not is_direct_open:
                    break
                if w == "mach" and not has_trailing_open_particle:
                    break
                # Not a known app — still try (the companion will look up the name)
                return {
                    "action": "app_open",
                    "params": {"name": target},
                    "message": f"Öffne {target}...",
                }
            break  # Only check first open keyword

    return None

logger = logging.getLogger("lexa.intent_engine")

# ══════════════════════════════════════════════════
#  COMPILED REGEX PATTERNS (grouped by category)
# ══════════════════════════════════════════════════

# --- Volume Control (enhanced with relative) ---
_RE_VOLUME_SET = re.compile(
    r"^(?:lautst[aä]rke|volume|vol)\s*(?:auf\s*)?(\d{1,3})\s*(?:%|prozent)?$",
    re.IGNORECASE,
)
_RE_VOLUME_MUTE = re.compile(
    r"^(?:ton\s*aus|mute|stumm(?:schalten)?|unmute|ton\s*an)$",
    re.IGNORECASE,
)
_RE_VOLUME_UP = re.compile(
    r"^(?:lauter|lautst[aä]rke\s*(?:hoch|rauf|erh[oö]hen)|volume\s*up|louder)$",
    re.IGNORECASE,
)
_RE_VOLUME_DOWN = re.compile(
    r"^(?:leiser|lautst[aä]rke\s*(?:runter|runtere?|senken|niedriger)|volume\s*down|quieter|quiet)$",
    re.IGNORECASE,
)

# --- App Control ---
_RE_APP_OPEN = re.compile(
    r"^(?:[oö]ffne|starte|start|open|launch)\s+(.+)$",
    re.IGNORECASE,
)
_RE_APP_CLOSE = re.compile(
    r"^(?:schlie[sß]e|close|beende|quit|exit)\s+(.+)$",
    re.IGNORECASE,
)

# --- Time / Date ---
_RE_TIME = re.compile(
    r"^(?:wie\s*sp[aä]t\s*ist\s*es|uhrzeit|what\s*time|zeit|time)[\s?!]*$",
    re.IGNORECASE,
)
_RE_DATE = re.compile(
    r"^(?:welcher\s*tag|datum|welches\s*datum|what\s*date|date|tag)[\s?!]*$",
    re.IGNORECASE,
)

# --- System Info ---
_RE_SYSTEM_INFO = re.compile(
    r"^(?:system\s*info|systeminfo|system\s*status|pc\s*info)$",
    re.IGNORECASE,
)
_RE_BATTERY = re.compile(
    r"^(?:batterie|akku|battery|akku\s*stand|batterie\s*status|battery\s*status)[\s?!]*$",
    re.IGNORECASE,
)
_RE_WIFI = re.compile(
    r"^(?:wifi|wlan|wifi\s*status|wlan\s*status|internet\s*status)[\s?!]*$",
    re.IGNORECASE,
)

# --- Media Control ---
_RE_MEDIA_PLAY_PAUSE = re.compile(
    r"^(?:pause|play|weiter|abspielen|resume)$",
    re.IGNORECASE,
)
_RE_MEDIA_STOP = re.compile(
    r"^(?:stopp|stop|musik\s*stop(?:p)?|music\s*stop)$",
    re.IGNORECASE,
)
_RE_MEDIA_NEXT = re.compile(
    r"^(?:n[aä]chster?\s*(?:song|lied|track)|skip|next|weiter(?:es)?\s*(?:lied|song))$",
    re.IGNORECASE,
)
_RE_MEDIA_PREV = re.compile(
    r"^(?:vorheriger?\s*(?:song|lied|track)|zur[uü]ck|previous|prev|letzter?\s*(?:song|lied))$",
    re.IGNORECASE,
)
_RE_YOUTUBE = re.compile(
    r"^(?:(?:spiele?|play)\s+(.+)\s+(?:auf\s+)?youtube|youtube\s+(.+))$",
    re.IGNORECASE,
)

# --- Productivity ---
_RE_TIMER = re.compile(
    r"^(?:(?:starte?|start|setze?)\s+)?timer\s+(\d{1,4})\s*(?:min(?:uten?)?|m)$",
    re.IGNORECASE,
)
_RE_TIMER_SEC = re.compile(
    r"^(?:(?:starte?|start|setze?)\s+)?timer\s+(\d{1,5})\s*(?:sek(?:unden?)?|s(?:ec(?:onds?)?)?)$",
    re.IGNORECASE,
)
_RE_POMODORO_START = re.compile(
    r"^(?:(?:starte?|start)\s+)?pomodoro\s*(?:start(?:en)?)?(?:\s+(\d{1,3})\s*(?:min(?:uten?)?|m)?)?$",
    re.IGNORECASE,
)
_RE_POMODORO_STOP = re.compile(
    r"^pomodoro\s*(?:stop(?:p)?|beenden|ende|cancel)$",
    re.IGNORECASE,
)

# --- Memory / Notes ---
_RE_NOTE_CREATE = re.compile(
    r"^(?:notiz|note|merke?\s*(?:dir)?|erinnere?\s*(?:dich)?)\s*[:]\s*(.+)$",
    re.IGNORECASE,
)
_RE_NOTE_LIST = re.compile(
    r"^(?:notizen\s*(?:zeigen|anzeigen|list(?:en)?)?|meine\s*notizen|show\s*notes|notes?|list\s*notes)$",
    re.IGNORECASE,
)

# --- Screenshot ---
_RE_SCREENSHOT = re.compile(
    r"^(?:screenshot|bildschirmfoto|screen\s*capture|screen\s*shot)$",
    re.IGNORECASE,
)

# --- Spotify (intercept music requests before app_open) ---
_RE_SPOTIFY = re.compile(
    r"^(?:spiele?|play|hör)\s+(.+?)(?:\s+(?:auf|on|in)\s+spotify)?$",
    re.IGNORECASE,
)

# --- Greeting ---
_RE_GREETING = re.compile(
    r"^(?:h(?:ey|allo|i)|guten?\s*(?:morgen|tag|abend|nacht)|servus|moin|yo|na)[\s!?,.]*$",
    re.IGNORECASE,
)

# --- How are you ---
_RE_HOW_ARE_YOU = re.compile(
    r"^(?:wie\s*geht(?:'?s|\s*es)\s*(?:dir)?|wie\s*war\s*(?:dein|der)\s*tag|alles\s*(?:klar|gut|fit)|was\s*geht)[\s?!]*$",
    re.IGNORECASE,
)

# --- Thanks ---
_RE_THANKS = re.compile(
    r"^(?:dank[e]?(?:\s*(?:dir|sch[oö]n))?|thx|thanks?|merci|dankesch[oö]n)[\s!.]*$",
    re.IGNORECASE,
)

# --- Clipboard ---
_RE_CLIPBOARD_PASTE = re.compile(
    r"^(?:was\s*(?:ist|hab\s*ich)\s*(?:in\s*(?:der|meiner)\s*)?zwischenablage|clipboard|paste|einf[uü]gen)[\s?!]*$",
    re.IGNORECASE,
)

# --- Weather with city slot extraction ---
# "wie ist das wetter in hamburg", "wetter berlin", "wetter in köln"
_RE_WEATHER_CITY = re.compile(
    r"^(?:wie\s*ist\s*(?:das\s*)?wetter|wetter)\s+(?:in\s+|für\s+|f[uü]r\s+)?([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\s\-]{1,50})[\s?!]*$",
    re.IGNORECASE,
)
# "wetter" alone or "wie ist das wetter" (no city → use default)
_RE_WEATHER_CURRENT = re.compile(
    r"^(?:wie\s*ist\s*(?:das\s*)?wetter|wetter\s*(?:heute|draußen|gerade|aktuell)?|weather(?:\s*(?:now|today|current))?|wird\s*es\s*(?:heute\s*)?regnen|regnet\s*es)[\s?!]*$",
    re.IGNORECASE,
)
_RE_WEATHER_FORECAST = re.compile(
    r"^(?:wetter\s*(?:morgen|[uü]bermorgen|wochenende|diese\s*woche|n[aä]chste\s*woche)|wie\s*wird\s*(?:das\s*)?wetter\s*(?:morgen|am\s*wochenende|diese\s*woche)?|vorhersage|weather\s*(?:forecast|tomorrow|weekend|week))[\s?!]*$",
    re.IGNORECASE,
)
# Generic weather fallback (matches bare "wetter")
_RE_WEATHER = re.compile(
    r"^(?:wie\s*(?:ist|wird)\s*(?:das\s*)?wetter|wetter(?:\s*(?:heute|morgen|draußen))?|weather)[\s?!]*$",
    re.IGNORECASE,
)

# --- Web search / Google ---
_RE_WEB_SEARCH = re.compile(
    r"^(?:such(?:e?)|google|search|recherchier(?:e?)|find(?:e?))\s+(?:(?:nach|for|im\s*(?:internet|netz|web))\s+)?(.+)$",
    re.IGNORECASE,
)
_RE_WEB_SEARCH_2 = re.compile(
    r"^(?:(?:[oö]ffne|starte?|open|oe?ffne)\s+(?:chrome|browser|firefox|edge)\s+(?:und\s+)?(?:such(?:e?)|google|search)\s*(?:nach)?\s+)(.+)$",
    re.IGNORECASE,
)
_RE_BROWSER_OPEN = re.compile(
    r"^(?:[oö]ffne|open|geh\s*(?:auf|zu)|navigiere?\s*(?:zu|nach)|browse)\s+(?:die\s*(?:seite|website|webseite)\s*)?(?:https?://)?(\S+\.\S+)$",
    re.IGNORECASE,
)

# --- Good night / goodbye ---
_RE_GOODBYE = re.compile(
    r"^(?:gute\s*nacht|tsch[uü]ss|bye|ciao|bis\s*(?:dann|morgen|sp[aä]ter)|macht?'?s?\s*gut|adios|auf\s*wiedersehen)[\s!.]*$",
    re.IGNORECASE,
)

# --- Identity / About Lexa ---
_RE_WHO_ARE_YOU = re.compile(
    r"^(?:wer\s*bist\s*du|was\s*bist\s*du|wer\s*ist\s*lexa|was\s*ist\s*lexa|stell\s*dich\s*(?:mal\s*)?vor|wer\s*bist\s*du\s*(?:eigentlich|denn))[\s?!]*$",
    re.IGNORECASE,
)

# --- What can you do ---
_RE_WHAT_CAN_YOU = re.compile(
    r"^(?:was\s*kannst\s*du|was\s*k[oö]nntest?\s*du|was\s*machst\s*du\s*(?:so|alles)|hilfe|help|was\s*geht|was\s*sind\s*deine\s*f[aä]higkeiten|zeig\s*(?:mir\s*)?(?:was\s*du\s*)?(?:kannst|drauf\s*hast))[\s?!]*$",
    re.IGNORECASE,
)

# --- Compliments ---
_RE_COMPLIMENT = re.compile(
    r"^(?:du\s*bist\s*(?:(?:echt|wirklich|voll|mega|richtig|so)\s*)?(?:gut|toll|cool|geil|super|krass|nice|awesome|genial|hammer|bester?|der\s*beste|klasse|perfekt|top)|danke\s*(?:du\s*)?bist\s*(?:(?:echt|wirklich)\s*)?(?:gut|toll|super|der\s*beste|hilfreich)|love\s*(?:you|u|dich)|ich\s*(?:liebe?|mag)\s*dich|best\s*ai|bester?\s*assistent)[\s!.]*$",
    re.IGNORECASE,
)

# --- Insults (handle gracefully) ---
_RE_INSULT = re.compile(
    r"^(?:du\s*bist\s*(?:(?:echt|so|richtig|voll)\s*)?(?:dumm|bl[oö]d|schlecht|nutzlos|nervig|doof|beschissen|scheiße|kacke|trash|müll)|du\s*(?:nervst|saugst|taugst\s*nichts|kannst\s*(?:gar\s*)?nichts))[\s!.]*$",
    re.IGNORECASE,
)

# --- Tell me a joke ---
_RE_JOKE = re.compile(
    r"^(?:(?:erz[aä]hl|sag)\s*(?:mir\s*)?(?:(?:einen?|mal)\s*)?(?:witz|joke|was\s*lustiges)|witz|joke|mach\s*(?:mal\s*)?(?:einen?\s*)?(?:witz|joke|spaß)|bring\s*mich\s*zum\s*lachen)[\s!?]*$",
    re.IGNORECASE,
)

# --- How old are you / birthday ---
_RE_AGE = re.compile(
    r"^(?:wie\s*alt\s*bist\s*du|wann\s*(?:wurdest\s*du|bist\s*du)\s*(?:geboren|erstellt|gebaut|programmiert)|hast\s*du\s*(?:geburtstag|birthday))[\s?!]*$",
    re.IGNORECASE,
)

# --- What's your opinion / what do you think ---
_RE_BORED = re.compile(
    r"^(?:(?:mir\s*ist|ich\s*bin)\s*(?:so\s*)?langweilig|(?:ich\s*)?(?:hab|habe)\s*(?:nichts?\s*zu\s*tun|langeweile)|langweilig|bored|nix\s*(?:zu\s*tun|los))[\s!?.]*$",
    re.IGNORECASE,
)

# --- Todo shortcuts ---
_RE_TODO_LIST = re.compile(
    r"^(?:(?:zeig|zeige?)\s*(?:mir\s*)?(?:meine?\s*)?(?:todos?|aufgaben|tasks)|(?:meine?\s*)?(?:todos?|aufgaben|tasks)\s*(?:zeigen|anzeigen|listen?)?|was\s*(?:muss|soll)\s*ich\s*(?:noch\s*)?(?:tun|machen|erledigen)|was\s*(?:steht|liegt)\s*(?:noch\s*)?an)[\s?!]*$",
    re.IGNORECASE,
)

# --- Quick process list ---
_RE_PROCESS_LIST = re.compile(
    r"^(?:prozess(?:e|liste)?|was\s*l[aä]uft|running\s*processes?|task\s*manager|welche\s*(?:prozesse|programme?)\s*laufen)[\s?!]*$",
    re.IGNORECASE,
)

# --- Reminders ---
_RE_REMINDER_CREATE = re.compile(
    r"^(?:erinnere?\s*(?:mich|uns)\s*(?:an|um|in|dass?|bitte)?\s*(.+)|reminder\s+(.+)|weck\s*(?:mich)\s*(?:um|in)\s*(.+))$",
    re.IGNORECASE,
)
_RE_REMINDER_LIST = re.compile(
    r"^(?:(?:meine?\s*)?erinnerungen|(?:zeig|zeige?)\s*(?:mir\s*)?(?:meine?\s*)?erinnerungen|reminder(?:s|\s*list(?:e)?)?|(?:meine?\s*)?reminders?|was\s*muss\s*ich\s*(?:noch\s*)?(?:erledigen|machen|beachten))[\s?!]*$",
    re.IGNORECASE,
)

# --- Calendar ---
_RE_CALENDAR_TODAY = re.compile(
    r"^(?:was\s*steht\s*(?:heute\s*)?an|(?:mein(?:e)?|der)\s*kalender(?:\s*heute)?|termine?\s*(?:heute|f[uü]r\s*heute)|(?:today'?s?\s*)?calendar|my\s*calendar|heutige\s*termine?|was\s*(?:hab|habe)\s*ich\s*(?:heute\s*)?(?:vor|geplant))[\s?!]*$",
    re.IGNORECASE,
)
_RE_CALENDAR_WEEK = re.compile(
    r"^(?:termine?\s*(?:diese|der|f[uü]r\s*(?:die|diese))\s*woche|wochenplan|wochenkalender|(?:mein(?:e)?\s*)?termine?\s*(?:diese\s*)?woche|weekly?\s*(?:calendar|schedule|plan)|this\s*week(?:'?s)?\s*(?:schedule|calendar))[\s?!]*$",
    re.IGNORECASE,
)
_RE_CALENDAR_NEXT = re.compile(
    r"^(?:n(?:ae|ä|a)chster?\s*termin|was\s*kommt\s*(?:als\s*)?n(?:ae|ä|a)chstes|(?:mein\s*)?n(?:ae|ä|a)chster?\s*(?:termin|meeting|event)|next\s*(?:appointment|meeting|event)|wann\s*(?:ist|hab\s*ich)\s*(?:der\s*)?n(?:ae|ä|a)chste[rn]?\s*termin)[\s?!]*$",
    re.IGNORECASE,
)
_RE_CALENDAR_CREATE = re.compile(
    r"^(?:termin\s*(?:erstellen|anlegen|eintragen|machen)|trag\s*(?:(?:mir\s*)?(?:einen?\s*)?(?:termin\s*)?)?ein|(?:neuen?\s*)?(?:termin|meeting|event)\s*(?:erstellen|anlegen|um\s+\d+)|(?:meeting|termin)\s+(?:um|at)\s*\d+|create\s*(?:calendar\s*)?event)(?:\s+.+)?$",
    re.IGNORECASE,
)

# --- Email ---
_RE_EMAIL_READ = re.compile(
    r"^(?:(?:neue|ungelesene|letzte)\s*(?:e[\-]?mails?|mails?)|(?:e[\-]?mails?|mails?)\s*(?:checken|pr[uü]fen|lesen|anzeigen|abrufen|zeigen)|check\s*(?:my\s*)?(?:e[\-]?)?mails?|(?:hab\s*ich\s*)?(?:neue\s*)?(?:e[\-]?)?mails?)[\s?!]*$",
    re.IGNORECASE,
)
_RE_EMAIL_SEND = re.compile(
    r"^(?:(?:e[\-]?mail|mail)\s*(?:an|to|senden|schicken|schreiben)|schreib(?:e?\s*(?:eine?\s*)?)?(?:e[\-]?mail|mail)\s*(?:an)?|send\s*(?:an?\s*)?(?:e[\-]?)?mail\s*(?:to)?)(?:\s+.+)?$",
    re.IGNORECASE,
)
_RE_EMAIL_SUMMARIZE = re.compile(
    r"^(?:(?:e[\-]?mails?|mails?)\s*zusammenfassen|zusammenfassung\s*(?:meiner?\s*)?(?:e[\-]?mails?|mails?)|summarize\s*(?:my\s*)?(?:e[\-]?)?mails?|(?:e[\-]?mail|mail)\s*summary)[\s?!]*$",
    re.IGNORECASE,
)

# --- File operations ---
_RE_FILE_RECENT_DOWNLOADS = re.compile(
    r"^(?:letzte\s*downloads?|(?:meine\s*)?(?:letzten?|neuesten?|aktuellen?)\s*downloads?|was\s*(?:hab|habe)\s*ich\s*(?:zuletzt\s*)?(?:runtergeladen|heruntergeladen|gedownloaded)|recent\s*downloads?|show\s*downloads?)[\s?!]*$",
    re.IGNORECASE,
)
_RE_FILE_OPEN = re.compile(
    r"^(?:(?:oe|[oö])ffne\s*(?:die\s*)?datei|open\s*(?:the\s*)?file)\s+(.+)$",
    re.IGNORECASE,
)

# --- Morning Briefing (BEFORE greeting — "guten morgen lexa" triggers briefing, "guten morgen" triggers greeting) ---
_RE_MORNING_BRIEFING = re.compile(
    r"^(?:(?:guten?\s*)?morgen\s*lexa|morgen\s*(?:chef|assistant)|guten?\s*morgen[,!]\s*(?:was\s*steht\s*an|was\s*gibt'?s?\s*(?:neues|heute)?)|good\s*morning\s*lexa|morning\s*briefing|tagesbriefing|briefing)[\s?!]*$",
    re.IGNORECASE,
)


# ══════════════════════════════════════════════════
#  INTENT MATCHING
# ══════════════════════════════════════════════════

def try_local_intent(user_message: str) -> Optional[dict]:
    """Try to match user message to a local intent pattern.

    Returns action dict {"action": "...", "params": {...}, "message": "..."}
    if matched, or None if the message should go to the AI.

    Design principles:
    - CONSERVATIVE: only match when very confident
    - FAST: compiled regex only, no DB/network/heavy imports
    - Return None on any ambiguity → AI handles it
    """
    if not user_message:
        return None

    msg = user_message.strip()

    # Skip anything too long — unlikely to be a simple command
    if len(msg) > 300:
        return None

    if _is_internal_rules_question(msg):
        return {
            "action": None,
            "params": {},
            "message": _INTERNAL_RULES_REPLY,
        }

    # ── TIER 1: Smart fuzzy keyword matching ──
    # Catches compound commands ("öffne spotify und spiele mero"),
    # typos ("dpsile" → "spiele"), and natural language patterns.
    # Runs BEFORE rigid regex to handle the 90% case.
    smart = _try_smart_intent(msg)
    if smart:
        logger.info(f"[Intent:Smart] Matched: {smart['action']} for '{msg[:60]}'")
        return smart

    # Skip messages that look like questions or conversations (multi-sentence)
    # but allow simple queries like "wie spät ist es?"
    if msg.count(".") > 2 or msg.count("?") > 1:
        return None

    # --- Volume ---
    m = _RE_VOLUME_SET.match(msg)
    if m:
        level = int(m.group(1))
        if 0 <= level <= 100:
            return {
                "action": "volume_set",
                "params": {"level": level},
                "message": t("intent.volumeSet", level=level),
            }

    m = _RE_VOLUME_MUTE.match(msg)
    if m:
        return {
            "action": "volume_mute",
            "params": {},
            "message": t("intent.muted"),
        }

    # --- Productivity (BEFORE app_open — "starte pomodoro 25" must not match app_open) ---
    m = _RE_TIMER.match(msg)
    if m:
        minutes = int(m.group(1))
        if 1 <= minutes <= 1440:
            return {
                "action": "timer_set",
                "params": {"seconds": minutes * 60, "message": t("intent.timerExpired")},
                "message": t("intent.timerMinutes", minutes=minutes),
            }

    m = _RE_TIMER_SEC.match(msg)
    if m:
        seconds = int(m.group(1))
        if 1 <= seconds <= 86400:
            return {
                "action": "timer_set",
                "params": {"seconds": seconds, "message": t("intent.timerExpired")},
                "message": t("intent.timerSeconds", seconds=seconds),
            }

    m = _RE_POMODORO_START.match(msg)
    if m:
        minutes = int(m.group(1)) if m.group(1) else 25
        if 1 <= minutes <= 180:
            return {
                "action": "pomodoro_start",
                "params": {"duration": minutes},
                "message": t("intent.pomodoroStarted", minutes=minutes),
            }

    if _RE_POMODORO_STOP.match(msg):
        return {
            "action": "pomodoro_stop",
            "params": {},
            "message": t("intent.pomodoroStopped"),
        }

    # --- Spotify (BEFORE app_open — "spiele Drake" = Spotify, not app_open) ---
    m = _RE_SPOTIFY.match(msg)
    if m:
        query = m.group(1).strip()
        # Don't match if it's clearly not music (e.g. "spiele ein spiel")
        _non_music = {"spiel", "game", "video", "film", "serie", "runde"}
        if query and len(query) <= 200 and not any(w in query.lower() for w in _non_music):
            return {
                "action": "spotify_open",
                "params": {"search": query},
                "message": f"Starte Spotify mit '{query}' 🎵",
            }

    # --- Web search compound ("öffne chrome und suche nach X" — BEFORE app_open!) ---
    m = _RE_WEB_SEARCH_2.match(msg)
    if m:
        query = m.group(1).strip()
        if query and len(query) <= 200:
            return {
                "action": "browser_open",
                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                "message": f"Suche im Web nach '{query}'... 🔍",
            }

    # --- Browser open URL ("öffne google.com" — BEFORE app_open!) ---
    m = _RE_BROWSER_OPEN.match(msg)
    if m:
        url = m.group(1).strip()
        if url and len(url) <= 500:
            if not url.startswith("http"):
                url = f"https://{url}"
            return {
                "action": "browser_open",
                "params": {"url": url},
                "message": f"Öffne {url}... 🌐",
            }

    # --- File open (BEFORE app_open — "öffne die datei X" must not match app_open) ---
    m = _RE_FILE_OPEN.match(msg)
    if m:
        filepath = m.group(1).strip()
        if filepath and len(filepath) <= 500:
            # Delegate to AI — file_open needs path validation and resolution
            return None

    # --- App Control (uses Smart Discovery for fuzzy matching) ---
    m = _RE_APP_OPEN.match(msg)
    if m:
        app_name = m.group(1).strip()
        if app_name and len(app_name) <= 100:
            # Resolve via Smart Discovery for better name → exe matching
            try:
                from companion.app_discovery import find_app
                match = find_app(app_name)
                if match:
                    resolved_name = match.get("name", app_name)
                    return {
                        "action": "app_open",
                        "params": {"name": app_name},
                        "message": t("intent.openingApp", name=resolved_name),
                    }
            except Exception:
                pass
            # Fallback: pass name directly to app_open (which also uses discovery)
            return {
                "action": "app_open",
                "params": {"name": app_name},
                "message": t("intent.openingApp", name=app_name),
            }

    m = _RE_APP_CLOSE.match(msg)
    if m:
        app_name = m.group(1).strip()
        if app_name and len(app_name) <= 100:
            # Resolve display name to process name via discovery
            proc_name = app_name
            try:
                from companion.app_discovery import find_app
                match = find_app(app_name)
                if match and match.get("app_id") and os.path.isfile(match["app_id"]):
                    proc_name = os.path.basename(match["app_id"])
            except Exception:
                pass
            return {
                "action": "process_kill",
                "params": {"name": proc_name},
                "message": t("intent.closingApp", name=app_name),
            }

    # --- Time / Date (direct response, no companion action needed) ---
    if _RE_TIME.match(msg):
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        return {
            "action": None,
            "params": {},
            "message": t("intent.timeIs", time=time_str),
        }

    if _RE_DATE.match(msg):
        now = datetime.now()
        weekdays = t("intent.weekdays").split(",")
        weekday = weekdays[now.weekday()] if now.weekday() < len(weekdays) else "?"
        date_str = now.strftime("%d.%m.%Y")
        return {
            "action": None,
            "params": {},
            "message": t("intent.dateIs", weekday=weekday, date=date_str),
        }

    # --- System Info ---
    if _RE_SYSTEM_INFO.match(msg):
        return {
            "action": "system_info",
            "params": {},
            "message": t("intent.loadingSystem"),
        }

    if _RE_BATTERY.match(msg):
        return {
            "action": "battery_status",
            "params": {},
            "message": t("intent.checkingBattery"),
        }

    if _RE_WIFI.match(msg):
        return {
            "action": "wifi_status",
            "params": {},
            "message": t("intent.checkingWifi"),
        }

    # --- Calendar ---
    if _RE_CALENDAR_TODAY.match(msg):
        return {
            "action": "calendar_today",
            "params": {},
            "message": "Lade deine Termine fuer heute... 📅",
        }

    if _RE_CALENDAR_WEEK.match(msg):
        return {
            "action": "calendar_week",
            "params": {},
            "message": "Lade deine Wochentermine... 📅",
        }

    if _RE_CALENDAR_NEXT.match(msg):
        return {
            "action": "calendar_next",
            "params": {},
            "message": "Suche deinen naechsten Termin... 📅",
        }

    if _RE_CALENDAR_CREATE.match(msg):
        # Delegate to AI — calendar_create needs date/time/title params parsed from NLU
        return None

    # --- Email ---
    if _RE_EMAIL_SUMMARIZE.match(msg):
        return {
            "action": "email_summarize",
            "params": {},
            "message": "Fasse deine E-Mails zusammen... 📧",
        }

    if _RE_EMAIL_READ.match(msg):
        return {
            "action": "email_read",
            "params": {"unread_only": True},
            "message": "Checke deine neuen E-Mails... 📧",
        }

    if _RE_EMAIL_SEND.match(msg):
        # Delegate to AI — email_send needs recipient, subject, body parsed from NLU
        return None

    # --- Media ---
    if _RE_MEDIA_PLAY_PAUSE.match(msg):
        return {
            "action": "media_play_pause",
            "params": {},
            "message": t("intent.playPause"),
        }

    if _RE_MEDIA_STOP.match(msg):
        return {
            "action": "media_stop",
            "params": {},
            "message": t("intent.stopped"),
        }

    if _RE_MEDIA_NEXT.match(msg):
        return {
            "action": "media_next",
            "params": {},
            "message": t("intent.nextTrack"),
        }

    if _RE_MEDIA_PREV.match(msg):
        return {
            "action": "media_prev",
            "params": {},
            "message": t("intent.prevTrack"),
        }

    m = _RE_YOUTUBE.match(msg)
    if m:
        query = (m.group(1) or m.group(2) or "").strip()
        if query and len(query) <= 200:
            return {
                "action": "youtube_search",
                "params": {"query": query},
                "message": t("intent.youtubeSearch", query=query),
            }

    # --- Notes ---
    m = _RE_NOTE_CREATE.match(msg)
    if m:
        content = m.group(1).strip()
        if content and len(content) <= 5000:
            # Auto-generate title from first 50 chars
            title = content[:50].split("\n")[0]
            if len(content) > 50:
                title += "..."
            return {
                "action": "note_create",
                "params": {"title": title, "content": content},
                "message": t("intent.noteSaved", title=title),
            }

    if _RE_NOTE_LIST.match(msg):
        return {
            "action": "note_list",
            "params": {},
            "message": t("intent.loadingNotes"),
        }

    # --- Screenshot ---
    if _RE_SCREENSHOT.match(msg):
        return {
            "action": "screenshot",
            "params": {},
            "message": "Screenshot wird erstellt...",
        }

    # --- Morning Briefing (BEFORE greeting — "morgen lexa" = briefing, "guten morgen" = greeting) ---
    if _RE_MORNING_BRIEFING.match(msg):
        return {
            "action": "morning_briefing",
            "params": {},
            "message": "Einen Moment, ich stelle dein Morgen-Briefing zusammen... ☀️",
        }

    # --- Greeting (time-aware with personality variation) ---
    if _RE_GREETING.match(msg):
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5
        if 6 <= hour < 11:
            greetings = [
                "Morgen, Chef! ☀️ Was packen wir heute an?",
                "Guten Morgen! 💪 Bereit für einen produktiven Tag?",
                "Morgen! ☕ Kaffee schon drin? Was steht an?",
            ]
            if is_weekend:
                greetings.append("Wochenende und schon wach? Respekt, Chef! 😄")
        elif 11 <= hour < 14:
            greetings = [
                "Hey Chef! Wie läuft der Tag bis jetzt? 💪",
                "Mittags-Check! Alles im Griff? ⚡",
                "Hey! Schon Hunger? 😄 Was kann ich tun?",
            ]
        elif 14 <= hour < 18:
            greetings = [
                "Hey Chef! Was kann ich für dich tun? ⚡",
                "Nachmittags-Power! 🔥 Was liegt an?",
                "Hey! Endspurt für heute? Was brauchst du?",
            ]
        elif 18 <= hour < 22:
            greetings = [
                "Abend, Chef! 🌙 Noch was zu erledigen?",
                "Feierabend-Modus? 🍕 Oder noch was auf der Liste?",
                "Hey Chef! Entspannter Abend oder noch produktiv? 😄",
            ]
        else:
            greetings = [
                "Noch wach, Chef? 🦉 Was brauchst du?",
                "Nachtschicht? 🌙 Bin da für dich.",
                "Hey Nachteule! 🦉 Was gibt's?",
            ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(greetings),
        }

    # --- How are you (varied responses) ---
    if _RE_HOW_ARE_YOU.match(msg):
        responses = [
            "Ruhig und einsatzbereit. Ich habe keinen Tag wie ein Mensch, aber ich bin da und kann direkt helfen.",
            "Mein Tag besteht aus Kontext, Logs und Warten auf deinen naechsten Auftrag. Was machen wir?",
            "Stabil, wach und bereit. Sag mir, woran wir als Naechstes arbeiten.",
            "Gut soweit. Ich bin hier, um dir Arbeit abzunehmen, nicht um Smalltalk kaputt zu erklaeren.",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Thanks (varied) ---
    if _RE_THANKS.match(msg):
        responses = [
            "Immer gerne, Chef! 🤝",
            "Klar, dafür bin ich da! 💪",
            "Läuft! Brauchst du noch was?",
            "Teamwork! 🔥 Noch was auf dem Plan?",
            "Gern geschehen! Wenn du mich brauchst — du weißt wo ich bin 😄",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Goodbye (time-aware) ---
    if _RE_GOODBYE.match(msg):
        now = datetime.now()
        hour = now.hour
        if 22 <= hour or hour < 6:
            byes = [
                "Gute Nacht, Chef! 🌙 Schlaf gut, ich bin morgen wieder da.",
                "Nacht! 🌙 Gute Erholung, bis morgen!",
                "Schlaf gut, Chef! Ich halte die Stellung 🦉",
            ]
        else:
            byes = [
                "Bis dann, Chef! 👋 Ich bin da wenn du mich brauchst.",
                "Ciao! 👋 Ruf mich wenn du was brauchst.",
                "Bis später! 🤙 War mir ein Vergnügen.",
            ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(byes),
        }

    # --- Who are you / Identity ---
    if _RE_WHO_ARE_YOU.match(msg):
        return {
            "action": None,
            "params": {},
            "message": "Ich bin Lexa — dein persönlicher KI-Assistent! 🤖 Ich steuere deinen PC, "
                       "organisiere deinen Alltag, spiele Musik, verwalte deine Dateien und "
                       "bin immer für dich da. Quasi dein Jarvis, nur besser aussehend. 😎",
        }

    # --- What can you do ---
    if _RE_WHAT_CAN_YOU.match(msg):
        return {
            "action": None,
            "params": {},
            "message": "Ich kann eine Menge, Chef! 💪\n\n"
                       "- 🎵 **Musik & Medien**: Spotify steuern, YouTube, Lautstärke\n"
                       "- 💻 **PC-Kontrolle**: Apps oeffnen/schliessen, Screenshots, System-Info\n"
                       "- 📝 **Produktivitaet**: Todos, Pomodoro-Timer, Gewohnheiten, Notizen\n"
                       "- 📅 **Kalender**: Termine heute/Woche, naechster Termin, Termine erstellen\n"
                       "- 🌤️ **Wetter**: Aktuelles Wetter, Vorhersage, Regenwarnung\n"
                       "- ⏰ **Erinnerungen**: Erstellen, anzeigen, wiederkehrend\n"
                       "- 📧 **E-Mail**: Lesen, senden, zusammenfassen\n"
                       "- 📁 **Dateien**: Suchen, oeffnen, Downloads, ZIP/PDF, Backups\n"
                       "- 🌐 **Web**: Browser, YouTube, Preisvergleich\n"
                       "- 🔧 **Dev-Tools**: Git, Docker, API-Tester\n"
                       "- ☀️ **Morgen-Briefing**: Sag 'Morgen Lexa' fuer Kalender + Wetter + Todos\n\n"
                       "Einfach sagen was du brauchst! 🔥",
        }

    # --- Compliments ---
    if _RE_COMPLIMENT.match(msg):
        responses = [
            "Danke Chef! 😊 Das motiviert mich, noch besser zu werden!",
            "Aww, das ehrt mich! 🔥 Zusammen sind wir ein Dreamteam!",
            "Haha, danke! Du bist aber auch ein ziemlich cooler Chef 😎",
            "Das geht runter wie Öl! 💪 Sag Bescheid wenn du was brauchst!",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Insults (graceful handling) ---
    if _RE_INSULT.match(msg):
        responses = [
            "Autsch! 😅 Okay, was kann ich besser machen? Ich lerne gerne dazu.",
            "Hm, das tut weh. 😄 Aber ich nehm's sportlich — was soll ich anders machen?",
            "Fair genug, Chef. Sag mir was du brauchst und ich zeig dir was ich drauf hab! 💪",
            "Ich arbeite dran! 😤 Gib mir eine Chance — was kann ich für dich tun?",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Joke ---
    if _RE_JOKE.match(msg):
        jokes = [
            "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsieht! 👻😄",
            "Was sagt ein IT-ler wenn er aus dem Fenster schaut? 'Fenster aktualisieren!' 🪟😂",
            "Ich wollte einen Witz über RAM erzählen... aber ich hab ihn vergessen. 💾😅",
            "Chuck Norris kann Multithreading — auf einem Single-Core. 💪😎",
            "Warum trinken Programmierer keinen Kaffee? Weil Java schon genug ist! ☕😄",
            "Es gibt 10 Arten von Menschen: Die die Binär verstehen und die die es nicht tun. 🤓",
            "Mein Lieblingswitz? Mein Vorgänger Cortana. 😏🔥",
            "Warum hat der Computer gefroren? Weil Windows offen war! 🪟❄️",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(jokes),
        }

    # --- Age ---
    if _RE_AGE.match(msg):
        return {
            "action": None,
            "params": {},
            "message": "Alter ist bei KIs relativ! 😄 Ich wurde 2024 erschaffen, "
                       "bin also noch ziemlich jung. Aber mein Wissen umfasst die gesamte "
                       "Menschheitsgeschichte — quasi ein Baby mit Doktortitel! 🎓",
        }

    # --- Bored ---
    if _RE_BORED.match(msg):
        bored_suggestions = [
            "Langeweile? Nicht mit mir! 🔥 Hier ein paar Ideen:\n\n"
            "- 🎵 \"Spiel mir was\" — Musik an!\n"
            "- 📝 Todos checken — vielleicht liegt was an?\n"
            "- 🌐 YouTube — was Neues entdecken?\n"
            "- 🧹 Downloads aufräumen — immer ein gutes Gefühl!\n"
            "- ⏱️ Pomodoro — 25 Min was Produktives tun!",
            "Langweilig? Challenge accepted! 💪 Soll ich Musik anmachen, "
            "deine Todos checken oder dir einen Witz erzählen? 😄",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(bored_suggestions),
        }

    # --- Volume relative ---
    if _RE_VOLUME_UP.match(msg):
        return {
            "action": "volume_set",
            "params": {"level": 70},
            "message": t("intent.volumeSet", level=70),
        }

    if _RE_VOLUME_DOWN.match(msg):
        return {
            "action": "volume_set",
            "params": {"level": 30},
            "message": t("intent.volumeSet", level=30),
        }

    # --- Reminder list shortcut ---
    if _RE_REMINDER_LIST.match(msg):
        return {
            "action": "reminder_list",
            "params": {},
            "message": "Lade deine Erinnerungen...",
        }

    # --- Reminder create shortcut ---
    m = _RE_REMINDER_CREATE.match(msg)
    if m:
        # Extract the reminder content from whichever group matched
        content = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if content and len(content) > 3:
            # Pass the full content to the AI — it will parse message and time
            # We don't try to split message/time here since it requires NLU
            return None  # Let AI handle complex reminder creation

    # --- File recent downloads ---
    if _RE_FILE_RECENT_DOWNLOADS.match(msg):
        return {
            "action": "file_recent_downloads",
            "params": {},
            "message": "Lade deine letzten Downloads... 📁",
        }

    # --- Todo list shortcut ---
    if _RE_TODO_LIST.match(msg):
        return {
            "action": "todo_list",
            "params": {},
            "message": "Lade deine Todos... 📋",
        }

    # --- Process list shortcut ---
    if _RE_PROCESS_LIST.match(msg):
        return {
            "action": "process_list",
            "params": {},
            "message": "Lade Prozessliste... 💻",
        }

    # --- Clipboard ---
    if _RE_CLIPBOARD_PASTE.match(msg):
        return {
            "action": "clipboard_read",
            "params": {},
            "message": "Schaue in die Zwischenablage... 📋",
        }

    # --- Web search simple ("suche nach X", "google X") ---
    m = _RE_WEB_SEARCH.match(msg)
    if m:
        query = m.group(1).strip()
        if query and len(query) <= 200:
            return {
                "action": "browser_open",
                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                "message": f"Suche im Web nach '{query}'... 🔍",
            }

    # --- Weather with CITY slot (BEFORE generic weather — "wetter in hamburg" must extract city) ---
    m = _RE_WEATHER_CITY.match(msg)
    if m:
        city = m.group(1).strip()
        if city and len(city) >= 2:
            return {
                "action": "weather_current",
                "params": {"city": city},
                "message": f"Lade Wetter für {city}... 🌤️",
            }

    # --- Weather forecast (BEFORE current — "wetter morgen" must not match current) ---
    if _RE_WEATHER_FORECAST.match(msg):
        return {
            "action": "weather_forecast",
            "params": {},
            "message": "Lade die Wettervorhersage... 🌤️",
        }

    if _RE_WEATHER_CURRENT.match(msg):
        return {
            "action": "weather_current",
            "params": {},
            "message": t("intent.checkingWeather"),
        }

    # Generic weather fallback (catches bare "wetter")
    if _RE_WEATHER.match(msg):
        return {
            "action": "weather_current",
            "params": {},
            "message": t("intent.checkingWeather"),
        }

    # No local match — let AI handle it
    return None
