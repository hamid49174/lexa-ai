const SETTINGS_ALLOWED_THEMES = ["dark", "light"];
const SETTINGS_ALLOWED_ACCENTS = ["purple", "blue", "green", "rose", "amber"];
const SETTINGS_ALLOWED_FONT_SIZES = ["13", "14", "15", "16"];
const SETTINGS_ALLOWED_LANGUAGES = ["de", "en"];

function settingsSafeChoice(value, allowedValues, fallback) {
  const normalized = String(value == null ? "" : value);
  return allowedValues.includes(normalized) ? normalized : fallback;
}

function settingsSafeTheme(theme) {
  return settingsSafeChoice(theme, SETTINGS_ALLOWED_THEMES, "dark");
}

function settingsSafeAccent(accent) {
  return settingsSafeChoice(accent, SETTINGS_ALLOWED_ACCENTS, "purple");
}

function settingsSafeFontSize(size) {
  return settingsSafeChoice(size, SETTINGS_ALLOWED_FONT_SIZES, "14");
}

function settingsSafeLanguage(lang) {
  return settingsSafeChoice(lang, SETTINGS_ALLOWED_LANGUAGES, "de");
}
