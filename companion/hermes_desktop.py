"""Hermes desktop task controller.

This module is the deterministic desktop layer between Hermes' natural-language
task and Lexa's guarded PC-control tools. It deliberately separates planning
from execution: read-only observation happens immediately, but clicks/typing/
hotkeys are only prepared as a pending Lexa confirmation.
"""

from __future__ import annotations

import ctypes
import re
import subprocess
import time
import unicodedata
from typing import Any

from backend.shared import set_pending_confirmation
from companion import desktop_control, desktop_engine, ocr, ui_automation

MAX_HERMES_DESKTOP_STEPS = 8
MAX_HERMES_DESKTOP_MESSAGE_CHARS = 1600

_CLICK_WORDS = (
    "klick",
    "klicke",
    "klicken",
    "kilcke",
    "kilck",
    "klcike",
    "klcik",
    "click",
    "drueck",
    "druecke",
    "druck",
    "drucke",
)
_FIND_WORDS = ("finde", "find", "suche", "such", "zeige", "pruefe", "prufe")
_OBSERVE_TERMS = (
    "was siehst",
    "was erkennst",
    "lies die echten windows-controls",
    "echte windows controls",
    "windows-controls",
    "windows controls",
    "klickbare buttons",
    "klickbare controls",
    "aktuelles fenster analys",
)
_SCREEN_TEXT_TERMS = (
    "bildschirmtext",
    "text auf dem bildschirm",
    "fenstertext",
    "lies den fenstertext",
    "lese den fenstertext",
    "lies den bildschirm",
    "lese den bildschirm",
    "lies den text",
    "lese den text",
    "lies mir den text",
    "lese mir den text",
    "lies mir bitte den text",
    "lese mir bitte den text",
    "lies den text vor",
    "lese den text vor",
    "lies bitte den text",
    "lese bitte den text",
    "lies kurz den text",
    "lese kurz den text",
    "lies mal den text",
    "lese mal den text",
    "zeig mir den text",
    "zeige mir den text",
    "zeig den text",
    "zeige den text",
    "was steht",
    "read text",
    "ocr",
)
_SCROLL_WORDS = ("scroll", "scrolle", "scrollen", "rolle")
_WAIT_WORDS = ("warte", "warten", "wait")
_SELECT_ALL_TERMS = (
    "markiere alles",
    "markier alles",
    "alles markieren",
    "waehle alles aus",
    "wahle alles aus",
    "select all",
)
_SAVE_TERMS = (
    "speichere",
    "speicher",
    "sichere",
    "save",
)
_SAVE_AS_TERMS = (
    "speichere unter",
    "speicher unter",
    "speichern unter",
    "save as",
)
_UNDO_TERMS = (
    "rueckgaengig",
    "rueckgangig",
    "ruckgaengig",
    "ruckgangig",
    "undo",
)
_COPY_TERMS = (
    "kopiere",
    "kopier",
    "copy",
)
_CUT_TERMS = (
    "schneide",
    "schneid",
    "ausschneiden",
    "cut",
)
_PASTE_TERMS = (
    "fuege ein",
    "fuge ein",
    "paste",
)
_PRINT_TERMS = (
    "print",
    "ausdrucken",
    "drucke aus",
    "druck aus",
)
_OPEN_FILE_TERMS = (
    "oeffne datei",
    "offne datei",
    "datei oeffnen",
    "datei offnen",
    "open file",
)
_NEW_FILE_TERMS = (
    "neue datei",
    "neue file",
    "datei neu",
    "new file",
)
_NEW_FOLDER_TERMS = (
    "neuer ordner",
    "neuen ordner",
    "neue ordner",
    "ordner neu",
    "erstelle neuen ordner",
    "erstell neuen ordner",
    "create new folder",
    "new folder",
)
_NEW_TAB_TERMS = (
    "neuer tab",
    "neuen tab",
    "neues tab",
    "neue registerkarte",
    "neuen registerkarte",
    "tab neu",
    "registerkarte neu",
    "new tab",
)
_NEXT_TAB_TERMS = (
    "nachster tab",
    "nachsten tab",
    "naechster tab",
    "naechsten tab",
    "nachste registerkarte",
    "nachsten registerkarte",
    "naechste registerkarte",
    "naechsten registerkarte",
    "tab weiter",
    "next tab",
)
_PREVIOUS_TAB_TERMS = (
    "vorheriger tab",
    "vorherigen tab",
    "voriger tab",
    "vorigen tab",
    "vorherige registerkarte",
    "vorherigen registerkarte",
    "vorige registerkarte",
    "vorigen registerkarte",
    "tab zurueck",
    "tab zuruck",
    "previous tab",
)
_CLOSE_FILE_TERMS = (
    "schliesse datei",
    "schliesse file",
    "datei schliessen",
    "schliesse tab",
    "tab schliessen",
    "close file",
    "close tab",
)
_FIND_BOX_TERMS = (
    "oeffne suche",
    "offne suche",
    "suche oeffnen",
    "suche offnen",
    "oeffne suchfeld",
    "offne suchfeld",
    "suchfeld oeffnen",
    "suchfeld offnen",
    "oeffne suchleiste",
    "offne suchleiste",
    "suchleiste oeffnen",
    "suchleiste offnen",
    "open search",
    "open find",
)
_ADDRESS_BAR_TERMS = (
    "oeffne adressleiste",
    "offne adressleiste",
    "adressleiste oeffnen",
    "adressleiste offnen",
    "fokussiere adressleiste",
    "adressleiste fokussieren",
    "oeffne url leiste",
    "offne url leiste",
    "url leiste oeffnen",
    "url leiste offnen",
    "fokussiere url leiste",
    "url leiste fokussieren",
    "open address bar",
    "focus address bar",
    "open url bar",
    "focus url bar",
    "open location bar",
    "focus location bar",
)
_REFRESH_TARGET_TERMS = (
    "seite",
    "page",
    "tab",
    "fenster",
    "window",
    "browser",
)
_NAVIGATION_TARGET_TERMS = (
    "seite",
    "page",
    "tab",
    "fenster",
    "window",
    "browser",
)
_ZOOM_IN_TERMS = (
    "zoome rein",
    "zoom rein",
    "zoome hinein",
    "zoom hinein",
    "zoom in",
    "vergroessere zoom",
    "vergrossere zoom",
    "zoom vergroessern",
    "zoom vergrossern",
)
_ZOOM_OUT_TERMS = (
    "zoome raus",
    "zoom raus",
    "zoome heraus",
    "zoom heraus",
    "zoom out",
    "verkleinere zoom",
    "zoom verkleinern",
)
_ZOOM_RESET_TERMS = (
    "zoom zuruecksetzen",
    "zoom zurucksetzen",
    "setze zoom zurueck",
    "setze zoom zuruck",
    "zoom reset",
    "reset zoom",
    "zoom normal",
    "normaler zoom",
    "standard zoom",
)
_FULLSCREEN_TERMS = (
    "vollbild",
    "vollbildmodus",
    "fullscreen",
    "full screen",
)
_HOTKEY_SINGLE_KEYS = (
    "enter",
    "return",
    "tab",
    "esc",
    "escape",
    "backspace",
    "delete",
    "del",
    "space",
    "left",
    "right",
    "up",
    "down",
    "pageup",
    "pagedown",
    "home",
    "end",
    "insert",
)
_HOTKEY_MODIFIER_KEYS = (
    "ctrl",
    "control",
    "strg",
    "steuerung",
    "alt",
    "shift",
    "umschalt",
    "win",
    "meta",
    "cmd",
)
_HOTKEY_KEY_ALIASES = {
    "strg": "ctrl",
    "control": "ctrl",
    "steuerung": "ctrl",
    "umschalt": "shift",
    "escape": "esc",
    "links": "left",
    "rechts": "right",
    "oben": "up",
    "unten": "down",
    "pfeillinks": "left",
    "pfeilrechts": "right",
    "pfeiloben": "up",
    "pfeilunten": "down",
    "pfeilhoch": "up",
    "pfeilrunter": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "arrowup": "up",
    "arrowdown": "down",
    "bildauf": "pageup",
    "bildhoch": "pageup",
    "bildab": "pagedown",
    "bildrunter": "pagedown",
    "pos1": "home",
    "anfang": "home",
    "ende": "end",
    "einfg": "insert",
    "einfuegen": "insert",
    "eingabe": "enter",
    "eingabetaste": "enter",
    "entf": "delete",
    "loeschen": "delete",
    "loschen": "delete",
    "ruecktaste": "backspace",
    "rucktaste": "backspace",
    "leer": "space",
    "leertaste": "space",
}
_HOTKEY_CONNECTOR_TOKENS = {"und", "plus", "mit"}
_HOTKEY_CANONICAL_MODIFIERS = {"ctrl", "control", "alt", "shift", "win", "meta", "cmd"}
_HOTKEY_PHRASE_ALIASES = {
    "pfeil links": "left",
    "pfeil rechts": "right",
    "pfeil oben": "up",
    "pfeil unten": "down",
    "pfeil hoch": "up",
    "pfeil runter": "down",
    "arrow left": "left",
    "arrow right": "right",
    "arrow up": "up",
    "arrow down": "down",
    "bild auf": "pageup",
    "bild hoch": "pageup",
    "bild ab": "pagedown",
    "bild runter": "pagedown",
    "page up": "pageup",
    "page down": "pagedown",
}
_INLINE_CONFIRM_TERMS = (
    "ich bestaetige",
    "ich bestatige",
    "ich bestaetige es",
    "ich bestatige es",
    "bestaetige",
    "bestatige",
    "bestaetige es",
    "bestatige es",
    "ausfuehren",
    "ausfuhren",
    "freigabe",
    "confirm",
)
_SHORT_CONFIRM_TERMS = {
    "ja", "yes", "ok", "okay",
    "bestaetige", "bestatige", "ausfuehren", "ausfuhren",
}
_CONFIRM_ONLY_TERMS = frozenset(_SHORT_CONFIRM_TERMS | {
    "ich bestaetige",
    "ich bestatige",
    "ich bestaetige es",
    "ich bestatige es",
    "bestaetige es",
    "bestatige es",
})
_CANCEL_ONLY_TERMS = {
    "nein",
    "no",
    "abbrechen",
    "abbruch",
    "cancel",
    "stop",
    "stopp",
    "nicht ausfuehren",
    "nicht ausfuhren",
}
_MUTATING_DESKTOP_KINDS = {"scroll", "click", "type", "hotkey"}
_ACTION_START_WORDS = (
    "/?hermes",
    "lexa",
    "klick",
    "kilck",
    "klcik",
    "click",
    "tippe",
    "tipp",
    "schreibe",
    "schreib",
    "finde",
    "find",
    "suche",
    "such",
    "fokussiere",
    "fokus",
    "focus",
    "zeige",
    "pruefe",
    "prufe",
    "lies",
    "lese",
    "was",
    "markiere",
    "markier",
    "waehle",
    "wahle",
    "select",
    "ersetze",
    "ersetz",
    "replace",
    "loesche",
    "losche",
    "leere",
    "clear",
    "speichere",
    "speicher",
    "speichern",
    "sichere",
    "save",
    "rueckgaengig",
    "rueckgangig",
    "ruckgaengig",
    "ruckgangig",
    "undo",
    "kopiere",
    "kopier",
    "copy",
    "schneide",
    "schneid",
    "ausschneiden",
    "cut",
    "fuege",
    "fuge",
    "paste",
    "print",
    "ausdrucken",
    "oeffne",
    "offne",
    "open",
    "adressleiste",
    "url",
    "erstelle",
    "erstell",
    "create",
    "ordner",
    "folder",
    "neue",
    "neuer",
    "neuen",
    "neues",
    "nachster",
    "nachsten",
    "naechster",
    "naechsten",
    "vorheriger",
    "vorherigen",
    "voriger",
    "vorigen",
    "wechsle",
    "wechsele",
    "wechsel",
    "wechseln",
    "neu",
    "new",
    "schliesse",
    "schliess",
    "close",
    "aktualisiere",
    "aktualisier",
    "aktualisieren",
    "refresh",
    "reload",
    "lade",
    "gehe",
    "geh",
    "navigiere",
    "navigate",
    "zurueck",
    "zuruck",
    "back",
    "vorwaerts",
    "vorwarts",
    "forward",
    "zoome",
    "zoom",
    "vergroessere",
    "vergroesser",
    "verkleinere",
    "verkleiner",
    "vollbild",
    "vollbildmodus",
    "fullscreen",
    "beende",
    "verlasse",
    "drueck",
    "druecke",
    "druck",
    "drucke",
    "hotkey",
    "scroll",
    "scrolle",
    "warte",
    "wait",
)
_INLINE_CONFIRM_PREFIX_RE = re.compile(
    r"^\s*(?:ja|yes|ok|okay|(?:ich\s+)?(?:bestaetige|bestatige)(?:\s+es)?|ausfuehren|ausfuhren|confirm)[,:\s-]+"
    r"(?=(?:" + "|".join(_ACTION_START_WORDS) + r")\b)",
)
# Nur echte deiktische Verweiswoerter: Artikel (das/den/die) wurden entfernt,
# weil sie bei kurzen Klickzielen wie "klicke das" faelschlich das zuletzt
# gefundene Control referenziert und dabei die Mehrdeutigkeitspruefung
# uebersprungen haben. Artikel werden jetzt als (ggf. unvollstaendiges) echtes
# Ziel behandelt und durchlaufen weiterhin die Mehrdeutigkeitspruefung.
_DEICTIC_TERMS = {"darauf", "drauf", "daruf", "es", "ihn", "sie"}
_ACTION_SPLIT_RE = re.compile(
    r"\s*(?:[.;!?]\s+(?=(?:/?hermes\b|ja|yes|ok|okay|(?:ich\s+)?best(?:ae|a|\u00e4)tige(?:\s+es)?|ausf(?:ue|u|\u00fc)hren|confirm|klick|kilck|klcik|click|tippe|tipp|schreibe|schreib|"
    r"finde|find|suche|such|fokussiere|fokus|focus|zeige|pruefe|prufe|lies|lese|was|markiere|markier|waehle|wahle|select|ersetze|ersetz|replace|loesche|losche|leere|clear|speichere|speicher|speichern|sichere|save|rueckgaengig|rueckgangig|ruckgaengig|ruckgangig|undo|kopiere|kopier|copy|schneide|schneid|ausschneiden|cut|fuege|fuge|paste|print|ausdrucken|oeffne|offne|open|adressleiste|url|erstelle|erstell|create|ordner|folder|neue|neuer|neuen|neues|nachster|nachsten|naechster|naechsten|vorheriger|vorherigen|voriger|vorigen|wechsle|wechsele|wechsel|wechseln|neu|new|schlie(?:ss|\u00df)(?:e|en)?|schliess(?:e|en)?|close|aktualisiere|aktualisier|aktualisieren|refresh|reload|lade|gehe|geh|navigiere|navigate|zurueck|zuruck|back|vorwaerts|vorwarts|forward|zoome|zoom|vergroessere|vergroesser|verkleinere|verkleiner|vollbild|vollbildmodus|fullscreen|beende|verlasse|drueck|druecke|druck|drucke|"
    r"hotkey|scroll|scrolle|warte|wait)\b)|\bund\s+dann\s+|\bdanach\s+|\bthen\s+|"
    r"\bund\s+(?=(?:klick|kilck|klcik|click|tippe|tipp|schreibe|schreib|"
    r"markiere|markier|waehle|wahle|select|ersetze|ersetz|replace|loesche|losche|leere|clear|speichere|speicher|speichern|sichere|save|rueckgaengig|rueckgangig|ruckgaengig|ruckgangig|undo|kopiere|kopier|copy|schneide|schneid|ausschneiden|cut|fuege|fuge|paste|print|ausdrucken|oeffne|offne|open|adressleiste|url|erstelle|erstell|create|ordner|folder|neue|neuer|neuen|neues|nachster|nachsten|naechster|naechsten|vorheriger|vorherigen|voriger|vorigen|wechsle|wechsele|wechsel|wechseln|neu|new|schlie(?:ss|\u00df)(?:e|en)?|schliess(?:e|en)?|close|aktualisiere|aktualisier|aktualisieren|refresh|reload|lade|gehe|geh|navigiere|navigate|zurueck|zuruck|back|vorwaerts|vorwarts|forward|zoome|zoom|vergroessere|vergroesser|verkleinere|verkleiner|vollbild|vollbildmodus|fullscreen|beende|verlasse|drueck|druecke|druck|drucke|hotkey|scroll|scrolle|warte|wait)\b))",
    flags=re.IGNORECASE,
)


def _ascii_fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return (
        text
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _window_match_fold(value: str) -> str:
    text = _ascii_fold(value)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _window_query_aliases(query: str) -> set[str]:
    folded = _window_match_fold(query)
    aliases = {folded} if folded else set()
    tokens = set(folded.split())
    if "notepad" in tokens:
        aliases.add("editor")
    if folded == "editor":
        aliases.add("notepad")
    return {alias for alias in aliases if alias}


def _window_title_matches_query(title: str, query: str) -> bool:
    folded_title = _window_match_fold(title)
    folded_query = _window_match_fold(query)
    if not folded_title or not folded_query:
        return False
    if folded_query in folded_title or folded_title in folded_query:
        return True
    for alias in _window_query_aliases(folded_query):
        if alias in folded_title:
            return True
    return False


def _clean_instruction(value: str) -> str:
    text = re.sub(r"^\s*/?hermes[:,\s-]*", "", str(value or "").strip(), flags=re.IGNORECASE)
    text = re.sub(
        r"^\s*lexa\s+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes[:,\s-]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip(" \t\r\n.;")


def _strip_inline_confirmation_prefix(value: str) -> tuple[str, bool]:
    text = str(value or "").strip()
    match = _INLINE_CONFIRM_PREFIX_RE.match(_ascii_fold(text))
    if not match:
        return text, False
    return text[match.end():].strip(), True


def _extract_quoted_text(value: str) -> str:
    quote_pairs = (
        ('"', '"'),
        ("'", "'"),
        (chr(0x201c), chr(0x201d)),  # left/right double quotation marks
        (chr(0x201e), chr(0x201c)),  # German low/high double quotation marks
        (chr(0x201a), chr(0x2018)),  # low/high single quotation marks
        (chr(0x00ab), chr(0x00bb)),  # guillemets
    )
    for opener, closer in quote_pairs:
        pattern = re.escape(opener) + r"(?P<text>.+?)" + re.escape(closer)
        match = re.search(pattern, value)
        if match:
            return match.group("text").strip()
    return ""


def _expand_replace_text_instruction(instruction: str) -> list[str]:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return [instruction]
    if not re.search(r"\b(?:ersetze|ersetz|replace)\b", text):
        return [instruction]
    if not re.search(r"\b(?:text|inhalt|alles)\b", text):
        return [instruction]
    if not re.search(r"\b(?:durch|mit|with)\b", text):
        return [instruction]
    replacement = _extract_quoted_text(instruction)
    if not replacement:
        return [instruction]
    window = _extract_window_hint(instruction)
    window_suffix = f" im Fenster {window}" if window else ""
    return [
        f"markiere alles{window_suffix}",
        f'tippe "{replacement}"{window_suffix}',
    ]


def _expand_clear_text_instruction(instruction: str) -> list[str]:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return [instruction]
    if not re.search(r"\b(?:loesche|losche|leere|clear)\b", text):
        return [instruction]
    if not re.search(r"\b(?:text|inhalt|alles)\b", text):
        return [instruction]
    window = _extract_window_hint(instruction)
    window_suffix = f" im Fenster {window}" if window else ""
    return [
        f"markiere alles{window_suffix}",
        f"druecke Entf{window_suffix}",
    ]


def _expand_copy_text_instruction(instruction: str) -> list[str]:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return [instruction]
    if not any(re.search(rf"\b{re.escape(term)}\b", text) for term in _COPY_TERMS):
        return [instruction]
    if not re.search(r"\b(?:text|inhalt|alles)\b", text):
        return [instruction]
    window = _extract_window_hint(instruction)
    window_suffix = f" im Fenster {window}" if window else ""
    return [
        f"markiere alles{window_suffix}",
        f"druecke Strg+C{window_suffix}",
    ]


def _expand_cut_text_instruction(instruction: str) -> list[str]:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return [instruction]
    if not any(re.search(rf"\b{re.escape(term)}\b", text) for term in _CUT_TERMS):
        return [instruction]
    if not re.search(r"\b(?:text|inhalt|alles)\b", text):
        return [instruction]
    window = _extract_window_hint(instruction)
    window_suffix = f" im Fenster {window}" if window else ""
    return [
        f"markiere alles{window_suffix}",
        f"druecke Strg+X{window_suffix}",
    ]


def _has_inline_confirmation_fragment(value: str) -> bool:
    folded = re.sub(r"\s+", " ", _ascii_fold(value)).strip()
    if _has_inline_cancel_fragment(folded):
        return False
    if folded in _SHORT_CONFIRM_TERMS:
        return True
    return any(re.search(rf"\b{re.escape(term)}\b", folded) for term in _INLINE_CONFIRM_TERMS)


def _has_inline_cancel_fragment(value: str) -> bool:
    folded = re.sub(r"\s+", " ", _ascii_fold(value)).strip()
    if folded in _CANCEL_ONLY_TERMS:
        return True
    return bool(
        re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b.{0,24}\b(?:ausfuehren|ausfuhren|machen|klicken|klicke|click|tippen|tippe|schreiben|schreibe|druecken|druecke|scrollen|scrolle)\b", folded)
        or re.search(r"\b(?:fuehre|fuhre|mach(?:e)?|klick(?:e)?|click|tipp(?:e)?|schreib(?:e)?|drueck(?:e)?|druck(?:e)?|scroll(?:e)?)\b.{0,24}\b(?:nicht|nie)\b", folded)
    )


def _message_has_inline_preapproval(message: str) -> bool:
    raw = str(message or "")[:MAX_HERMES_DESKTOP_MESSAGE_CHARS].replace("\r\n", "\n")
    raw = re.sub(r"(?<!^)(?=/hermes\b)", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?<!^)(?=\bhermes\s*[:,])", "\n", raw, flags=re.IGNORECASE)
    for line in raw.split("\n"):
        line = _clean_instruction(line)
        if not line:
            continue
        fragments = [frag.strip() for frag in _ACTION_SPLIT_RE.split(line) if frag.strip()] or [line]
        for fragment in fragments:
            cleaned = _clean_instruction(fragment)
            if _has_inline_confirmation_fragment(cleaned):
                return True
            _, stripped_prefix = _strip_inline_confirmation_prefix(cleaned)
            if stripped_prefix:
                return True
    return False


def _message_has_inline_cancel(message: str) -> bool:
    raw = str(message or "")[:MAX_HERMES_DESKTOP_MESSAGE_CHARS].replace("\r\n", "\n")
    raw = re.sub(r"(?<!^)(?=/hermes\b)", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?<!^)(?=\bhermes\s*[:,])", "\n", raw, flags=re.IGNORECASE)
    for line in raw.split("\n"):
        line = _clean_instruction(line)
        if not line:
            continue
        fragments = [frag.strip() for frag in _ACTION_SPLIT_RE.split(line) if frag.strip()] or [line]
        if any(_has_inline_cancel_fragment(_clean_instruction(fragment)) for fragment in fragments):
            return True
    return False


def split_hermes_desktop_instructions(message: str) -> list[str]:
    """Split a user prompt into independent Hermes desktop instructions."""
    raw = str(message or "")[:MAX_HERMES_DESKTOP_MESSAGE_CHARS].replace("\r\n", "\n")
    raw = re.sub(r"(?<!^)(?=/hermes\b)", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?<!^)(?=\bhermes\s*[:,])", "\n", raw, flags=re.IGNORECASE)
    parts: list[str] = []
    for line in raw.split("\n"):
        line = _clean_instruction(line)
        if not line:
            continue
        fragments = [frag.strip() for frag in _ACTION_SPLIT_RE.split(line) if frag.strip()]
        if not fragments:
            fragments = [line]
        for fragment in fragments:
            cleaned = _clean_instruction(fragment)
            folded_cleaned = re.sub(r"\s+", " ", _ascii_fold(cleaned)).strip()
            if folded_cleaned in _CONFIRM_ONLY_TERMS or folded_cleaned in _CANCEL_ONLY_TERMS:
                continue
            cleaned, _ = _strip_inline_confirmation_prefix(cleaned)
            cleaned = _clean_instruction(cleaned)
            if cleaned:
                for replace_expanded in _expand_replace_text_instruction(cleaned):
                    for clear_expanded in _expand_clear_text_instruction(replace_expanded):
                        for copy_expanded in _expand_copy_text_instruction(clear_expanded):
                            for expanded in _expand_cut_text_instruction(copy_expanded):
                                if expanded:
                                    parts.append(expanded)
                                    if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
                                        break
                            if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
                                break
                        if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
                            break
                    if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
                        break
            if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
                break
        if len(parts) >= MAX_HERMES_DESKTOP_STEPS:
            break
    return parts


def is_multi_step_desktop_prompt(message: str) -> bool:
    instructions = split_hermes_desktop_instructions(message)
    if len(instructions) < 2:
        return False
    actionable = 0
    for instruction in instructions:
        kind = classify_desktop_instruction(instruction)
        if kind != "unknown":
            actionable += 1
    return actionable >= 2


def _hotkey_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _ascii_fold(value))


def _canonical_hotkey_token(token: str) -> str:
    return _HOTKEY_KEY_ALIASES.get(token, token)


def _is_hotkey_modifier(token: str) -> bool:
    return _canonical_hotkey_token(token) in _HOTKEY_CANONICAL_MODIFIERS


def _is_hotkey_terminal_key(token: str) -> bool:
    canonical = _canonical_hotkey_token(token)
    return (
        canonical in _HOTKEY_SINGLE_KEYS
        or re.fullmatch(r"[a-z0-9]", canonical) is not None
        or re.fullmatch(r"f(?:[1-9]|1[0-2])", canonical) is not None
    )


def _is_paste_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:hotkey|tastenkombi|druecke|drueck|drucke|druck|press)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _PASTE_TERMS)


def _is_print_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    if re.search(
        r"\b(?:auf|button|btn|knopf|taste|enter|tab|esc|escape|entf|delete|del|"
        r"leertaste|space|strg|ctrl|control|alt|shift|umschalt|win|pfeil|pos1|"
        r"bild|ruecktaste|rucktaste|einfuegen|einfg)\b",
        text,
    ):
        return False
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _PRINT_TERMS):
        return True
    return re.search(r"\bdrucke?\b", text) is not None


def _is_open_file_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _OPEN_FILE_TERMS)


def _is_new_file_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _NEW_FILE_TERMS)


def _is_new_folder_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _NEW_FOLDER_TERMS)


def _is_new_tab_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _NEW_TAB_TERMS)


def _is_next_tab_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _NEXT_TAB_TERMS)


def _is_previous_tab_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _PREVIOUS_TAB_TERMS)


def _is_close_file_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _CLOSE_FILE_TERMS)


def _is_find_box_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _FIND_BOX_TERMS)


def _is_address_bar_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _ADDRESS_BAR_TERMS)


def _is_refresh_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    target_pattern = r"(?:%s)" % "|".join(re.escape(term) for term in _REFRESH_TARGET_TERMS)
    return bool(
        re.search(rf"\b(?:aktualisiere|aktualisier|refresh|reload)\s+(?:die\s+|den\s+|das\s+)?{target_pattern}\b", text)
        or re.search(rf"\b{target_pattern}\s+(?:aktualisieren|refresh|reload)\b", text)
        or re.search(rf"\b(?:lade|reload)\s+(?:die\s+|den\s+|das\s+)?{target_pattern}\s+neu\b", text)
        or re.search(rf"\b{target_pattern}\s+neu\s+laden\b", text)
    )


def _has_navigation_target(text: str) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _NAVIGATION_TARGET_TERMS)


def _is_browser_back_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return _has_navigation_target(text) and re.search(r"\b(?:zurueck|zuruck|back)\b", text) is not None


def _is_browser_forward_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return _has_navigation_target(text) and re.search(r"\b(?:vorwaerts|vorwarts|forward)\b", text) is not None


def _is_zoom_in_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _ZOOM_IN_TERMS)


def _is_zoom_out_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _ZOOM_OUT_TERMS)


def _is_zoom_reset_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _ZOOM_RESET_TERMS)


def _is_fullscreen_command(instruction: str) -> bool:
    text = _ascii_fold(instruction)
    if re.search(r"\b(?:nicht|nie|kein(?:e|en|em|er)?|abbrechen|stop|stopp)\b", text):
        return False
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in _FULLSCREEN_TERMS)


def _extract_spaced_hotkey(instruction: str) -> str:
    tokens = _hotkey_tokens(instruction)
    for index, token in enumerate(tokens):
        if not _is_hotkey_modifier(token):
            continue
        parts: list[str] = []
        pos = index
        while pos < len(tokens):
            current = tokens[pos]
            if parts and current in _HOTKEY_CONNECTOR_TOKENS:
                pos += 1
                continue
            if _is_hotkey_modifier(current):
                parts.append(_canonical_hotkey_token(current))
                pos += 1
                continue
            break
        while pos < len(tokens) and tokens[pos] in _HOTKEY_CONNECTOR_TOKENS:
            pos += 1
        if pos < len(tokens) and _is_hotkey_terminal_key(tokens[pos]):
            parts.append(_canonical_hotkey_token(tokens[pos]))
            return "+".join(parts)
    return ""


def _extract_single_hotkey(instruction: str) -> str:
    text = _ascii_fold(instruction)
    if not re.search(r"\b(?:hotkey|tastenkombi|druecke|drueck|drucke|druck|press)\b", text):
        return ""
    folded_tokens = " ".join(_hotkey_tokens(_strip_safety_phrases(instruction)))
    for phrase, key in _HOTKEY_PHRASE_ALIASES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", folded_tokens):
            return key
    ignored = {
        "hotkey",
        "tastenkombi",
        "druecke",
        "drueck",
        "drucke",
        "druck",
        "press",
        "bitte",
        "mal",
        "kurz",
        "taste",
        "key",
        "die",
        "den",
        "das",
        "eine",
        "einen",
        "im",
        "in",
        "ins",
        "fenster",
        "window",
        "app",
    }
    for token in _hotkey_tokens(_strip_safety_phrases(instruction)):
        if token in ignored or token in _HOTKEY_CONNECTOR_TOKENS:
            continue
        if _is_hotkey_modifier(token):
            continue
        if _is_hotkey_terminal_key(token):
            return _canonical_hotkey_token(token)
    return ""


def classify_desktop_instruction(instruction: str) -> str:
    text = _ascii_fold(_strip_safety_phrases(instruction))
    if any(term in text for term in _OBSERVE_TERMS):
        return "observe"
    if any(term in text for term in _SCREEN_TEXT_TERMS):
        return "screen_text"
    if any(text.startswith(word) or f" {word} " in f" {text} " for word in _WAIT_WORDS):
        return "wait"
    if any(term in text for term in _SELECT_ALL_TERMS):
        return "hotkey"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _SAVE_AS_TERMS):
        return "hotkey"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _SAVE_TERMS):
        return "hotkey"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _UNDO_TERMS):
        return "hotkey"
    if _is_paste_command(instruction):
        return "hotkey"
    if _is_print_command(instruction):
        return "hotkey"
    if _is_open_file_command(instruction):
        return "hotkey"
    if _is_new_file_command(instruction):
        return "hotkey"
    if _is_new_folder_command(instruction):
        return "hotkey"
    if _is_new_tab_command(instruction):
        return "hotkey"
    if _is_next_tab_command(instruction):
        return "hotkey"
    if _is_previous_tab_command(instruction):
        return "hotkey"
    if _is_close_file_command(instruction):
        return "hotkey"
    if _is_find_box_command(instruction):
        return "hotkey"
    if _is_address_bar_command(instruction):
        return "hotkey"
    if _is_refresh_command(instruction):
        return "hotkey"
    if _is_zoom_in_command(instruction):
        return "hotkey"
    if _is_zoom_out_command(instruction):
        return "hotkey"
    if _is_zoom_reset_command(instruction):
        return "hotkey"
    if _is_fullscreen_command(instruction):
        return "hotkey"
    if _is_browser_back_command(instruction):
        return "hotkey"
    if _is_browser_forward_command(instruction):
        return "hotkey"
    if "+" in text and (
        re.search(r"\b(?:hotkey|tastenkombi|druecke|drueck|drucke|druck|press)\b", text)
        or any(re.search(rf"\b{re.escape(key)}\b", text) for key in _HOTKEY_MODIFIER_KEYS)
    ):
        return "hotkey"
    if re.search(r"\b(?:hotkey|tastenkombi|druecke|drueck|drucke|druck|press)\b", text) and _extract_spaced_hotkey(instruction):
        return "hotkey"
    if _extract_single_hotkey(instruction):
        return "hotkey"
    if (
        any(text.startswith(word) or f" {word} " in f" {text} " for word in _SCROLL_WORDS)
        or "nach unten" in text
        or "nach oben" in text
        or re.search(r"\b(?:runter|hoch)\b", text)
    ):
        return "scroll"
    if any(text.startswith(word) or f" {word} " in f" {text} " for word in _CLICK_WORDS):
        return "click"
    if re.search(r"\b(?:tippe|tipp|schreibe|schreib)\b", text):
        return "type"
    if any(text.startswith(word) or f" {word} " in f" {text} " for word in _FIND_WORDS):
        return "find"
    return "unknown"


def _strip_safety_phrases(text: str) -> str:
    value = str(text or "")
    for pattern in (
        r"\b(?:(?:und|aber)\s+)?(?:ich\s+)?(?:bestaetige|bestatige|bestaetigen|bestatigen|confirm|confirmed|freigabe)\b(?:\s+es|\s+das)?",
        r"\b(?:(?:und|aber)\s+)?(?:aendere|andere|veraendere|verandere)\s+nichts\b",
        r"\b(?:aber|und)\s+(?:klicke|klick|click|druecke|drueck|drucke|druck|tippe|tipp|schreibe|schreib|scrolle|scroll|rolle)\s+(?:noch\s+)?nicht\b",
        r"\b(?:aber|und)\s+(?:nicht|nie)\s+(?:klicken|klicke|klick|click|druecken|druecke|drueck|drucke|druck|tippen|tippe|tipp|schreiben|schreibe|schreib|scrollen|scrolle|scroll|rollen|rolle)\b",
    ):
        match = re.search(pattern, _ascii_fold(value), flags=re.IGNORECASE)
        if match:
            value = value[:match.start()]
    return value.strip(" .,:;!?")


def _extract_after_action_word(instruction: str, words: tuple[str, ...]) -> str:
    text = _strip_safety_phrases(instruction)
    pattern = r"\b(?:" + "|".join(re.escape(word) for word in words) + r")\b"
    match = re.search(pattern, _ascii_fold(text))
    if not match:
        return ""
    original_tail = text[match.end():]
    original_tail = re.sub(
        r"^\s+(?:(?:bitte|mal|kurz|auf|den|die|das|einen|eine|einem|einer|irgend(?:\s+einen)?|anderen|andere)\s+)+",
        " ",
        original_tail,
        flags=re.IGNORECASE,
    )
    original_tail = re.sub(r"\b(?:button|btn|knopf|taste|control|element)\b", "", original_tail, flags=re.IGNORECASE)
    return original_tail.strip(" .,:;!?")


def _strip_target_window_hint(target: str, instruction: str) -> str:
    value = str(target or "").strip(" .,:;!?")
    window = _extract_window_hint(instruction)
    if not value or not window:
        return value
    original_stripped = re.sub(
        rf"\s+\b(?:(?:in|im|bei)\s+)?(?:fenster|window|app)\s+{re.escape(window.strip())}\b\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" .,:;!?")
    if original_stripped != value:
        return original_stripped
    original_stripped = re.sub(
        rf"\s+\b(?:in|im|bei)\s+{re.escape(window.strip())}\b\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip(" .,:;!?")
    if original_stripped != value:
        return original_stripped
    folded_value = _ascii_fold(value)
    folded_window = re.escape(_ascii_fold(window).strip())
    match = re.search(
        rf"\s+\b(?:(?:in|im|bei)\s+)?(?:fenster|window|app)\s+{folded_window}\b\s*$",
        folded_value,
    )
    if match:
        return value[:match.start()].strip(" .,:;!?")
    match = re.search(
        rf"\s+\b(?:in|im|bei)\s+{folded_window}\b\s*$",
        folded_value,
    )
    if match:
        return value[:match.start()].strip(" .,:;!?")
    return value


def _extract_find_target(instruction: str) -> tuple[str, str]:
    text = _strip_safety_phrases(instruction)
    folded = _ascii_fold(text)
    control_type = "Button" if any(word in folded for word in ("button", "knopf", "taste", "btn")) else ""
    match = re.search(
        r"\b(?:finde|find|suche|such|zeige|pruefe|prufe)\b"
        r".{0,50}?\b(?:button|btn|knopf|taste|control|element)\b"
        r"\s+(?P<target>.+)$",
        folded,
    )
    if match:
        target = match.group("target")
    else:
        target = _extract_after_action_word(text, _FIND_WORDS)
    target = re.split(
        r"\b(?:im|in|am|auf)\s+(?:aktuellen|aktiven|sichtbaren)?\s*(?:fenster|bildschirm|screen)\b",
        target,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    target = _strip_target_window_hint(target, instruction)
    return target.strip(" .,:;!?"), control_type


def _extract_click_target(instruction: str) -> str:
    target = _extract_after_action_word(instruction, _CLICK_WORDS)
    target = re.split(
        r"\b(?:im|in|am|auf)\s+(?:aktuellen|aktiven|sichtbaren)?\s*(?:fenster|bildschirm|screen)\b",
        target,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    target = _strip_target_window_hint(target, instruction)
    return target.strip(" .,:;!?") or "darauf"


def _extract_typed_text(instruction: str) -> str:
    quote_pairs = (
        ('"', '"'),
        ("'", "'"),
        (chr(0x201c), chr(0x201d)),  # left/right double quotation marks
        (chr(0x201e), chr(0x201c)),  # German low/high double quotation marks
        (chr(0x201a), chr(0x2018)),  # low/high single quotation marks
        (chr(0x00ab), chr(0x00bb)),  # guillemets
    )
    for opener, closer in quote_pairs:
        pattern = re.escape(opener) + r"(?P<text>.+?)" + re.escape(closer)
        match = re.search(pattern, instruction)
        if match:
            return match.group("text").strip()
    target = _extract_after_action_word(instruction, ("tippe", "tipp", "schreibe", "schreib"))
    # Ohne Anfuehrungszeichen kann der Resttext noch eine Folge-Aktion
    # enthalten (z. B. "Hallo Welt und speichere"), wenn der vorherige Split
    # die Instruktion nicht getrennt hat. Damit niemals Steuerwoerter ins
    # aktive Fenster getippt werden, am ersten Folge-Aktionswort abschneiden.
    fragments = [frag.strip() for frag in _ACTION_SPLIT_RE.split(target) if frag.strip()]
    if fragments:
        target = fragments[0]
    target = _strip_target_window_hint(target, instruction)
    return target.strip()


def _extract_window_hint(instruction: str) -> str:
    text = _strip_safety_phrases(instruction)
    known_app_window = r"notepad|editor|discord|spotify|chrome|brave|code|vscode|explorer|whatsapp|telegram|edge|firefox|obsidian"
    patterns = (
        r"\b(?:im|in|ins)\s+(?:fenster|window|app)\s+(?P<window>.+?)(?=\s+(?:und|aber|durch|aus|vor|um)\b|[.;,!?]|$)",
        r"\b(?:das|den|die|dem)?\s*(?:fenster|window|app)(?!\s+(?:und|aber|mit|per)\b)\s+(?P<window>.+?)(?=\s+(?:mit|und|aber|per|durch|aus|vor|um)\b|[.;,!?]|$)",
        rf"\b(?:in|im|bei|aus|von)\s+(?P<window>{known_app_window})(?=\s+(?:und|aber|mit|per|durch|aus|vor|um)\b|[.;,!?]|$)",
        r"\b(?:in|im|bei)\s+(?P<window>[A-Za-z0-9][A-Za-z0-9 _.,()+-]{1,80})$",
    )
    # Lagewoerter/Strukturbegriffe sind keine Fensternamen. Das letzte (lose)
    # Pattern faengt sonst Resttext wie "Menue oben rechts" als Fenstername.
    location_words = {
        "oben", "unten", "rechts", "links", "mitte", "ecke",
        "menue", "menu", "leiste", "rand", "bereich", "seite",
    }
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        window = match.group("window").strip(" .,:;!?")
        folded = _ascii_fold(window)
        if folded in {"das aktive feld", "aktive feld", "aktuellen fenster", "aktuelles fenster", "aktiven fenster"}:
            continue
        if len(window) > 80:
            continue
        # Nur das letzte, bewusst lose Pattern (kein expliziter "fenster"-/
        # App-Marker) strenger pruefen: hoechstens drei Tokens und keine
        # Lagewoerter, damit Klickziel-Resttext nicht als Fenster gilt.
        if index == len(patterns) - 1:
            tokens = folded.split()
            if len(tokens) > 3 or any(token in location_words for token in tokens):
                continue
        return window
    return ""


def _extract_hotkey(instruction: str) -> str:
    text = _ascii_fold(instruction)
    if any(term in text for term in _SELECT_ALL_TERMS):
        return "ctrl+a"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _SAVE_AS_TERMS):
        return "ctrl+shift+s"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _SAVE_TERMS):
        return "ctrl+s"
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in _UNDO_TERMS):
        return "ctrl+z"
    if _is_paste_command(instruction):
        return "ctrl+v"
    if _is_print_command(instruction):
        return "ctrl+p"
    if _is_open_file_command(instruction):
        return "ctrl+o"
    if _is_new_file_command(instruction):
        return "ctrl+n"
    if _is_new_folder_command(instruction):
        return "ctrl+shift+n"
    if _is_new_tab_command(instruction):
        return "ctrl+t"
    if _is_next_tab_command(instruction):
        return "ctrl+tab"
    if _is_previous_tab_command(instruction):
        return "ctrl+shift+tab"
    if _is_close_file_command(instruction):
        return "ctrl+w"
    if _is_find_box_command(instruction):
        return "ctrl+f"
    if _is_address_bar_command(instruction):
        return "ctrl+l"
    if _is_refresh_command(instruction):
        return "ctrl+r"
    if _is_zoom_in_command(instruction):
        return "ctrl+plus"
    if _is_zoom_out_command(instruction):
        return "ctrl+minus"
    if _is_zoom_reset_command(instruction):
        return "ctrl+0"
    if _is_fullscreen_command(instruction):
        return "f11"
    if _is_browser_back_command(instruction):
        return "alt+left"
    if _is_browser_forward_command(instruction):
        return "alt+right"
    match = re.search(r"\b([a-z0-9]+(?:\s*\+\s*[a-z0-9]+)+)\b", text)
    if match:
        return _normalize_hotkey(match.group(1))
    spaced = _extract_spaced_hotkey(instruction)
    if spaced:
        return spaced
    single = _extract_single_hotkey(instruction)
    if single:
        return single
    return ""


def _normalize_hotkey(keys: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*\+\s*", _ascii_fold(keys)) if part.strip()]
    normalized = [_HOTKEY_KEY_ALIASES.get(part, part) for part in parts]
    return "+".join(normalized)


def _extract_occurrence(instruction: str) -> int:
    text = _ascii_fold(instruction)
    ordinal_words = {
        "ersten": 1,
        "erste": 1,
        "zweiten": 2,
        "zweite": 2,
        "dritten": 3,
        "dritte": 3,
        "vierten": 4,
        "vierte": 4,
        "fuenften": 5,
        "funften": 5,
        "fuenfte": 5,
        "funfte": 5,
    }
    for word, value in ordinal_words.items():
        if re.search(rf"\b{word}\b", text):
            return value
    match = re.search(r"\b([1-9])\s*(?:\.|ten|te|nd|rd|th)?\b", text)
    if match:
        return max(1, min(9, int(match.group(1))))
    return 1


def _extract_scroll_clicks(instruction: str) -> int:
    text = _ascii_fold(instruction)
    match = re.search(r"\b(\d{1,2})\b", text)
    amount = max(1, min(20, int(match.group(1)))) if match else 3
    direction = -1
    if "nach oben" in text or re.search(r"\b(?:hoch|up)\b", text):
        direction = 1
    if "nach unten" in text or re.search(r"\b(?:runter|down)\b", text):
        direction = -1
    return direction * amount


def _extract_wait_seconds(instruction: str) -> float:
    text = _ascii_fold(instruction).replace(",", ".")
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    seconds = float(match.group(1)) if match else 1.0
    if "minute" in text:
        seconds *= 60.0
    return max(0.1, min(10.0, seconds))


def _control_center(control: dict[str, Any]) -> tuple[int | None, int | None]:
    if control.get("rect_valid") is False:
        return None, None
    rect = control.get("rect") if isinstance(control, dict) else None
    if not isinstance(rect, dict):
        return None, None
    try:
        coords = [float(rect.get(key)) for key in ("left", "top", "right", "bottom")]
        if (
            coords[2] <= coords[0]
            or coords[3] <= coords[1]
            or any(abs(coord) >= 30000 for coord in coords)
        ):
            return None, None
        return (
            int(round((coords[0] + coords[2]) / 2)),
            int(round((coords[1] + coords[3]) / 2)),
        )
    except (TypeError, ValueError):
        return None, None


def _summarize_tree(data: dict[str, Any]) -> str:
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    if not windows:
        return "Kein echtes UIA-Fenster lesbar."
    first = windows[0] if isinstance(windows[0], dict) else {}
    title = str(first.get("title") or "aktuelles Fenster").strip()
    labels: list[str] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        for control in window.get("controls") or []:
            if not isinstance(control, dict):
                continue
            if control.get("control_type") not in {"Button", "SplitButton", "MenuItem", "Edit", "ListItem", "TabItem"}:
                continue
            label = str(control.get("name") or control.get("automation_id") or "").strip()
            if label and label not in labels:
                labels.append(label[:80])
            if len(labels) >= 10:
                break
    listed = ", ".join(f'"{label}"' for label in labels) if labels else "keine klaren Buttons"
    return f'Aktuelles Fenster: "{title}". Klickbare Controls: {listed}.'


def _summarize_find(data: dict[str, Any]) -> str:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    if not matches:
        return "Kein passendes Control gefunden."
    first = matches[0] if isinstance(matches[0], dict) else {}
    label = str(first.get("name") or first.get("automation_id") or "Control")
    ctype = str(first.get("control_type") or "Control")
    window = str(first.get("window_title") or "aktuelles Fenster")
    x, y = _control_center(first)
    pos = f" bei X={x}, Y={y}" if x is not None and y is not None else ""
    extra = f" Es gibt {len(matches)} Treffer." if len(matches) > 1 else ""
    return f'Gefunden: "{label}" ({ctype}) im Fenster "{window}"{pos}.{extra}'


def _ocr_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    return payload if isinstance(payload, dict) else {}


def _find_ocr_block(data: dict[str, Any], target: str) -> dict[str, Any]:
    payload = _ocr_payload(data)
    blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else []
    block = desktop_control._find_ocr_text_block(blocks, target)
    return block if isinstance(block, dict) else {}


def _summarize_ocr_find(data: dict[str, Any], target: str) -> str:
    if not data.get("success"):
        return f"OCR-Fallback konnte nicht lesen: {data.get('error') or 'unbekannter OCR-Fehler'}."
    block = _find_ocr_block(data, target)
    if not block:
        return "Auch im OCR-Text wurde kein passendes Ziel gefunden."
    text = str(block.get("text") or target).strip()
    engine = str(_ocr_payload(data).get("engine") or "ocr")
    return f'OCR-Fallback gefunden: "{text}" ({engine}).'


def _match_label(match: dict[str, Any]) -> str:
    return str(match.get("name") or match.get("automation_id") or "").strip()


def _match_window(match: dict[str, Any]) -> str:
    return str(match.get("window_title") or "").strip()


def _find_is_ambiguous(data: dict[str, Any]) -> bool:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    if len(matches) < 2:
        return False
    first = matches[0] if isinstance(matches[0], dict) else {}
    second = matches[1] if isinstance(matches[1], dict) else {}
    first_score = float(first.get("score") or 0)
    second_score = float(second.get("score") or 0)
    same_label = _ascii_fold(_match_label(first)) == _ascii_fold(_match_label(second))
    same_window = _ascii_fold(_match_window(first)) == _ascii_fold(_match_window(second))
    return not (same_label and same_window) and abs(first_score - second_score) <= 8.0


def _summarize_alternatives(data: dict[str, Any], limit: int = 4) -> str:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    labels: list[str] = []
    for match in matches[:limit]:
        if not isinstance(match, dict):
            continue
        label = _match_label(match) or "Control"
        window = _match_window(match) or "aktuelles Fenster"
        ctype = str(match.get("control_type") or "Control")
        labels.append(f'"{label}" ({ctype}, {window})')
    return ", ".join(labels)


def _tree_contains_text(data: dict[str, Any], text: str) -> bool:
    needle = str(text or "").strip()
    if not needle:
        return False
    folded_needle = _ascii_fold(needle)
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    for window in windows:
        if not isinstance(window, dict):
            continue
        values = [window.get("title")]
        values.extend(
            (control.get("name") or control.get("automation_id"))
            for control in (window.get("controls") or [])
            if isinstance(control, dict)
        )
        for value in values:
            if folded_needle in _ascii_fold(str(value or "")):
                return True
    return False


def _visible_text_contains(text: str, expected: str) -> bool:
    needle = re.sub(r"\s+", " ", _ascii_fold(expected)).strip()
    haystack = re.sub(r"\s+", " ", _ascii_fold(text)).strip()
    return bool(needle and needle in haystack)


def _verification_payload(
    *,
    method: str,
    status: str = "unknown",
    summary: str = "",
    checked: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    normalized_status = status if status in {"passed", "failed", "unknown"} else "unknown"
    payload: dict[str, Any] = {
        "checked": bool(checked),
        "method": method,
        "status": normalized_status,
        "passed": True if normalized_status == "passed" else False if normalized_status == "failed" else None,
    }
    if summary:
        payload["summary"] = summary
    payload.update(extra)
    return payload


def _ui_find_with_type_fallback(target: str, control_type: str = "", window: str = "", max_results: int = 10) -> tuple[dict[str, Any], str]:
    data = ui_automation.ui_find(target, control_type=control_type, window=window, max_results=max_results)
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    if matches or not control_type:
        return data, control_type
    relaxed = ui_automation.ui_find(target, control_type="", window=window, max_results=max_results)
    relaxed_matches = relaxed.get("matches") if isinstance(relaxed.get("matches"), list) else []
    if relaxed_matches:
        relaxed["relaxed_control_type_from"] = control_type
        return relaxed, ""
    return data, control_type


def _first_find_match(data: dict[str, Any]) -> dict[str, Any]:
    matches = data.get("matches") if isinstance(data.get("matches"), list) else []
    first = matches[0] if matches and isinstance(matches[0], dict) else {}
    return first


def _first_actionable_tree_control(data: dict[str, Any]) -> dict[str, Any]:
    windows = data.get("windows") if isinstance(data.get("windows"), list) else []
    for window in windows:
        if not isinstance(window, dict):
            continue
        for control in window.get("controls") or []:
            if not isinstance(control, dict):
                continue
            if control.get("control_type") in {"Button", "SplitButton", "MenuItem", "Edit", "ListItem", "TabItem"}:
                label = str(control.get("name") or control.get("automation_id") or "").strip()
                if label:
                    return control
    return {}


_QUEUE_CONTEXT_KEYS = ("last_target", "last_control_type", "last_window")


def _clean_queue_context(context: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(context, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key in _QUEUE_CONTEXT_KEYS:
        value = str(context.get(key) or "").strip()
        if value:
            cleaned[key] = value[:300]
    return cleaned


def _queue_context(last_target: str, last_control_type: str, last_window: str) -> dict[str, str]:
    return _clean_queue_context({
        "last_target": last_target,
        "last_control_type": last_control_type,
        "last_window": last_window,
    })


def _prepare_confirmation(
    params: dict[str, Any],
    deferred_instructions: list[str] | None = None,
    queue_context: dict[str, Any] | None = None,
) -> None:
    pending: dict[str, Any] = {"action": "hermes_desktop_commit", "params": params}
    queue = [str(item).strip() for item in (deferred_instructions or []) if str(item or "").strip()]
    if queue:
        queue_payload: dict[str, Any] = {
            "type": "hermes_desktop_instructions",
            "instructions": queue[:MAX_HERMES_DESKTOP_STEPS],
        }
        cleaned_context = _clean_queue_context(queue_context)
        if cleaned_context:
            queue_payload["context"] = cleaned_context
        pending["queue"] = queue_payload
    set_pending_confirmation(pending)


def _set_foreground_window(hwnd: int, title: str, engine: str) -> dict[str, Any]:
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Win32 window focus is only available on Windows")
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
    except Exception:
        pass
    time.sleep(0.05)
    focused = bool(user32.SetForegroundWindow(hwnd))
    try:
        focused = focused or int(user32.GetForegroundWindow()) == int(hwnd)
    except Exception:
        pass
    if not focused:
        raise RuntimeError(f"window focus failed: {title}")
    return {
        "focused": True,
        "window_title": title,
        "engine": engine,
    }


def _focus_window_via_win32(window: str) -> dict[str, Any]:
    target = str(window or "").strip()
    if not target:
        raise ValueError("window is required")
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Win32 window focus is only available on Windows")

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    query = _window_match_fold(target)
    matches: list[tuple[int, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = str(buffer.value or "").strip()
        if title and _window_title_matches_query(title, query):
            matches.append((int(hwnd), title))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not matches:
        raise ValueError(f"window not found: {window}")

    hwnd, title = matches[0]
    return _set_foreground_window(hwnd, title or window, "win32")


def _center_cursor_on_window(window: str) -> dict[str, Any] | None:
    """Move the cursor to the center of the matching window, best-effort.

    Mouse-wheel events are delivered by Windows to the window under the cursor,
    not to the focused window. Before a wheel scroll we therefore park the cursor
    over the target window so the scroll lands where it was intended. Returns the
    move result, or None when the window can't be resolved (then the caller keeps
    the existing behavior of scrolling at the current cursor position).
    """
    target = str(window or "").strip()
    if not target or not hasattr(ctypes, "windll"):
        return None

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    query = _window_match_fold(target)
    matches: list[tuple[int, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = str(buffer.value or "").strip()
        if title and _window_title_matches_query(title, query):
            matches.append((int(hwnd), title))
        return True

    try:
        user32.EnumWindows(enum_proc(callback), 0)
        if not matches:
            return None
        hwnd, _title = matches[0]
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        width = int(rect.right) - int(rect.left)
        height = int(rect.bottom) - int(rect.top)
        if width <= 0 or height <= 0:
            return None
        center_x = int(rect.left) + width // 2
        center_y = int(rect.top) + height // 2
        return desktop_control.desktop_move(center_x, center_y)
    except Exception:
        return None


def _focus_window_by_pid(pid: int, label: str = "") -> dict[str, Any]:
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Win32 window focus is only available on Windows")

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    target_pid = int(pid or 0)
    matches: list[tuple[int, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if int(window_pid.value or 0) != target_pid:
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = str(buffer.value or "").strip()
        if title:
            matches.append((int(hwnd), title))
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not matches:
        raise ValueError(f"window not found for process: {pid}")
    hwnd, title = matches[0]
    return _set_foreground_window(hwnd, title or label or str(pid), "win32-pid")


def _known_window_launcher(window: str) -> list[str]:
    folded = _window_match_fold(window)
    if "notepad" in folded or folded in {"editor"}:
        return ["notepad.exe"]
    return []


def _launch_and_focus_known_window(window: str) -> dict[str, Any]:
    command = _known_window_launcher(window)
    if not command:
        raise ValueError(f"window not found: {window}")
    proc = subprocess.Popen(command)
    deadline = time.monotonic() + 4.0
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        time.sleep(0.2)
        try:
            result = _focus_window_by_pid(proc.pid, label=window)
            result["opened_app"] = command[0]
            return result
        except Exception as exc:
            last_error = exc
        try:
            result = _focus_window_via_win32(window)
            result["opened_app"] = command[0]
            return result
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError(f"window not found: {window}")


def _focus_window_for_action(window: str) -> dict[str, Any] | None:
    target = str(window or "").strip()
    if not target:
        return None
    try:
        result = ui_automation.ui_focus(target)
    except Exception as uia_exc:
        try:
            result = _focus_window_via_win32(target)
            result["fallback_from"] = "uia"
            result["fallback_reason"] = str(uia_exc)[:180]
        except Exception as win32_exc:
            result = _launch_and_focus_known_window(target)
            result["fallback_from"] = "launch"
            result["fallback_reason"] = f"{str(uia_exc)[:90]}; {str(win32_exc)[:90]}"
    time.sleep(0.15)
    return result


def _focused_title_matches_target(target: str, focused_title: str) -> bool:
    """Prueft, ob der fokussierte Fenstertitel zum angeforderten Zielfenster passt.

    Toleriert Teiltreffer ("Notepad" ⊂ "*Test - Notepad"). Wird nur als
    Negativ-Signal genutzt: ein klarer Mismatch verhindert das Tippen ins
    falsche Fenster. Fehlt der Titel, gibt es kein verlaessliches Signal —
    dann wird NICHT abgebrochen (kein Fehlalarm).
    """
    t = re.sub(r"\s+", " ", str(target or "").strip().lower())
    title = re.sub(r"\s+", " ", str(focused_title or "").strip().lower())
    if not t or not title:
        return True
    return t in title or title in t


def _clip_text(value: object, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _pending_action_notice(line: str, *, inline_preapproval: bool, deferred: list[str]) -> str:
    if inline_preapproval:
        line += " Eingebaute Ja/OK-Zeilen zaehlen nicht als Freigabe; antworte nach dieser Vorbereitung separat mit Ja."
    if deferred:
        preview = "; ".join(_clip_text(item, 80) for item in deferred[:3])
        line += f" Weitere Desktop-Schritte pausiert bis danach: {preview}."
    return line


def hermes_desktop_task(
    message: str = "",
    max_steps: int = MAX_HERMES_DESKTOP_STEPS,
    initial_context: dict[str, Any] | None = None,
) -> dict:
    """Run a guarded Hermes desktop task plan.

    Read-only desktop inspection happens immediately. Any state-changing desktop
    operation is stored as a pending confirmation for hermes_desktop_commit.
    """
    inline_preapproval = _message_has_inline_preapproval(message)
    inline_cancel = _message_has_inline_cancel(message)
    instructions = split_hermes_desktop_instructions(message)
    if not instructions:
        instructions = ["was siehst du"]
    limit = max(1, min(MAX_HERMES_DESKTOP_STEPS, int(max_steps or MAX_HERMES_DESKTOP_STEPS)))
    steps: list[dict[str, Any]] = []
    summary: list[str] = []
    prepared_action: dict[str, Any] | None = None
    deferred_instructions: list[str] = []
    needs_clarification = False
    context = _clean_queue_context(initial_context)
    last_target = context.get("last_target", "")
    last_control_type = context.get("last_control_type", "")
    last_window = context.get("last_window", "")

    limited_instructions = instructions[:limit]
    for instruction_index, instruction in enumerate(limited_instructions):
        kind = classify_desktop_instruction(instruction)
        try:
            if kind in _MUTATING_DESKTOP_KINDS and (inline_cancel or _has_inline_cancel_fragment(instruction)):
                line = (
                    "Mutierende Desktop-Aktion nicht vorbereitet: "
                    "Der Auftrag enthaelt eine Nicht-ausfuehren- oder Abbruch-Formulierung. "
                    "Ich habe nichts veraendert."
                )
                steps.append({
                    "kind": "cancelled_mutation",
                    "instruction": instruction,
                    "requested_kind": kind,
                    "success": True,
                    "summary": line,
                })
                summary.append(line)
                continue
            if kind == "observe":
                window_hint = _extract_window_hint(instruction)
                data = ui_automation.ui_tree(window=window_hint, max_depth=3, max_controls=80)
                text = _summarize_tree(data)
                windows = data.get("windows") if isinstance(data.get("windows"), list) else []
                if windows and isinstance(windows[0], dict):
                    last_window = str(windows[0].get("title") or "").strip()
                elif window_hint:
                    last_window = window_hint
                primary = _first_actionable_tree_control(data)
                if primary:
                    last_target = str(primary.get("name") or primary.get("automation_id") or "").strip()
                    last_control_type = str(primary.get("control_type") or "").strip()
                    last_window = str(primary.get("window_title") or last_window).strip()
                steps.append({"kind": "observe", "instruction": instruction, "success": True, "data": data, "summary": text})
                summary.append(text)
            elif kind == "screen_text":
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                data = desktop_engine.read_screen_text(window=target_window)
                payload = desktop_engine.ocr_payload(data)
                text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
                method = str(payload.get("method") or payload.get("provider") or "ocr")
                ui_text_data = data.get("ui_text_data") if isinstance(data.get("ui_text_data"), dict) else None
                line = (
                    ("Bildschirmtext per UIA gelesen." if method == "uia_text" else "Bildschirmtext gelesen.")
                    + (f" Textanfang: {text[:220]}" if text else " Kein Text erkannt.")
                )
                if target_window:
                    last_window = target_window
                steps.append({
                    "kind": "screen_text",
                    "instruction": instruction,
                    "success": True,
                    "window": target_window,
                    "method": method,
                    "data": data,
                    "ui_text_data": ui_text_data,
                    "summary": line,
                })
                summary.append(line)
            elif kind == "wait":
                seconds = _extract_wait_seconds(instruction)
                data = desktop_control.desktop_wait(seconds=seconds)
                line = f"Gewartet: {data.get('seconds', seconds)} Sekunden."
                steps.append({"kind": "wait", "instruction": instruction, "success": True, "data": data, "summary": line})
                summary.append(line)
            elif kind == "find":
                target, control_type = _extract_find_target(instruction)
                if not target:
                    raise ValueError("Kein Ziel fuer UI-Suche erkannt.")
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                data, effective_control_type = _ui_find_with_type_fallback(
                    target,
                    control_type=control_type,
                    window=target_window,
                )
                text = _summarize_find(data)
                first_match = _first_find_match(data)
                ocr_public: dict[str, Any] | None = None
                if first_match:
                    last_target = str(first_match.get("name") or first_match.get("automation_id") or target).strip()
                    last_control_type = str(first_match.get("control_type") or effective_control_type or "").strip()
                    last_window = str(first_match.get("window_title") or target_window or last_window).strip()
                else:
                    if target_window:
                        last_window = target_window
                    ocr_data = ocr.ocr_screenshot(window_title=target_window or last_window or None)
                    ocr_text = _summarize_ocr_find(ocr_data, target)
                    block = _find_ocr_block(ocr_data, target)
                    if block:
                        last_target = str(block.get("text") or target).strip()
                        last_control_type = ""
                        text = ocr_text
                        ocr_public = {
                            "success": True,
                            "matched_text": last_target,
                            "engine": _ocr_payload(ocr_data).get("engine"),
                        }
                    else:
                        text = f"{text} {ocr_text}"
                        ocr_public = {"success": False, "summary": ocr_text}
                steps.append({
                    "kind": "find",
                    "instruction": instruction,
                    "success": True,
                    "target": target,
                    "control_type": effective_control_type,
                    "requested_control_type": control_type,
                    "window": target_window,
                    "data": data,
                    "ocr": ocr_public,
                    "summary": text,
                })
                summary.append(text + " Ich habe nichts veraendert.")
            elif kind == "scroll":
                clicks = _extract_scroll_clicks(instruction)
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                if target_window:
                    last_window = target_window
                params = {"kind": "scroll", "scroll_clicks": clicks, "window": target_window, "verify": True}
                prepared_action = params
                direction = "nach oben" if clicks > 0 else "nach unten"
                window_suffix = f' im Fenster "{target_window}"' if target_window else ""
                line = (
                    f"Freigabe vorbereitet: Ich wuerde {abs(clicks)} Schritt(e) {direction}{window_suffix} scrollen. "
                    "Lexa fuehrt das erst nach deiner Bestaetigung aus."
                )
                deferred_instructions = limited_instructions[instruction_index + 1 :]
                _prepare_confirmation(params, deferred_instructions, _queue_context(last_target, last_control_type, last_window))
                line = _pending_action_notice(line, inline_preapproval=inline_preapproval, deferred=deferred_instructions)
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": params, "summary": line})
                summary.append(line)
                break
            elif kind == "click":
                target = _extract_click_target(instruction)
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                folded_target = _ascii_fold(target)
                from_recent = folded_target in _DEICTIC_TERMS and bool(last_target)
                if folded_target in _DEICTIC_TERMS and last_target:
                    target = last_target
                control_type = last_control_type or "Button"
                occurrence = _extract_occurrence(instruction)
                resolved: dict[str, Any] = {}
                try:
                    data, effective_control_type = _ui_find_with_type_fallback(
                        target,
                        control_type=control_type,
                        window=target_window,
                        max_results=5,
                    )
                    if _find_is_ambiguous(data) and not from_recent:
                        alternatives = _summarize_alternatives(data)
                        line = (
                            f'Das Klickziel "{target}" ist mehrdeutig: {alternatives}. '
                            "Bitte sag genauer, welches Control ich vorbereiten soll."
                        )
                        needs_clarification = True
                        steps.append({"kind": "clarification", "instruction": instruction, "success": False, "data": data, "summary": line})
                        summary.append(line)
                        break
                    first_match = _first_find_match(data)
                    if first_match:
                        target = _match_label(first_match) or target
                        control_type = str(first_match.get("control_type") or effective_control_type or control_type).strip()
                        last_window = str(first_match.get("window_title") or target_window or last_window).strip()
                        resolved = {
                            "source": "ui",
                            "matched_text": target,
                            "window": last_window,
                            "score": first_match.get("score"),
                        }
                    else:
                        if target_window:
                            last_window = target_window
                        ocr_data = ocr.ocr_screenshot(window_title=target_window or last_window or None)
                        block = _find_ocr_block(ocr_data, target)
                        if block:
                            target = str(block.get("text") or target).strip()
                            control_type = ""
                            resolved = {"source": "ocr", "matched_text": target, "engine": _ocr_payload(ocr_data).get("engine")}
                except Exception as exc:
                    resolved = {"source": "deferred", "warning": str(exc)[:180]}
                if target:
                    last_target = target
                if control_type:
                    last_control_type = control_type
                if target_window and not last_window:
                    last_window = target_window
                params = {
                    "kind": "click",
                    "text": target,
                    "control_type": control_type,
                    "window": last_window,
                    "occurrence": occurrence,
                    "button": "left",
                    "verify": True,
                }
                prepared_action = params
                window_suffix = f' im Fenster "{last_window}"' if last_window else ""
                occurrence_suffix = f" (Treffer {occurrence})" if occurrence > 1 else ""
                line = (
                    f'Freigabe vorbereitet: Ich wuerde "{target}"{occurrence_suffix}{window_suffix} klicken. '
                    "Lexa fuehrt das erst nach deiner Bestaetigung aus."
                )
                deferred_instructions = limited_instructions[instruction_index + 1 :]
                _prepare_confirmation(params, deferred_instructions, _queue_context(last_target, last_control_type, last_window))
                line = _pending_action_notice(line, inline_preapproval=inline_preapproval, deferred=deferred_instructions)
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": params, "resolved": resolved, "summary": line})
                summary.append(line)
                break
            elif kind == "type":
                text = _extract_typed_text(instruction)
                if not text:
                    raise ValueError("Kein Text zum Tippen erkannt.")
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                if target_window:
                    last_window = target_window
                params = {
                    "kind": "type",
                    "typing_text": text,
                    "window": target_window,
                    "typing_interval_ms": 8,
                    "verify": True,
                }
                prepared_action = params
                window_suffix = f' im Fenster "{target_window}"' if target_window else " in das aktive Feld"
                line = f"Freigabe vorbereitet: Ich wuerde Text{window_suffix} tippen."
                deferred_instructions = limited_instructions[instruction_index + 1 :]
                _prepare_confirmation(params, deferred_instructions, _queue_context(last_target, last_control_type, last_window))
                line = _pending_action_notice(line, inline_preapproval=inline_preapproval, deferred=deferred_instructions)
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": {"kind": "type"}, "summary": line})
                summary.append(line)
                break
            elif kind == "hotkey":
                keys = _extract_hotkey(instruction)
                if not keys:
                    raise ValueError("Keine Tastenkombination erkannt.")
                window_hint = _extract_window_hint(instruction)
                target_window = window_hint or last_window
                if target_window:
                    last_window = target_window
                params = {"kind": "hotkey", "keys": keys, "window": target_window, "verify": True}
                prepared_action = params
                window_suffix = f' im Fenster "{target_window}"' if target_window else ""
                line = f"Freigabe vorbereitet: Ich wuerde die Tastenkombination {keys}{window_suffix} ausfuehren."
                deferred_instructions = limited_instructions[instruction_index + 1 :]
                _prepare_confirmation(params, deferred_instructions, _queue_context(last_target, last_control_type, last_window))
                line = _pending_action_notice(line, inline_preapproval=inline_preapproval, deferred=deferred_instructions)
                steps.append({"kind": "pending_confirmation", "instruction": instruction, "success": True, "params": params, "summary": line})
                summary.append(line)
                break
            else:
                steps.append({"kind": "unknown", "instruction": instruction, "success": False, "error": "Nicht als Desktop-Schritt erkannt."})
        except Exception as exc:
            text = f"Schritt konnte nicht ausgefuehrt werden: {exc}"
            steps.append({"kind": kind, "instruction": instruction, "success": False, "error": str(exc), "summary": text})
            summary.append(text)

    if not summary:
        data = ui_automation.ui_tree(max_depth=3, max_controls=80)
        text = _summarize_tree(data)
        steps.append({"kind": "observe", "instruction": "fallback observe", "success": True, "data": data, "summary": text})
        summary.append(text)

    return {
        "engine": "lexa-hermes-desktop-controller",
        "steps": steps,
        "summary": " ".join(summary),
        "prepared_action": prepared_action,
        "deferred_instructions": deferred_instructions,
        "queue_context": _queue_context(last_target, last_control_type, last_window),
        "inline_preapproval_ignored": inline_preapproval and prepared_action is not None,
        "inline_cancel_detected": inline_cancel,
        "needs_confirmation": prepared_action is not None,
        "needs_clarification": needs_clarification,
    }


def hermes_desktop_commit(
    kind: str = "click",
    text: str = "",
    control_type: str = "",
    window: str = "",
    occurrence: int = 1,
    button: str = "left",
    typing_text: str = "",
    typing_interval_ms: int = 8,
    keys: str = "",
    scroll_clicks: int = -3,
    verify: bool = True,
) -> dict:
    """Execute one prepared Hermes desktop action after Lexa confirmation."""
    action_kind = _ascii_fold(kind or "click").strip()
    verification: dict[str, Any] = {"checked": False}

    if action_kind == "click":
        result = ui_automation.ui_click(
            text=text or "darauf",
            control_type=control_type,
            window=window,
            occurrence=occurrence,
            button=button or "left",
            fallback_ocr=True,
        )
        if verify:
            time.sleep(0.25)
            try:
                after = ui_automation.ui_tree(window=window or result.get("window_title", ""), max_depth=2, max_controls=40)
                observed = bool(after.get("window_count") or after.get("control_count"))
                status = "passed" if observed else "unknown"
                verification = {
                    "checked": True,
                    "method": "ui_tree_after_click",
                    "status": status,
                    "passed": True if status == "passed" else None,
                    "window_count": after.get("window_count", 0),
                    "control_count": after.get("control_count", 0),
                    "summary": _summarize_tree(after),
                }
            except Exception as exc:
                verification = _verification_payload(
                    method="ui_tree_after_click",
                    status="unknown",
                    summary="Aktion wurde gesendet, aber die Nachpruefung konnte keinen UI-Snapshot lesen.",
                    error=str(exc),
                )
        target = result.get("matched_text") or result.get("target") or text or "Control"
        return {
            "kind": "click",
            "summary": f"Ausgefuehrt: Ich habe '{target}' bei X={result.get('x')}, Y={result.get('y')} geklickt.",
            "click": result,
            "verification": verification,
        }

    if action_kind == "scroll":
        focus_result = _focus_window_for_action(window)
        verify_window = str((focus_result or {}).get("window_title") or window or "").strip()
        # Wheel events go to the window under the cursor, not the focused window.
        # Park the cursor over the target window so the scroll lands there.
        cursor_result = _center_cursor_on_window(verify_window)
        # Wurde ein Zielfenster verlangt, der Cursor aber nicht darueber
        # platziert (Fenster nicht aufloesbar), wuerde an der aktuellen
        # Cursorposition gescrollt - moeglicherweise im falschen Fenster.
        # Dann lieber nicht blind scrollen, sondern dem Nutzer melden.
        window_requested = bool(str(window or "").strip())
        if window_requested and cursor_result is None:
            return {
                "kind": "scroll",
                "summary": (
                    f'Nicht ausgefuehrt: Das Zielfenster "{window}" wurde nicht gefunden. '
                    "Ich habe nicht gescrollt, um nicht im falschen Fenster zu landen."
                ),
                "result": {"scrolled": False, "reason": "target_window_not_found"},
                "focus": focus_result,
                "verification": _verification_payload(
                    method="scroll_target_window_not_found",
                    status="failed",
                    summary=f'Zielfenster "{window}" konnte nicht aufgeloest werden; Scroll abgebrochen.',
                ),
            }
        result = desktop_control.desktop_scroll(clicks=scroll_clicks)
        if isinstance(result, dict) and cursor_result is not None:
            result["cursor_centered"] = True
        if verify:
            time.sleep(0.15)
            try:
                after = ui_automation.ui_tree(window=verify_window, max_depth=2, max_controls=40)
                observed = bool(after.get("window_count") or after.get("control_count"))
                status = "passed" if observed else "unknown"
                verification = {
                    "checked": True,
                    "method": "ui_tree_after_scroll",
                    "status": status,
                    "passed": True if status == "passed" else None,
                    "window_count": after.get("window_count", 0),
                    "control_count": after.get("control_count", 0),
                    "summary": _summarize_tree(after),
                }
            except Exception as exc:
                verification = _verification_payload(
                    method="ui_tree_after_scroll",
                    status="unknown",
                    summary="Scroll wurde gesendet, aber die Nachpruefung konnte keinen UI-Snapshot lesen.",
                    error=str(exc),
                )
        direction = "nach oben" if int(scroll_clicks or 0) > 0 else "nach unten"
        return {
            "kind": "scroll",
            "summary": f"Ausgefuehrt: Ich habe {abs(int(scroll_clicks or 0))} Schritt(e) {direction} gescrollt.",
            "result": result,
            "focus": focus_result,
            "verification": verification,
        }

    if action_kind == "type":
        focus_result = _focus_window_for_action(window)
        verify_window = str((focus_result or {}).get("window_title") or window or "").strip()
        # Wurde ein Zielfenster verlangt, aber ein klar anderes Fenster fokussiert
        # (SetForegroundWindow kann an Windows-Foreground-Locks scheitern), dann
        # NICHT blind tippen — analog zum scroll-Pfad. Bei fehlendem Titel-Signal
        # wird bewusst nicht abgebrochen (kein Fehlalarm).
        window_requested = bool(str(window or "").strip())
        focused_title = str((focus_result or {}).get("window_title") or "").strip()
        if window_requested and not _focused_title_matches_target(window, focused_title):
            return {
                "kind": "type",
                "summary": (
                    f'Nicht ausgefuehrt: Das Zielfenster "{window}" wurde nicht fokussiert '
                    f'(aktiv: "{focused_title}"). Ich habe nicht getippt, um nicht im falschen '
                    "Fenster zu landen."
                ),
                "result": {"typed": False, "reason": "target_window_not_focused"},
                "focus": focus_result,
                "verification": _verification_payload(
                    method="type_target_window_mismatch",
                    status="failed",
                    summary=f'Zielfenster "{window}" wurde nicht fokussiert; Tippen abgebrochen.',
                ),
            }
        result = desktop_control.desktop_type(text=typing_text, interval_ms=typing_interval_ms)
        if verify:
            # Manche Apps aktualisieren den UIA-Baum/Value erst nach einem kurzen
            # Tick. Analog zu click/scroll/hotkey kurz warten, sonst meldet die
            # Verifikation faelschlich "failed", obwohl der Text getippt wurde.
            time.sleep(0.2)
            try:
                after = ui_automation.ui_tree(window=verify_window, max_depth=2, max_controls=40)
                ui_found = _tree_contains_text(after, typing_text)
                text_found = ui_found
                text_method = "uia_tree"
                screen_check_failed = False
                if not text_found:
                    try:
                        screen = desktop_engine.read_screen_text(window=verify_window)
                        payload = desktop_engine.ocr_payload(screen)
                        screen_text = str(payload.get("text") or "")
                        text_found = _visible_text_contains(screen_text, typing_text)
                        text_method = str(payload.get("method") or payload.get("provider") or "screen_text")
                    except Exception:
                        screen_check_failed = True
                        text_method = "uia_tree"
                status = "passed" if text_found else "unknown" if screen_check_failed else "failed"
                base_summary = _summarize_tree(after)
                if text_found:
                    summary = f"Erwarteter Text ist sichtbar. {base_summary}"
                elif screen_check_failed:
                    summary = f"Erwarteter Text wurde im UI-Snapshot nicht gefunden; OCR-Nachpruefung war nicht verfuegbar. {base_summary}"
                else:
                    summary = f"Erwarteter Text wurde nach dem Tippen nicht sichtbar gefunden. {base_summary}"
                verification = _verification_payload(
                    method="ui_tree_or_screen_text_after_type",
                    status=status,
                    summary=summary,
                    window_count=after.get("window_count", 0),
                    control_count=after.get("control_count", 0),
                    typed_text_found=bool(text_found),
                    text_check_method=text_method,
                )
            except Exception as exc:
                verification = _verification_payload(
                    method="ui_tree_after_type",
                    status="unknown",
                    summary="Text wurde gesendet, aber die Nachpruefung konnte keinen UI-Snapshot lesen.",
                    error=str(exc),
                )
        return {
            "kind": "type",
            "summary": "Ausgefuehrt: Ich habe den vorbereiteten Text in das aktive Feld getippt.",
            "result": result,
            "focus": focus_result,
            "verification": verification,
        }

    if action_kind == "hotkey":
        focus_result = _focus_window_for_action(window)
        verify_window = str((focus_result or {}).get("window_title") or window or "").strip()
        result = desktop_control.desktop_hotkey(keys=keys)
        verification = _verification_payload(
            method="hotkey_sent",
            status="unknown",
            summary="Tastenkombination wurde gesendet; ohne Zielzustand kann Hermes das Ergebnis nur begrenzt pruefen.",
            checked=bool(verify),
        )
        if verify and verify_window:
            time.sleep(0.15)
            try:
                after = ui_automation.ui_tree(window=verify_window, max_depth=2, max_controls=40)
                observed = bool(after.get("window_count") or after.get("control_count"))
                verification = _verification_payload(
                    method="ui_tree_after_hotkey",
                    status="passed" if observed else "failed",
                    summary=(
                        _summarize_tree(after)
                        if observed
                        else f'Zielfenster "{verify_window}" wurde nach der Tastenkombination nicht wiedergefunden.'
                    ),
                    window_count=after.get("window_count", 0),
                    control_count=after.get("control_count", 0),
                )
            except Exception as exc:
                verification = _verification_payload(
                    method="ui_tree_after_hotkey",
                    status="unknown",
                    summary="Tastenkombination wurde gesendet, aber die Nachpruefung konnte keinen UI-Snapshot lesen.",
                    error=str(exc),
                )
        return {
            "kind": "hotkey",
            "summary": f"Ausgefuehrt: Ich habe {keys} gedrueckt.",
            "result": result,
            "focus": focus_result,
            "verification": verification,
        }

    raise ValueError(f"Unbekannte Hermes-Desktop-Aktion: {kind}")
