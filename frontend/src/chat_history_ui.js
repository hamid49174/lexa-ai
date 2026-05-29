/*
 * Conversation history UI helpers for classic renderer scripts.
 * Backend load/save/delete orchestration stays in chat.js.
 */

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

  actions.appendChild(exportBtn);
  actions.appendChild(delBtn);
  item.appendChild(content);
  item.appendChild(actions);

  bindKeyboardAction(item, () => switchConversation(conversation.id), {
    label: t("chat.openConversationLabel", { title: accessibleTitle, count }) + (attention ? `. ${attentionStatus}` : ""),
  });

  return item;
}
