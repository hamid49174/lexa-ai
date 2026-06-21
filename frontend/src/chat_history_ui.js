/*
 * Conversation history UI helpers for classic renderer scripts.
 * Backend load/save/delete orchestration stays in chat.js.
 */

// ── Datums-Gruppierung der Konversationsliste (Top-Tier wie ChatGPT/Claude/Gemini) ──
// Pinned bleibt eine eigene Gruppe oben; der Rest wird nach updated_at gebucketet.
// Pure + testbar (nowMs injizierbar).
function _parseConvDate(value) {
  const s = String(value || "").trim();
  if (!s) return null;
  // Backend liefert "YYYY-MM-DD HH:MM:SS" (localtime) -> ISO-tauglich machen.
  const d = new Date(s.indexOf("T") === -1 ? s.replace(" ", "T") : s);
  return isNaN(d.getTime()) ? null : d;
}

function chatHistoryBucket(updatedAt, nowMs) {
  const d = _parseConvDate(updatedAt);
  if (!d) return "older";
  const now = new Date(nowMs);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayMs = 86400000;
  const ts = d.getTime();
  if (ts >= startOfToday) return "today";
  if (ts >= startOfToday - dayMs) return "yesterday";
  if (ts >= startOfToday - 7 * dayMs) return "week";
  if (ts >= startOfToday - 30 * dayMs) return "month";
  return "older";
}

function groupConversationsByDate(conversations, nowMs) {
  const pinned = [];
  const buckets = { today: [], yesterday: [], week: [], month: [], older: [] };
  for (const c of (conversations || [])) {
    if (c && c.is_pinned) { pinned.push(c); continue; }
    buckets[chatHistoryBucket(c && c.updated_at, nowMs)].push(c);
  }
  const groups = [];
  if (pinned.length) groups.push({ key: "pinned", items: pinned });
  for (const k of ["today", "yesterday", "week", "month", "older"]) {
    if (buckets[k].length) groups.push({ key: k, items: buckets[k] });
  }
  return groups;
}

function conversationGroupLabel(key) {
  const fallback = {
    pinned: "Angepinnt", today: "Heute", yesterday: "Gestern",
    week: "Letzte 7 Tage", month: "Letzte 30 Tage", older: "Älter",
  };
  return typeof t === "function" ? t("history.group." + key) : (fallback[key] || key);
}

if (typeof window !== "undefined") {
  window.chatHistoryBucket = chatHistoryBucket;
  window.groupConversationsByDate = groupConversationsByDate;
}

function conversationListRawTitle(conversation) {
  const title = String((conversation && conversation.title) || "").trim();
  return title || t("chat.newChatTitle");
}

function conversationListLooksTechnicalAgentTitle(title) {
  const text = String(title || "").trim().toLowerCase();
  if (!text) return true;
  return (
    /\bagent\s+(run|attention|task)\b/.test(text) ||
    /\b(blocked|reloaded|clean)\s+agent\b/.test(text) ||
    /\bneeds\s+confirmation\b/.test(text)
  );
}

function conversationListAttentionTitle(conversation) {
  const title = conversationListRawTitle(conversation);
  return conversationListLooksTechnicalAgentTitle(title)
    ? t("chat.agentAttentionFallbackTitle")
    : title;
}

function conversationListDisplayTitle(conversation, options = {}) {
  const title = options.attention
    ? conversationListAttentionTitle(conversation)
    : conversationListRawTitle(conversation);
  return title.length > 28 ? title.substring(0, 28) + "\u2026" : title;
}

function conversationListAttentionStatusText(attention) {
  const failed = Math.max(0, Number(attention?.failed || 0));
  const blocked = Math.max(0, Number(attention?.blocked || 0));
  if (failed > 0 && blocked > 0) return t("chat.agentAttentionStatusBoth", { failed, blocked });
  if (failed > 0) return t("chat.agentAttentionStatusReview", { count: failed });
  if (blocked > 0) return t("chat.agentAttentionStatusApproval", { count: blocked });
  return t("chat.agentAttentionStatusClear");
}

function conversationListSafePreviewText(text) {
  const preview = String(text || "").trim();
  if (/^(needs\s+confirmation|agent\s+run|blocked\s+agent|reloaded\s+agent|agent\s+attention)\b/i.test(preview)) {
    return t("chat.agentAttentionPreviewNeedsReview");
  }
  return preview;
}

function conversationListPreviewText(conversation) {
  const preview = conversationListSafePreviewText((conversation && conversation.last_message) || "");
  return preview.substring(0, 50) + (preview.length > 50 ? "\u2026" : "");
}

function renderConversationEmptyState(container, message) {
  if (!container) return;
  const empty = document.createElement("div");
  empty.className = "conv-empty";
  empty.setAttribute("role", "status");
  empty.setAttribute("aria-live", "polite");
  empty.textContent = message || "";
  container.replaceChildren(empty);
}

const CONVERSATION_ICON_NS = "http://www.w3.org/2000/svg";

function createConversationSvgIcon(children, options = {}) {
  const svg = document.createElementNS(CONVERSATION_ICON_NS, "svg");
  const attrs = {
    width: options.size || "11",
    height: options.size || "11",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": options.strokeWidth || "2",
    "aria-hidden": "true",
  };
  Object.entries(attrs).forEach(([name, value]) => svg.setAttribute(name, value));
  children.forEach((child) => {
    const el = document.createElementNS(CONVERSATION_ICON_NS, child.tag);
    Object.entries(child.attrs || {}).forEach(([name, value]) => el.setAttribute(name, value));
    svg.appendChild(el);
  });
  return svg;
}

function createConversationExportIcon() {
  return createConversationSvgIcon([
    { tag: "path", attrs: { d: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" } },
    { tag: "polyline", attrs: { points: "7 10 12 15 17 10" } },
    { tag: "line", attrs: { x1: "12", y1: "15", x2: "12", y2: "3" } },
  ]);
}

function createConversationResolveIcon() {
  return createConversationSvgIcon([
    { tag: "path", attrs: { d: "M20 6L9 17l-5-5" } },
  ], { strokeWidth: "2.4" });
}

function createConversationListItem(conversation, options = {}) {
  const attention = options.attention || null;
  const isActive = Boolean(options.isActive);
  const rawTitle = conversationListRawTitle(conversation);
  const accessibleTitle = attention ? conversationListAttentionTitle(conversation) : rawTitle;
  const title = conversationListDisplayTitle(conversation, { attention: Boolean(attention) });
  const count = conversation.message_count || 0;
  const attentionStatus = attention ? conversationListAttentionStatusText(attention) : "";

  const item = document.createElement("div");
  item.className = "conv-item" + (isActive ? " active" : "") + (attention ? " needs-agent-attention" : "");
  item.dataset.convId = conversation.id;
  item.title = accessibleTitle;
  item.setAttribute("aria-current", isActive ? "page" : "false");

  const content = document.createElement("div");
  content.className = "conv-item-content";

  const titleEl = document.createElement("div");
  titleEl.className = "conv-title";
  titleEl.textContent = title;
  titleEl.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    startRenameConversation(conversation, titleEl);
  });
  content.appendChild(titleEl);

  if (conversation.last_message) {
    const preview = document.createElement("div");
    preview.className = "conv-preview";
    preview.textContent = conversationListPreviewText(conversation);
    content.appendChild(preview);
  }

  const meta = document.createElement("div");
  meta.className = "conv-meta";
  meta.textContent = t("chat.messageCount", {count});
  if (attention) {
    const badge = document.createElement("span");
    badge.className = "conv-agent-attention-badge";
    badge.textContent = attentionStatus;
    meta.appendChild(badge);
  }
  content.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "conv-actions";

  const pinned = Boolean(conversation.is_pinned);
  if (pinned) item.classList.add("pinned");
  const pinBtn = document.createElement("button");
  pinBtn.type = "button";
  pinBtn.className = "conv-action-btn conv-pin-btn" + (pinned ? " pinned" : "");
  pinBtn.title = pinned ? "Loslösen" : "Anpinnen";
  pinBtn.setAttribute("aria-label", pinned ? "Konversation loslösen" : "Konversation anpinnen");
  pinBtn.textContent = "📌";
  pinBtn.addEventListener("click", (e) => { e.stopPropagation(); togglePinConversation(conversation, pinBtn); });

  const renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.className = "conv-action-btn conv-rename-btn";
  renameBtn.title = "Umbenennen";
  renameBtn.setAttribute("aria-label", "Konversation umbenennen");
  renameBtn.textContent = "✎";
  renameBtn.addEventListener("click", (e) => { e.stopPropagation(); startRenameConversation(conversation, titleEl); });

  const exportBtn = document.createElement("button");
  exportBtn.type = "button";
  exportBtn.className = "conv-action-btn";
  exportBtn.title = t("chat.export");
  exportBtn.setAttribute("aria-label", t("chat.exportConversationLabel", { title: accessibleTitle }));
  exportBtn.appendChild(createConversationExportIcon());
  exportBtn.addEventListener("click", (e) => { e.stopPropagation(); exportConversation(conversation.id); });

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "conv-delete-btn";
  delBtn.title = t("common.delete");
  delBtn.setAttribute("aria-label", t("chat.deleteConversationLabel", { title: accessibleTitle }));
  delBtn.textContent = "\u00d7";
  delBtn.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(conversation.id, delBtn); });

  if (attention) {
    const resolveBtn = document.createElement("button");
    resolveBtn.type = "button";
    resolveBtn.className = "conv-action-btn conv-agent-resolve-btn";
    resolveBtn.title = t("chat.agentAttentionResolveLabel", { title: accessibleTitle });
    resolveBtn.setAttribute("aria-label", t("chat.agentAttentionResolveLabel", { title: accessibleTitle }));
    resolveBtn.appendChild(createConversationResolveIcon());
    resolveBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      resolveAgentAttentionForConversation(conversation.id, conversation.title);
    });
    actions.appendChild(resolveBtn);
  }

  actions.appendChild(pinBtn);
  actions.appendChild(renameBtn);
  actions.appendChild(exportBtn);
  actions.appendChild(delBtn);
  item.appendChild(content);
  item.appendChild(actions);

  bindKeyboardAction(item, () => switchConversation(conversation.id), {
    label: t("chat.openConversationLabel", { title: accessibleTitle, count }) + (attention ? `. ${attentionStatus}` : ""),
  });
  // Korrekte Listen-Semantik: Container ist role="list" -> Items als listitem
  // markieren (ueberschreibt das von bindKeyboardAction gesetzte role="button";
  // tabindex + Enter/Space-Handler bleiben erhalten, Aktivierung funktioniert weiter).
  item.setAttribute("role", "listitem");

  return item;
}

// Inline-Umbenennen einer Konversation (Doppelklick auf Titel oder ✎-Button).
function startRenameConversation(conversation, titleEl) {
  if (!titleEl || titleEl.parentElement?.querySelector(".conv-rename-input")) return;
  const current = conversationListRawTitle(conversation);
  const input = document.createElement("input");
  input.type = "text";
  input.className = "conv-rename-input";
  input.value = current;
  input.maxLength = 120;
  input.setAttribute("aria-label", t("chat.renameConversationLabel") || "Konversation umbenennen");
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  let done = false;
  const finish = async (commit) => {
    if (done) return;
    done = true;
    const next = input.value.trim();
    if (input.parentElement) input.replaceWith(titleEl);
    if (!commit || !next || next === current) return;
    titleEl.textContent = next;
    try {
      await window.lexa.conversationUpdate(conversation.id, { title: next });
      if (typeof updateConversationTitleLocally === "function") {
        updateConversationTitleLocally(conversation.id, next);
      }
      conversation.title = next;
      showToast(t("toast.conversationRenamed") || "Konversation umbenannt", "success", 2000);
    } catch (e) {
      console.warn("[Chat] Rename failed:", e.message || e);
      titleEl.textContent = current;
      showToast(t("toast.conversationSaveFailed") || "Umbenennen fehlgeschlagen", "warning", 3000);
    }
  };

  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    else if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (e) => e.stopPropagation());
}

// Konversation an-/abpinnen (gepinnte sortieren oben).
async function togglePinConversation(conversation, btn) {
  const next = !conversation.is_pinned;
  if (btn) btn.disabled = true;
  try {
    await window.lexa.conversationUpdate(conversation.id, { is_pinned: next });
    conversation.is_pinned = next ? 1 : 0;
    if (typeof refreshConversationSidebar === "function") {
      await refreshConversationSidebar();
    } else if (typeof renderConversationList === "function") {
      renderConversationList();
    }
  } catch (e) {
    console.warn("[Chat] Pin toggle failed:", e.message || e);
    showToast(t("toast.conversationSaveFailed") || "Anpinnen fehlgeschlagen", "warning", 2500);
    if (btn) btn.disabled = false;
  }
}
