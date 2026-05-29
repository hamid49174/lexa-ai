/* Safe preference storage for renderer UI state.
   Business data must stay in backend APIs or dedicated volatile helpers. */
const LEXA_STORAGE_MEMORY = new Map();

function lexaStorageBackend() {
  try { return window.localStorage || null; } catch (_e) { return null; }
}

function lexaStorageKey(key) {
  return String(key || "").trim();
}

function lexaStorageGet(key, fallback = "") {
  const safeKey = lexaStorageKey(key);
  if (!safeKey) return fallback;
  try {
    const value = lexaStorageBackend()?.getItem(safeKey);
    if (value !== null && value !== undefined) {
      LEXA_STORAGE_MEMORY.set(safeKey, value);
      return value;
    }
  } catch (_e) {
  }
  return LEXA_STORAGE_MEMORY.has(safeKey) ? LEXA_STORAGE_MEMORY.get(safeKey) : fallback;
}

function lexaStorageSet(key, value) {
  const safeKey = lexaStorageKey(key);
  if (!safeKey) return false;
  const text = String(value ?? "");
  LEXA_STORAGE_MEMORY.set(safeKey, text);
  try {
    lexaStorageBackend()?.setItem(safeKey, text);
    return true;
  } catch (_e) {
    return false;
  }
}

function lexaStorageRemove(key) {
  const safeKey = lexaStorageKey(key);
  if (!safeKey) return false;
  LEXA_STORAGE_MEMORY.delete(safeKey);
  try {
    lexaStorageBackend()?.removeItem(safeKey);
    return true;
  } catch (_e) {
    return false;
  }
}

function lexaStorageJson(key, fallback = []) {
  try {
    const parsed = JSON.parse(lexaStorageGet(key, ""));
    return parsed === null || parsed === undefined ? fallback : parsed;
  } catch (_e) {
    return fallback;
  }
}
