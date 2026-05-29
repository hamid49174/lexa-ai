/*
 * Chat state and transient renderer storage.
 * Backend SQLite remains the source of truth; these caches are volatile.
 */

// Data flow: SQLite (backend) = single source of truth.
// Renderer chat state is volatile: memory first, sessionStorage fallback.
// localStorage is intentionally not used for chat business data.
let _newConversationInFlight = false;
let _conversationSwitchSeq = 0;
let _conversationSwitchInFlight = 0;
const CHAT_HISTORY_CACHE_KEY = "lexa-chat-history";
const CHAT_DRAFT_CACHE_KEY = "lexa-chat-draft";
const CHAT_ACTIVE_CONVERSATION_CACHE_KEY = "lexa-active-conversation";
const _chatTransientMemory = new Map();
const _chatLegacyMigratedKeys = new Set();

function chatSessionStorage() {
  try { return window.sessionStorage || null; } catch (_e) { return null; }
}

function chatLegacyLocalStorage() {
  try { return window.localStorage || null; } catch (_e) { return null; }
}

function chatMigrateLegacyTransientKey(key) {
  const safeKey = String(key || "");
  if (!safeKey || _chatLegacyMigratedKeys.has(safeKey)) return;
  _chatLegacyMigratedKeys.add(safeKey);
  const local = chatLegacyLocalStorage();
  if (!local) return;
  try {
    const legacy = local.getItem(safeKey);
    if (legacy !== null && !_chatTransientMemory.has(safeKey)) {
      _chatTransientMemory.set(safeKey, legacy);
      try { chatSessionStorage()?.setItem(safeKey, legacy); } catch (_e) {}
    }
    local.removeItem(safeKey);
  } catch (_e) {}
}

function chatTransientGetItem(key) {
  const safeKey = String(key || "");
  if (!safeKey) return null;
  if (!_chatTransientMemory.has(safeKey)) chatMigrateLegacyTransientKey(safeKey);
  if (_chatTransientMemory.has(safeKey)) return _chatTransientMemory.get(safeKey);
  try {
    const value = chatSessionStorage()?.getItem(safeKey) ?? null;
    if (value !== null) _chatTransientMemory.set(safeKey, value);
    if (value !== null) return value;
  } catch (_e) {
  }
  const local = chatLegacyLocalStorage();
  if (!local) return null;
  try {
    const legacy = local.getItem(safeKey);
    if (legacy !== null) {
      _chatTransientMemory.set(safeKey, legacy);
      try { chatSessionStorage()?.setItem(safeKey, legacy); } catch (_e) {}
      local.removeItem(safeKey);
      return legacy;
    }
  } catch (_e) {}
  return null;
}

function chatTransientSetItem(key, value) {
  const safeKey = String(key || "");
  if (!safeKey) return;
  const text = String(value ?? "");
  _chatLegacyMigratedKeys.add(safeKey);
  _chatTransientMemory.set(safeKey, text);
  try { chatSessionStorage()?.setItem(safeKey, text); } catch (_e) {}
  try { chatLegacyLocalStorage()?.removeItem(safeKey); } catch (_e) {}
}

function chatTransientRemoveItem(key) {
  const safeKey = String(key || "");
  if (!safeKey) return;
  _chatLegacyMigratedKeys.add(safeKey);
  _chatTransientMemory.delete(safeKey);
  try { chatSessionStorage()?.removeItem(safeKey); } catch (_e) {}
  try { chatLegacyLocalStorage()?.removeItem(safeKey); } catch (_e) {}
}

function chatCachedHistorySnapshot() {
  try {
    const parsed = JSON.parse(chatTransientGetItem(CHAT_HISTORY_CACHE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_e) {
    return [];
  }
}

function chatSetActiveConversationId(convId) {
  const value = String(convId || "").trim();
  if (value) chatTransientSetItem(CHAT_ACTIVE_CONVERSATION_CACHE_KEY, value);
  else chatTransientRemoveItem(CHAT_ACTIVE_CONVERSATION_CACHE_KEY);
}

function chatGetActiveConversationId() {
  return chatTransientGetItem(CHAT_ACTIVE_CONVERSATION_CACHE_KEY) || "";
}

function clearChatActiveConversationId() {
  chatTransientRemoveItem(CHAT_ACTIVE_CONVERSATION_CACHE_KEY);
}

function setChatDraft(value) {
  const text = String(value || "");
  if (text) chatTransientSetItem(CHAT_DRAFT_CACHE_KEY, text);
  else chatTransientRemoveItem(CHAT_DRAFT_CACHE_KEY);
}

function getChatDraft() {
  return chatTransientGetItem(CHAT_DRAFT_CACHE_KEY) || "";
}

function clearChatDraft() {
  chatTransientRemoveItem(CHAT_DRAFT_CACHE_KEY);
}

function clearChatVolatileState() {
  [CHAT_HISTORY_CACHE_KEY, CHAT_DRAFT_CACHE_KEY, CHAT_ACTIVE_CONVERSATION_CACHE_KEY].forEach(chatTransientRemoveItem);
}
