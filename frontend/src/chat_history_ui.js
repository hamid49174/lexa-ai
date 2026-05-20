/*
 * Conversation history UI helpers for classic renderer scripts.
 * Backend load/save/delete orchestration stays in chat.js.
 */

function conversationListDisplayTitle(conversation) {
  return conversation.title.length > 28 ? conversation.title.substring(0, 28) + "\u2026" : conversation.title;
}

function conversationListPreviewText(conversation) {
  return conversation.last_message.substring(0, 50) + (conversation.last_message.length > 50 ? "\u2026" : "");
}

function renderConversationEmptyState(container, message) {
  if (!container) return;
  container.innerHTML = '<div class="conv-empty">' + escapeHtml(message) + '</div>';
}

function createConversationListItem(conversation, options = {}) {
  const attention = options.attention || null;
  const isActive = Boolean(options.isActive);
  const title = conversationListDisplayTitle(conversation);
  const count = conversation.message_count || 0;

  const item = document.createElement("div");
  item.className = "conv-item" + (isActive ? " active" : "") + (attention ? " needs-agent-attention" : "");
  item.dataset.convId = conversation.id;
  item.title = conversation.title;
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
    badge.textContent = t("chat.agentAttentionShortCounts", { failed: attention.failed, blocked: attention.blocked });
    meta.appendChild(badge);
  }
  content.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "conv-actions";

  const exportBtn = document.createElement("button");
  exportBtn.type = "button";
  exportBtn.className = "conv-action-btn";
  exportBtn.title = t("chat.export");
  exportBtn.setAttribute("aria-label", t("chat.exportConversationLabel", { title: conversation.title }));
  exportBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
  exportBtn.addEventListener("click", (e) => { e.stopPropagation(); exportConversation(conversation.id); });

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "conv-delete-btn";
  delBtn.title = t("common.delete");
  delBtn.setAttribute("aria-label", t("chat.deleteConversationLabel", { title: conversation.title }));
  delBtn.textContent = "\u00d7";
  delBtn.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(conversation.id, delBtn); });

  if (attention) {
    const resolveBtn = document.createElement("button");
    resolveBtn.type = "button";
    resolveBtn.className = "conv-action-btn conv-agent-resolve-btn";
    resolveBtn.title = t("chat.agentAttentionResolveLabel", { title: conversation.title });
    resolveBtn.setAttribute("aria-label", t("chat.agentAttentionResolveLabel", { title: conversation.title }));
    resolveBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>';
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
    label: t("chat.openConversationLabel", { title: conversation.title, count }) + (attention ? `. ${t("chat.agentAttentionCounts", { failed: attention.failed, blocked: attention.blocked })}` : ""),
  });

  return item;
}
