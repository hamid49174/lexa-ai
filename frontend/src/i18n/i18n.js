/* ════════════════════════════════════════════════
   LEXA AI — Internationalization (i18n) Module
   Lightweight translation system with lazy-loaded
   language packs and fallback chain.
   Phase 42.1 — IPC-first loading for Electron reliability
   ════════════════════════════════════════════════ */

const LexaI18n = (() => {
  // Available languages
  const LANGUAGES = {
    de: { name: "Deutsch", file: "de.json" },
    en: { name: "English", file: "en.json" },
  };

  // State
  let _currentLang = lexaStorageGet("lexa-lang", "de");
  let _strings = {};       // Current language strings
  let _fallback = {};      // Fallback strings (German = default)
  let _loaded = false;
  let _loadPromise = null;

  // Resolve the base path for JSON packs at load time.
  // document.currentScript is only reliable while the script is executing
  // synchronously, so we cache it here (it is null inside async callbacks).
  // Query strings (e.g. i18n.js?v=2) are stripped to keep the path clean.
  const _basePath = (() => {
    const src = document.currentScript && document.currentScript.getAttribute("src");
    if (!src) return "./i18n/";
    return src.split("?")[0].replace(/i18n\.js$/, "");
  })();

  function _debug(message) {
    if (window.LEXA_DEBUG_I18N === true) console.debug(message);
  }

  // ── Core translation function ──────────────────
  function t(key, params) {
    const template = _strings[key] || _fallback[key] || key;
    if (!params) return template;

    // Replace {{param}} placeholders.
    // Coerce values to String to avoid "[object Object]" for accidental
    // object/array params; keep the placeholder for null/undefined.
    return template.replace(/\{\{(\w+)\}\}/g, (_, name) => {
      const value = params[name];
      return value !== undefined && value !== null ? String(value) : `{{${name}}}`;
    });
  }

  // ── Load language pack ─────────────────────────
  async function _loadLanguage(lang) {
    const info = LANGUAGES[lang];
    if (!info) {
      console.warn(`[i18n] Unknown language: ${lang}`);
      return {};
    }

    // Strategy 1: Electron IPC (most reliable — bypasses file:// and CSP issues)
    if (window.lexa && typeof window.lexa.loadI18n === "function") {
      try {
        const data = await window.lexa.loadI18n(lang);
        if (data && typeof data === "object" && Object.keys(data).length > 0) {
          _debug(`[i18n] Loaded ${lang} via IPC (${Object.keys(data).length} keys)`);
          return data;
        }
      } catch (e) {
        console.warn(`[i18n] IPC load failed for ${lang}:`, e.message);
      }
    }

    // Strategy 2: fetch() fallback (works in dev server / non-Electron)
    // Reuse the base path cached at load time via document.currentScript.
    // It already strips query strings (e.g. i18n.js?v=2) and is more reliable
    // than re-querying the DOM, where the script tag may be renamed/bundled.
    try {
      const resp = await fetch(_basePath + info.file);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      _debug(`[i18n] Loaded ${lang} via fetch (${Object.keys(data).length} keys)`);
      return data;
    } catch (e) {
      console.warn(`[i18n] fetch() also failed for ${lang}: ${e.message}`);
      return {};
    }
  }

  // ── Initialize ─────────────────────────────────
  async function init(lang) {
    if (lang) _currentLang = lang;

    // Always load German as fallback
    _fallback = await _loadLanguage("de");

    if (_currentLang !== "de") {
      _strings = await _loadLanguage(_currentLang);
    } else {
      _strings = _fallback;
    }

    _loaded = true;
    lexaStorageSet("lexa-lang", _currentLang);
    document.documentElement.lang = _currentLang;

    // Dispatch event for UI updates
    window.dispatchEvent(new CustomEvent("lexa-lang-changed", {
      detail: { lang: _currentLang }
    }));

    _debug(`[i18n] Initialized: ${_currentLang} (${Object.keys(_strings).length} strings, fallback: ${Object.keys(_fallback).length})`);
  }

  // ── Switch language ────────────────────────────
  async function setLanguage(lang) {
    if (!LANGUAGES[lang]) {
      console.warn(`[i18n] Unknown language: ${lang}`);
      return false;
    }
    _currentLang = lang;
    await init(lang);
    return true;
  }

  // ── Translate all data-i18n elements ───────────
  function translatePage() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      const translated = t(key);
      if (translated !== key) {
        el.textContent = translated;
      }
    });

    // Translate placeholders
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
      const key = el.getAttribute("data-i18n-placeholder");
      const translated = t(key);
      if (translated !== key) {
        el.placeholder = translated;
      }
    });

    // Translate titles/tooltips
    document.querySelectorAll("[data-i18n-title]").forEach(el => {
      const key = el.getAttribute("data-i18n-title");
      const translated = t(key);
      if (translated !== key) {
        el.title = translated;
      }
    });

    // Translate accessible labels
    document.querySelectorAll("[data-i18n-aria-label]").forEach(el => {
      const key = el.getAttribute("data-i18n-aria-label");
      const translated = t(key);
      if (translated !== key) {
        el.setAttribute("aria-label", translated);
      }
    });
  }

  // ── Getters ────────────────────────────────────
  function getCurrentLanguage() { return _currentLang; }
  function getAvailableLanguages() { return { ...LANGUAGES }; }
  function isLoaded() { return _loaded; }

  // Public API
  return {
    t,
    init,
    setLanguage,
    translatePage,
    getCurrentLanguage,
    getAvailableLanguages,
    isLoaded,
  };
})();

// Global shorthand
const t = LexaI18n.t;
// Expose locale for toLocaleTimeString / toLocaleDateString
// Maps language code to BCP 47 locale tag
Object.defineProperty(t, "_locale", {
  get() {
    const lang = LexaI18n.getCurrentLanguage();
    const localeMap = { de: "de-DE", en: "en-US" };
    return localeMap[lang] || "de-DE";
  }
});
