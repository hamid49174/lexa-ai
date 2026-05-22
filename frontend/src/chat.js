/* ════════════════════════════════════════════════
   LEXA AI — Chat Module
   Extracted from app.js for modularity.
   Contains: sendMessage, formatMessage, escapeHtml, addMessage,
   conversations, search, export, voice, suggestions,
   chat input history, snippet autocomplete, drag & drop.
   ════════════════════════════════════════════════ */

// ── ESCAPE HTML (shared utility) ─────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function bindKeyboardAction(el, handler, options = {}) {
  if (!el || typeof handler !== "function") return;
  const nativeInteractive = ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
  if (options.label) el.setAttribute("aria-label", options.label);
  if (!nativeInteractive) {
    if (!el.hasAttribute("role")) el.setAttribute("role", "button");
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    el.addEventListener("keydown", (e) => {
      if (e.target !== el) return;
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handler(e);
      }
    });
  }
  el.addEventListener("click", handler);
}

// ── CHAT PERSISTENCE ─────────────────────────────
// Data flow: SQLite (backend) = single source of truth.
// localStorage = session cache only (max CHAT_HISTORY_LOCAL_MAX messages).
// saveChatHistory() writes to localStorage as a fast local cache.
// loadChatHistory() tries backend conversation first, falls back to localStorage.
let _newConversationInFlight = false;
let _conversationSwitchSeq = 0;
let _conversationSwitchInFlight = 0;

function setNewConversationControlsBusy(busy) {
  document.querySelectorAll('[data-action="newConversation"]').forEach((btn) => {
    if (!(btn instanceof HTMLButtonElement)) return;
    btn.disabled = Boolean(busy);
    if (busy) btn.setAttribute("aria-busy", "true");
    else btn.removeAttribute("aria-busy");
  });
}

function getMessagePersistText(msg) {
  if (!msg) return "";
  const stored = msg.dataset?.persistText || "";
  if (stored.trim()) return stored.trim();
  return (
    msg.querySelector(".msg-text")?.textContent
    || msg.querySelector(".agent-summary")?.textContent
    || ""
  ).trim();
}

function setMessagePersistText(msg, text) {
  if (!msg) return;
  const source = String(text || "").trim();
  if (source) msg.dataset.persistText = source;
  else delete msg.dataset.persistText;
}

function lexaStringHash(value) {
  const text = String(value || "");
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) + hash) ^ text.charCodeAt(i);
  return (hash >>> 0).toString(36);
}

function normalizeAgentRunMeta(meta) {
  if (!meta || typeof meta !== "object") return null;
  const steps = Array.isArray(meta.steps)
    ? meta.steps.slice(0, 80).map((step, index) => ({
        index: step?.index ?? index,
        action: String(step?.action || "").slice(0, 120),
        status: String(step?.status || "").slice(0, 40),
        params: step?.params && typeof step.params === "object" ? step.params : {},
        duration_ms: Number(step?.duration_ms || 0) || 0,
      }))
    : [];
  const counts = meta.counts && typeof meta.counts === "object"
    ? ["found", "changed", "done", "blocked", "failed"].reduce((acc, kind) => {
        acc[kind] = Math.max(0, Number(meta.counts[kind] || 0));
        return acc;
      }, createAgentOutcomeCounts())
    : agentRunOutcomeCounts(steps);
  const summary = String(meta.summary || "").trim();
  const totalDurationMs = Math.max(0, Number(meta.total_duration_ms || meta.totalDurationMs || 0));
  if (!summary && !steps.length && !agentOutcomeTotal(counts)) return null;
  return { type: "agent_run", summary, steps, counts, total_duration_ms: totalDurationMs };
}

function getMessageAgentRunMeta(msg) {
  const raw = msg?.dataset?.agentRunMeta || "";
  if (!raw) return null;
  try {
    return normalizeAgentRunMeta(JSON.parse(raw));
  } catch (_e) {
    return null;
  }
}

function setMessageAgentRunMeta(msg, meta) {
  if (!msg) return null;
  const normalized = normalizeAgentRunMeta(meta);
  if (!normalized) {
    delete msg.dataset.agentRunMeta;
    msg.classList.remove("agent-message");
    return null;
  }
  msg.dataset.agentRunMeta = JSON.stringify(normalized);
  msg.classList.add("agent-message");
  return normalized;
}

function agentRunMetaMessageKey(role, content) {
  return `${String(role || "assistant")}:${lexaStringHash(content)}`;
}

function agentRunMetaCacheKey(convId) {
  return `lexa-agent-run-meta:${String(convId || "local")}`;
}

function agentRunAttentionResolvedCacheKey(convId) {
  return `lexa-agent-run-attention-resolved:${String(convId || "local")}`;
}

function agentRunAttentionResolvedHistoryCacheKey() {
  return "lexa-agent-run-attention-resolved-history";
}

function agentRunAttentionResolvedHistoryLimit() {
  return 12;
}

function agentRunAttentionResolvedHistoryMaxAgeMs() {
  return 14 * 24 * 60 * 60 * 1000;
}

function agentRunAttentionRecordKey(record, index = 0) {
  if (record?.key) return String(record.key);
  return `record:${index}:${lexaStringHash(JSON.stringify(record?.meta || {}))}`;
}

function agentRunAttentionResolvedKeys(convId) {
  try {
    const parsed = JSON.parse(localStorage.getItem(agentRunAttentionResolvedCacheKey(convId)) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch (_e) {
    return new Set();
  }
}

function saveAgentRunAttentionResolvedKeys(convId, keys) {
  const list = Array.from(keys || []).map(String).filter(Boolean);
  try {
    if (list.length) localStorage.setItem(agentRunAttentionResolvedCacheKey(convId), JSON.stringify(list));
    else localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
  } catch (e) {
    console.warn("[Chat] Failed to save resolved Agent attention:", e.message || e);
  }
}

function normalizeAgentRunAttentionResolvedHistoryItems(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => ({
      convId: item?.convId,
      title: String(item?.title || t("chat.newChatTitle")).slice(0, 120),
      failed: Math.max(0, Number(item?.failed || 0)),
      blocked: Math.max(0, Number(item?.blocked || 0)),
      keys: Array.isArray(item?.keys) ? item.keys.map(String).filter(Boolean) : [],
      resolved_at: Math.max(0, Number(item?.resolved_at || 0)),
    }))
    .filter((item) => item.convId && item.keys.length);
}

function agentRunAttentionResolvedHistoryItemHasEvidence(item) {
  const keys = Array.isArray(item?.keys) ? item.keys.map(String).filter(Boolean) : [];
  if (!item?.convId || !keys.length) return false;
  const resolved = agentRunAttentionResolvedKeys(item.convId);
  const stillResolved = keys.filter((key) => resolved.has(key));
  if (!stillResolved.length) return false;
  let records = [];
  try {
    records = JSON.parse(localStorage.getItem(agentRunMetaCacheKey(item.convId)) || "[]");
  } catch (_e) {
    records = [];
  }
  if (!Array.isArray(records) || !records.length) return false;
  const recordKeys = new Set(records.map((record, index) => agentRunAttentionRecordKey(record, index)));
  return stillResolved.some((key) => recordKeys.has(key));
}

function pruneAgentRunAttentionResolvedHistoryItems(items, now = Date.now()) {
  const maxAgeMs = agentRunAttentionResolvedHistoryMaxAgeMs();
  return normalizeAgentRunAttentionResolvedHistoryItems(items)
    .filter((item) => {
      if (item.resolved_at && now - item.resolved_at > maxAgeMs) return false;
      return agentRunAttentionResolvedHistoryItemHasEvidence(item);
    })
    .slice(0, agentRunAttentionResolvedHistoryLimit());
}

function saveAgentRunAttentionResolvedHistory(items) {
  const list = normalizeAgentRunAttentionResolvedHistoryItems(items)
    .slice(0, agentRunAttentionResolvedHistoryLimit());
  try {
    if (list.length) localStorage.setItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify(list));
    else localStorage.removeItem(agentRunAttentionResolvedHistoryCacheKey());
  } catch (e) {
    console.warn("[Chat] Failed to save Agent attention history:", e.message || e);
  }
}

function agentAttentionLooksTechnicalTitle(title) {
  const text = String(title || "").trim().toLowerCase();
  if (!text) return true;
  return (
    /\bagent\s+(run|attention|task)\b/.test(text) ||
    /\b(blocked|reloaded|clean)\s+agent\b/.test(text) ||
    /\bneeds\s+confirmation\b/.test(text)
  );
}

function agentAttentionDisplayTitle(title) {
  const raw = String(title || "").trim();
  if (agentAttentionLooksTechnicalTitle(raw)) return t("chat.agentAttentionFallbackTitle");
  return raw.length > 80 ? raw.slice(0, 77) + "..." : raw;
}

function agentAttentionStatusSummary(failed, blocked) {
  const failedCount = Math.max(0, Number(failed || 0));
  const blockedCount = Math.max(0, Number(blocked || 0));
  if (failedCount > 0 && blockedCount > 0) {
    return t("chat.agentAttentionStatusBoth", { failed: failedCount, blocked: blockedCount });
  }
  if (failedCount > 0) return t("chat.agentAttentionStatusReview", { count: failedCount });
  if (blockedCount > 0) return t("chat.agentAttentionStatusApproval", { count: blockedCount });
  return t("chat.agentAttentionStatusClear");
}

function agentRunAttentionResolvedHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(agentRunAttentionResolvedHistoryCacheKey()) || "[]");
    const normalized = normalizeAgentRunAttentionResolvedHistoryItems(parsed);
    const pruned = pruneAgentRunAttentionResolvedHistoryItems(normalized);
    if (JSON.stringify(pruned) !== JSON.stringify(normalized.slice(0, agentRunAttentionResolvedHistoryLimit()))) {
      saveAgentRunAttentionResolvedHistory(pruned);
    }
    return pruned;
  } catch (_e) {
    return [];
  }
}

function agentRunAttentionResolvedHistoryForConversations(convList) {
  const history = agentRunAttentionResolvedHistory();
  const ids = new Set((Array.isArray(convList) ? convList : [])
    .map((conv) => String(conv?.id || ""))
    .filter(Boolean));
  if (!ids.size) return [];
  const visible = history.filter((item) => ids.has(String(item.convId)));
  if (visible.length !== history.length) saveAgentRunAttentionResolvedHistory(visible);
  return visible;
}

function recordAgentAttentionResolution(item) {
  const keys = Array.isArray(item?.keys) ? item.keys.map(String).filter(Boolean) : [];
  if (!item?.convId || !keys.length) return;
  const signature = `${String(item.convId)}:${keys.slice().sort().join("|")}`;
  const existing = agentRunAttentionResolvedHistory()
    .filter((entry) => `${String(entry.convId)}:${entry.keys.slice().sort().join("|")}` !== signature);
  saveAgentRunAttentionResolvedHistory([{
    convId: item.convId,
    title: String(item.title || t("chat.newChatTitle")).slice(0, 120),
    failed: Math.max(0, Number(item.failed || 0)),
    blocked: Math.max(0, Number(item.blocked || 0)),
    keys,
    resolved_at: Date.now(),
  }, ...existing]);
}

function removeAgentAttentionResolution(convId, keys) {
  const keySet = new Set((Array.isArray(keys) ? keys : [keys]).map(String).filter(Boolean));
  if (!convId || !keySet.size) return;
  saveAgentRunAttentionResolvedHistory(agentRunAttentionResolvedHistory().filter((item) =>
    String(item.convId) !== String(convId) || !item.keys.some((key) => keySet.has(String(key)))
  ));
}

function restoreAgentAttentionHistoryItem(item) {
  const keys = Array.isArray(item?.keys) ? item.keys.map(String).filter(Boolean) : [];
  if (!item?.convId || !keys.length) return false;
  const resolved = agentRunAttentionResolvedKeys(item.convId);
  keys.forEach((key) => resolved.delete(key));
  saveAgentRunAttentionResolvedKeys(item.convId, resolved);
  removeAgentAttentionResolution(item.convId, keys);
  renderConversationList();
  showToast(t("chat.agentAttentionRestored"), "success", 1800);
  return true;
}

function saveAgentRunMetaForConversation(convId) {
  if (!convId || !chatMessages) return;
  const records = [];
  chatMessages.querySelectorAll(".message").forEach((msg) => {
    const meta = getMessageAgentRunMeta(msg);
    if (!meta) return;
    const text = getMessagePersistText(msg);
    if (!text) return;
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    records.push({ key: agentRunMetaMessageKey(role, text), meta });
  });
  try {
    if (records.length) localStorage.setItem(agentRunMetaCacheKey(convId), JSON.stringify(records));
    else localStorage.removeItem(agentRunMetaCacheKey(convId));
  } catch (e) {
    console.warn("[Chat] Failed to save Agent run metadata:", e.message || e);
  }
}

function clearAgentRunLocalStateForConversation(convId) {
  if (!convId) return;
  localStorage.removeItem(agentRunMetaCacheKey(convId));
  localStorage.removeItem(agentRunAttentionResolvedCacheKey(convId));
  saveAgentRunAttentionResolvedHistory(agentRunAttentionResolvedHistory().filter((item) => String(item.convId) !== String(convId)));
}

function markConversationClearedLocally(convId) {
  if (!convId) return false;
  const convList = LexaState.get("conversationsList");
  if (!Array.isArray(convList)) return false;
  let changed = false;
  const next = convList.map((conv) => {
    if (String(conv?.id) !== String(convId)) return conv;
    changed = true;
    return { ...conv, message_count: 0, last_message: "", messages: [] };
  });
  if (changed) LexaState.set("conversationsList", next);
  return changed;
}

function removeConversationLocally(convId) {
  const convList = LexaState.get("conversationsList");
  const next = (Array.isArray(convList) ? convList : []).filter((conv) => String(conv?.id) !== String(convId));
  LexaState.set("conversationsList", next);
  if (typeof updateConversationCount === "function") {
    updateConversationCount(next.length);
  }
  renderConversationList();
  return next;
}

function upsertConversationLocally(conv) {
  if (!conv?.id) return [];
  const convList = LexaState.get("conversationsList");
  const existing = Array.isArray(convList) ? convList : [];
  const normalized = {
    id: conv.id,
    title: conv.title || t("chat.newChatTitle"),
    message_count: Number(conv.message_count || 0),
    last_message: conv.last_message || "",
    ...conv,
  };
  const next = [normalized, ...existing.filter((item) => String(item?.id) !== String(conv.id))];
  LexaState.set("conversationsList", next);
  if (typeof updateConversationCount === "function") {
    updateConversationCount(next.length);
  }
  renderConversationList();
  return next;
}

function updateConversationTitleLocally(convId, title) {
  const nextTitle = String(title || "").trim();
  if (!convId || !nextTitle) return false;
  const convList = LexaState.get("conversationsList");
  if (!Array.isArray(convList)) return false;
  let changed = false;
  const next = convList.map((conv) => {
    if (String(conv?.id) !== String(convId)) return conv;
    if (conv.title === nextTitle) return conv;
    changed = true;
    return { ...conv, title: nextTitle };
  });
  if (!changed) return false;
  LexaState.set("conversationsList", next);
  renderConversationList();
  return true;
}

function createAgentRunMetaResolver(convId) {
  let records = [];
  try {
    records = JSON.parse(localStorage.getItem(agentRunMetaCacheKey(convId)) || "[]");
  } catch (_e) {
    records = [];
  }
  if (!Array.isArray(records) || !records.length) return () => null;
  const used = new Set();
  return (role, content) => {
    const key = agentRunMetaMessageKey(role, content);
    const index = records.findIndex((record, idx) => !used.has(idx) && record?.key === key);
    if (index < 0) return null;
    used.add(index);
    return normalizeAgentRunMeta(records[index].meta);
  };
}

function agentRunAttentionForConversation(conv) {
  const convId = conv?.id;
  if (!convId) return null;
  let records = [];
  try {
    records = JSON.parse(localStorage.getItem(agentRunMetaCacheKey(convId)) || "[]");
  } catch (_e) {
    records = [];
  }
  if (!Array.isArray(records) || !records.length) return null;
  const totals = { failed: 0, blocked: 0, runs: 0 };
  const resolved = agentRunAttentionResolvedKeys(convId);
  const keys = [];
  records.forEach((record, index) => {
    const key = agentRunAttentionRecordKey(record, index);
    if (resolved.has(key)) return;
    const meta = normalizeAgentRunMeta(record?.meta);
    if (!meta) return;
    const failed = Number(meta.counts?.failed || 0);
    const blocked = Number(meta.counts?.blocked || 0);
    if (failed > 0 || blocked > 0) {
      totals.failed += failed;
      totals.blocked += blocked;
      totals.runs += 1;
      keys.push(key);
    }
  });
  if (!totals.runs) return null;
  const title = conv.title || t("chat.newChatTitle");
  return {
    convId,
    title,
    displayTitle: agentAttentionDisplayTitle(title),
    statusSummary: agentAttentionStatusSummary(totals.failed, totals.blocked),
    keys,
    ...totals,
  };
}

function agentRunAttentionListForConversations(convList) {
  return (Array.isArray(convList) ? convList : [])
    .map(agentRunAttentionForConversation)
    .filter(Boolean);
}

function updateAgentAttentionFilterButton(attentionCount, active) {
  const btn = document.getElementById("agent-attention-filter-btn");
  if (!btn) return;
  const hasAttention = Number(attentionCount) > 0;
  btn.hidden = !hasAttention;
  btn.disabled = !hasAttention;
  btn.classList.toggle("hidden", !hasAttention);
  btn.classList.toggle("active", Boolean(active && hasAttention));
  btn.setAttribute("aria-hidden", hasAttention ? "false" : "true");
  btn.setAttribute("aria-pressed", active && hasAttention ? "true" : "false");
  const label = active && hasAttention
    ? t("chat.agentAttentionFilterClear", { count: attentionCount })
    : t("chat.agentAttentionFilterLabel", { count: attentionCount });
  btn.title = label;
  btn.setAttribute("aria-label", label);
}

function updateAgentAttentionHeaderSummary(attentionList, convList) {
  const summary = document.getElementById("agent-attention-summary");
  if (!summary) return;
  const openCount = Array.isArray(attentionList) ? attentionList.length : 0;
  const resolvedCount = agentRunAttentionResolvedHistoryForConversations(convList).length;
  const hasConversations = Array.isArray(convList) && convList.length > 0;
  if (!openCount && !resolvedCount) {
    summary.textContent = "";
    if (hasConversations) {
      summary.hidden = false;
      summary.classList.remove("hidden");
      summary.title = t("chat.agentAttentionHeaderClearLabel");
      summary.setAttribute("aria-label", summary.title);
      const clear = document.createElement("span");
      clear.className = "agent-attention-summary-chip clear";
      clear.textContent = t("chat.agentAttentionHeaderClear");
      summary.appendChild(clear);
      return;
    }
    summary.hidden = true;
    summary.classList.add("hidden");
    summary.removeAttribute("title");
    summary.removeAttribute("aria-label");
    return;
  }
  summary.hidden = false;
  summary.classList.remove("hidden");
  summary.textContent = "";
  summary.title = t("chat.agentAttentionHeaderLabel", { open: openCount, resolved: resolvedCount });
  summary.setAttribute("aria-label", summary.title);
  if (openCount) {
    const open = document.createElement("span");
    open.className = "agent-attention-summary-chip open";
    open.textContent = t("chat.agentAttentionHeaderOpen", { count: openCount });
    summary.appendChild(open);
  }
  if (resolvedCount) {
    const resolved = document.createElement("span");
    resolved.className = "agent-attention-summary-chip resolved";
    resolved.textContent = t("chat.agentAttentionHeaderResolved", { count: resolvedCount });
    summary.appendChild(resolved);
  }
}

function toggleAgentAttentionFilter() {
  const attentionCount = agentRunAttentionListForConversations(LexaState.get("conversationsList") || []).length;
  const next = attentionCount > 0 && !LexaState.get("conversationAttentionOnly");
  LexaState.set("conversationAttentionOnly", next);
  renderConversationList();
}

function resolveAgentAttentionForConversation(convId, title = "") {
  const attention = agentRunAttentionForConversation({ id: convId, title });
  if (!attention?.keys?.length) return false;
  const resolved = agentRunAttentionResolvedKeys(convId);
  attention.keys.forEach((key) => resolved.add(key));
  saveAgentRunAttentionResolvedKeys(convId, resolved);
  recordAgentAttentionResolution(attention);
  renderConversationList();
  showToast(t("chat.agentAttentionResolved"), "success", 1800);
  return true;
}

function renderAgentAttentionPanel(container, convList) {
  if (!container) return 0;
  const attention = agentRunAttentionListForConversations(convList).slice(0, 4);
  if (!attention.length) return 0;
  const panel = document.createElement("div");
  panel.className = "agent-attention-panel";
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", t("chat.agentAttentionTitle"));
  const title = document.createElement("div");
  title.className = "agent-attention-title";
  title.textContent = t("chat.agentAttentionTitle");
  const list = document.createElement("div");
  list.className = "agent-attention-list";
  list.setAttribute("role", "list");
  attention.forEach((item) => {
    const displayTitle = item.displayTitle || agentAttentionDisplayTitle(item.title);
    const statusSummary = item.statusSummary || agentAttentionStatusSummary(item.failed, item.blocked);
    const row = document.createElement("div");
    row.className = "agent-attention-row";
    row.setAttribute("role", "listitem");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "agent-attention-item";
    btn.setAttribute("aria-label", t("chat.agentAttentionOpenLabel", {
      title: displayTitle,
      failed: item.failed,
      blocked: item.blocked,
      summary: statusSummary,
    }));
    const label = document.createElement("span");
    label.className = "agent-attention-conv";
    label.textContent = displayTitle;
    const count = document.createElement("span");
    count.className = "agent-attention-count";
    count.textContent = statusSummary;
    btn.appendChild(label);
    btn.appendChild(count);
    btn.addEventListener("click", () => switchConversation(item.convId));
    const resolveBtn = document.createElement("button");
    resolveBtn.type = "button";
    resolveBtn.className = "agent-attention-resolve-btn";
    resolveBtn.title = t("chat.agentAttentionResolveLabel", { title: displayTitle });
    resolveBtn.setAttribute("aria-label", t("chat.agentAttentionResolveLabel", { title: displayTitle }));
    resolveBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>';
    resolveBtn.addEventListener("click", () => resolveAgentAttentionForConversation(item.convId, item.title));
    row.appendChild(btn);
    row.appendChild(resolveBtn);
    list.appendChild(row);
  });
  panel.appendChild(title);
  panel.appendChild(list);
  container.appendChild(panel);
  return attention.length;
}

function renderAgentAttentionFilterNote(container, count) {
  if (!container) return;
  const note = document.createElement("div");
  note.className = "agent-attention-filter-note";
  note.textContent = t("chat.agentAttentionFilterActive", { count });
  container.appendChild(note);
}

function renderAgentResolvedHistoryPanel(container, convList) {
  if (!container) return 0;
  const items = agentRunAttentionResolvedHistoryForConversations(convList).slice(0, 3);
  if (!items.length) return 0;
  const panel = document.createElement("div");
  panel.className = "agent-resolved-panel";
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", t("chat.agentResolvedTitle"));
  const title = document.createElement("div");
  title.className = "agent-resolved-title";
  title.textContent = t("chat.agentResolvedTitle");
  const list = document.createElement("div");
  list.className = "agent-resolved-list";
  list.setAttribute("role", "list");
  items.forEach((item) => {
    const displayTitle = agentAttentionDisplayTitle(item.title);
    const statusSummary = agentAttentionStatusSummary(item.failed, item.blocked);
    const row = document.createElement("div");
    row.className = "agent-resolved-row";
    row.setAttribute("role", "listitem");
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "agent-resolved-item";
    openBtn.setAttribute("aria-label", t("chat.agentResolvedOpenLabel", {
      title: displayTitle,
      failed: item.failed,
      blocked: item.blocked,
      summary: statusSummary,
    }));
    const label = document.createElement("span");
    label.className = "agent-resolved-conv";
    label.textContent = displayTitle;
    const count = document.createElement("span");
    count.className = "agent-resolved-count";
    count.textContent = statusSummary;
    openBtn.appendChild(label);
    openBtn.appendChild(count);
    openBtn.addEventListener("click", () => switchConversation(item.convId));
    const restoreBtn = document.createElement("button");
    restoreBtn.type = "button";
    restoreBtn.className = "agent-resolved-restore-btn";
    restoreBtn.title = t("chat.agentResolvedRestoreLabel", { title: displayTitle });
    restoreBtn.setAttribute("aria-label", t("chat.agentResolvedRestoreLabel", { title: displayTitle }));
    restoreBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/></svg>';
    restoreBtn.addEventListener("click", () => restoreAgentAttentionHistoryItem(item));
    row.appendChild(openBtn);
    row.appendChild(restoreBtn);
    list.appendChild(row);
  });
  panel.appendChild(title);
  panel.appendChild(list);
  container.appendChild(panel);
  return items.length;
}

function isPersistableChatMessage(msg) {
  return Boolean(msg) && !msg.classList.contains("typing-message");
}

function saveChatHistory() {
  if (!chatMessages) return;
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg) => {
    if (!isPersistableChatMessage(msg)) return;
    const text = getMessagePersistText(msg);
    const type = msg.classList.contains("user-message") ? "user" : "system";
    if (text) {
      const meta = getMessageAgentRunMeta(msg);
      messages.push(meta ? { text, type, meta } : { text, type });
    }
  });
  const toSave = messages.slice(-(LexaConfig.CHAT_HISTORY_LOCAL_MAX));
  try {
    localStorage.setItem("lexa-chat-history", JSON.stringify(toSave));
  } catch (e) { console.warn("[Chat] Failed to save chat history to localStorage:", e.message || e); }
}

function persistChatAfterDomMutation() {
  saveChatHistory();
  saveCurrentConversation();
}

function clearRenderedChatMessages() {
  if (!chatMessages) return;
  chatMessages.querySelectorAll(".message").forEach((msg) => msg.remove());
}

// ── AUTO-SAVE CONVERSATION ────────────────────────
async function autoSaveConversation() {
  const convId = LexaState.get("currentConversationId");
  if (_conversationSwitchInFlight > 0) return;
  if (!convId || !LexaState.get("backendOnline") || !chatMessages) return;
  try {
    saveAgentRunMetaForConversation(convId);
    const messages = [];
    chatMessages.querySelectorAll(".message").forEach((msg) => {
      if (!isPersistableChatMessage(msg)) return;
      const text = getMessagePersistText(msg);
      const role = msg.classList.contains("user-message") ? "user" : "assistant";
      if (text) messages.push({ role, content: text });
    });
    if (messages.length === 0) return;
    await window.lexa.conversationUpdate(convId, { messages });
  } catch (e) { console.warn("[Chat] Auto-save conversation failed:", e.message || e); }
}

// ── TIMER POLLING ─────────────────────────────────
// Reuse a single AudioContext to avoid browser resource limits (~6 max)
let _sharedAudioCtx = null;
function _getAudioCtx() {
  if (!_sharedAudioCtx || _sharedAudioCtx.state === "closed") {
    _sharedAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  // Resume if suspended (browser autoplay policy)
  if (_sharedAudioCtx.state === "suspended") _sharedAudioCtx.resume();
  return _sharedAudioCtx;
}
function playBeep(type = "timer") {
  try {
    const ctx = _getAudioCtx();
    const notes = type === "pomodoro"
      ? [523.25, 659.25, 783.99, 1046.50]
      : [880, 880];
    let t = ctx.currentTime;
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, t + i * 0.15);
      gain.gain.setValueAtTime(0.25, t + i * 0.15);
      gain.gain.exponentialRampToValueAtTime(0.001, t + i * 0.15 + 0.3);
      osc.start(t + i * 0.15);
      osc.stop(t + i * 0.15 + 0.35);
    });
  } catch (e) { console.warn("[Chat] Beep playback failed:", e.message || e); }
}

async function checkTimers() {
  if (!LexaState.get("backendOnline")) return;
  try {
    const data = await window.lexa.timers();
    const timers = data.timers || [];
    if (timers.length === 0) return;
    for (const timer of timers) {
      playBeep("timer");
      showToast(`\u23f0 ${timer.message}`, "success", 8000);
      sendNotification("Lexa Timer", timer.message);
      addMessage(`\u23f0 Timer: ${timer.message}`, "system", null, false, true);
    }
    await window.lexa.timersAcknowledge();
  } catch (e) { console.warn("[Chat] Timer check failed:", e.message || e); }
  try {
    const pomo = await window.lexa.pomodoroStatus();
    if (pomo.completed_just_now) {
      const task = pomo.completed_task || t("chat.pomodoroTask");
      playBeep("pomodoro");
      showToast(`\u23f0 ${t("pomodoro.completed")}: ${task}`, "success", 8000);
      sendNotification("Lexa Pomodoro", t("chat.pomodoroFinishedNotif", {task}));
      addMessage(`\u23f0 ${t("chat.pomodoroFinishedChat", {task})}`, "system", null, false, true);
      await window.lexa.pomodoroAcknowledge();
    }
  } catch (e) { console.warn("[Chat] Pomodoro check failed:", e.message || e); }
}

function renderPersistedConversationMessages(messages, convId = null) {
  const items = Array.isArray(messages) ? messages : [];
  const agentMetaForMessage = convId ? createAgentRunMetaResolver(convId) : null;
  items.forEach((msg) => {
    const text = msg?.content ?? msg?.text ?? "";
    if (!String(text).trim()) return;
    const type = msg?.role === "user" || msg?.type === "user" ? "user" : "system";
    const meta = type === "system"
      ? (msg?.meta || (agentMetaForMessage ? agentMetaForMessage(msg?.role || "assistant", text) : null))
      : null;
    addMessage(text, type, null, false, true, { agentRunMeta: meta });
  });
}

async function loadChatHistory() {
  // Try loading from backend conversation (SQLite = source of truth)
  const convId = LexaState.get("currentConversationId") || localStorage.getItem("lexa-active-conversation");
  if (convId && LexaState.get("backendOnline")) {
    try {
      const conv = await window.lexa.conversationGet(convId);
      if (conv && !conv.detail && Array.isArray(conv.messages)) {
        const activeConvId = conv.id || convId;
        clearRenderedChatMessages();
        LexaState.set("currentConversationId", activeConvId);
        renderPersistedConversationMessages(conv.messages, activeConvId);
        saveAgentRunMetaForConversation(activeConvId);
        return;
      }
    } catch (e) { console.warn("[Chat] Failed to load conversation from backend, falling back to localStorage:", e.message || e); }
  }
  // Fallback: load from localStorage session cache
  try {
    const saved = localStorage.getItem("lexa-chat-history");
    if (!saved) return;
    const messages = JSON.parse(saved);
    if (!Array.isArray(messages)) return;
    clearRenderedChatMessages();
    renderPersistedConversationMessages(messages, convId);
    if (convId) saveAgentRunMetaForConversation(convId);
  } catch (e) { console.warn("[Chat] Failed to load chat history from localStorage:", e.message || e); }
}

// ── CHAT MESSAGE DISPLAY ─────────────────────────
function clearChat() {
  const msgs = chatMessages.querySelectorAll(".message");
  msgs.forEach((m) => m.remove());
  localStorage.removeItem("lexa-chat-history");
  const convId = LexaState.get("currentConversationId");
  if (convId) {
    clearAgentRunLocalStateForConversation(convId);
    markConversationClearedLocally(convId);
    renderConversationList();
  }
  if (convId) {
    window.lexa.conversationUpdate(convId, { messages: [] })
      .then(() => refreshConversationSidebar())
      .catch((e) => {
        console.warn("[Chat] Failed to sync cleared conversation:", e.message || e);
        showToast(t("toast.chatClearSyncFailed"), "warning", 3500);
      });
  }
  // Restore hero greeting view — orb always stays visible
  const sleekGreeting = document.getElementById("sleek-greeting");
  if (sleekGreeting) sleekGreeting.classList.remove("hidden");
  const floatingCards = document.getElementById("floating-cards-container");
  if (floatingCards) floatingCards.classList.remove("hidden");
  const chatMessagesEl = document.getElementById("chat-messages");
  if (chatMessagesEl) chatMessagesEl.classList.add("hidden");
  // Clear orb transcript
  clearOrbTranscript();
  // Return to ambient mode
  window._chatViewOpen = false;
  const chatArrow = document.getElementById("chat-view-arrow");
  if (chatArrow) chatArrow.classList.remove("flipped");
  showToast(t("toast.chatCleared"), "info", 2000);
}

function renderMessageAvatar(avatar, type = "system") {
  avatar.textContent = "";
  avatar.setAttribute("aria-label", type === "user" ? t("chat.userNameYou") : t("chat.systemNameLexa"));

  if (type === "user") {
    return;
  }

  const logo = document.createElement("img");
  logo.src = "./logo.png";
  logo.alt = "";
  logo.setAttribute("aria-hidden", "true");
  avatar.appendChild(logo);
}

function clipAgentStepText(value, limit = 64) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}...` : text;
}

function agentStepParamSummary(params) {
  if (!params || typeof params !== "object") return "";
  const preferredKeys = ["url", "query", "title", "message", "prompt", "path", "file_path", "dir_path", "name", "command"];
  for (const key of preferredKeys) {
    const value = params[key];
    if (value === undefined || value === null || value === "") continue;
    if (key === "url") {
      try {
        const parsed = new URL(String(value));
        return clipAgentStepText(parsed.hostname || value, 54);
      } catch (_e) {
        return clipAgentStepText(value, 54);
      }
    }
    if (key === "path" || key === "file_path" || key === "dir_path") {
      const parts = String(value).split(/[\\/]+/).filter(Boolean);
      return clipAgentStepText(parts[parts.length - 1] || value, 54);
    }
    if (key === "name" || key === "command") {
      return clipAgentStepText(String(value).replace(/[_-]+/g, " "), 54);
    }
    return clipAgentStepText(value, 54);
  }
  const first = Object.values(params).find((value) => ["string", "number", "boolean"].includes(typeof value));
  return first === undefined ? "" : clipAgentStepText(first, 54);
}

function agentStepActionLabel(action) {
  const name = String(action || "").trim();
  if (!name) return t("chat.agentStepUnknown");
  const commandKey = `cmd.desc.${name}`;
  const commandLabel = t(commandKey);
  if (commandLabel && commandLabel !== commandKey) return commandLabel;
  if (name.startsWith("personal_os_")) return t("chat.agentStepPersonalOs");
  if (name.startsWith("web_") || name.startsWith("browser_")) return t("chat.agentStepWeb");
  if (name.startsWith("file_") || name.includes("_file") || name.includes("pdf")) return t("chat.agentStepFile");
  if (name.startsWith("git_")) return t("chat.agentStepGit");
  if (name.startsWith("memory_") || name.startsWith("note_") || name.startsWith("todo_") || name.startsWith("routine_")) return t("chat.agentStepKnowledge");
  if (name.startsWith("email_") || name.startsWith("calendar_") || name.startsWith("telegram_") || name.startsWith("discord_")) return t("chat.agentStepComms");
  if (name.startsWith("app_") || name.startsWith("system_") || name.startsWith("process_") || name.startsWith("window_") || name.startsWith("volume_") || name.startsWith("brightness_") || name.startsWith("wifi_") || name.startsWith("battery_") || name === "screenshot") return t("chat.agentStepSystem");
  return t("chat.agentStepTool");
}

function agentStepDisplayLabel(step) {
  const label = agentStepActionLabel(step?.action);
  const detail = agentStepParamSummary(step?.params);
  return detail ? t("chat.agentStepWithDetail", { label, detail }) : label;
}

function agentStepTechnicalLabel(step) {
  const action = String(step?.action || "").trim() || t("chat.agentStepUnknown");
  const params = step?.params && typeof step.params === "object" ? step.params : {};
  const parts = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${clipAgentStepText(value, 80)}`);
  return parts.length ? `${action}(${parts.join(", ")})` : action;
}

function agentStepOutcomeKind(step) {
  const status = String(step?.status || "").toLowerCase();
  const action = String(step?.action || "").toLowerCase();
  if (status === "failed") return "failed";
  if (status === "blocked" || status === "needs_confirmation") return "blocked";
  if (status && status !== "success") return "done";
  if (
    action.startsWith("web_") ||
    action.startsWith("browser_") ||
    action.startsWith("personal_os_") ||
    action.endsWith("_list") ||
    action.endsWith("_read") ||
    action.endsWith("_search") ||
    action.includes("_status") ||
    action.includes("_info") ||
    action.includes("_graph") ||
    action.includes("_view") ||
    action.includes("_history") ||
    action.includes("_diff") ||
    action.includes("_log")
  ) return "found";
  if (
    action.includes("_add") ||
    action.includes("_create") ||
    action.includes("_update") ||
    action.includes("_delete") ||
    action.includes("_write") ||
    action.includes("_set") ||
    action.includes("_toggle") ||
    action.includes("_move") ||
    action.includes("_resize") ||
    action.includes("_rename") ||
    action.includes("_clean") ||
    action.includes("_organize") ||
    action.includes("_merge") ||
    action.includes("_split") ||
    action.includes("_convert") ||
    action.includes("_send") ||
    action.includes("_commit") ||
    action.includes("_push") ||
    action.includes("_pull")
  ) return "changed";
  return "done";
}

function agentStepOutcomeLabel(kind) {
  const normalized = String(kind || "done").replace(/[^a-z_]/gi, "");
  const suffix = normalized ? normalized[0].toUpperCase() + normalized.slice(1) : "Done";
  const key = `chat.agentOutcome${suffix}`;
  const label = t(key);
  return label === key ? t("chat.agentOutcomeDone") : label;
}

function createAgentOutcomeCounts() {
  return { found: 0, changed: 0, done: 0, blocked: 0, failed: 0 };
}

function agentRunOutcomeCounts(steps) {
  const counts = createAgentOutcomeCounts();
  (Array.isArray(steps) ? steps : []).forEach((step) => {
    const kind = agentStepOutcomeKind(step);
    counts[kind] = (counts[kind] || 0) + 1;
  });
  return counts;
}

function recordAgentStepOutcome(step, counts, stepOutcomes) {
  if (!counts || !stepOutcomes) return;
  const key = step?.index !== undefined && step?.index !== null
    ? String(step.index)
    : agentStepTechnicalLabel(step);
  const previous = stepOutcomes.get(key);
  if (previous && counts[previous] > 0) counts[previous] -= 1;
  const next = agentStepOutcomeKind(step);
  counts[next] = (counts[next] || 0) + 1;
  stepOutcomes.set(key, next);
}

function renderAgentOutcomeSummary(summaryEl, counts) {
  if (!summaryEl) return;
  summaryEl.textContent = "";
  const entries = ["found", "changed", "done", "blocked", "failed"]
    .map((kind) => ({ kind, count: Number(counts?.[kind] || 0) }))
    .filter((entry) => entry.count > 0);
  summaryEl.hidden = entries.length === 0;
  if (!entries.length) return;
  entries.forEach(({ kind, count }) => {
    const chip = document.createElement("span");
    chip.className = `agent-outcome-chip ${kind}`;
    chip.setAttribute("role", "listitem");
    chip.textContent = `${agentStepOutcomeLabel(kind)} ${count}`;
    summaryEl.appendChild(chip);
  });
  const ariaParts = entries.map(({ kind, count }) => `${agentStepOutcomeLabel(kind)} ${count}`);
  summaryEl.setAttribute("aria-label", `${t("chat.agentOutcomeSummaryLabel")}: ${ariaParts.join(", ")}`);
}

function agentOutcomeTotal(counts) {
  return ["found", "changed", "done", "blocked", "failed"]
    .reduce((total, kind) => total + Number(counts?.[kind] || 0), 0);
}

function agentCompletionOutcomeSummary(counts) {
  return ["found", "changed", "done", "blocked", "failed"]
    .map((kind) => ({ kind, count: Number(counts?.[kind] || 0) }))
    .filter((entry) => entry.count > 0)
    .map(({ kind, count }) => `${agentStepOutcomeLabel(kind)} ${count}`)
    .join(", ");
}

function agentCompletionContinuePrompt(run, counts, summaryText) {
  const agentCommand = LEXA_COMPOSER_COMMANDS.find((command) => command.id === "agent");
  const prefix = composerCommandPrefix(agentCommand);
  const steps = Array.isArray(run?.steps) ? run.steps : [];
  const unresolved = steps
    .filter((step) => ["failed", "blocked", "needs_confirmation"].includes(String(step?.status || "").toLowerCase()) || ["failed", "blocked"].includes(agentStepOutcomeKind(step)))
    .slice(0, 8);
  const stepLines = unresolved.map((step) => `- ${agentStepDisplayLabel(step)} | ${agentStepOutcomeLabel(agentStepOutcomeKind(step))}`);
  const outcomeLine = agentCompletionOutcomeSummary(counts) || t("chat.agentCompletionContinueNoOutcomes");
  const rawSummary = String(summaryText || run?.summary || "").trim();
  const lead = `${prefix}${t("chat.agentCompletionContinuePromptIntro")}\n\n${t("chat.agentCompletionContinueNextRequest")} `;
  const source = [
    `${t("chat.agentCompletionContinueOutcomes")}: ${outcomeLine}`,
    `${t("chat.agentCompletionContinueUnresolved")}:\n${stepLines.length ? stepLines.join("\n") : t("chat.agentCompletionContinueNoUnresolved")}`,
    rawSummary ? `${t("chat.agentCompletionContinuePriorSummary")}:\n${rawSummary}` : "",
    t("chat.agentCompletionContinueBoundary"),
  ].filter(Boolean).join("\n\n");
  const clipMarker = `\n\n${t("chat.agentCompletionContinueClipMarker")}`;
  const maxInput = Math.max(1, Number(LexaConfig?.MAX_CHAT_INPUT_LENGTH) || 12000);
  const targetMax = Math.max(1, maxInput - 300);
  const sourceBudget = Math.max(0, targetMax - lead.length);
  const marker = source.length > sourceBudget && clipMarker.length < sourceBudget ? clipMarker : "";
  const sourceLimit = Math.max(0, sourceBudget - marker.length);
  const boundedSource = source.length > sourceLimit ? `${source.slice(0, sourceLimit)}${marker}` : source;
  const text = `${lead}\n\n${boundedSource}`.slice(0, targetMax);
  return { text, cursorStart: Math.min(lead.length, text.length) };
}

function startAgentCompletionContinue(btn) {
  if (btn?.disabled) return;
  const prompt = String(btn?._lexaAgentContinuePrompt || "").trim();
  if (!prompt) { showToast(t("chat.agentCompletionContinueEmpty"), "warning", 2000); return; }
  chatInput.value = prompt;
  syncChatInputSize();
  localStorage.setItem("lexa-chat-draft", prompt);
  chatInput.focus();
  const cursorStart = Math.max(0, Number(btn?._lexaAgentContinueCursor || 0));
  if (typeof chatInput.setSelectionRange === "function") {
    chatInput.setSelectionRange(cursorStart, cursorStart);
  }
  flashIconButton(btn, "\u2713", "\u21AA", 1500, t("chat.agentCompletionContinueStarted"));
  showToast(t("chat.agentCompletionContinueStarted"), "success", 1600);
}

function agentCompletionAttentionKeyFromText(text) {
  const source = String(text || "").trim();
  return source ? agentRunMetaMessageKey("assistant", source) : "";
}

function isAgentCompletionAttentionResolved(text) {
  const convId = LexaState.get("currentConversationId");
  const key = agentCompletionAttentionKeyFromText(text);
  return Boolean(convId && key && agentRunAttentionResolvedKeys(convId).has(key));
}

function markAgentCompletionResolveButtonDone(btn) {
  if (!btn) return;
  btn.classList.add("is-resolved");
  btn.dataset.resolved = "true";
  btn.textContent = t("chat.agentCompletionResolveUndoButton");
  btn.title = t("chat.agentCompletionResolveUndoTooltip");
  btn.setAttribute("aria-label", t("chat.agentCompletionResolveUndoTooltip"));
}

function markAgentCompletionResolveButtonOpen(btn) {
  if (!btn) return;
  btn.classList.remove("is-resolved");
  btn.dataset.resolved = "false";
  btn.textContent = t("chat.agentCompletionResolveButton");
  btn.title = t("chat.agentCompletionResolveTooltip");
  btn.setAttribute("aria-label", t("chat.agentCompletionResolveTooltip"));
}

function undoAgentCompletionResolve(btn) {
  const convId = LexaState.get("currentConversationId");
  const msg = btn?.closest?.(".message");
  const key = agentCompletionAttentionKeyFromText(getMessagePersistText(msg));
  if (!convId || !key) {
    showToast(t("chat.agentCompletionResolveEmpty"), "warning", 1800);
    return false;
  }
  const resolved = agentRunAttentionResolvedKeys(convId);
  resolved.delete(key);
  saveAgentRunAttentionResolvedKeys(convId, resolved);
  removeAgentAttentionResolution(convId, [key]);
  markAgentCompletionResolveButtonOpen(btn);
  renderConversationList();
  showToast(t("chat.agentAttentionRestored"), "success", 1800);
  return true;
}

function startAgentCompletionResolve(btn) {
  if (btn?.disabled) return false;
  if (btn?.dataset?.resolved === "true") return undoAgentCompletionResolve(btn);
  const convId = LexaState.get("currentConversationId");
  const msg = btn?.closest?.(".message");
  const text = getMessagePersistText(msg);
  const meta = getMessageAgentRunMeta(msg);
  const counts = meta?.counts || agentRunOutcomeCounts(meta?.steps);
  const key = agentCompletionAttentionKeyFromText(text);
  const hasAttention = Number(counts?.failed || 0) > 0 || Number(counts?.blocked || 0) > 0;
  if (!convId || !msg || !key || !hasAttention) {
    showToast(t("chat.agentCompletionResolveEmpty"), "warning", 1800);
    return false;
  }
  saveAgentRunMetaForConversation(convId);
  const resolved = agentRunAttentionResolvedKeys(convId);
  resolved.add(key);
  saveAgentRunAttentionResolvedKeys(convId, resolved);
  recordAgentAttentionResolution({
    convId,
    title: (LexaState.get("conversationsList") || []).find((conv) => String(conv.id) === String(convId))?.title || t("chat.newChatTitle"),
    failed: Number(counts?.failed || 0),
    blocked: Number(counts?.blocked || 0),
    keys: [key],
  });
  markAgentCompletionResolveButtonDone(btn);
  renderConversationList();
  showToast(t("chat.agentAttentionResolved"), "success", 1800);
  return true;
}

function renderAgentCompletionPanel(panel, counts, options = {}) {
  if (!panel) return;
  const failed = Number(counts?.failed || 0);
  const blocked = Number(counts?.blocked || 0);
  const total = agentOutcomeTotal(counts);
  const state = failed > 0
    ? { kind: "failed", label: t("chat.agentCompletionFailed"), next: t("chat.agentCompletionNextFailed") }
    : blocked > 0
      ? { kind: "blocked", label: t("chat.agentCompletionBlocked"), next: t("chat.agentCompletionNextBlocked") }
      : { kind: "complete", label: t("chat.agentCompletionComplete"), next: t("chat.agentCompletionNextComplete") };
  const needsYou = failed > 0 && blocked > 0
    ? t("chat.agentCompletionNeedsBoth", { failed, blocked })
    : failed > 0
      ? t("chat.agentCompletionNeedsFailed", { count: failed })
      : blocked > 0
        ? t("chat.agentCompletionNeedsBlocked", { count: blocked })
        : t("chat.agentCompletionNeedsClear");

  panel.hidden = false;
  panel.className = `agent-completion-panel ${state.kind}`;
  panel.textContent = "";
  const stateEl = document.createElement("div");
  stateEl.className = "agent-completion-state";
  stateEl.textContent = state.label;
  const grid = document.createElement("div");
  grid.className = "agent-completion-grid";
  grid.setAttribute("role", "list");
  [
    [t("chat.agentCompletionReached"), t("chat.agentCompletionReachedValue", { count: total })],
    [t("chat.agentCompletionNeedsYou"), needsYou],
    [t("chat.agentCompletionNext"), state.next],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "agent-completion-item";
    item.setAttribute("role", "listitem");
    const labelEl = document.createElement("span");
    labelEl.className = "agent-completion-label";
    labelEl.textContent = label;
    const valueEl = document.createElement("span");
    valueEl.className = "agent-completion-value";
    valueEl.textContent = value;
    item.appendChild(labelEl);
    item.appendChild(valueEl);
    grid.appendChild(item);
  });
  panel.appendChild(stateEl);
  panel.appendChild(grid);
  if (failed > 0 || blocked > 0) {
    const actions = document.createElement("div");
    actions.className = "agent-completion-actions";
    if (options?.continuePrompt?.text) {
      const continueButton = document.createElement("button");
      continueButton.type = "button";
      continueButton.className = "agent-completion-continue-btn";
      continueButton.dataset.icon = "\u21AA";
      continueButton.textContent = t("chat.agentCompletionContinueButton");
      continueButton.title = t("chat.agentCompletionContinueTooltip");
      continueButton.setAttribute("aria-label", t("chat.agentCompletionContinueTooltip"));
      continueButton._lexaAgentContinuePrompt = options.continuePrompt.text;
      continueButton._lexaAgentContinueCursor = options.continuePrompt.cursorStart;
      continueButton.addEventListener("click", () => startAgentCompletionContinue(continueButton));
      actions.appendChild(continueButton);
    }
    const resolveButton = document.createElement("button");
    resolveButton.type = "button";
    resolveButton.className = "agent-completion-resolve-btn";
    resolveButton.dataset.icon = "\u2713";
    resolveButton.textContent = t("chat.agentCompletionResolveButton");
    resolveButton.title = t("chat.agentCompletionResolveTooltip");
    resolveButton.setAttribute("aria-label", t("chat.agentCompletionResolveTooltip"));
    resolveButton.addEventListener("click", () => startAgentCompletionResolve(resolveButton));
    if (options?.attentionResolved) markAgentCompletionResolveButtonDone(resolveButton);
    actions.appendChild(resolveButton);
    panel.appendChild(actions);
  }
  panel.setAttribute("aria-label", `${t("chat.agentCompletionLabel")}: ${state.label}. ${needsYou}. ${state.next}`);
}

function renderAgentStepOutcome(stepEl, step) {
  if (!stepEl) return;
  stepEl.querySelector(".agent-step-outcome")?.remove();
  const kind = agentStepOutcomeKind(step);
  const badge = document.createElement("span");
  badge.className = `agent-step-outcome ${kind}`;
  badge.textContent = agentStepOutcomeLabel(kind);
  const duration = stepEl.querySelector(".agent-step-duration");
  if (duration) stepEl.insertBefore(badge, duration);
  else stepEl.appendChild(badge);
  const visibleLabel = stepEl.querySelector(".agent-step-label")?.textContent || t("chat.agentStepUnknown");
  const technicalLabel = stepEl.dataset?.technicalLabel || agentStepTechnicalLabel(step);
  stepEl.dataset.technicalLabel = technicalLabel;
  stepEl.setAttribute("aria-label", `${visibleLabel}. ${badge.textContent}`);
}

function renderPersistedAgentRunMeta(body, meta, summaryText) {
  const normalized = normalizeAgentRunMeta(meta);
  if (!body || !normalized) return;
  const counts = normalized.counts || agentRunOutcomeCounts(normalized.steps);
  const run = { steps: normalized.steps, summary: normalized.summary || summaryText, total_duration_ms: normalized.total_duration_ms };

  const completionEl = document.createElement("div");
  completionEl.className = "agent-completion-panel";
  completionEl.setAttribute("role", "group");
  completionEl.setAttribute("aria-label", t("chat.agentCompletionLabel"));
  renderAgentCompletionPanel(completionEl, counts, {
    continuePrompt: agentCompletionContinuePrompt(run, counts, normalized.summary || summaryText),
    attentionResolved: isAgentCompletionAttentionResolved(summaryText || normalized.summary),
  });
  body.appendChild(completionEl);

  const outcomeSummaryEl = document.createElement("div");
  outcomeSummaryEl.className = "agent-outcome-summary";
  outcomeSummaryEl.setAttribute("role", "list");
  outcomeSummaryEl.setAttribute("aria-label", t("chat.agentOutcomeSummaryLabel"));
  renderAgentOutcomeSummary(outcomeSummaryEl, counts);
  if (!outcomeSummaryEl.hidden) body.appendChild(outcomeSummaryEl);
}

function addMessage(text, type = "system", action = null, requiresConfirmation = false, silent = false, options = {}) {
  const sleekGreeting = document.getElementById("sleek-greeting");
  if (sleekGreeting && !sleekGreeting.classList.contains("hidden")) sleekGreeting.classList.add("hidden");
  // Orb stays visible — don't hide voice-orb-container
  const floatingCards = document.getElementById("floating-cards-container");
  if (floatingCards && !floatingCards.classList.contains("hidden")) floatingCards.classList.add("hidden");
  // Hide conversation starters when sending a message
  const starters = document.getElementById("conversation-starters");
  if (starters && !starters.classList.contains("hidden")) starters.classList.add("hidden");
  // Chat messages stay hidden in ambient mode — only revealed by arrow key
  // (chat-messages visibility is managed by toggleChatView)

  const msg = document.createElement("div");
  msg.className = `message ${type}-message`;
  setMessagePersistText(msg, text);
  const isUser = type === "user";
  const agentRunMeta = !isUser ? setMessageAgentRunMeta(msg, options?.agentRunMeta) : null;
  const avatarClass = isUser ? "user" : "system";
  const nameText = isUser ? t("chat.userNameYou") : t("chat.systemNameLexa");
  const timeStr = new Date().toLocaleTimeString(t._locale || "de-DE", { hour: "2-digit", minute: "2-digit" });

  const avatar = document.createElement("div");
  avatar.className = `msg-avatar ${avatarClass}`;
  renderMessageAvatar(avatar, avatarClass);

  const body = document.createElement("div");
  body.className = "msg-body";
  const header = document.createElement("div");
  header.className = "msg-header";
  const nameSpan = document.createElement("span");
  nameSpan.className = "msg-name";
  nameSpan.textContent = nameText;
  const agentBadge = document.createElement("span");
  agentBadge.className = "agent-badge";
  agentBadge.textContent = t("chat.agentBadge");
  const timeSpan = document.createElement("span");
  timeSpan.className = "msg-time";
  timeSpan.textContent = timeStr;
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "msg-copy-btn";
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  header.appendChild(nameSpan);
  if (agentRunMeta) header.appendChild(agentBadge);
  header.appendChild(timeSpan);
  header.appendChild(copyBtn);

  if (!isUser) {
    // Thumbs-up to save as memory
    const thumbsBtn = document.createElement("button");
    thumbsBtn.type = "button";
    thumbsBtn.className = "msg-thumbs-btn";
    setIconButton(thumbsBtn, "\u2605", t("chat.saveAsMemoryTooltip"));
    thumbsBtn.addEventListener("click", () => saveMessageAsMemory(thumbsBtn, msg));
    header.appendChild(createContinueFromMessageButton());
    header.appendChild(createVerifyAnswerButton());
    header.appendChild(createMessageExportButton());
    const moreActions = [thumbsBtn, createWorkspaceHandoffButton()];

    // Regenerate button for Lexa messages
    if (!silent) {
      const regenBtn = document.createElement("button");
      regenBtn.type = "button";
      regenBtn.className = "msg-action-btn msg-regen-btn";
      setIconButton(regenBtn, "\u21BB", t("chat.regenerateTooltip"));
      regenBtn.addEventListener("click", () => startRegenerateMessage(regenBtn, msg));
      moreActions.push(regenBtn);
    }
    header.appendChild(createMessageActionOverflowMenu(moreActions));
  }

  if (isUser && !silent) {
    // Edit button for user messages
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "msg-action-btn msg-edit-btn";
    setIconButton(editBtn, "\u270E", t("chat.editTooltip"));
    editBtn.addEventListener("click", () => {
      const currentText = getMessagePersistText(msg);
      chatInput.value = currentText;
      syncChatInputSize();
      chatInput.focus();
      // Remove this message and all messages after it
      const allMsgs = Array.from(chatMessages.querySelectorAll(".message"));
      const idx = allMsgs.indexOf(msg);
      if (idx >= 0) {
        for (let i = allMsgs.length - 1; i >= idx; i--) {
          allMsgs[i].remove();
        }
        persistChatAfterDomMutation();
      }
      showToast(t("chat.editLoaded"), "info", 2000);
    });
    header.appendChild(editBtn);

    // Delete button for user messages
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "msg-action-btn msg-del-btn";
    setIconButton(delBtn, "\u00D7", t("chat.deleteTooltip"));
    delBtn.addEventListener("click", () => {
      if (delBtn.disabled) return;
      delBtn.disabled = true;
      delBtn.setAttribute("aria-busy", "true");
      msg.classList.add("msg-deleting");
      setTimeout(() => {
        msg.remove();
        persistChatAfterDomMutation();
      }, 200);
    });
    header.appendChild(delBtn);
  }

  const msgTextEl = document.createElement("div");
  msgTextEl.className = "msg-text";
  renderFormattedMessage(msgTextEl, text);
  body.appendChild(header);
  if (agentRunMeta) renderPersistedAgentRunMeta(body, agentRunMeta, text);
  body.appendChild(msgTextEl);

  if (action && options?.showLocalActionCard) {
    appendToolConfirmationUi(body, action);
  }

  msg.appendChild(avatar);
  msg.appendChild(body);
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  trimChatMessages();
  if (!silent) saveChatHistory();
}

function renderFormattedMessage(target, text) {
  if (!target) return;
  target.replaceChildren();
  appendFormattedMessage(target, String(text || ""));
}

function renderStreamingText(target, text, showCursor = true) {
  if (!target) return;
  target.textContent = String(text || "");
  if (showCursor) {
    const cursor = document.createElement("span");
    cursor.className = "streaming-cursor";
    target.appendChild(cursor);
  }
}

function denyAction(btn) {
  const parent = btn.parentElement;
  parent.querySelector(".confirm-btn")?.remove();
  btn.textContent = t("chat.denied");
  btn.disabled = true;
  btn.classList.add("action-denied");
  // Clear pending confirmation on the backend
  try { fetch(`${window.lexa.API_BASE}/chat/confirm-clear`, { method: "POST", credentials: "include" }); } catch (_) {}
  showToast(t("toast.actionCancelled"), "warning");
}

function handleChatToolActionBlocked(action, options = {}) {
  const actionName = chatToolActionName(action);
  console.info("[Chat] Blocked automatic local tool execution from chat", {
    action: actionName,
    param_keys: chatToolActionParamKeys(action),
    source: options.source || "chat",
  });
  if (options.toast === true) {
    showToast(t("chat.localActionBlockedToast", { action: actionName }), "warning", 3200);
  }
  return false;
}

// ── FOLLOW-UP SUGGESTIONS ─────────────────────────
function generateSuggestions(responseText, userQuestion) {
  const suggestions = [];
  const lower = responseText.toLowerCase();
  const userLower = (userQuestion || "").toLowerCase();

  // ── Topic-specific follow-ups (prioritized) ──
  // Music context
  if (lower.includes("spotify") || lower.includes("musik") || lower.includes("song") || lower.includes("playlist")) {
    suggestions.push(t("chat.suggNextSong"), t("chat.suggQuieter"), t("chat.suggPause"));
  }
  // Todo/task context
  if (lower.includes("todo") || lower.includes("aufgabe") || lower.includes("erledigt")) {
    if (lower.includes("erledigt") || lower.includes("abgehakt")) {
      suggestions.push(t("chat.suggWhatsLeft"), t("chat.suggNewTodo"));
    } else {
      suggestions.push(t("chat.suggShowTodos"), t("chat.suggNewTodo"));
    }
  }
  // Notes context
  if (lower.includes("notiz") || lower.includes("note") || lower.includes("gespeichert")) {
    suggestions.push(t("chat.suggShowNotes"));
  }
  // System/performance context
  if (lower.includes("prozess") || lower.includes("ram") || lower.includes("cpu") || lower.includes("speicher")) {
    if (lower.includes("85%") || lower.includes("90%") || lower.includes("95%") || lower.includes("hoch")) {
      suggestions.push(t("chat.suggShowMemHogs"), t("chat.suggKillProcess"));
    } else {
      suggestions.push(t("chat.suggProcessList"), t("chat.suggDiskAnalysis"));
    }
  }
  // Screenshot context
  if (lower.includes("screenshot")) {
    suggestions.push(t("chat.suggScreenshotAgain"), t("chat.suggScreenshotPdf"));
  }
  // Timer/Pomodoro context
  if (lower.includes("timer") || lower.includes("pomodoro")) {
    if (lower.includes("fertig") || lower.includes("abgelaufen")) {
      suggestions.push(t("chat.suggNewTimer5"), t("chat.suggStartPomodoro"));
    } else {
      suggestions.push(t("chat.suggTimerStatus"), t("chat.suggStopPomodoro"));
    }
  }
  // File context
  if (lower.includes("datei") || lower.includes("ordner") || lower.includes("file") || lower.includes("download")) {
    suggestions.push(t("chat.suggCleanDownloads"), t("chat.suggFindDuplicates"));
  }
  // Git/Dev context
  if (lower.includes("git") || lower.includes("commit") || lower.includes("branch")) {
    suggestions.push(t("chat.suggGitStatus"), t("chat.suggGitLog"));
  }
  // Email context
  if (lower.includes("email") || lower.includes("mail") || lower.includes("nachricht")) {
    suggestions.push(t("chat.suggCheckEmails"));
  }
  // Error/problem context — offer debugging help
  if (lower.includes("fehler") || lower.includes("error") || lower.includes("problem") || lower.includes("funktioniert nicht")) {
    suggestions.push(t("chat.suggRetry"), t("chat.suggSysteminfo"));
  }
  // Explanation context — offer deeper dive
  if (lower.includes("bedeutet") || lower.includes("erklärt") || lower.includes("verstehe")) {
    suggestions.push(t("chat.suggMoreDetails"), t("chat.suggShowExample"));
  }

  // ── Time-aware suggestions ──
  if (suggestions.length === 0) {
    const hour = new Date().getHours();
    if (hour >= 6 && hour < 10) {
      suggestions.push(t("chat.suggWhatToday"), t("chat.suggCheckEmails"), t("chat.suggSysteminfo"));
    } else if (hour >= 10 && hour < 12) {
      suggestions.push(t("chat.suggShowTodos"), t("chat.suggStartPomodoro"));
    } else if (hour >= 12 && hour < 14) {
      suggestions.push(t("chat.suggTimer30"), t("chat.suggPlayMusic"));
    } else if (hour >= 14 && hour < 18) {
      suggestions.push(t("chat.suggShowTodos"), t("chat.suggWhatDoneToday"));
    } else if (hour >= 18 && hour < 22) {
      suggestions.push(t("chat.suggCleanDownloads"), t("chat.suggPlayMusic"));
    } else {
      suggestions.push(t("chat.suggGoodnightRoutine"), t("chat.suggTimer10"));
    }
  }

  // ── Contextual follow-up based on user's question ──
  if (suggestions.length < 3) {
    if (userLower.includes("wie") || userLower.includes("warum") || userLower.includes("was ist")) {
      suggestions.push(t("chat.suggTellMore"));
    }
    if (userLower.includes("zeig") || userLower.includes("liste") || userLower.includes("such")) {
      suggestions.push(t("chat.suggMoreResults"));
    }
  }

  // Deduplicate and limit
  return [...new Set(suggestions)].slice(0, 3);
}

// ── DRAFT RECOVERY ────────────────────────────────
function recoverDraft() {
  const draft = localStorage.getItem("lexa-chat-draft");
  if (draft && chatInput) {
    chatInput.value = draft;
    syncChatInputSize();
  }
}

function syncChatInputSize() {
  if (!chatInput) return;
  if (chatInput.tagName === "TEXTAREA") {
    const maxHeight = 160;
    const metrics = window.getComputedStyle ? window.getComputedStyle(chatInput) : null;
    const lineHeight = Number.parseFloat(metrics?.lineHeight) || 22;
    const paddingY = (Number.parseFloat(metrics?.paddingTop) || 0) + (Number.parseFloat(metrics?.paddingBottom) || 0);
    const maxRows = Math.max(1, Math.floor((maxHeight - paddingY) / lineHeight));
    const neededRows = Math.max(1, Math.ceil(((chatInput.scrollHeight || lineHeight) - paddingY) / lineHeight));
    chatInput.rows = Math.min(maxRows, neededRows);
    chatInput.classList.toggle("is-scrollable", neededRows > maxRows);
  }
  chatInput.classList.toggle("has-content", Boolean(chatInput.value));
  const counter = document.getElementById("char-counter");
  const metrics = chatInputMetrics(chatInput.value);
  chatInput.setAttribute("aria-invalid", metrics.over ? "true" : "false");
  if (!counter) return;
  counter.textContent = metrics.label;
  counter.classList.toggle("hidden", !metrics.visible);
  counter.classList.toggle("warn", metrics.warn);
  counter.classList.toggle("danger", metrics.danger || metrics.over);
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "message system-message typing-message";
  div.id = "typing-indicator";
  const avatar = document.createElement("div");
  avatar.className = "msg-avatar system";
  renderMessageAvatar(avatar, "system");
  const body = document.createElement("div");
  body.className = "msg-body";
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator";
  const label = document.createElement("span");
  label.className = "typing-label";
  label.textContent = t("chat.thinkingLabel");
  indicator.appendChild(label);
  const dots = document.createElement("span");
  dots.className = "typing-dots";
  for (let i = 0; i < 3; i++) { const dot = document.createElement("span"); dot.className = "typing-dot"; dots.appendChild(dot); }
  indicator.appendChild(dots);
  const stopBtn = document.createElement("button");
  stopBtn.type = "button";
  stopBtn.className = "stop-thinking-btn";
  stopBtn.textContent = t("chat.stopResponseButton");
  stopBtn.title = t("chat.stopResponseTooltip");
  stopBtn.setAttribute("aria-label", t("chat.stopResponseTooltip"));
  stopBtn.addEventListener("click", () => {
    if (window._lexaStreamAbort) {
      window._lexaStreamAbortReason = "user";
      window._lexaStreamAbort.abort();
    }
    hideTyping();
    LexaState.set("isLoading", false);
    const sendBtn = document.getElementById("send-btn");
    if (sendBtn) sendBtn.disabled = false;
  });
  indicator.appendChild(stopBtn);
  body.appendChild(indicator);
  div.appendChild(avatar);
  div.appendChild(body);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById("typing-indicator");
  if (el) {
    el.classList.add("typing-fade-out");
    setTimeout(() => el.remove(), 200);
  }
}

// ── SEND MESSAGE (streaming) ─────────────────────
async function sendMessage() {
  if (LexaState.get("isLoading")) return;
  const rawText = chatInput.value.trim();
  const text = expandComposerSlashAlias(rawText) || rawText;
  if (!text) return;
  if (text.length > LexaConfig.MAX_CHAT_INPUT_LENGTH) { showToast(t("chat.messageTooLong", {max: LexaConfig.MAX_CHAT_INPUT_LENGTH}), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }

  // Phase 46: Auto-detect if this task needs the multi-step agent
  // Manual override: /agent prefix always triggers agent mode
  // Auto-detect: complex tasks with multiple actions, "und dann", etc.
  const agentManual = text.startsWith("/agent ");
  const agentText = agentManual ? text.slice(7).trim() : text;
  if (agentManual || _needsAgentMode(text)) {
    if (agentText) {
      sendAgentMessage(agentText);
      return;
    }
  }

  LexaState.set("isLoading", true);
  pushChatHistory(text);
  chatHistoryIdx = -1;

  if (!LexaState.get("currentConversationId")) {
    try {
      const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
      LexaState.set("currentConversationId", result.id);
      localStorage.setItem("lexa-active-conversation", result.id);
      const data = await window.lexa.conversations();
      LexaState.set("conversationsList", data.conversations || []);
      renderConversationList();
    } catch (e) { console.warn("[Chat] Failed to create conversation:", e.message || e); }
  }

  const isFirstMessage = chatMessages.querySelectorAll(".user-message").length === 0;
  // Typed messages always open chat view so user sees the response
  if (!window._chatViewOpen) toggleChatView();
  addMessage(text, "user");

  localStorage.setItem("lexa-chat-draft", "");
  chatInput.value = "";
  syncChatInputSize();
  sendBtn.disabled = true;
  if (isFirstMessage) autoTitleConversation(text);

  const msgEl = document.createElement("div");
  msgEl.className = "message system-message";
  const timeStr = new Date().toLocaleTimeString(t._locale || "de-DE", { hour: "2-digit", minute: "2-digit" });

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar system";
  renderMessageAvatar(avatar, "system");

  const body = document.createElement("div");
  body.className = "msg-body";
  const header = document.createElement("div");
  header.className = "msg-header";
  const nameSpan = document.createElement("span");
  nameSpan.className = "msg-name";
  nameSpan.textContent = t("chat.systemNameLexa");
  const timeSpan = document.createElement("span");
  timeSpan.className = "msg-time";
  timeSpan.textContent = timeStr;
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "msg-copy-btn";
  copyBtn.disabled = true;
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  const memoryBtn = document.createElement("button");
  memoryBtn.type = "button";
  memoryBtn.className = "msg-thumbs-btn";
  memoryBtn.disabled = true;
  setIconButton(memoryBtn, "\u2605", t("chat.saveAsMemoryTooltip"));
  memoryBtn.addEventListener("click", () => saveMessageAsMemory(memoryBtn, msgEl));
  const workspaceBtn = createWorkspaceHandoffButton();
  workspaceBtn.disabled = true;
  const continueBtn = createContinueFromMessageButton(true);
  const verifyBtn = createVerifyAnswerButton(true);
  const exportBtn = createMessageExportButton(true);
  const regenBtn = document.createElement("button");
  regenBtn.type = "button";
  regenBtn.className = "msg-action-btn msg-regen-btn";
  regenBtn.disabled = true;
  setIconButton(regenBtn, "\u21BB", t("chat.regenerateTooltip"));
  regenBtn.addEventListener("click", () => startRegenerateMessage(regenBtn, msgEl, text));
  header.appendChild(nameSpan);
  header.appendChild(timeSpan);
  header.appendChild(copyBtn);
  header.appendChild(continueBtn);
  header.appendChild(verifyBtn);
  header.appendChild(exportBtn);
  header.appendChild(createMessageActionOverflowMenu([memoryBtn, workspaceBtn, regenBtn]));

  const textEl = document.createElement("div");
  textEl.className = "msg-text streaming-text";
  const cursor = document.createElement("span");
  cursor.className = "streaming-cursor";
  textEl.appendChild(cursor);

  body.appendChild(header);
  body.appendChild(textEl);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  let fullText = "";
  let actionData = null;
  let requiresConfirmation = false;
  let streamRenderQueued = false;
  let streamRenderActive = true;
  const scheduleStreamRender = () => {
    if (streamRenderQueued) return;
    streamRenderQueued = true;
    const schedule = window.requestAnimationFrame || ((fn) => setTimeout(fn, 16));
    schedule(() => {
      streamRenderQueued = false;
      if (!streamRenderActive) return;
      renderStreamingText(textEl, fullText);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    });
  };

  try {
    window._lexaStreamAbort = new AbortController();
    window._lexaStreamAbortReason = "";
    const _streamTimeout = setTimeout(() => {
      window._lexaStreamAbortReason = "timeout";
      window._lexaStreamAbort.abort();
    }, 45000);
    let response;
    try {
      response = await fetch(`${window.lexa.API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text }),
        signal: window._lexaStreamAbort.signal,
      });
    } catch (abortErr) {
      clearTimeout(_streamTimeout);
      if (abortErr.name === "AbortError") {
        const stoppedByUser = window._lexaStreamAbortReason === "user";
        streamRenderActive = false;
        textEl.classList.remove("streaming-text");
        textEl.textContent = stoppedByUser ? t("chat.responseStopped") : t("chat.connectionTimeout");
        LexaState.set("isLoading", false); sendBtn.disabled = false;
        window._lexaStreamAbort = null;
        window._lexaStreamAbortReason = "";
        saveChatHistory();
        saveCurrentConversation();
        return;
      }
      throw abortErr;
    }

    if (!response.ok) {
      clearTimeout(_streamTimeout);
      const errData = await response.json().catch(() => ({}));
      streamRenderActive = false;
      textEl.classList.remove("streaming-text");
      let errMsg = errData.detail || t("common.connectionError");
      if (response.status === 429) { errMsg = t("chat.tooManyRequestsShort"); showToast(t("toast.rateLimitReached"), "warning"); }
      else if (response.status === 503) errMsg = t("chat.backendOverloaded");
      else if (response.status >= 500) errMsg = t("common.error") + ` (${response.status})`;
      renderFormattedMessage(textEl, errMsg);
      setMessagePersistText(msgEl, errMsg);
      copyBtn.disabled = false;
      memoryBtn.disabled = false;
      workspaceBtn.disabled = false;
      continueBtn.disabled = false;
      verifyBtn.disabled = false;
      exportBtn.disabled = false;
      regenBtn.disabled = false;
      LexaState.set("isLoading", false); sendBtn.disabled = false;
      window._lexaStreamAbort = null;
      window._lexaStreamAbortReason = "";
      saveChatHistory();
      saveCurrentConversation();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamError = null;
    let streamStoppedByUser = false;
    let streamTimedOut = false;
    const streamStart = Date.now();
    const STREAM_TIMEOUT_MS = 45000;
    try {
      while (true) {
        if (Date.now() - streamStart > STREAM_TIMEOUT_MS) {
          console.warn("[LEXA] Stream timeout after 45s");
          streamTimedOut = true;
          window._lexaStreamAbortReason = "timeout";
          await reader.cancel();
          break;
        }
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsedBuffer = chatStreamBufferedLines(buffer);
        const lines = parsedBuffer.lines;
        buffer = parsedBuffer.buffer;
        for (const line of lines) {
          const data = parseChatStreamDataLine(line);
          if (!data) continue;
          if (data.c) { fullText += data.c; scheduleStreamRender(); }
          if (data.done) { actionData = data.action; requiresConfirmation = data.rc; if (data.reply && !fullText) { fullText = data.reply; } streamError = null; }
        }
      }
    } catch (streamErr) {
      streamStoppedByUser = window._lexaStreamAbortReason === "user";
      if (!streamStoppedByUser) {
        streamError = streamErr;
        console.warn("[LEXA] Stream unterbrochen:", streamErr);
      }
      try { await reader.cancel(); } catch (e) { console.warn("[Chat] Reader cancel failed:", e.message || e); }
    }

    clearTimeout(_streamTimeout);
    streamRenderActive = false;
    textEl.classList.remove("streaming-text");
    if (actionData && typeof chatActionDisplayReply === "function") {
      fullText = chatActionDisplayReply({ reply: fullText, action: actionData });
    }
    if (fullText) {
      renderFormattedMessage(textEl, fullText);
      if (streamStoppedByUser || streamTimedOut || streamError) {
        const warn = document.createElement("span");
        warn.className = "stream-warning";
        warn.textContent = streamStoppedByUser ? t("chat.responseStopped") : "\u26A0 " + t("chat.connectionInterrupted");
        textEl.appendChild(warn);
      }
    } else if (streamStoppedByUser) {
      textEl.textContent = t("chat.responseStopped");
    } else if (streamTimedOut) {
      textEl.textContent = t("chat.connectionTimeout");
    } else if (streamError) {
      textEl.textContent = t("chat.connectionLostRetry");
    } else {
      fullText = t("chat.emptyResponseFallback");
      renderFormattedMessage(textEl, fullText);
    }

    if (actionData) {
      handleChatToolActionBlocked(actionData);
    }
    // Show follow-up suggestion chips if response has substance
    if (fullText && fullText.length > 50 && !actionData) {
      const suggestDiv = document.createElement("div");
      suggestDiv.className = "msg-suggestions";
      const suggestions = generateSuggestions(fullText, text);
      suggestions.forEach(s => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "suggestion-chip";
        chip.textContent = s;
        chip.addEventListener("click", () => {
          chatInput.value = s;
          suggestDiv.remove();
          sendMessage();
        });
        suggestDiv.appendChild(chip);
      });
      if (suggestions.length > 0) body.appendChild(suggestDiv);
    }
    setMessagePersistText(msgEl, fullText || textEl.textContent);
    if (getMessagePersistText(msgEl)) {
      copyBtn.disabled = false;
      memoryBtn.disabled = false;
      workspaceBtn.disabled = false;
      continueBtn.disabled = false;
      verifyBtn.disabled = false;
      exportBtn.disabled = false;
      regenBtn.disabled = false;
    }
    playTTS(actionData?.message || fullText);
  } catch (err) {
    streamRenderActive = false;
    textEl.classList.remove("streaming-text");
    textEl.textContent = t("chat.backendUnreachable");
    setMessagePersistText(msgEl, textEl.textContent);
    copyBtn.disabled = false;
    memoryBtn.disabled = false;
    workspaceBtn.disabled = false;
    continueBtn.disabled = false;
    verifyBtn.disabled = false;
    exportBtn.disabled = false;
    regenBtn.disabled = false;
    showToast(t("toast.chatError"), "error");
  }

  saveChatHistory();
  saveCurrentConversation();
  LexaState.set("isLoading", false);
  sendBtn.disabled = false;
  window._lexaStreamAbort = null;
  window._lexaStreamAbortReason = "";
}

// ── AGENT MODE (Phase 46) ────────────────────────
// Auto-detects when a task needs multiple steps (agent mode)

function _needsAgentMode(text) {
  if (!text || text.length < 15) return false;
  const lower = text.toLowerCase()
    .replace(/[äÄ]/g, "ae").replace(/[öÖ]/g, "oe")
    .replace(/[üÜ]/g, "ue").replace(/[ß]/g, "ss");
  return _AGENT_PATTERNS.some(p => p.test(lower));
}

// Triggered by auto-detection or /agent prefix
function agentUserFacingError(message) {
  const text = String(message || "").trim();
  if (!text || /^(unknown|undefined|null)$/i.test(text)) return t("chat.agentErrorGeneric");
  if (
    /^\d{3}\b/.test(text) ||
    /\b(unauthorized|forbidden|not found|internal server error|bad gateway|gateway timeout)\b/i.test(text) ||
    /\b(failed to fetch|networkerror|econn|socket|timeout|ipc|handler failed)\b/i.test(text)
  ) return t("chat.agentErrorGeneric");
  return t("chat.agentError", { msg: clipAgentStepText(text, 120) });
}

async function sendAgentMessage(text, options) {
  const agentText = String(text || "").trim();
  const displayText = String(options?.displayText || agentText).trim();
  if (!agentText) return;

  pushChatHistory(displayText);
  chatHistoryIdx = -1;

  // Ensure conversation exists
  if (!LexaState.get("currentConversationId")) {
    try {
      const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
      LexaState.set("currentConversationId", result.id);
      localStorage.setItem("lexa-active-conversation", result.id);
      const data = await window.lexa.conversations();
      LexaState.set("conversationsList", data.conversations || []);
      renderConversationList();
    } catch (e) { console.warn("[Agent] Failed to create conversation:", e.message || e); }
  }

  const isFirstMessage = chatMessages.querySelectorAll(".user-message").length === 0;
  if (!window._chatViewOpen) toggleChatView();
  addMessage(displayText, "user");

  localStorage.setItem("lexa-chat-draft", "");
  chatInput.value = "";
  syncChatInputSize();
  LexaState.set("isLoading", true);
  sendBtn.disabled = true;
  if (isFirstMessage) autoTitleConversation(displayText);

  // Build agent message container
  const msgEl = document.createElement("div");
  msgEl.className = "message system-message agent-message";
  msgEl.setAttribute("aria-busy", "true");

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar system";
  renderMessageAvatar(avatar, "system");

  const body = document.createElement("div");
  body.className = "msg-body";
  let agentReader = null;
  let agentStoppedByUser = false;

  const header = document.createElement("div");
  header.className = "msg-header";
  const nameSpan = document.createElement("span");
  nameSpan.className = "msg-name";
  nameSpan.textContent = t("chat.systemNameLexa");
  const badge = document.createElement("span");
  badge.className = "agent-badge";
  badge.textContent = t("chat.agentBadge");
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "msg-copy-btn";
  copyBtn.disabled = true;
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  const memoryBtn = document.createElement("button");
  memoryBtn.type = "button";
  memoryBtn.className = "msg-thumbs-btn";
  memoryBtn.disabled = true;
  setIconButton(memoryBtn, "\u2605", t("chat.saveAsMemoryTooltip"));
  memoryBtn.addEventListener("click", () => saveMessageAsMemory(memoryBtn, msgEl));
  const workspaceBtn = createWorkspaceHandoffButton();
  workspaceBtn.disabled = true;
  const continueBtn = createContinueFromMessageButton(true);
  const verifyBtn = createVerifyAnswerButton(true);
  const exportBtn = createMessageExportButton(true);
  header.appendChild(nameSpan);
  header.appendChild(badge);
  header.appendChild(copyBtn);
  header.appendChild(continueBtn);
  header.appendChild(verifyBtn);
  header.appendChild(exportBtn);
  header.appendChild(createMessageActionOverflowMenu([memoryBtn, workspaceBtn]));

  const stepsContainer = document.createElement("div");
  stepsContainer.className = "agent-steps";
  stepsContainer.setAttribute("role", "list");
  stepsContainer.setAttribute("aria-label", t("chat.agentStepsLabel"));

  const completionEl = document.createElement("div");
  completionEl.className = "agent-completion-panel";
  completionEl.setAttribute("role", "group");
  completionEl.setAttribute("aria-label", t("chat.agentCompletionLabel"));
  completionEl.hidden = true;

  const outcomeSummaryEl = document.createElement("div");
  outcomeSummaryEl.className = "agent-outcome-summary";
  outcomeSummaryEl.setAttribute("role", "list");
  outcomeSummaryEl.setAttribute("aria-label", t("chat.agentOutcomeSummaryLabel"));
  outcomeSummaryEl.hidden = true;

  const summaryEl = document.createElement("div");
  summaryEl.className = "agent-summary agent-status";
  summaryEl.setAttribute("role", "status");
  summaryEl.setAttribute("aria-live", "polite");
  summaryEl.setAttribute("aria-atomic", "true");
  summaryEl.textContent = t("chat.agentStarting");

  const stopBtn = document.createElement("button");
  stopBtn.type = "button";
  stopBtn.className = "stop-thinking-btn agent-stop-btn";
  stopBtn.textContent = t("common.cancel");
  stopBtn.title = t("chat.agentStopTooltip");
  stopBtn.setAttribute("aria-label", t("chat.agentStopTooltip"));
  stopBtn.addEventListener("click", async () => {
    if (stopBtn.disabled) return;
    agentStoppedByUser = true;
    stopBtn.disabled = true;
    msgEl.removeAttribute("aria-busy");
    summaryEl.classList.remove("agent-status");
    summaryEl.textContent = t("chat.agentStopped");
    try {
      if (agentReader) await agentReader.cancel();
    } catch (e) {
      console.warn("[Agent] Reader cancel failed:", e.message || e);
    }
    LexaState.set("isLoading", false);
    sendBtn.disabled = false;
  });
  header.appendChild(stopBtn);

  body.appendChild(header);
  body.appendChild(completionEl);
  body.appendChild(outcomeSummaryEl);
  body.appendChild(stepsContainer);
  body.appendChild(summaryEl);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const response = await window.lexa.agentRun(agentText);
    if (agentStoppedByUser) {
      try { await response?.body?.cancel?.(); } catch (e) { console.warn("[Agent] Body cancel failed:", e.message || e); }
      throw new Error("agent_stream_stopped");
    }
    if (!response.ok) {
      msgEl.removeAttribute("aria-busy");
      summaryEl.classList.remove("agent-status");
      summaryEl.textContent = agentUserFacingError(response.statusText);
      setMessagePersistText(msgEl, summaryEl.textContent);
      copyBtn.disabled = false;
      memoryBtn.disabled = false;
      workspaceBtn.disabled = false;
      continueBtn.disabled = false;
      verifyBtn.disabled = false;
      exportBtn.disabled = false;
      LexaState.set("isLoading", false);
      sendBtn.disabled = false;
      stopBtn.disabled = true;
      stopBtn.classList.add("is-complete");
      saveChatHistory();
      saveCurrentConversation();
      return;
    }

    agentReader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const AGENT_STREAM_TIMEOUT_MS = 120000;
    const agentStreamStartedAt = Date.now();
    const agentOutcomeCounts = createAgentOutcomeCounts();
    const agentStepOutcomes = new Map();

    while (true) {
      const remainingMs = AGENT_STREAM_TIMEOUT_MS - (Date.now() - agentStreamStartedAt);
      if (remainingMs <= 0) {
        try { await agentReader.cancel(); } catch (e) { console.warn("[Agent] Reader cancel failed:", e.message || e); }
        throw new Error("agent_stream_timeout");
      }
      const readResult = await Promise.race([
        agentReader.read(),
        new Promise((resolve) => setTimeout(() => resolve({ timeout: true }), remainingMs)),
      ]);
      if (readResult.timeout) {
        try { await agentReader.cancel(); } catch (e) { console.warn("[Agent] Reader cancel failed:", e.message || e); }
        throw new Error("agent_stream_timeout");
      }
      const { done, value } = readResult;
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        try {
          const event = JSON.parse(raw);

          if (event.type === "thinking") {
            if (event.message) {
              summaryEl.classList.remove("agent-status");
              renderFormattedMessage(summaryEl, event.message);
            } else {
              summaryEl.classList.add("agent-status");
              summaryEl.textContent = t("chat.agentWorking");
            }
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }

          if (event.type === "step_start") {
            summaryEl.classList.add("agent-status");
            summaryEl.textContent = t("chat.agentWorking");
            const step = event.step || {};
            const stepEl = document.createElement("div");
            stepEl.className = "agent-step running";
            stepEl.id = `agent-step-${step.index}`;
            stepEl.setAttribute("role", "listitem");
            const readableLabel = agentStepDisplayLabel(step);
            const technicalLabel = agentStepTechnicalLabel(step);
            const icon = document.createElement("span");
            icon.className = "agent-step-icon";
            icon.textContent = "\u23F3"; // hourglass
            const label = document.createElement("span");
            label.className = "agent-step-label";
            label.textContent = readableLabel;
            stepEl.dataset.technicalLabel = technicalLabel;
            stepEl.title = readableLabel;
            stepEl.setAttribute("aria-label", readableLabel);
            stepEl.appendChild(icon);
            stepEl.appendChild(label);
            stepsContainer.appendChild(stepEl);
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }

          if (event.type === "step_done") {
            const step = event.step || {};
            const stepEl = document.getElementById(`agent-step-${step.index}`);
            if (stepEl) {
              stepEl.className = `agent-step ${step.status === "success" ? "success" : "failed"}`;
              const icon = stepEl.querySelector(".agent-step-icon");
              if (icon) icon.textContent = step.status === "success" ? "\u2705" : "\u274C";
              renderAgentStepOutcome(stepEl, step);
              // Add duration
              if (step.duration_ms) {
                const dur = document.createElement("span");
                dur.className = "agent-step-duration";
                dur.textContent = `${Math.round(step.duration_ms)}ms`;
                stepEl.appendChild(dur);
                renderAgentStepOutcome(stepEl, step);
              }
              recordAgentStepOutcome(step, agentOutcomeCounts, agentStepOutcomes);
              renderAgentOutcomeSummary(outcomeSummaryEl, agentOutcomeCounts);
            }
          }

          if (event.type === "step_blocked") {
            const step = event.step || {};
            const stepEl = document.getElementById(`agent-step-${step.index}`);
            if (stepEl) {
              stepEl.className = "agent-step blocked";
              const icon = stepEl.querySelector(".agent-step-icon");
              if (icon) icon.textContent = "\u26A0\uFE0F";
              const note = document.createElement("span");
              note.className = "agent-step-note";
              note.textContent = t("chat.agentNeedsConfirmation");
              stepEl.appendChild(note);
              renderAgentStepOutcome(stepEl, step);
              recordAgentStepOutcome(step, agentOutcomeCounts, agentStepOutcomes);
              renderAgentOutcomeSummary(outcomeSummaryEl, agentOutcomeCounts);
            }
          }

          if (event.type === "done") {
            const run = event.run || {};
            const finalOutcomeCounts = Array.isArray(run.steps) && run.steps.length
              ? agentRunOutcomeCounts(run.steps)
              : agentOutcomeCounts;
            renderAgentOutcomeSummary(outcomeSummaryEl, finalOutcomeCounts);
            setMessageAgentRunMeta(msgEl, {
              summary: run.summary || t("chat.agentCompleted"),
              steps: Array.isArray(run.steps) ? run.steps : [],
              counts: finalOutcomeCounts,
              total_duration_ms: run.total_duration_ms,
            });
            renderAgentCompletionPanel(completionEl, finalOutcomeCounts, {
              continuePrompt: agentCompletionContinuePrompt(run, finalOutcomeCounts, run.summary || summaryEl.textContent),
            });
            if (run.summary) {
              summaryEl.classList.remove("agent-status");
              renderFormattedMessage(summaryEl, run.summary);
              setMessagePersistText(msgEl, run.summary);
            } else {
              summaryEl.classList.remove("agent-status");
              summaryEl.textContent = t("chat.agentCompleted");
              setMessagePersistText(msgEl, summaryEl.textContent);
            }
            msgEl.removeAttribute("aria-busy");
            copyBtn.disabled = false;
            memoryBtn.disabled = false;
            workspaceBtn.disabled = false;
            continueBtn.disabled = false;
            verifyBtn.disabled = false;
            exportBtn.disabled = false;
            const durEl = document.createElement("div");
            durEl.className = "agent-duration";
            durEl.textContent = t("chat.agentSteps", {count: run.steps?.length || 0, ms: Math.round(run.total_duration_ms || 0)});
            body.appendChild(durEl);
          }

          if (event.type === "error") {
            summaryEl.classList.remove("agent-status");
            summaryEl.textContent = agentUserFacingError(event.message);
            setMessagePersistText(msgEl, summaryEl.textContent);
            msgEl.removeAttribute("aria-busy");
          }
        } catch (e) {
          console.warn("[Agent] SSE parse error:", e);
        }
      }
    }
  } catch (err) {
    const timedOut = err?.message === "agent_stream_timeout";
    const stopped = err?.message === "agent_stream_stopped" || agentStoppedByUser;
    summaryEl.classList.remove("agent-status");
    summaryEl.textContent = stopped ? t("chat.agentStopped") : (timedOut ? t("chat.agentTimeout") : t("chat.agentUnreachable"));
    setMessagePersistText(msgEl, summaryEl.textContent);
    msgEl.removeAttribute("aria-busy");
    if (!stopped) showToast(timedOut ? t("chat.agentTimeout") : t("chat.agentErrorGeneric"), "error");
  }

  agentReader = null;
  msgEl.removeAttribute("aria-busy");
  if ((summaryEl.textContent || "").trim()) {
    if (!msgEl.dataset?.persistText) setMessagePersistText(msgEl, summaryEl.textContent);
    copyBtn.disabled = false;
    memoryBtn.disabled = false;
    workspaceBtn.disabled = false;
    continueBtn.disabled = false;
    verifyBtn.disabled = false;
    exportBtn.disabled = false;
  }
  stopBtn.disabled = true;
  stopBtn.classList.add("is-complete");
  saveChatHistory();
  saveCurrentConversation();
  LexaState.set("isLoading", false);
  sendBtn.disabled = false;
}

async function regenerateMessage(originalPrompt) {
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return false; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return false; }
  const prompt = String(originalPrompt || "").trim();
  if (!prompt) { showToast(t("chat.regenerateMissingPrompt"), "warning", 2200); return false; }
  // Remove last system message
  const msgs = chatMessages.querySelectorAll(".message.system-message");
  if (msgs.length > 0) msgs[msgs.length - 1].remove();
  // Re-send the original message
  chatInput.value = prompt;
  await sendMessage();
  return true;
}

async function confirmAction(btn, actionStr) {
  let action = null;
  try {
    action = JSON.parse(decodeURIComponent(actionStr));
  } catch (_) {
    action = { action: "unknown", params: {} };
  }
  btn.textContent = t("chat.localActionBlockedButton");
  btn.disabled = true;
  // Clear pending confirmation on the backend (user clicked the button)
  try { await fetch(`${window.lexa.API_BASE}/chat/confirm-clear`, { method: "POST", credentials: "include" }); } catch (_) {}
  handleChatToolActionBlocked(action);
}

// ── SEND MODE (Enter vs Ctrl+Enter) ──────────────
window.ctrlEnterMode = localStorage.getItem("lexa-ctrl-enter") === "true";
function applySendModeToggle(enabled) {
  window.ctrlEnterMode = !!enabled;
  localStorage.setItem("lexa-ctrl-enter", enabled);
  const toggle = document.getElementById("ctrl-enter-toggle");
  if (toggle) toggle.checked = enabled;
  const hint = document.getElementById("chat-send-hint");
  if (hint) hint.textContent = enabled ? t("chat.sendHintCtrlEnter") : t("chat.sendHintEnter");
}

// ── CHAT INPUT HISTORY (shell-like Up/Down) ──────
const chatInputHistory = [];
let chatHistoryIdx = -1;
let chatInputDraft = "";
function pushChatHistory(text) {
  if (!text || chatInputHistory[0] === text) return;
  chatInputHistory.unshift(text);
  if (chatInputHistory.length > LexaConfig.CHAT_INPUT_HISTORY_MAX) chatInputHistory.length = LexaConfig.CHAT_INPUT_HISTORY_MAX;
  chatHistoryIdx = -1;
}

// ── SNIPPET AUTOCOMPLETE ─────────────────────────
let _snippetCache = null;
let _snippetPopup = null;
let _snippetIdx = 0;

async function getSnippets() {
  if (!_snippetCache) { try { const d = await window.lexa.snippets(); _snippetCache = d.snippets || []; } catch (e) { console.warn("[Chat] Failed to load snippets:", e.message || e); _snippetCache = []; } }
  return _snippetCache;
}
function closeSnippetPopup() { if (_snippetPopup) { _snippetPopup.remove(); _snippetPopup = null; } }
function buildSnippetPopup(snippets, query) {
  closeSnippetPopup();
  if (snippets.length === 0) return;
  _snippetIdx = 0;
  const popup = document.createElement("div");
  popup.className = "snippet-autocomplete";
  popup.setAttribute("role", "listbox");
  snippets.forEach((s, i) => {
    const item = document.createElement("div");
    item.className = "snippet-ac-item" + (i === 0 ? " selected" : "");
    const name = document.createElement("span");
    name.className = "snippet-ac-name";
    name.textContent = s.name || "";
    const preview = document.createElement("span");
    preview.className = "snippet-ac-preview";
    preview.textContent = (s.text || "").substring(0, 40) + ((s.text || "").length > 40 ? "\u2026" : "");
    item.appendChild(name);
    item.appendChild(preview);
    item.addEventListener("mousedown", (e) => { e.preventDefault(); applySnippet(s.text); });
    popup.appendChild(item);
  });
  _snippetPopup = popup;
  const container = chatInput.closest(".sleek-input-container") || chatInput.closest(".chat-input-area") || chatInput.parentElement;
  if (container) { container.classList.add("snippet-anchor"); container.appendChild(popup); }
}
function applySnippet(text) {
  chatInput.value = text;
  syncChatInputSize();
  closeSnippetPopup();
  chatInput.focus();
}
function navigateSnippetPopup(dir) {
  if (!_snippetPopup) return false;
  const items = _snippetPopup.querySelectorAll(".snippet-ac-item");
  if (items.length === 0) return false;
  items[_snippetIdx]?.classList.remove("selected");
  _snippetIdx = (_snippetIdx + dir + items.length) % items.length;
  items[_snippetIdx]?.classList.add("selected");
  return true;
}
function selectSnippetPopup() {
  if (!_snippetPopup) return false;
  const selected = _snippetPopup.querySelector(".snippet-ac-item.selected");
  if (selected) selected.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  return !!selected;
}
function invalidateSnippetCache() { _snippetCache = null; }

let _composerCommandOpen = false;
let _composerCommandIdx = 0;
let _composerCommandLastQuery = "";

function composerCommandQuery() {
  const value = String(chatInput?.value || "");
  if (!value.startsWith("/")) return "";
  return value.slice(1).split(/\s+/)[0].toLowerCase();
}

function updateComposerCommandActiveDescendant() {
  const palette = document.getElementById("composer-command-palette");
  const rows = _composerCommandRows();
  const activeRow = _composerCommandOpen ? rows[_composerCommandIdx] : null;
  if (palette) palette.setAttribute("aria-hidden", _composerCommandOpen ? "false" : "true");
  if (!chatInput) return;
  chatInput.setAttribute("aria-controls", "composer-command-palette");
  chatInput.setAttribute("aria-expanded", _composerCommandOpen ? "true" : "false");
  chatInput.setAttribute("aria-autocomplete", "list");
  if (activeRow?.id) chatInput.setAttribute("aria-activedescendant", activeRow.id);
  else chatInput.removeAttribute("aria-activedescendant");
}

function renderComposerCommandPalette(query = composerCommandQuery()) {
  const palette = document.getElementById("composer-command-palette");
  if (!palette) return;
  const normalizedQuery = composerCommandAliasKey(query);
  if (normalizedQuery !== _composerCommandLastQuery) {
    _composerCommandIdx = 0;
    _composerCommandLastQuery = normalizedQuery;
  }
  const items = composerCommandSearchItems(query);
  if (_composerCommandIdx >= items.length) _composerCommandIdx = 0;
  palette.innerHTML = "";
  if (!items.length) {
    palette.innerHTML = `<div class="composer-command-empty" role="option" aria-disabled="true">${escapeHtml(t("composer.empty"))}</div>`;
    updateComposerCommandActiveDescendant();
    return;
  }
  items.forEach((command, index) => {
    const label = composerCommandLabel(command);
    const desc = composerCommandDesc(command);
    const prefixHint = composerCommandHintText(command);
    const row = document.createElement("button");
    row.type = "button";
    row.id = `composer-command-option-${command.id}`;
    row.className = "composer-command-item" + (index === _composerCommandIdx ? " selected" : "");
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", index === _composerCommandIdx ? "true" : "false");
    row.setAttribute("aria-label", `${label}: ${desc}. ${prefixHint}`);
    row.title = `${label}: ${desc} (${prefixHint})`;
    row.dataset.commandId = command.id;
    row.innerHTML = `
      <span class="composer-command-icon" aria-hidden="true">${composerCommandIconSvg(command.icon)}</span>
      <span class="composer-command-main">
        <span class="composer-command-label">${escapeHtml(label)}</span>
        <span class="composer-command-desc">${escapeHtml(desc)}</span>
      </span>
      <span class="composer-command-prefix">${escapeHtml(prefixHint)}</span>
    `;
    row.addEventListener("mousedown", (e) => {
      e.preventDefault();
      selectComposerCommand(command.id);
    });
    palette.appendChild(row);
  });
  updateComposerCommandActiveDescendant();
}

function setComposerCommandPaletteOpen(open, options = {}) {
  const palette = document.getElementById("composer-command-palette");
  const button = document.getElementById("composer-command-btn");
  if (!palette) return;
  _composerCommandOpen = Boolean(open);
  if (button) {
    button.classList.toggle("active", _composerCommandOpen);
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", _composerCommandOpen ? "true" : "false");
    button.setAttribute("aria-controls", "composer-command-palette");
  }
  palette.classList.toggle("hidden", !_composerCommandOpen);
  palette.setAttribute("aria-hidden", _composerCommandOpen ? "false" : "true");
  if (_composerCommandOpen) {
    renderComposerCommandPalette(options.query || composerCommandQuery());
    if (options.focusInput !== false && chatInput) {
      setTimeout(() => {
        if (_composerCommandOpen && typeof chatInput.focus === "function") chatInput.focus();
      }, 0);
    }
  } else {
    updateComposerCommandActiveDescendant();
  }
}

function toggleComposerCommandPalette() {
  if (!_composerCommandOpen) {
    _composerCommandIdx = 0;
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: true });
  } else {
    setComposerCommandPaletteOpen(false);
  }
}

function closeComposerCommandPalette() {
  setComposerCommandPaletteOpen(false);
}

function updateComposerCommandPaletteFromInput() {
  if (!chatInput) return;
  const value = String(chatInput.value || "");
  if (value.startsWith("/") && !value.includes(" ")) {
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: false });
  } else if (_composerCommandOpen && value.trim() !== "") {
    closeComposerCommandPalette();
  }
}

function selectComposerCommand(commandId) {
  const command = LEXA_COMPOSER_COMMANDS.find((item) => item.id === commandId);
  if (!command || !chatInput) return false;
  const label = composerCommandLabel(command);
  chatInput.value = composerCommandPrefix(command);
  syncChatInputSize();
  closeComposerCommandPalette();
  chatInput.focus();
  try { localStorage.setItem("lexa-chat-draft", chatInput.value); } catch (_) {}
  showToast(t("composer.readyToast", { label }), "info", 1600);
  return true;
}

function _composerCommandRows() {
  return [...document.querySelectorAll("#composer-command-palette .composer-command-item")];
}

function handleComposerCommandKeydown(e) {
  if (!_composerCommandOpen) return false;
  const rows = _composerCommandRows();
  if (e.key === "Escape") {
    e.preventDefault();
    closeComposerCommandPalette();
    return true;
  }
  if (!rows.length) return false;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const dir = e.key === "ArrowDown" ? 1 : -1;
    rows[_composerCommandIdx]?.classList.remove("selected");
    rows[_composerCommandIdx]?.setAttribute("aria-selected", "false");
    _composerCommandIdx = (_composerCommandIdx + dir + rows.length) % rows.length;
    rows[_composerCommandIdx]?.classList.add("selected");
    rows[_composerCommandIdx]?.setAttribute("aria-selected", "true");
    rows[_composerCommandIdx]?.scrollIntoView({ block: "nearest" });
    updateComposerCommandActiveDescendant();
    return true;
  }
  if (e.key === "Enter" || e.key === "Tab") {
    e.preventDefault();
    const id = rows[_composerCommandIdx]?.dataset.commandId;
    return selectComposerCommand(id);
  }
  return false;
}

function setupComposerCommandPalette() {
  const button = document.getElementById("composer-command-btn");
  const palette = document.getElementById("composer-command-palette");
  if (!button || !palette) return;
  updateComposerCommandActiveDescendant();
  button.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown") return;
    e.preventDefault();
    _composerCommandIdx = 0;
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: true });
  });
  document.addEventListener("mousedown", (e) => {
    if (!_composerCommandOpen) return;
    if (palette.contains(e.target) || button.contains(e.target)) return;
    closeComposerCommandPalette();
  });
}

// ══════════════════════════════════════════════════════
//  VOICE SYSTEM v3 — Clean rebuild
//  Flow: Mic Button → Record → STT → Show Text → AI → TTS
// ══════════════════════════════════════════════════════

// ── STATE ──
const Voice = {
  recording: false,
  mediaRecorder: null,
  audioChunks: [],
  stream: null,
  ttsQueue: [],
  ttsPlaying: false,
  ttsAudio: null,
  ttsAudioUrl: null,
  ttsRunId: 0,
  recordMimeType: "audio/webm",
  silenceTimer: null,
  recordTimeout: null,
  audioCtx: null,
};

const VOICE_TTS_MIN_CHUNK_CHARS = 10;
const VOICE_TTS_MAX_CHUNK_CHARS = 420;
const VOICE_TTS_PLAYBACK_RATE = 1.08;

function voiceUiText(key, fallback, params) {
  try {
    const text = typeof t === "function" ? t(key, params) : "";
    return text && text !== key ? text : fallback;
  } catch (_) {
    return fallback;
  }
}

function setVoiceToggleA11y(button, active, labelKey, titleKey, fallbackLabel, fallbackTitle) {
  if (!button) return;
  button.dataset.i18nAriaLabel = labelKey;
  button.dataset.i18nTitle = titleKey;
  button.setAttribute("aria-label", voiceUiText(labelKey, fallbackLabel));
  button.setAttribute("aria-pressed", active ? "true" : "false");
  button.title = voiceUiText(titleKey, fallbackTitle);
}

function updateMicToggleA11y(active = false) {
  const mic = document.getElementById("mic-btn");
  setVoiceToggleA11y(
    mic,
    active,
    "chat.micToggleLabel",
    active ? "chat.micStopTitle" : "chat.micStartTitle",
    "Voice recording",
    active ? "Stop voice recording (Ctrl+M)" : "Start voice recording (Ctrl+M)"
  );
}

function updateMicProcessingA11y(processing = false) {
  const mic = document.getElementById("mic-btn");
  if (!mic) return;
  const isProcessing = Boolean(processing);
  mic.classList.toggle("processing", isProcessing);
  mic.setAttribute("aria-busy", isProcessing ? "true" : "false");
}

function updateTtsToggleA11y(active = false) {
  const ttsToggle = document.getElementById("tts-toggle");
  setVoiceToggleA11y(
    ttsToggle,
    active,
    "chat.ttsToggleLabel",
    active ? "chat.ttsToggleOnTitle" : "chat.ttsToggleOffTitle",
    "Text-to-speech",
    active ? "Text-to-speech is on. Click to turn off." : "Text-to-speech is off. Click to turn on."
  );
}

// ── SETUP (called once from app.js init) ──
function setupVoice() {
  const mic = document.getElementById("mic-btn");
  const tts = document.getElementById("tts-toggle");

  if (mic) {
    updateMicToggleA11y(Voice.recording);
    updateMicProcessingA11y(false);
    mic.addEventListener("click", voiceToggle);
    console.log("[Voice] Mic button ready");
  } else {
    console.warn("[Voice] mic-btn not found in DOM");
  }

  if (tts) {
    const initialTtsEnabled = Boolean(LexaState.get("ttsEnabled"));
    tts.classList.toggle("active", initialTtsEnabled);
    updateTtsToggleA11y(initialTtsEnabled);
    tts.addEventListener("click", () => {
      const on = !LexaState.get("ttsEnabled");
      LexaState.set("ttsEnabled", on);
      tts.classList.toggle("active", on);
      updateTtsToggleA11y(on);
      if (!on) voiceTTSClear();
      showToast(on ? t("chat.ttsEnabled") : t("chat.ttsDisabled"), "info", 1500);
    });
  }
}

// ── MIC TOGGLE ──
function voiceToggle() {
  if (Voice.recording) voiceStop(); else voiceStart();
}

function voicePreferredMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function voiceUsesOrbSurface(state) {
  const safeState = String(state || "").toLowerCase();
  return Boolean(window.__lexaOrbVoiceActive)
    && ["listening", "processing", "speaking", "bargein", "error"].includes(safeState);
}

function voiceHideStatusBar() {
  if (typeof VoiceStatusBar === "undefined") return;
  if (!VoiceStatusBar._bar && typeof VoiceStatusBar.init === "function") VoiceStatusBar.init();
  VoiceStatusBar.hide();
}

function voiceEndOrbSurface() {
  if (typeof window !== "undefined") window.__lexaOrbVoiceActive = false;
  showOrbListening(false);
  voiceSetOrbConversationState(null);
  voiceHideStatusBar();
}

function voiceStatusBarUpdate({ state, transcript, provider, latency } = {}) {
  if (typeof VoiceStatusBar === "undefined") return;
  const safeState = state ? String(state).toLowerCase() : "";
  if (voiceUsesOrbSurface(safeState)) {
    if (safeState === "error") {
      voiceEndOrbSurface();
    } else {
      showOrbListening(false);
      voiceSetOrbConversationState(safeState === "bargein" ? "listening" : safeState);
      voiceHideStatusBar();
    }
    return;
  }
  if (safeState === "speaking") {
    voiceStatusBarReset({ hide: true });
    return;
  }
  VoiceStatusBar.show();
  if (state) VoiceStatusBar.setState(state);
  if (transcript !== undefined) VoiceStatusBar.setTranscript(transcript);
  if (provider !== undefined) VoiceStatusBar.setProvider(provider);
  if (latency !== undefined) VoiceStatusBar.setLatency(latency);
}

function voiceStatusBarReset(options) {
  const hide = Boolean(options?.hide);
  if (typeof window !== "undefined" && window.__lexaOrbVoiceActive) {
    voiceEndOrbSurface();
    return;
  }
  if (typeof VoiceStatusBar === "undefined") return;
  if (!VoiceStatusBar._bar && typeof VoiceStatusBar.init === "function") VoiceStatusBar.init();
  VoiceStatusBar.setState("idle");
  VoiceStatusBar.setTranscript("");
  VoiceStatusBar.setProvider("");
  VoiceStatusBar.setLatency(0);
  if (hide) VoiceStatusBar.hide();
}

function voiceSpeechPending() {
  return Boolean(LexaState.get("ttsEnabled") && (Voice.ttsPlaying || Voice.ttsQueue.length > 0));
}

function voiceStatusBarResetIfNoSpeechPending() {
  if (!voiceSpeechPending()) voiceStatusBarReset();
}

function voiceSetOrbConversationState(state) {
  const safeState = state || null;
  if (typeof window !== "undefined" && typeof window.setOrbConversationState === "function") {
    window.setOrbConversationState(safeState);
    return;
  }
  if (typeof _setOrbConversationState === "function") {
    _setOrbConversationState(safeState);
    return;
  }

  const orbCanvas = document.getElementById("voice-orb-canvas");
  const orbContainer = document.getElementById("voice-orb-container");
  if (orbCanvas) {
    orbCanvas.classList.remove("conv-listening", "conv-processing", "conv-speaking", "conv-bargein");
    if (safeState) orbCanvas.classList.add("conv-" + safeState);
  }
  if (orbContainer) {
    orbContainer.classList.toggle("conversation-active", Boolean(safeState));
    if (safeState) orbContainer.dataset.convState = safeState;
    else delete orbContainer.dataset.convState;
  }
  if (window.dashboardOrb && typeof window.dashboardOrb.setConversationState === "function") {
    window.dashboardOrb.setConversationState(safeState);
  }
}

function voiceRecorderWillProcessOnStop() {
  return Boolean(Voice.mediaRecorder && Voice.mediaRecorder.state !== "inactive");
}

function voiceApiBase() {
  return window.lexa?.API_BASE || "http://127.0.0.1:8000";
}

function voiceTTSFindSplit(text, maxLength = VOICE_TTS_MAX_CHUNK_CHARS) {
  const value = String(text || "");
  if (value.length <= maxLength) return value.length;
  const windowText = value.slice(0, maxLength);
  const minSplit = Math.floor(maxLength * 0.45);
  for (const boundary of [". ", "! ", "? ", "\n", "; ", ": ", ", "]) {
    const index = windowText.lastIndexOf(boundary);
    if (index >= minSplit) return index + (boundary === "\n" ? 1 : boundary.length - 1);
  }
  const spaceIndex = windowText.lastIndexOf(" ");
  if (spaceIndex >= minSplit) return spaceIndex;
  return maxLength;
}

function voiceTTSChunkText(text, maxLength = VOICE_TTS_MAX_CHUNK_CHARS) {
  let remaining = String(text || "").replace(/\s+/g, " ").trim();
  const chunks = [];
  while (remaining.length > maxLength) {
    const splitAt = voiceTTSFindSplit(remaining, maxLength);
    const chunk = remaining.slice(0, splitAt).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function voiceTTSFlushBuffer(buffer, force = false) {
  const value = String(buffer || "");
  const complete = value.match(/^(.*[.!?\n])\s*/s);
  let speakable = "";
  let remaining = value;
  if (complete && complete[1].trim().length >= VOICE_TTS_MIN_CHUNK_CHARS) {
    speakable = complete[1];
    remaining = value.slice(complete[0].length);
  } else if (force) {
    speakable = value;
    remaining = "";
  } else if (value.length >= VOICE_TTS_MAX_CHUNK_CHARS) {
    const splitAt = voiceTTSFindSplit(value);
    speakable = value.slice(0, splitAt);
    remaining = value.slice(splitAt);
  }
  if (speakable.trim()) voiceTTSEnqueue(speakable.trim());
  return remaining.trimStart();
}

// ── START RECORDING ──
async function voiceStart() {
  const mic = document.getElementById("mic-btn");
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: t("chat.sttUnavailableMsg"), provider: "" });
    showToast(t("chat.sttUnavailableMsg"), "error");
    return;
  }

  try {
    Voice.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    const message = voiceUiText("chat.micAccessDeniedMsg", "Microphone access denied. Please allow access.");
    voiceStatusBarUpdate({ state: "error", transcript: message, provider: "" });
    showToast(message, "error");
    return;
  }

  Voice.audioChunks = [];
  const mimeType = voicePreferredMimeType();
  try {
    Voice.mediaRecorder = new MediaRecorder(Voice.stream, mimeType ? { mimeType } : undefined);
    Voice.recordMimeType = Voice.mediaRecorder.mimeType || mimeType || "audio/webm";
  } catch (e) {
    if (Voice.stream) { Voice.stream.getTracks().forEach(t => t.stop()); Voice.stream = null; }
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: t("chat.sttUnavailableMsg"), provider: "" });
    showToast(t("chat.sttUnavailableMsg"), "error");
    return;
  }
  Voice.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) Voice.audioChunks.push(e.data); };
  Voice.mediaRecorder.onstop = () => voiceProcess();
  Voice.mediaRecorder.start();
  Voice.recording = true;
  LexaState.set("isRecording", true);
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(true);
  updateMicToggleA11y(true);

  if (mic) mic.classList.add("recording");
  voiceStatusBarUpdate({ state: "listening", transcript: "", provider: voiceUiText("chat.voiceProviderRecording", "Recording") });

  // Silence detection
  voiceStartSilenceDetect(Voice.stream);

  // Safety: max 30s
  Voice.recordTimeout = setTimeout(() => { if (Voice.recording) voiceStop(); }, 30000);

  console.log("[Voice] Recording started");
}

// ── STOP RECORDING ──
function voiceStop() {
  const mic = document.getElementById("mic-btn");
  const shouldProcessRecording = voiceRecorderWillProcessOnStop();
  if (Voice.silenceTimer) { clearInterval(Voice.silenceTimer); Voice.silenceTimer = null; }
  if (Voice.recordTimeout) { clearTimeout(Voice.recordTimeout); Voice.recordTimeout = null; }
  if (shouldProcessRecording) Voice.mediaRecorder.stop();
  if (Voice.stream) { Voice.stream.getTracks().forEach(t => t.stop()); Voice.stream = null; }
  Voice.recording = false;
  LexaState.set("isRecording", false);
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
  updateMicToggleA11y(false);
  if (mic) mic.classList.remove("recording");
  updateMicProcessingA11y(shouldProcessRecording);
  if (shouldProcessRecording) {
    voiceStatusBarUpdate({ state: "processing", provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });
  } else {
    voiceStatusBarResetIfNoSpeechPending();
  }
  console.log("[Voice] Recording stopped");
}

// ── SILENCE DETECTION ──
function voiceStartSilenceDetect(stream) {
  try {
    if (!Voice.audioCtx) Voice.audioCtx = new AudioContext();
    const src = Voice.audioCtx.createMediaStreamSource(stream);
    const analyser = Voice.audioCtx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    const data = new Float32Array(analyser.fftSize);
    let silenceStart = null;
    let hasSpeech = false;

    Voice.silenceTimer = setInterval(() => {
      if (!Voice.recording) { clearInterval(Voice.silenceTimer); return; }
      analyser.getFloatTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      const rms = Math.sqrt(sum / data.length);

      if (rms > 0.012) { hasSpeech = true; silenceStart = null; }
      else if (hasSpeech) {
        if (!silenceStart) silenceStart = Date.now();
        else if (Date.now() - silenceStart > 2000) {
          console.log("[Voice] Silence detected, auto-stop");
          clearInterval(Voice.silenceTimer);
          voiceStop();
        }
      }
    }, 100);
  } catch (e) {
    console.warn("[Voice] Silence detection failed:", e);
  }
}

// ── PROCESS: STT → CHAT → TTS ──
async function voiceProcess() {
  const blob = new Blob(Voice.audioChunks, { type: Voice.recordMimeType || "audio/webm" });
  if (blob.size < 100) {
    const message = voiceUiText("chat.voiceNoRecording", "No recording captured.");
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: message, provider: "" });
    showToast(message, "warning");
    return;
  }

  const mic = document.getElementById("mic-btn");
  updateMicProcessingA11y(true);
  voiceStatusBarUpdate({ state: "processing", transcript: voiceUiText("chat.voiceTranscribing", "Transcribing speech..."), provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });

  // Auto-open chat so user sees results
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();

  try {
    // 1. STT
    console.log("[Voice] Sending to STT, blob size:", blob.size);
    const stt = await window.lexa.stt(blob);
    console.log("[Voice] STT result:", stt);

    if (!stt.success || !stt.text || !stt.text.trim()) {
      voiceStatusBarUpdate({ state: "error", transcript: voiceUiText("chat.voiceNotUnderstood", "Could not understand."), provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });
      showToast(voiceUiText("chat.voiceNotUnderstoodFull", "Could not understand. Please try again."), "warning", 2500);
      updateMicProcessingA11y(false);
      return;
    }

    voiceStatusBarUpdate({ state: "processing", transcript: stt.text, provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });

    // Show user text in chat
    addMessage(stt.text, "user", null, false, true);

    // 2. AI Chat (streaming)
    console.log("[Voice] Sending to AI:", stt.text);
    updateMicProcessingA11y(false);

    await voiceStreamChat(stt.text);

  } catch (e) {
    console.error("[Voice] Pipeline error:", e);
    const errorText = e.message || String(e);
    voiceStatusBarUpdate({ state: "error", transcript: errorText, provider: "" });
    showToast(voiceUiText("chat.voiceErrorPrefix", "Voice error: {{msg}}", { msg: errorText }), "error");
    updateMicProcessingA11y(false);
  }
}

// ── STREAMING CHAT + TTS ──
async function voiceStreamChat(text) {
  const API = voiceApiBase();
  let fullText = "";
  let action = null;
  let requiresConfirmation = false;
  let timeout = null;
  let reader = null;

  try {
    voiceStatusBarUpdate({ state: "processing", provider: voiceUiText("chat.voiceProviderResponse", "Antwort"), transcript: text });
    const abort = new AbortController();
    timeout = setTimeout(() => abort.abort(), 45000);

    const resp = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        message: text,
        conversation_id: LexaState.get("activeConversationId"),
      }),
      signal: abort.signal,
    });

    if (!resp.ok) {
      // Fallback to non-streaming
      const fallback = await window.lexa.chat(text);
      handleChatResponse(fallback, true);
      voiceStatusBarResetIfNoSpeechPending();
      if (timeout) { clearTimeout(timeout); timeout = null; }
      return;
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let ttsBuf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.c) {
            fullText += d.c;
            ttsBuf += d.c;
            ttsBuf = voiceTTSFlushBuffer(ttsBuf);
          }
          if (d.done) {
            action = d.action || null;
            requiresConfirmation = d.rc || false;
            ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);
          }
        } catch (_) {}
      }
    }

    ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);
    if (timeout) { clearTimeout(timeout); timeout = null; }

    if (fullText) {
      const displayText = action && typeof chatActionDisplayReply === "function"
        ? chatActionDisplayReply({ reply: fullText, action })
        : fullText;
      addMessage(displayText, "system", action, requiresConfirmation, true);
      if (action) handleChatToolActionBlocked(action, { source: "voice", toast: false });
    }
    voiceStatusBarResetIfNoSpeechPending();

  } catch (e) {
    if (timeout) { clearTimeout(timeout); timeout = null; }
    if (reader) {
      try { await reader.cancel(); } catch (cancelErr) { console.warn("[Voice] Reader cancel failed:", cancelErr.message || cancelErr); }
    }
    console.warn("[Voice] Stream failed, fallback:", e);
    try {
      const fb = await window.lexa.chat(text);
      handleChatResponse(fb, true);
      voiceStatusBarResetIfNoSpeechPending();
    } catch (_) {
      const backendMessage = voiceUiText("chat.voiceBackendUnreachable", "Connection error. Backend not reachable.");
      voiceStatusBarUpdate({ state: "error", transcript: backendMessage, provider: "" });
      addMessage(backendMessage, "system");
    }
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

// ── TTS QUEUE ──
function voiceTTSEnqueue(text) {
  if (!LexaState.get("ttsEnabled") || !text) return;
  const chunks = voiceTTSChunkText(text);
  chunks.forEach((chunk) => Voice.ttsQueue.push(chunk));
  if (!Voice.ttsPlaying && Voice.ttsQueue.length > 0) voiceTTSNext();
}

function voiceTTSResetPlayback(options) {
  const hide = Boolean(options?.hide);
  Voice.ttsQueue.length = 0;
  Voice.ttsPlaying = false;
  voiceStatusBarReset({ hide });
  voiceSetOrbConversationState(null);
}

async function voiceTTSNext() {
  if (Voice.ttsQueue.length === 0) {
    const wasPlaying = Voice.ttsPlaying;
    Voice.ttsPlaying = false;
    if (wasPlaying) {
      voiceStatusBarReset();
      voiceSetOrbConversationState(null);
    }
    return;
  }
  Voice.ttsPlaying = true;
  const runId = Voice.ttsRunId;
  const text = Voice.ttsQueue.shift();
  try {
    voiceSetOrbConversationState("speaking");
    voiceStatusBarUpdate({
      state: "speaking",
      transcript: voiceUiText("chat.voiceSpeakingResponse", "Speaking response..."),
      provider: voiceUiText("chat.voiceProviderSpeech", "Voice"),
    });
    const url = await window.lexa.tts(text);
    if (url) {
      if (runId !== Voice.ttsRunId || !LexaState.get("ttsEnabled")) {
        URL.revokeObjectURL(url);
        voiceTTSResetPlayback({ hide: !LexaState.get("ttsEnabled") });
        return;
      }
      const audio = new Audio(url);
      audio.playbackRate = VOICE_TTS_PLAYBACK_RATE;
      if ("preservesPitch" in audio) audio.preservesPitch = true;
      Voice.ttsAudio = audio;
      Voice.ttsAudioUrl = url;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        if (Voice.ttsAudio === audio) {
          Voice.ttsAudio = null;
          Voice.ttsAudioUrl = null;
        }
        URL.revokeObjectURL(url);
        if (runId === Voice.ttsRunId && Voice.ttsQueue.length === 0) {
          voiceStatusBarReset();
          voiceSetOrbConversationState(null);
        }
        if (runId === Voice.ttsRunId) voiceTTSNext();
      };
      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);
    } else {
      if (runId === Voice.ttsRunId) voiceTTSNext();
    }
  } catch (e) {
    console.warn("[TTS] Error:", e);
    if (runId === Voice.ttsRunId) voiceTTSNext();
  }
}

function voiceTTSClear() {
  Voice.ttsRunId += 1;
  const audio = Voice.ttsAudio;
  const url = Voice.ttsAudioUrl;
  Voice.ttsAudio = null;
  Voice.ttsAudioUrl = null;
  voiceTTSResetPlayback({ hide: true });
  if (audio) {
    audio.onended = null;
    audio.onerror = null;
    try { audio.pause(); } catch (_) {}
    try { audio.removeAttribute("src"); audio.load(); } catch (_) {}
  }
  if (url) URL.revokeObjectURL(url);
}

// ── COMPAT: functions referenced by other modules ──
function toggleRecording() { voiceToggle(); }
function playTTS(text) { voiceTTSEnqueue(text); }
function showOrbListening(show) {
  const el = document.getElementById("orb-listening-text");
  if (el) el.classList.toggle("hidden", !show);
}
function showOrbTranscript(userText, lexaText) {
  const container = document.getElementById("orb-transcript");
  const userEl = document.getElementById("orb-user-text");
  const lexaEl = document.getElementById("orb-lexa-text");
  if (!container) return;
  if (userText !== undefined && userEl) userEl.textContent = userText;
  if (lexaText !== undefined && lexaEl) lexaEl.textContent = lexaText;
  container.classList.remove("hidden");
}
function clearOrbTranscript() {
  const c = document.getElementById("orb-transcript");
  const u = document.getElementById("orb-user-text");
  const l = document.getElementById("orb-lexa-text");
  if (c) c.classList.add("hidden");
  if (u) u.textContent = "";
  if (l) l.textContent = "";
}
function clearVoiceTranscriptPanel() {
  const p = document.getElementById("voice-transcript-panel");
  const l = document.getElementById("voice-transcript-list");
  if (p) p.classList.add("hidden");
  if (l) l.innerHTML = "";
}
function toggleChatView() {
  const msgs = document.getElementById("chat-messages");
  const arrow = document.getElementById("chat-view-arrow");
  const orb = document.getElementById("voice-orb-container");
  const greeting = document.getElementById("sleek-greeting");
  const cards = document.getElementById("floating-cards-container");
  if (!msgs) return;
  window._chatViewOpen = !window._chatViewOpen;
  if (window._chatViewOpen) {
    msgs.classList.remove("hidden");
    msgs.scrollTop = msgs.scrollHeight;
    if (arrow) arrow.classList.add("flipped");
    if (orb) orb.classList.add("compact");
    if (greeting) greeting.classList.add("hidden");
    if (cards) cards.classList.add("hidden");
  } else {
    msgs.classList.add("hidden");
    if (arrow) arrow.classList.remove("flipped");
    if (orb) orb.classList.remove("compact");
  }
}
function renderTalkButton(listening = false) {
  const btn = document.getElementById("talk-to-lexa-btn");
  if (!btn) return;
  const active = listening || Voice.recording;
  btn.classList.toggle("listening", active);
  const icon = active
    ? '<path d="M12 2v20M17 5v14M7 5v14M22 8v8M2 8v8"/>'
    : '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm0 14a5 5 0 0 1-5-5H5a7 7 0 0 0 14 0h-2a5 5 0 0 1-5 5Zm-2 4v3h4v-3h-4Z"/>';
  const labelKey = active ? "chat.endConversation" : "chat.talkToLexaBtn";
  const label = typeof t === "function" ? t(labelKey) : (active ? "End conversation" : "Talk to Lexa");
  btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="talk-btn-icon">' + icon + '</svg><span data-voice-entry-label data-i18n="' + labelKey + '">' + label + '</span>';
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(active);
}

// ══════════════════════════════════════════════════════

function handleChatResponse(res, ambient = false) {
  if (res.detail) {
      if (ambient) showOrbTranscript(undefined, res.detail);
      addMessage(res.detail, "system", null, false, ambient);
      if (res.detail.includes("Zu viele")) showToast(t("toast.rateLimitHit"), "warning");
  }
  else {
    const displayReply = typeof chatActionDisplayReply === "function" ? chatActionDisplayReply(res) : res.reply;
    if (ambient) showOrbTranscript(undefined, displayReply);
    addMessage(displayReply, "system", res.action, res.requires_confirmation, ambient);
    playTTS(displayReply);
    if (res.action) handleChatToolActionBlocked(res.action, { source: "chat-response", toast: false });
  }
}

// ── SMART SUGGESTIONS ───────────────────────────

// ── CONVERSATION STARTERS ───────────────────────
function _getConversationStarters() {
  return {
    morning: [
      { icon: "sun", title: t("chat.starterDayPlan"), text: t("chat.starterDayPlanDesc"), msg: t("chat.starterMsgDayPlan") },
      { icon: "mail", title: t("chat.starterEmails"), text: t("chat.starterEmailsDesc"), msg: t("chat.starterMsgEmails") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescMorning"), msg: t("chat.starterMsgTodos") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDesc"), msg: t("chat.starterMsgSysteminfo") },
    ],
    afternoon: [
      { icon: "timer", title: t("chat.starterPomodoro"), text: t("chat.starterPomodoroDesc"), msg: t("chat.starterMsgPomodoro") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescAfternoon"), msg: t("chat.starterMsgTodos") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescWork"), msg: t("chat.starterMsgFocusMusic") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDescPerf"), msg: t("chat.starterMsgSysteminfo") },
    ],
    evening: [
      { icon: "chart", title: t("chat.starterReview"), text: t("chat.starterReviewDesc"), msg: t("chat.starterMsgWhatDone") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescChill"), msg: t("chat.starterMsgChillMusic") },
      { icon: "spark", title: t("chat.starterCleanup"), text: t("chat.starterCleanupDesc"), msg: t("chat.starterMsgCleanDownloads") },
      { icon: "note", title: t("chat.starterNotes"), text: t("chat.starterNotesDesc"), msg: t("chat.starterMsgShowNotes") },
    ],
    night: [
      { icon: "moon", title: t("chat.starterNightMode"), text: t("chat.starterNightModeDesc"), msg: t("chat.starterMsgQuieter") },
      { icon: "note", title: t("chat.starterNotes"), text: t("chat.starterNotesDescNight"), msg: t("chat.starterMsgShowNotes") },
      { icon: "timer", title: t("chat.starterTimer"), text: t("chat.starterTimerDesc"), msg: t("chat.starterMsgTimer30") },
      { icon: "message", title: t("chat.starterSmalltalk"), text: t("chat.starterSmalltalkDesc"), msg: t("chat.starterMsgHowAreYou") },
    ],
    general: [
      { icon: "bolt", title: t("chat.starterQuickStart"), text: t("chat.starterQuickStartDesc"), msg: t("chat.starterMsgWhatCanYouDo") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescGeneral"), msg: t("chat.starterMsgTodos") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescGeneral"), msg: t("chat.starterMsgGoodMusic") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDescGeneral"), msg: t("chat.starterMsgSysteminfo") },
    ],
  };
}

function starterIconSvg(name) {
  const paths = {
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 3-3 3 2 4-6"/>',
    checklist: '<path d="m5 7 2 2 4-4"/><path d="M13 7h6"/><path d="m5 17 2 2 4-4"/><path d="M13 17h6"/>',
    mail: '<path d="M4 6h16v12H4z"/><path d="m4 7 8 6 8-6"/>',
    message: '<path d="M5 6h14v10H8l-3 3V6Z"/><path d="M8 10h8"/><path d="M8 13h5"/>',
    moon: '<path d="M20 15.4A7.5 7.5 0 0 1 8.6 4 8 8 0 1 0 20 15.4Z"/>',
    music: '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
    note: '<path d="M6 4h9l3 3v13H6z"/><path d="M14 4v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
    spark: '<path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z"/><path d="M19 15v4"/><path d="M17 17h4"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/>',
    system: '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M8 20h8"/><path d="M10 16v4"/><path d="M14 16v4"/>',
    timer: '<circle cx="12" cy="13" r="7"/><path d="M12 9v4l3 2"/><path d="M9 2h6"/>',
  };
  const path = paths[name] || paths.spark;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

function renderConversationStarters() {
  const grid = document.getElementById("starter-grid");
  if (!grid) return;

  const starterCommandIds = ["workspace", "research", "think", "os"];
  const starters = starterCommandIds
    .map((id) => LEXA_COMPOSER_COMMANDS.find((command) => command.id === id))
    .filter(Boolean);

  grid.innerHTML = "";
  starters.forEach((command) => {
    const label = composerCommandLabel(command);
    const desc = composerCommandDesc(command);
    const hint = composerCommandHintText(command);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "starter-card";
    card.setAttribute("aria-label", `${label}: ${desc}. ${hint}`);
    card.title = `${label}: ${desc}`;
    const iconEl = document.createElement("span");
    iconEl.className = "starter-icon";
    iconEl.dataset.icon = command.icon || "spark";
    iconEl.innerHTML = composerCommandIconSvg(command.icon || "spark");
    iconEl.setAttribute("aria-hidden", "true");
    const content = document.createElement("div");
    content.className = "starter-content";
    const titleEl = document.createElement("span");
    titleEl.className = "starter-title";
    titleEl.textContent = label;
    const descEl = document.createElement("span");
    descEl.className = "starter-desc";
    descEl.textContent = desc;
    const prefixEl = document.createElement("span");
    prefixEl.className = "starter-prefix";
    prefixEl.textContent = hint;
    content.appendChild(titleEl);
    content.appendChild(descEl);
    content.appendChild(prefixEl);
    card.appendChild(iconEl);
    card.appendChild(content);
    card.addEventListener("click", () => {
      selectComposerCommand(command.id);
    });
    grid.appendChild(card);
  });
}

// ── PERFORMANCE ──────────────────────────────────
function trimChatMessages() {
  const msgs = chatMessages.querySelectorAll(".message");
  if (msgs.length > LexaConfig.MAX_DOM_MESSAGES) {
    const toRemove = msgs.length - LexaConfig.MAX_DOM_MESSAGES;
    for (let i = 0; i < toRemove; i++) msgs[i].remove();
  }
}

// ── CONVERSATIONS ───────────────────────────────
async function loadConversations() {
  try {
    await refreshConversationSidebar();

    // We explicitly do NOT auto-switch to an old conversation here
    // so the app remains in its beautiful, clean zero-state.
    LexaState.set("currentConversationId", null);
    localStorage.removeItem("lexa-active-conversation");
  } catch (e) {
    console.warn("[Chat] Failed to load conversations:", e.message || e);
  }
}

async function refreshConversationSidebar() {
  const data = await window.lexa.conversations();
  LexaState.set("conversationsList", data.conversations || []);
  if (typeof updateConversationCount === "function") {
    updateConversationCount(LexaState.get("conversationsList").length);
  }
  renderConversationList();
}

function restoreActiveConversationSelection(convId, activeConversationValue) {
  LexaState.set("currentConversationId", convId || null);
  if (activeConversationValue === null || activeConversationValue === undefined) {
    localStorage.removeItem("lexa-active-conversation");
  } else {
    localStorage.setItem("lexa-active-conversation", activeConversationValue);
  }
  renderConversationList();
}

function renderConversationList() {
  const container = document.getElementById("conversation-list");
  if (!container) return;
  const convList = LexaState.get("conversationsList") || [];
  const attentionList = agentRunAttentionListForConversations(convList);
  const attentionById = new Map(attentionList.map((item) => [String(item.convId), item]));
  let attentionOnly = Boolean(LexaState.get("conversationAttentionOnly"));
  if (attentionOnly && attentionList.length === 0) {
    LexaState.set("conversationAttentionOnly", false);
    attentionOnly = false;
  }
  updateAgentAttentionFilterButton(attentionList.length, attentionOnly);
  updateAgentAttentionHeaderSummary(attentionList, convList);
  if (typeof updateConversationCount === "function") {
    updateConversationCount(convList.length);
  }
  if (convList.length === 0) { renderConversationEmptyState(container, t("chat.noConversations")); return; }
  container.innerHTML = "";
  if (attentionOnly) renderAgentAttentionFilterNote(container, attentionList.length);
  else renderAgentAttentionPanel(container, convList);
  renderAgentResolvedHistoryPanel(container, convList);
  const visibleConversations = attentionOnly ? convList.filter((c) => attentionById.has(String(c.id))) : convList;
  if (visibleConversations.length === 0) {
    renderConversationEmptyState(container, t("chat.noAgentAttentionConversations"));
    return;
  }
  visibleConversations.forEach(c => {
    const attention = attentionById.get(String(c.id));
    const isActive = c.id === LexaState.get("currentConversationId");
    container.appendChild(createConversationListItem(c, { attention, isActive }));
  });
}
async function newConversation() {
  if (_newConversationInFlight) return false;
  _newConversationInFlight = true;
  setNewConversationControlsBusy(true);
  try {
    await saveCurrentConversation({ notifyFailure: true });
    const title = t("chat.newChatTitle");
    let result = null;
    try {
      result = await window.lexa.conversationCreate(title);
    } catch (e) {
      console.warn("[Chat] Failed to create new conversation:", e.message || e);
      showToast(t("toast.createError"), "error");
      return false;
    }
    if (!result?.id) {
      console.warn("[Chat] Failed to create new conversation: missing id");
      showToast(t("toast.createError"), "error");
      return false;
    }
    LexaState.set("currentConversationId", result.id);
    localStorage.setItem("lexa-active-conversation", result.id);
    upsertConversationLocally({ id: result.id, title: result.title || title, message_count: 0, last_message: "" });
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m) => m.remove());
    try {
      await window.lexa.historyClear();
    } catch (e) {
      console.warn("[Chat] New conversation created but history clear failed:", e.message || e);
      showToast(t("toast.newChatHistoryClearFailed"), "warning", 3000);
    }
    try {
      const sleekGreeting = document.getElementById("sleek-greeting");
      if (sleekGreeting) sleekGreeting.classList.remove("hidden");
      const floatingCards = document.getElementById("floating-cards-container");
      if (floatingCards) floatingCards.classList.remove("hidden");
      const chatMessagesEl = document.getElementById("chat-messages");
      if (chatMessagesEl) chatMessagesEl.classList.add("hidden");
      clearOrbTranscript();
      window._chatViewOpen = false;
      const chatArrow = document.getElementById("chat-view-arrow");
      if (chatArrow) chatArrow.classList.remove("flipped");
      const startersEl = document.getElementById("conversation-starters");
      if (startersEl) { startersEl.classList.remove("hidden"); renderConversationStarters(); }
      try {
        await refreshConversationSidebar();
      } catch (e) {
        console.warn("[Chat] New conversation created but sidebar refresh failed:", e.message || e);
        showToast(t("toast.newChatRefreshFailed"), "warning", 3000);
        renderConversationList();
      }
      switchView("chat");
      chatInput.focus();
      showToast(t("toast.newChatStarted"), "info", 2000);
      return true;
    } catch (e) {
      console.warn("[Chat] New conversation created but local setup failed:", e.message || e);
      showToast(t("toast.loadError"), "warning", 3000);
      return false;
    }
  } finally {
    _newConversationInFlight = false;
    setNewConversationControlsBusy(false);
  }
}
async function switchConversation(convId, notify = true) {
  if (convId === LexaState.get("currentConversationId") && notify) return;
  const switchSeq = ++_conversationSwitchSeq;
  _conversationSwitchInFlight += 1;
  try {
    const previousConvId = LexaState.get("currentConversationId");
    const previousActiveConversation = localStorage.getItem("lexa-active-conversation");
    await saveCurrentConversation({ notifyFailure: notify });
    if (switchSeq !== _conversationSwitchSeq) return false;
    LexaState.set("currentConversationId", convId);
    localStorage.setItem("lexa-active-conversation", convId);
    try {
      const conv = await window.lexa.conversationGet(convId);
      if (switchSeq !== _conversationSwitchSeq) return false;
      if (!conv || conv.detail) {
        restoreActiveConversationSelection(previousConvId, previousActiveConversation);
        if (notify) showToast(t("toast.convNotFound"), "error");
        return false;
      }
      await window.lexa.conversationLoad(convId);
      if (switchSeq !== _conversationSwitchSeq) return false;
      const msgs = chatMessages.querySelectorAll(".message");
      msgs.forEach((m) => m.remove());
      const messages = conv.messages || [];
      renderPersistedConversationMessages(messages, convId);
      saveAgentRunMetaForConversation(convId);
      renderConversationList();
      if (notify) {
        switchView("chat");
        // Open chat view to show loaded conversation
        if (!window._chatViewOpen && messages.length > 0) toggleChatView();
        showToast(t("chat.chatLoaded", {title: conv.title}), "info", 1500);
      }
      return true;
    } catch (e) {
      if (switchSeq !== _conversationSwitchSeq) return false;
      restoreActiveConversationSelection(previousConvId, previousActiveConversation);
      console.warn("[Chat] Failed to switch conversation:", e.message || e);
      if (notify) showToast(t("toast.loadError"), "error");
      return false;
    }
  } finally {
    _conversationSwitchInFlight = Math.max(0, _conversationSwitchInFlight - 1);
  }
}
async function saveCurrentConversation(options = null) {
  const opts = options || {};
  const convId = LexaState.get("currentConversationId");
  if (!convId) return true;
  saveAgentRunMetaForConversation(convId);
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg) => {
    if (!isPersistableChatMessage(msg)) return;
    const text = getMessagePersistText(msg);
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    if (text) messages.push({ role, content: text });
  });
  try {
    await window.lexa.conversationUpdate(convId, { messages });
  } catch (e) {
    console.warn("[Chat] Failed to save conversation:", e.message || e);
    if (opts.notifyFailure) showToast(t("toast.conversationSaveFailed"), "warning", 3500);
    return false;
  }
  try {
    await refreshConversationSidebar();
  } catch (e) {
    console.warn("[Chat] Saved conversation but failed to refresh sidebar:", e.message || e);
    if (opts.notifyFailure) showToast(t("toast.conversationRefreshFailed"), "warning", 3000);
  }
  return true;
}
async function deleteConversation(convId, triggerBtn = null) {
  if (triggerBtn?.disabled || triggerBtn?.getAttribute("aria-busy") === "true") return;
  if (triggerBtn) {
    triggerBtn.disabled = true;
    triggerBtn.setAttribute("aria-busy", "true");
  }
  try {
    await window.lexa.conversationDelete(convId);
  } catch (e) {
    console.warn("[Chat] Failed to delete conversation:", e.message || e);
    showToast(t("toast.deleteError"), "error");
    return;
  }
  try {
    const wasActive = String(convId) === String(LexaState.get("currentConversationId")) || String(convId) === String(localStorage.getItem("lexa-active-conversation"));
    clearAgentRunLocalStateForConversation(convId);
    if (wasActive) {
      LexaState.set("currentConversationId", null);
      localStorage.removeItem("lexa-active-conversation");
    }
    let convList = removeConversationLocally(convId);
    try {
      await refreshConversationSidebar();
      convList = LexaState.get("conversationsList") || convList;
    } catch (e) {
      console.warn("[Chat] Deleted conversation but failed to refresh sidebar:", e.message || e);
      showToast(t("toast.deleteRefreshFailed"), "warning", 3000);
    }
    if (wasActive) {
      if (convList.length > 0) await switchConversation(convList[0].id);
      else await newConversation();
    }
    showToast(t("toast.chatDeleted"), "info", 2000);
  } catch (e) {
    console.warn("[Chat] Deleted conversation but failed to finish local cleanup:", e.message || e);
    showToast(t("toast.loadError"), "warning", 3000);
  }
  finally {
    if (triggerBtn?.isConnected) {
      triggerBtn.disabled = false;
      triggerBtn.removeAttribute("aria-busy");
    }
  }
}
async function autoTitleConversation(userMessage) {
  const convId = LexaState.get("currentConversationId");
  if (!convId) return;
  let title = String(userMessage || "").trim();
  if (title.length > 40) title = title.substring(0, 40) + "\u2026";
  if (!title) title = t("chat.newChatTitle");
  try {
    await window.lexa.conversationUpdate(convId, { title });
    updateConversationTitleLocally(convId, title);
  } catch (e) {
    console.warn("[Chat] Failed to set conversation title:", e.message || e);
  }
  try {
    const result = await window.lexa.generateTitle(userMessage);
    const generatedTitle = String(result?.title || "").trim();
    if (generatedTitle && generatedTitle !== title) {
      title = generatedTitle;
      await window.lexa.conversationUpdate(convId, { title });
      updateConversationTitleLocally(convId, title);
    }
  } catch (e) {
    console.warn("[Chat] Failed to generate AI title:", e.message || e);
  }
}

// ── DRAG & DROP + FILE UPLOAD ────────────────────
let dragCounter = 0;
function setupDragDrop() {
  const chatContainer = document.getElementById("chat-container");
  const overlay = document.getElementById("drop-zone-overlay");
  if (!chatContainer || !overlay) return;
  const fileInput = document.getElementById("file-input");
  const attachBtn = document.getElementById("attach-btn");
  if (fileInput) fileInput.addEventListener("change", handleFileSelect);
  if (attachBtn) attachBtn.addEventListener("click", triggerFileUpload);
  chatContainer.addEventListener("dragenter", (e) => { e.preventDefault(); dragCounter++; overlay.classList.add("visible"); });
  chatContainer.addEventListener("dragleave", (e) => { e.preventDefault(); dragCounter--; if (dragCounter <= 0) { dragCounter = 0; overlay.classList.remove("visible"); } });
  chatContainer.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  chatContainer.addEventListener("drop", (e) => { e.preventDefault(); dragCounter = 0; overlay.classList.remove("visible"); const files = e.dataTransfer.files; if (files.length > 0) handleFileUpload(files[0]); });
}
function triggerFileUpload() { document.getElementById("file-input")?.click(); }
function handleFileSelect(event) { const file = event.target.files?.[0]; if (file) handleFileUpload(file); event.target.value = ""; }

function buildFileUploadCard(file) {
  const ext = fileUploadExtension(file);
  const card = document.createElement("div");
  card.className = "file-card";

  const icon = document.createElement("div");
  icon.className = "file-card-icon";
  icon.textContent = getFileIcon(ext);

  const info = document.createElement("div");
  info.className = "file-card-info";

  const name = document.createElement("div");
  name.className = "file-card-name";
  name.textContent = file.name;

  const meta = document.createElement("div");
  meta.className = "file-card-meta";
  meta.textContent = `${ext} · ${fileUploadSizeLabel(file)}`;

  info.appendChild(name);
  info.appendChild(meta);
  card.appendChild(icon);
  card.appendChild(info);
  return card;
}

function addFileUploadMessage(file, userMsg) {
  addMessage(userMsg || "", "user");
  const messages = chatMessages.querySelectorAll(".message.user-message");
  const msg = messages[messages.length - 1];
  const textEl = msg?.querySelector(".msg-text");
  if (!textEl) return;
  const card = buildFileUploadCard(file);
  if (textEl.firstChild) {
    textEl.insertBefore(document.createElement("br"), textEl.firstChild);
  }
  textEl.insertBefore(card, textEl.firstChild);
}

function buildFileInfoBadge(fileInfo) {
  const badge = document.createElement("div");
  badge.className = "file-info-badge";
  badge.textContent = fileInfoBadgeText(fileInfo);
  return badge;
}

function addFileUploadResponse(res) {
  addMessage(fileUploadDisplayReply(res), "system", null, false);
  if (!res.file_info) return;
  const messages = chatMessages.querySelectorAll(".message.system-message");
  const msg = messages[messages.length - 1];
  const textEl = msg?.querySelector(".msg-text");
  if (!textEl) return;
  const badge = buildFileInfoBadge(res.file_info);
  if (textEl.firstChild) {
    textEl.insertBefore(document.createElement("br"), textEl.firstChild);
  }
  textEl.insertBefore(badge, textEl.firstChild);
}

async function handleFileUpload(file) {
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const maxSize = 2 * 1024 * 1024;
  if (file.size > maxSize) { showToast(t("toast.fileTooLarge"), "error"); return; }
  if (!LexaState.get("currentConversationId")) {
    try {
      const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
      LexaState.set("currentConversationId", result.id);
      localStorage.setItem("lexa-active-conversation", result.id);
      await refreshConversationSidebar();
    } catch (e) {
      console.warn("[Chat] Failed to create conversation for file upload:", e.message || e);
      showToast(t("toast.createError"), "error");
      return;
    }
  }
  const userMsg = chatInput.value.trim();
  addFileUploadMessage(file, userMsg);
  chatInput.value = ""; syncChatInputSize();
  const isFirst = chatMessages.querySelectorAll(".user-message").length <= 1;
  if (isFirst) autoTitleConversation(file.name);
  LexaState.set("isLoading", true); sendBtn.disabled = true; showTyping();
  try {
    const res = await window.lexa.chatFile(file, userMsg || "");
    hideTyping();
    if (res.detail) { addMessage(res.detail, "system"); showToast(t("toast.fileError"), "error"); }
    else {
      addFileUploadResponse(res);
      if (res.action) handleChatToolActionBlocked(res.action, { source: "file-upload" });
      playTTS(fileUploadDisplayReply(res));
    }
  } catch (err) { hideTyping(); addMessage(t("chat.uploadErrorMsg", {error: err.message}), "system"); showToast(t("toast.uploadError"), "error"); }
  saveChatHistory(); saveCurrentConversation(); LexaState.set("isLoading", false); sendBtn.disabled = false;
}
function getFileIcon(ext) {
  const icons = { PY: "\u{1F40D}", JS: "\u{1F7E8}", TS: "\u{1F535}", HTML: "\u{1F310}", CSS: "\u{1F3A8}", JSON: "\u{1F4CB}", MD: "\u{1F4DD}", TXT: "\u{1F4C4}", CSV: "\u{1F4CA}", LOG: "\u{1F4DC}", PDF: "\u{1F4D5}", PNG: "\u{1F5BC}", JPG: "\u{1F5BC}", JPEG: "\u{1F5BC}", GIF: "\u{1F5BC}", SVG: "\u{1F5BC}", SQL: "\u{1F5C3}", XML: "\u{1F4C3}", YAML: "\u2699", YML: "\u2699" };
  return icons[ext] || "\u{1F4CE}";
}

// ── GLOBAL SEARCH OVERLAY ────────────────────────
let searchDebounce = null;
let searchRestoreFocusEl = null;
function restoreSearchFocus() {
  const el = searchRestoreFocusEl;
  searchRestoreFocusEl = null;
  if (!el || !el.isConnected || typeof el.focus !== "function") return;
  try { el.focus({ preventScroll: true }); }
  catch (_) { try { el.focus(); } catch (_) {} }
}
function searchFocusableElements(root) {
  return [...root.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )].filter(el => !el.disabled && !el.hidden && el.getClientRects().length > 0);
}
function trapSearchFocus(root, event) {
  const items = searchFocusableElements(root);
  if (!items.length) {
    event.preventDefault();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
function openSearchOverlay() {
  let overlay = document.getElementById("search-overlay");
  if (!overlay) {
    overlay = document.createElement("div"); overlay.id = "search-overlay"; overlay.className = "search-overlay";
    overlay.innerHTML = `<div class="search-panel" role="dialog" aria-modal="true" aria-label="${escapeHtml(t("nav.searchTooltip"))}"><div class="search-header"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input type="text" id="search-input" class="search-input" placeholder="${escapeHtml(t("chat.searchPlaceholder"))}" aria-label="${escapeHtml(t("chat.searchPlaceholder"))}" autocomplete="off"><button type="button" class="search-close-btn" id="search-close-btn" aria-label="${escapeHtml(t("common.close"))}">\u00d7</button></div><div id="search-results" class="search-results"><div class="search-empty">${escapeHtml(t("chat.searchHint"))}</div></div></div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeSearchOverlay(); });
    document.getElementById("search-close-btn").addEventListener("click", closeSearchOverlay);
    document.getElementById("search-input").addEventListener("input", (e) => { clearTimeout(searchDebounce); searchDebounce = setTimeout(() => performSearch(e.target.value.trim()), 300); });
    document.getElementById("search-input").addEventListener("keydown", (e) => { if (e.key === "Escape") closeSearchOverlay(); });
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeSearchOverlay();
      if (e.key === "Tab") trapSearchFocus(overlay, e);
    });
  }
  const active = document.activeElement;
  if (active && active !== document.body && !overlay.contains(active)) {
    searchRestoreFocusEl = active;
  }
  overlay.classList.add("visible");
  const input = document.getElementById("search-input"); input.value = ""; input.focus();
  renderSearchEmpty(document.getElementById("search-results"), t("chat.searchHint"));
}
function closeSearchOverlay(options = {}) {
  document.getElementById("search-overlay")?.classList.remove("visible");
  if (options.restoreFocus !== false) restoreSearchFocus();
  else searchRestoreFocusEl = null;
}
async function performSearch(query) {
  const container = document.getElementById("search-results");
  if (!container) return;
  if (!query) { renderSearchEmpty(container, t("chat.searchHint")); return; }
  if (query.length < 2) { renderSearchEmpty(container, t("chat.searchMinChars")); return; }
  try {
    const data = await window.lexa.search(query);
    container.innerHTML = "";
    const buildSearchItem = (icon, title, meta, action) => {
      const item = document.createElement("div");
      item.className = "search-item";
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");
      item.setAttribute("aria-label", `${title}. ${meta || ""}`.trim());
      const iconEl = document.createElement("span");
      iconEl.className = "search-item-icon";
      iconEl.textContent = icon;
      const info = document.createElement("div");
      info.className = "search-item-info";
      const titleEl = document.createElement("div");
      titleEl.className = "search-item-title";
      appendHighlightedText(titleEl, String(title || ""), query);
      const metaEl = document.createElement("div");
      metaEl.className = "search-item-meta";
      metaEl.textContent = meta || "";
      info.appendChild(titleEl);
      info.appendChild(metaEl);
      item.appendChild(iconEl);
      item.appendChild(info);
      const runAction = () => { closeSearchOverlay({ restoreFocus: false }); action(); };
      item.addEventListener("click", runAction);
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          runAction();
        }
      });
      return item;
    };
    if (data.conversations?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryChats"); container.appendChild(catEl); for (const c of data.conversations) container.appendChild(buildSearchItem("\u{1F4AC}", c.title, `${t("chat.messageCount", {count: c.message_count || 0})} \u00b7 ${String(c.updated_at || "").substring(0, 16)}`, () => switchConversation(c.id))); }
    if (data.notes?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryNotes"); container.appendChild(catEl); for (const n of data.notes) container.appendChild(buildSearchItem("\u{1F4DD}", n.title, `${n.category || ""} \u00b7 ${String(n.created_at || "").substring(0, 10)}`, () => switchView("memory"))); }
    if (data.memories?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryMemories"); container.appendChild(catEl); for (const m of data.memories) { const preview = String(m.content || "").substring(0, 80) + (String(m.content || "").length > 80 ? "\u2026" : ""); container.appendChild(buildSearchItem("\u{1F9E0}", preview, `${m.category || ""} \u00b7 ${t("chat.importance", {value: parseInt(m.importance) || 0})}`, () => switchView("memory"))); } }
    let total = (data.conversations?.length || 0) + (data.notes?.length || 0) + (data.memories?.length || 0);

    // FTS deep search — adds additional results from full-text index
    try {
      const fts = await window.lexa.ftsSearch(query);
      if (fts && fts.total > 0) {
        // Collect existing note/memory IDs to avoid duplicates
        const existingNoteIds = new Set((data.notes || []).map(n => n.id));
        const existingMemoryIds = new Set((data.memories || []).map(m => m.id));

        const ftsNotes = (fts.notes || []).filter(n => !existingNoteIds.has(n.id));
        const ftsMemories = (fts.memories || []).filter(m => !existingMemoryIds.has(m.id));

        if (ftsNotes.length > 0) {
          const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryFtsNotes"); container.appendChild(catEl);
          for (const n of ftsNotes) {
            const snippet = String(n.snippet || n.title || "").substring(0, 100);
            container.appendChild(buildSearchItem("\u{1F50D}", snippet, `FTS \u00b7 ${n.category || ""} \u00b7 ${String(n.created_at || "").substring(0, 10)}`, () => switchView("memory")));
          }
          total += ftsNotes.length;
        }

        if (ftsMemories.length > 0) {
          const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryFtsMemories"); container.appendChild(catEl);
          for (const m of ftsMemories) {
            const snippet = String(m.snippet || m.content || "").substring(0, 100);
            container.appendChild(buildSearchItem("\u{1F50E}", snippet, `FTS \u00b7 ${m.category || ""} \u00b7 ${t("chat.importance", {value: parseInt(m.importance) || 0})}`, () => switchView("memory")));
          }
          total += ftsMemories.length;
        }
      }
    } catch (e) { console.warn("[Chat] FTS search not available:", e.message || e); }

    if (total === 0) renderSearchEmpty(container, t("chat.searchNoResults"));
    else { const countEl = document.createElement("div"); countEl.className = "search-count"; countEl.textContent = t("chat.searchResults", {count: total}); container.prepend(countEl); }
  } catch (e) { console.error("[Chat] Search failed:", e.message || e); renderSearchEmpty(container, t("chat.searchError")); }
}

function renderSearchEmpty(container, message) {
  if (!container) return;
  container.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "search-empty";
  empty.textContent = message || "";
  container.appendChild(empty);
}

function appendHighlightedText(target, text, query) {
  const source = String(text || "");
  const needle = String(query || "");
  if (!needle) {
    target.textContent = source;
    return;
  }
  const lowerSource = source.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  let index = 0;
  let matchAt = lowerSource.indexOf(lowerNeedle, index);
  while (matchAt !== -1) {
    if (matchAt > index) target.appendChild(document.createTextNode(source.slice(index, matchAt)));
    const mark = document.createElement("mark");
    mark.textContent = source.slice(matchAt, matchAt + needle.length);
    target.appendChild(mark);
    index = matchAt + needle.length;
    matchAt = lowerSource.indexOf(lowerNeedle, index);
  }
  if (index < source.length) target.appendChild(document.createTextNode(source.slice(index)));
}

// ── CONVERSATION EXPORT ──────────────────────────
async function exportConversation(convId, fmt = "markdown") {
  try {
    const cId = convId || LexaState.get("currentConversationId");
    const data = await window.lexa.conversationExport(cId, fmt);
    if (!data.text) { showToast(t("toast.exportFailed"), "error"); return; }
    const ext = fmt === "markdown" ? "md" : "txt";
    const blob = new Blob([data.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `lexa-chat-${cId}.${ext}`; a.click();
    URL.revokeObjectURL(url);
    showToast(t("chat.exported", {format: ext.toUpperCase()}), "success");
  } catch (e) { console.warn("[Chat] Export failed:", e.message || e); showToast(t("toast.exportError"), "error"); }
}
