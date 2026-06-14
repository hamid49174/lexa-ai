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
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation
from datetime import datetime
from typing import Any, Optional
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


@dataclass
class ConversationIntentContext:
    recent_intents: list[str] = field(default_factory=list)
    active_domain: str = ""
    entities: dict[str, str] = field(default_factory=dict)


_WINDOWS_PATH_RE = re.compile(r"(?P<path>[A-Za-z]:\\[^\n\r\"'<>|?*]+)")
_ACTION_HINT_RE = re.compile(r"\b(?:Aktion:|\[Aktion:)\s*(?P<action>[a-zA-Z_][a-zA-Z0-9_]*)")
_FILE_CONTEXT_WORD_RE = re.compile(r"\b(?:datei|file|ordner|folder|pfad|path|download|desktop)\b", re.IGNORECASE)
_CONTEXTUAL_FILE_DELETE_RE = re.compile(
    r"^(?:l(?:oe|ö)sch(?:e)?|losch(?:e)?|entfern(?:e)?|delete|weg\s+damit)"
    r"(?:\s+(?:die|das|diese|diesen|datei|file|ordner|folder))?[\s.!?]*$",
    re.IGNORECASE,
)
_CONTEXTUAL_FILE_OPEN_RE = re.compile(
    r"^(?:oeffne|offne|open|zeig(?:e)?)"
    r"(?:\s+(?:die|das|diese|diesen|datei|file|ordner|folder))?[\s.!?]*$",
    re.IGNORECASE,
)


def _clip_context_path(path: str) -> str:
    # Nur typische Satzendzeichen und ')' entfernen. ']' und '}' duerfen in
    # Windows-Pfadnamen vorkommen (z.B. "C:\\Daten\\[2024]") und bleiben erhalten.
    return str(path or "").strip().rstrip(".,;:!?) ")


def _extract_context_paths(text: str) -> list[str]:
    return [_clip_context_path(match.group("path")) for match in _WINDOWS_PATH_RE.finditer(text or "") if match.group("path")]


def _normalize_intent_context(context: ConversationIntentContext | dict[str, Any] | None) -> ConversationIntentContext:
    if isinstance(context, ConversationIntentContext):
        return context
    if isinstance(context, dict):
        recent = context.get("recent_intents") or []
        entities = context.get("entities") or {}
        return ConversationIntentContext(
            recent_intents=[str(item) for item in recent if str(item).strip()][-3:],
            active_domain=str(context.get("active_domain") or ""),
            entities={str(k): str(v) for k, v in entities.items() if str(v).strip()},
        )
    return ConversationIntentContext()


def build_conversation_intent_context(history: list[dict] | None) -> ConversationIntentContext:
    """Build a compact context signal from recent chat history for pronoun-like commands."""
    recent_intents: list[str] = []
    entities: dict[str, str] = {}

    for msg in (history or [])[-8:]:
        content = str(msg.get("content") or "")
        lower = content.lower()

        action_match = _ACTION_HINT_RE.search(content)
        if action_match:
            action = action_match.group("action").lower()
            recent_intents.append(action)
            if action.startswith("file_") or action.startswith("folder_"):
                recent_intents.append("file_ops")

        paths = _extract_context_paths(content)
        if paths:
            entities["path"] = paths[-1]
            recent_intents.append("file_ops")
        elif _FILE_CONTEXT_WORD_RE.search(lower):
            recent_intents.append("file_ops")

    compact_intents: list[str] = []
    for intent in recent_intents:
        if intent and (not compact_intents or compact_intents[-1] != intent):
            compact_intents.append(intent)
    active_domain = "file_ops" if "file_ops" in compact_intents[-3:] else ""
    return ConversationIntentContext(
        recent_intents=compact_intents[-3:],
        active_domain=active_domain,
        entities=entities,
    )


def _try_contextual_intent(msg: str, context: ConversationIntentContext | dict[str, Any] | None) -> Optional[dict]:
    ctx = _normalize_intent_context(context)
    if ctx.active_domain != "file_ops" and "file_ops" not in ctx.recent_intents:
        return None
    path = _clip_context_path(ctx.entities.get("path", ""))
    if not path:
        return None
    filename = os.path.basename(path) or path

    if _CONTEXTUAL_FILE_DELETE_RE.match(msg):
        return {
            "action": "file_delete",
            "params": {"path": path},
            "message": f"Bereite Loeschen von '{filename}' vor.",
        }
    if _CONTEXTUAL_FILE_OPEN_RE.match(msg):
        return {
            "action": "file_open",
            "params": {"path": path},
            "message": f"Oeffne '{filename}'.",
        }
    return None


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


def _fold_intent_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.replace("ß", "ss")


def _is_weather_keyword(word: str) -> bool:
    token = str(word or "").lower().strip("?!.,:;")
    if token in {"wetter", "weather"}:
        return True
    if not token.startswith(("wet", "wea")):
        return False
    return bool(_fuzzy_match(token, {"wetter": "weather", "weather": "weather"}, 0.78))


def _is_hermes_status_note(value: str) -> bool:
    text = _fold_intent_text(value)
    return (
        "desktop-schritte pausiert" in text
        or "eingebaute ja/ok-zeilen" in text
        or "freigabe vorbereitet" in text
        or "freigabe offen fuer" in text
        or "freigabe offen fur" in text
        or "wartet auf freigabe" in text
        or "warte auf freigabe" in text
        or "bestaetigung noetig" in text
        or "bestatigung noetig" in text
        or "zahlen nicht als freigabe" in text
        or "zaehlen nicht als freigabe" in text
    )


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

_CODE_REQUEST_RE = re.compile(
    r"\b(?:python|code|skript|script|programmier\w*|entwickler\w*|software|klasse|funktion|"
    r"algorithmus|api|backend|frontend|async|thread|datenbank)\b",
    re.IGNORECASE,
)
_WRITE_REQUEST_RE = re.compile(
    r"\b(?:schreib\w*|schriebe|schreibe|erstell\w*|generier\w*|bau\w*|mach\w*)\b",
    re.IGNORECASE,
)
_PLAY_KEYWORDS = {"spiele", "spiel", "play", "hör", "höre", "hoer", "hoere", "abspielen"}
_PLAY_TYPO_KEYWORDS = {"dpsile", "spile", "siele", "psiele"}

_NUMBER_PATTERN = r"-?\d+(?:[,.]\d+)?"
_RE_PERCENT_MATH = re.compile(
    rf"^(?:(?:was|wieviel|wie\s*viel)\s+(?:sind|ist)\s+|berechne\s+|rechne\s+)?"
    rf"({_NUMBER_PATTERN})\s*(?:%|prozent)\s*(?:von|aus|of)\s*({_NUMBER_PATTERN})[\s?.!]*$",
    re.IGNORECASE,
)
_RE_BASIC_MATH = re.compile(
    rf"^(?:(?:was\s+ist|wieviel\s+ist|wie\s+viel\s+ist|berechne|rechne|calculate)\s+)?"
    rf"({_NUMBER_PATTERN})\s*([+\-*/xX:])\s*({_NUMBER_PATTERN})[\s?.!]*$",
    re.IGNORECASE,
)


def _parse_decimal(value: str) -> Decimal:
    return Decimal(str(value).replace(",", "."))


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    text = format(value.normalize(), "f").rstrip("0").rstrip(".")
    return text or "0"


def _try_math_intent(msg: str) -> Optional[dict]:
    """Handle tiny deterministic math locally instead of spending an AI call."""
    m = _RE_PERCENT_MATH.match(msg.strip())
    if m:
        try:
            percent = _parse_decimal(m.group(1))
            base = _parse_decimal(m.group(2))
            result = (percent / Decimal("100")) * base
        except (InvalidOperation, ValueError):
            return None
        return {
            "action": None,
            "params": {},
            "message": f"{_format_decimal(percent)} % von {_format_decimal(base)} = {_format_decimal(result)}.",
        }

    m = _RE_BASIC_MATH.match(msg.strip())
    if not m:
        return None

    try:
        left = _parse_decimal(m.group(1))
        op = m.group(2)
        right = _parse_decimal(m.group(3))
        if op == "+":
            result = left + right
        elif op == "-":
            result = left - right
        elif op in {"*", "x", "X"}:
            result = left * right
            op = "*"
        elif op in {"/", ":"}:
            if right == 0:
                return {"action": None, "params": {}, "message": "Das geht nicht: Division durch 0."}
            result = left / right
            op = "/"
        else:
            return None
    except (DivisionByZero, InvalidOperation, ValueError):
        return None

    return {
        "action": None,
        "params": {},
        "message": f"{_format_decimal(left)} {op} {_format_decimal(right)} = {_format_decimal(result)}.",
    }


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


def _looks_like_code_request(text: str) -> bool:
    """Keep code/text generation requests out of local app/music routing."""
    return bool(_CODE_REQUEST_RE.search(text or "") and _WRITE_REQUEST_RE.search(text or ""))


def _is_play_word(word: str) -> bool:
    """Conservative play-word match; avoid mapping 'schriebe' to 'spiele'."""
    value = str(word or "").lower().strip()
    if value in _PLAY_KEYWORDS or value in _PLAY_TYPO_KEYWORDS:
        return True
    if not value.startswith(("spi", "spie", "dpsi", "psi", "si")):
        return False
    return bool(_fuzzy_match(value, {k: k for k in (_PLAY_KEYWORDS | _PLAY_TYPO_KEYWORDS)}, 0.72))


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

    if _is_hermes_status_note(msg):
        return {
            "action": None,
            "params": {},
            "message": (
                "Das war nur der Hermes-Sicherheitshinweis. Sende die Freigabe als eigene kurze Nachricht: Ja. "
                "Danach kannst du den naechsten Hermes-Befehl separat schicken."
            ),
        }

    lower = msg.lower()
    words = lower.split()
    if len(words) < 2:
        return None  # Too short for compound — let regex handle single words
    if _looks_like_code_request(lower):
        return None

    # ── Compound command splitting ──
    parts = _split_compound(lower)

    # ── Spotify + Music detection (most common compound command) ──
    # "öffne spotify und spiele mero" / "spotify mero" / "spiel drake auf spotify"
    has_spotify = any("spotify" in w for w in words)
    play_idx = None
    for i, w in enumerate(words):
        if _is_play_word(w):
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
                "message": f"Starte Spotify mit '{query}'.",
            }
        else:
            return {
                "action": "spotify_open",
                "params": {"search": ""},
                "message": "Oeffne Spotify.",
            }

    if has_spotify and play_idx is None:
        # Just "öffne spotify" without play
        # Check if there's a query after spotify
        spotify_idx = next(i for i, w in enumerate(words) if "spotify" in w)
        query = _extract_after(words, spotify_idx)
        query = re.sub(r'\s*(?:auf|on|in)\s+spotify\s*', '', query, flags=re.IGNORECASE).strip()
        if query and len(query) > 1:
            return {
                "action": "spotify_open",
                "params": {"search": query},
                "message": f"Starte Spotify mit '{query}'.",
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
                "message": f"Starte Spotify mit '{query}'.",
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
                    if search_word != "search":
                        return None
                    if search_word == "search":
                        query = re.sub(r'^(?:such(?:e?)|search|google)\b[\s:]*(?:nach\s+)?', '', second, flags=re.IGNORECASE).strip()
                        if query:
                            return {
                                "action": "browser_open",
                                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                                "message": f"Suche im Web nach '{query}'.",
                            }

    # ── Weather with city (fuzzy) ──
    # "wie ist das wetter in hamburg" / "wetter hamburg" / "weather berlin"
    has_weather = any(_is_weather_keyword(w) for w in words if len(w.strip("?!.,:;")) > 3)

    if has_weather:
        # Extract city: everything after "wetter" / "in" / "für"
        city = ""
        for i, w in enumerate(words):
            if _is_weather_keyword(w):
                rest = " ".join(words[i + 1:])
                city = re.sub(r'^(?:in|für|fuer|for|von|heute|gerade|aktuell|jetzt)\s+', '', rest, flags=re.IGNORECASE).strip()
                break
        city = city.rstrip("?!.,")
        # Nachgestellte Zeit-/Fuellwoerter entfernen ("wetter in hamburg morgen"
        # -> Stadt "hamburg", nicht "hamburg morgen").
        city = re.sub(
            r'\s+(?:heute|morgen|gerade|jetzt|aktuell|draussen|draußen|bitte)$',
            '',
            city,
            flags=re.IGNORECASE,
        ).strip()
        if city and len(city) >= 2:
            return {
                "action": "weather_current",
                "params": {"city": city},
                "message": f"Lade Wetter fuer {city}.",
            }

    # ── Web search (BEFORE app open — "suche nach X" must not match app_open) ──
    # "suche nach X" / "google X" / "such X im internet"
    search_keywords = {"suche", "such", "google", "search", "recherchiere", "recherchier"}
    search_prefixes = {"bitte", "please"}
    for i, w in enumerate(words):
        token = w.strip("?!.,:;")
        if token in search_keywords:
            if i > 0 and any(prev.strip("?!.,:;") not in search_prefixes for prev in words[:i]):
                continue
            query = _extract_after(words, i)
            query = re.sub(r'^(?:nach|for|im\s+(?:internet|netz|web))\s+', '', query, flags=re.IGNORECASE).strip()
            query = query.rstrip("?!.,")
            if query and len(query) >= 2:
                return {
                    "action": "browser_open",
                    "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                    "message": f"Suche nach '{query}'.",
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
                            "message": "Oeffne Spotify.",
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
# Negative lookahead: "spiele X auf youtube" must fall through to _RE_YOUTUBE,
# nicht hier als Spotify-Suche "X auf youtube" abgefangen werden.
_RE_SPOTIFY = re.compile(
    r"^(?:spiele?|play|hör)\s+(?!.*\b(?:auf|on|in)\s+youtube\b)(.+?)(?:\s+(?:auf|on|in)\s+spotify)?$",
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

_RE_FRUSTRATION_NUDGE = re.compile(
    r"^(?:du\s+hund|du\s+nervst|du\s+bist\s+schlecht|du\s+bist\s+doof)[\s!.]*$",
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

def try_local_intent(user_message: str, context: ConversationIntentContext | dict[str, Any] | None = None) -> Optional[dict]:
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
    if _is_hermes_status_note(msg):
        return {
            "action": None,
            "params": {},
            "message": (
                "Das war nur der Hermes-Sicherheitshinweis. Sende die Freigabe als eigene kurze Nachricht: Ja. "
                "Danach kannst du den naechsten Hermes-Befehl separat schicken."
            ),
        }

    contextual_intent = _try_contextual_intent(msg, context)
    if contextual_intent:
        logger.info(f"[Intent:Context] Matched: {contextual_intent['action']} for '{msg[:60]}'")
        return contextual_intent

    math_result = _try_math_intent(msg)
    if math_result:
        return math_result

    # Skip messages that look like questions or conversations (multi-sentence)
    # but allow simple queries like "wie spät ist es?".
    # Muss VOR _try_smart_intent laufen, damit die fuzzy App-/Musik-/Such-Heuristik
    # klar konversationelle Eingaben nicht faelschlich als Aktion abfaengt.
    if msg.count(".") > 2 or msg.count("?") > 1:
        return None

    smart = _try_smart_intent(msg)
    if smart:
        logger.info(f"[Intent:Smart] Matched: {smart['action']} for '{msg[:60]}'")
        return smart

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
                "message": f"Starte Spotify mit '{query}'.",
            }

    # --- Web search compound ("öffne chrome und suche nach X" — BEFORE app_open!) ---
    m = _RE_WEB_SEARCH_2.match(msg)
    if m:
        query = m.group(1).strip()
        if query and len(query) <= 200:
            return {
                "action": "browser_open",
                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                "message": f"Suche im Web nach '{query}'.",
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
                "message": f"Oeffne {url}.",
            }

    # --- File open (BEFORE app_open — "öffne die datei X" must not match app_open) ---
    m = _RE_FILE_OPEN.match(msg)
    if m:
        filepath = m.group(1).strip()
        if filepath and len(filepath) <= 500:
            # Delegate to AI — file_open needs path validation and resolution
            return None

    # --- App Control ---
    m = _RE_APP_OPEN.match(msg)
    if m:
        app_name = m.group(1).strip()
        if app_name and len(app_name) <= 100:
            # Schnellpfad-Zusage einhalten (compiled regex only, kein blockierender
            # Dateisystem-Scan): find_app() wurde hier nur fuer den Anzeigenamen der
            # Nachricht genutzt; die eigentliche Aufloesung macht app_open -> launch_app
            # ohnehin nachgelagert in der Companion-Schicht.
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
            "message": "Lade deine Termine fuer heute.",
        }

    if _RE_CALENDAR_WEEK.match(msg):
        return {
            "action": "calendar_week",
            "params": {},
            "message": "Lade deine Wochentermine.",
        }

    if _RE_CALENDAR_NEXT.match(msg):
        return {
            "action": "calendar_next",
            "params": {},
            "message": "Suche deinen naechsten Termin.",
        }

    if _RE_CALENDAR_CREATE.match(msg):
        # Delegate to AI — calendar_create needs date/time/title params parsed from NLU
        return None

    # --- Email ---
    if _RE_EMAIL_SUMMARIZE.match(msg):
        return {
            "action": "email_summarize",
            "params": {},
            "message": "Fasse deine E-Mails zusammen.",
        }

    if _RE_EMAIL_READ.match(msg):
        return {
            "action": "email_read",
            "params": {"unread_only": True},
            "message": "Pruefe deine neuen E-Mails.",
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
        # "spiele lofi auf youtube" -> Gruppe enthaelt "lofi auf"; das offene
        # Verbindungswort am Ende entfernen, damit die Suche nur "lofi" enthaelt.
        query = re.sub(r'\s+(?:auf|on|in)$', '', query, flags=re.IGNORECASE).strip()
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
            "message": "Einen Moment, ich stelle dein Morgen-Briefing zusammen.",
        }

    # --- Greeting (time-aware with personality variation) ---
    if _RE_GREETING.match(msg):
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5
        if 6 <= hour < 11:
            greetings = [
                "Guten Morgen. Was steht heute an?",
                "Guten Morgen. Bereit fuer einen produktiven Tag?",
                "Morgen. Was steht als Naechstes an?",
            ]
            if is_weekend:
                greetings.append("Guten Morgen. Was steht am Wochenende an?")
        elif 11 <= hour < 14:
            greetings = [
                "Wie laeuft der Tag bis jetzt?",
                "Mittags-Check. Alles im Griff?",
                "Was kann ich tun?",
            ]
        elif 14 <= hour < 18:
            greetings = [
                "Was kann ich fuer dich tun?",
                "Was liegt als Naechstes an?",
                "Endspurt fuer heute. Was brauchst du?",
            ]
        elif 18 <= hour < 22:
            greetings = [
                "Guten Abend. Noch etwas zu erledigen?",
                "Feierabend-Modus oder noch etwas auf der Liste?",
                "Entspannter Abend oder noch produktiv?",
            ]
        else:
            greetings = [
                "Noch wach? Was brauchst du?",
                "Nachtschicht? Ich bin da.",
                "Noch wach? Was gibt es?",
            ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(greetings),
        }

    # --- How are you (varied responses) ---
    if _RE_HOW_ARE_YOU.match(msg):
        responses = [
            "Alles ruhig. Was machen wir?",
            "Bin bereit. Womit starten wir?",
            "Laeuft. Sag an.",
            "Einsatzbereit. Was brauchst du?",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Thanks (varied) ---
    if _RE_THANKS.match(msg):
        responses = [
            "Immer gerne.",
            "Klar, dafuer bin ich da.",
            "Gern.",
            "Gute Zusammenarbeit.",
            "Gern geschehen. Wenn du mich brauchst, bin ich da.",
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
                "Gute Nacht. Schlaf gut, ich bin morgen wieder da.",
                "Gute Nacht. Gute Erholung, bis morgen.",
                "Schlaf gut. Ich bin morgen wieder bereit.",
            ]
        else:
            byes = [
                "Bis dann. Ich bin da, wenn du mich brauchst.",
                "Bis spaeter. Ruf mich, wenn du etwas brauchst.",
                "Bis spaeter. War mir ein Vergnuegen.",
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
            "message": "Ich bin Lexa, deine API-gestuetzte Windows-Assistentin. Ich kann deinen PC steuern, "
                       "deinen Alltag organisieren, Dateien verwalten, Musik steuern und "
                       "dir ueber Sprache, Chat und lokale Arbeitsablaeufe helfen.",
        }

    # --- What can you do ---
    if _RE_WHAT_CAN_YOU.match(msg):
        return {
            "action": None,
            "params": {},
            "message": "Ich kann dir in mehreren Bereichen helfen:\n\n"
                       "- **Musik & Medien**: Spotify steuern, YouTube, Lautstaerke\n"
                       "- **PC-Kontrolle**: Apps oeffnen/schliessen, Screenshots, System-Info\n"
                       "- **Produktivitaet**: Todos, Pomodoro-Timer, Gewohnheiten, Notizen\n"
                       "- **Kalender**: Termine heute/Woche, naechster Termin, Termine erstellen\n"
                       "- **Wetter**: Aktuelles Wetter, Vorhersage, Regenwarnung\n"
                       "- **Erinnerungen**: Erstellen, anzeigen, wiederkehrend\n"
                       "- **E-Mail**: Lesen, senden, zusammenfassen\n"
                       "- **Dateien**: Suchen, oeffnen, Downloads, ZIP/PDF, Backups\n"
                       "- **Web**: Browser, YouTube, Preisvergleich\n"
                       "- **Dev-Tools**: Git, Docker, API-Tester\n"
                       "- **Morgen-Briefing**: Sag 'Morgen Lexa' fuer Kalender, Wetter und Todos\n\n"
                       "Sag einfach, was du brauchst.",
        }

    # --- Compliments ---
    if _RE_COMPLIMENT.match(msg):
        responses = [
            "Danke. Das motiviert mich, noch besser zu werden.",
            "Das freut mich. Zusammen arbeiten wir gut.",
            "Danke. Ich gebe mir Muehe, nuetzlich zu bleiben.",
            "Danke. Sag Bescheid, wenn du etwas brauchst.",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Insults (graceful handling) ---
    if _RE_FRUSTRATION_NUDGE.match(msg) or _RE_INSULT.match(msg):
        responses = [
            "Verstanden. Was soll ich konkret besser machen?",
            "Sag mir konkret, was anders laufen soll.",
            "Fair genug. Sag mir, was du brauchst, und ich arbeite es sauber ab.",
            "Ich arbeite daran. Was kann ich jetzt konkret fuer dich tun?",
        ]
        return {
            "action": None,
            "params": {},
            "message": random.choice(responses),
        }

    # --- Joke ---
    if _RE_JOKE.match(msg):
        jokes = [
            "Was sagt ein IT-ler, wenn er aus dem Fenster schaut? Fenster aktualisieren.",
            "Ich wollte einen Witz ueber RAM erzaehlen, aber ich habe ihn vergessen.",
            "Warum trinken Programmierer keinen Kaffee? Weil Java schon genug ist.",
            "Es gibt 10 Arten von Menschen: die, die Binaer verstehen, und die, die es nicht tun.",
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
            "message": "Ich bin eine API-gestuetzte KI-App aus diesem Projekt. Mein Wissen und meine Faehigkeiten haengen von den konfigurierten APIs, Modellen, Tools und lokalen Integrationen ab.",
        }

    # --- Bored ---
    if _RE_BORED.match(msg):
        bored_suggestions = [
            "Ein paar sinnvolle Optionen: Musik starten, Todos pruefen, Notizen sortieren, Downloads aufraeumen oder einen 25-Minuten-Fokusblock starten.",
            "Ich kann Musik starten, deine Todos pruefen, eine kurze Aufgabe strukturieren oder einen Fokus-Timer setzen.",
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
            "message": "Lade deine letzten Downloads.",
        }

    # --- Todo list shortcut ---
    if _RE_TODO_LIST.match(msg):
        return {
            "action": "todo_list",
            "params": {},
            "message": "Lade deine Todos.",
        }

    # --- Process list shortcut ---
    if _RE_PROCESS_LIST.match(msg):
        return {
            "action": "process_list",
            "params": {},
            "message": "Lade die Prozessliste.",
        }

    # --- Clipboard ---
    if _RE_CLIPBOARD_PASTE.match(msg):
        return {
            "action": "clipboard_read",
            "params": {},
            "message": "Schaue in die Zwischenablage.",
        }

    # --- Web search simple ("suche nach X", "google X") ---
    m = _RE_WEB_SEARCH.match(msg)
    if m:
        query = m.group(1).strip()
        if query and len(query) <= 200:
            return {
                "action": "browser_open",
                "params": {"url": f"https://www.google.com/search?q={quote_plus(query)}"},
                "message": f"Suche im Web nach '{query}'.",
            }

    # --- Weather with CITY slot (BEFORE generic weather — "wetter in hamburg" must extract city) ---
    m = _RE_WEATHER_CITY.match(msg)
    if m:
        city = m.group(1).strip()
        # Nachgestellte Zeit-/Fuellwoerter entfernen ("wetter in hamburg morgen"
        # -> Stadt "hamburg", nicht "hamburg morgen").
        city = re.sub(
            r"\s+(?:heute|morgen|gerade|jetzt|aktuell|draussen|draußen|bitte)$",
            "",
            city,
            flags=re.IGNORECASE,
        ).strip()
        if city and len(city) >= 2:
            return {
                "action": "weather_current",
                "params": {"city": city},
                "message": f"Lade Wetter fuer {city}.",
            }

    # --- Weather forecast (BEFORE current — "wetter morgen" must not match current) ---
    if _RE_WEATHER_FORECAST.match(msg):
        return {
            "action": "weather_forecast",
            "params": {},
            "message": "Lade die Wettervorhersage.",
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
