/*
 * Chat agent-run metadata, attention sidebars, and completion panels.
 */

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

function agentRunStateGetItem(key) {
  return chatTransientGetItem(key);
}

function agentRunStateSetItem(key, value) {
  chatTransientSetItem(key, value);
}

function agentRunStateRemoveItem(key) {
  chatTransientRemoveItem(key);
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
    const parsed = JSON.parse(agentRunStateGetItem(agentRunAttentionResolvedCacheKey(convId)) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
  } catch (_e) {
    return new Set();
  }
}

function saveAgentRunAttentionResolvedKeys(convId, keys) {
  const list = Array.from(keys || []).map(String).filter(Boolean);
  try {
    if (list.length) agentRunStateSetItem(agentRunAttentionResolvedCacheKey(convId), JSON.stringify(list));
    else agentRunStateRemoveItem(agentRunAttentionResolvedCacheKey(convId));
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
    records = JSON.parse(agentRunStateGetItem(agentRunMetaCacheKey(item.convId)) || "[]");
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
    if (list.length) agentRunStateSetItem(agentRunAttentionResolvedHistoryCacheKey(), JSON.stringify(list));
    else agentRunStateRemoveItem(agentRunAttentionResolvedHistoryCacheKey());
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
    const parsed = JSON.parse(agentRunStateGetItem(agentRunAttentionResolvedHistoryCacheKey()) || "[]");
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
    if (records.length) agentRunStateSetItem(agentRunMetaCacheKey(convId), JSON.stringify(records));
    else agentRunStateRemoveItem(agentRunMetaCacheKey(convId));
  } catch (e) {
    console.warn("[Chat] Failed to save Agent run metadata:", e.message || e);
  }
}

function clearAgentRunLocalStateForConversation(convId) {
  if (!convId) return;
  agentRunStateRemoveItem(agentRunMetaCacheKey(convId));
  agentRunStateRemoveItem(agentRunAttentionResolvedCacheKey(convId));
  saveAgentRunAttentionResolvedHistory(agentRunAttentionResolvedHistory().filter((item) => String(item.convId) !== String(convId)));
}

// Conversation list mutation helpers live in chat_conversations.js.

function createAgentRunMetaResolver(convId) {
  let records = [];
  try {
    records = JSON.parse(agentRunStateGetItem(agentRunMetaCacheKey(convId)) || "[]");
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
    records = JSON.parse(agentRunStateGetItem(agentRunMetaCacheKey(convId)) || "[]");
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

const CHAT_ATTENTION_ICON_NS = "http://www.w3.org/2000/svg";

function createChatAttentionIcon(children, options = {}) {
  const svg = document.createElementNS(CHAT_ATTENTION_ICON_NS, "svg");
  const attrs = {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": options.strokeWidth || "2.4",
    "aria-hidden": "true",
  };
  Object.entries(attrs).forEach(([name, value]) => svg.setAttribute(name, value));
  children.forEach((child) => {
    const el = document.createElementNS(CHAT_ATTENTION_ICON_NS, child.tag);
    Object.entries(child.attrs || {}).forEach(([name, value]) => el.setAttribute(name, value));
    svg.appendChild(el);
  });
  return svg;
}

function createAgentAttentionResolveIcon() {
  return createChatAttentionIcon([
    { tag: "path", attrs: { d: "M20 6L9 17l-5-5" } },
  ], { strokeWidth: "2.5" });
}

function createAgentAttentionRestoreIcon() {
  return createChatAttentionIcon([
    { tag: "path", attrs: { d: "M3 12a9 9 0 1 0 3-6.7" } },
    { tag: "path", attrs: { d: "M3 4v6h6" } },
  ]);
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
    resolveBtn.appendChild(createAgentAttentionResolveIcon());
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
    restoreBtn.appendChild(createAgentAttentionRestoreIcon());
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

function clipAgentStepText(value, limit = 64) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, Math.max(0, limit - 1))}...` : text;
}

function compactHermesDesktopMessage(value) {
  const actionStart = "(?:/?hermes|klick|kilck|klcik|click|tippe|tipp|schreibe|schreib|finde|find|suche|such|zeige|pruefe|prufe|lies|lese|was|drueck|druecke|druck|drucke|drücke|drück|hotkey|scroll|scrolle|warte|wait)";
  let text = String(value || "").replace(/\r\n/g, "\n").replace(/\s+/g, " ").trim();
  text = text.replace(/^\s*\/?hermes[:,\s-]*/i, "");
  text = text.replace(new RegExp(`\\b(?:ja|yes|ok|okay)\\b[,\\s-]+(?=${actionStart}\\b)`, "gi"), "");
  const splitRe = new RegExp(`\\s*(?:[.;!?]\\s+(?=(?:${actionStart}|ja|yes|ok|okay)\\b)|\\bund\\s+dann\\s+|\\bdanach\\s+|\\bthen\\s+)`, "i");
  const first = String(text.split(splitRe)[0] || text).replace(/^\s*\/?hermes[:,\s-]*/i, "").trim();
  return clipAgentStepText(first || value, 54);
}

function agentStepText(key, fallback) {
  const translated = t(key);
  return translated && translated !== key ? translated : fallback;
}

function agentStepParamSummary(params, action = "") {
  if (!params || typeof params !== "object") return "";
  if (String(action || "") === "hermes_desktop_task" && params.message) {
    return compactHermesDesktopMessage(params.message);
  }
  const preferredKeys = ["window", "window_title", "text", "target", "url", "query", "title", "message", "prompt", "path", "file_path", "dir_path", "name", "command"];
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
  const first = Object.values(params).find((value) => ["string", "number"].includes(typeof value));
  return first === undefined ? "" : clipAgentStepText(first, 54);
}

function agentStepActionLabel(action) {
  const name = String(action || "").trim();
  if (!name) return t("chat.agentStepUnknown");
  const commandKey = `cmd.desc.${name}`;
  const commandLabel = t(commandKey);
  if (commandLabel && commandLabel !== commandKey) return commandLabel;
  if (name === "desktop_engine_status") return agentStepText("chat.agentStepDesktopStatus", "Desktop-Engine prüfen");
  if (name === "desktop_engine_observe") return agentStepText("chat.agentStepDesktopObserve", "Desktop beobachten");
  if (name === "screen_read_text" || name === "screen_ocr") return agentStepText("chat.agentStepScreenRead", "Bildschirmtext lesen");
  if (name === "ui_tree") return agentStepText("chat.agentStepUiTree", "Fenster analysieren");
  if (name === "ui_find") return agentStepText("chat.agentStepUiFind", "UI-Element suchen");
  if (name === "hermes_desktop_task") return agentStepText("chat.agentStepHermesDesktop", "Desktop-Aktion vorbereiten");
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
  const detail = agentStepParamSummary(step?.params, step?.action);
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
    action.includes("_observe") ||
    action === "screen_ocr" ||
    action === "ui_tree" ||
    action === "ui_find" ||
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
  setChatDraft(prompt);
  chatInput.focus();
  setTimeout(() => chatInput.focus(), 0);
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
