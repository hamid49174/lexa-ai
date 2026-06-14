"""
Backend i18n module for Lexa AI.
Provides t() function for translating backend strings.
Language is configurable at runtime via set_language().
"""

import json
import logging
import re
from pathlib import Path

_log = logging.getLogger("lexa.i18n")
_lang = "de"
_translations: dict[str, dict[str, str]] = {}


def init(lang: str = "de") -> None:
    """Load translation files from backend/i18n/ directory."""
    global _lang
    i18n_dir = Path(__file__).parent
    # Always load the base locales plus the requested one, so a runtime
    # language other than de/en is actually available before we activate it.
    for locale in sorted({"de", "en", lang}):
        path = i18n_dir / f"{locale}.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    _translations[locale] = json.load(f)
                _log.debug("Loaded %d keys for locale '%s'", len(_translations[locale]), locale)
            except Exception as e:
                _log.warning("Failed to load i18n file %s: %s", path, e)
        else:
            _log.warning("i18n file not found: %s", path)
    # Only activate the requested language if it was actually loaded,
    # otherwise stay on German to avoid an inconsistent (all-fallback) state.
    if lang in _translations:
        _lang = lang
    else:
        _log.warning("i18n language '%s' not available, falling back to 'de'", lang)
        _lang = "de"


def set_language(lang: str) -> bool:
    """Set the active language. Returns True if language is available."""
    global _lang
    if lang in _translations:
        _lang = lang
        return True
    return False


def get_language() -> str:
    """Get the current language code."""
    return _lang


def t(key: str, **kwargs) -> str:
    """
    Translate a key to the current language.
    Supports {{param}} placeholders: t("error.msg", name="foo")
    Falls back to key itself if not found.
    """
    text = _translations.get(_lang, {}).get(key)
    if text is None:
        # Fallback to German, then to key
        text = _translations.get("de", {}).get(key, key)
    if kwargs:
        for k, v in kwargs.items():
            text = text.replace("{{" + k + "}}", str(v))
    # Warn if any placeholders were left unreplaced (missing kwargs), so that
    # broken raw '{{param}}' tokens in the UI become visible in the logs.
    leftover = re.findall(r"\{\{(\w+)\}\}", text)
    if leftover:
        _log.warning("Missing i18n parameter(s) %s for key '%s'", leftover, key)
    return text


# Auto-init on import
init()
