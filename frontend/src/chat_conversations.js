/*
 * Chat conversation lifecycle, sidebar rendering, and local list mutation.
 */

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

async function loadConversations() {
  try {
    await refreshConversationSidebar();

    // We explicitly do NOT auto-switch to an old conversation here
    // so the app remains in its beautiful, clean zero-state.
    LexaState.set("currentConversationId", null);
    clearChatActiveConversationId();
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
    clearChatActiveConversationId();
  } else {
    chatSetActiveConversationId(activeConversationValue);
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
  container.replaceChildren();
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
    cancelScheduledConversationSave();
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
    chatSetActiveConversationId(result.id);
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
// Nicht-destruktives Bearbeiten: Konversation bis zur bearbeiteten Nachricht (exklusiv)
// in einen neuen Chat forken; das Original bleibt vollstaendig erhalten.
async function forkConversationForEdit(allMsgs, idx, editText) {
  if (!LexaState.get("backendOnline")) return false;
  const priorMessages = collectPersistableMessages(allMsgs.slice(0, idx));
  try {
    const created = await window.lexa.conversationCreate(t("chat.newChatTitle"));
    if (!created?.id) return false;
    if (priorMessages.length) {
      await window.lexa.conversationUpdate(created.id, { messages: priorMessages });
    }
    const ok = await switchConversation(created.id, false);
    if (!ok) return false;
    if (typeof chatInput !== "undefined" && chatInput) {
      chatInput.value = editText;
      if (typeof syncChatInputSize === "function") syncChatInputSize();
      chatInput.focus();
    }
    showToast("Bearbeitung in neuem Chat — Original bleibt erhalten", "info", 2800);
    return true;
  } catch (e) {
    console.warn("[Chat] edit-fork failed:", e.message || e);
    return false;
  }
}

async function switchConversation(convId, notify = true) {
  // Already on this conversation: avoid an unnecessary reload (and the
  // associated backend roundtrips / full DOM rebuild) regardless of the
  // notify flag. notify only governs user-facing toasts, not load avoidance.
  if (convId === LexaState.get("currentConversationId")) return true;
  const switchSeq = ++_conversationSwitchSeq;
  _conversationSwitchInFlight += 1;
  try {
    const previousConvId = LexaState.get("currentConversationId");
    const previousActiveConversation = chatGetActiveConversationId();
    cancelScheduledConversationSave();
    await saveCurrentConversation({ notifyFailure: notify });
    if (switchSeq !== _conversationSwitchSeq) return false;
    LexaState.set("currentConversationId", convId);
    chatSetActiveConversationId(convId);
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
// Alle Speicherungen laufen durch diese Promise-Kette -> strikt serialisiert.
// Verhindert das fruehere Last-Write-Wins (zwei parallele conversationUpdate-PUTs
// konnten sich gegenseitig ueberschreiben -> Datenverlust). Awaiten liefert,
// wenn DIESE Speicherung (und alle davor) durch sind. Sidebar-Refresh wurde
// entfernt (lief pro Save -> Flackern); new/switch/delete refreshen selbst.
let _convSaveChain = Promise.resolve();

function saveCurrentConversation(options = null) {
  const opts = options || {};
  _convSaveChain = _convSaveChain
    .then(() => _performConversationSave(opts))
    .catch((e) => {
      console.warn("[Chat] conversation save chain error:", e?.message || e);
      return false;
    });
  return _convSaveChain;
}

async function _performConversationSave(opts) {
  const convId = LexaState.get("currentConversationId");
  if (!convId) return true;
  saveAgentRunMetaForConversation(convId);
  const messages = collectPersistableMessages();
  // Niemals leer ueberschreiben (z.B. waehrend eines DOM-Clears) -> Wipe-Schutz.
  // Leeren erledigt clearChat() explizit ueber conversationUpdate(messages: []).
  if (!messages.length) return true;
  try {
    await window.lexa.conversationUpdate(convId, { messages });
  } catch (e) {
    console.warn("[Chat] Failed to save conversation:", e.message || e);
    if (opts.notifyFailure) showToast(t("toast.conversationSaveFailed"), "warning", 3500);
    return false;
  }
  return true;
}
async function deleteConversation(convId, triggerBtn = null) {
  if (triggerBtn?.disabled || triggerBtn?.getAttribute("aria-busy") === "true") return;
  const restoreTrigger = () => {
    if (triggerBtn?.isConnected) {
      triggerBtn.disabled = false;
      triggerBtn.removeAttribute("aria-busy");
    }
  };
  if (triggerBtn) {
    triggerBtn.disabled = true;
    triggerBtn.setAttribute("aria-busy", "true");
  }
  // Bestätigung vor dem destruktiven Löschen (kein Auto-Fokus auf "Löschen" ->
  // kein versehentliches Bestätigen via Enter). Abbruch lässt alles unverändert.
  if (typeof showInputModal === "function") {
    const conv = (LexaState.get("conversationsList") || []).find((c) => String(c.id) === String(convId));
    const convTitle = ((conv && conv.title) || "").trim() || t("chat.newChatTitle");
    const confirmed = await showInputModal(t("chat.deleteConfirm", { title: convTitle }), [], t("common.delete"));
    if (!confirmed) { restoreTrigger(); return; }
  }
  try {
    await window.lexa.conversationDelete(convId);
  } catch (e) {
    console.warn("[Chat] Failed to delete conversation:", e.message || e);
    showToast(t("toast.deleteError"), "error");
    restoreTrigger();
    return;
  }
  try {
    const wasActive = String(convId) === String(LexaState.get("currentConversationId")) || String(convId) === String(chatGetActiveConversationId());
    clearAgentRunLocalStateForConversation(convId);
    if (wasActive) {
      LexaState.set("currentConversationId", null);
      clearChatActiveConversationId();
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
      // switchConversation/newConversation swallow their own errors and signal
      // failure via a falsy return value (they do not throw), so the outer
      // catch never sees them. Inspect the result and fall back to a clean
      // zero-state with a clear hint instead of leaving an empty, unclear chat.
      const followUpOk = convList.length > 0
        ? await switchConversation(convList[0].id)
        : await newConversation();
      if (!followUpOk) {
        // Follow-up switch/create failed: fall back to a clean zero-state
        // (hero greeting) instead of leaving an empty, unexplained chat.
        LexaState.set("currentConversationId", null);
        clearChatActiveConversationId();
        chatMessages.querySelectorAll(".message").forEach((m) => m.remove());
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
        renderConversationList();
        showToast(t("toast.loadError"), "warning", 3000);
        return;
      }
    }
    showToast(t("toast.chatDeleted"), "info", 2000);
  } catch (e) {
    console.warn("[Chat] Deleted conversation but failed to finish local cleanup:", e.message || e);
    showToast(t("toast.loadError"), "warning", 3000);
  }
  finally {
    restoreTrigger();
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
