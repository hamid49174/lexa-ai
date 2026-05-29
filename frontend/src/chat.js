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

// Chat persistence/state helpers live in chat_state.js.

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

// Agent run metadata and attention helpers live in chat_agent_runs.js.

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
    chatTransientSetItem(CHAT_HISTORY_CACHE_KEY, JSON.stringify(toSave));
  } catch (e) { console.warn("[Chat] Failed to save chat history to volatile cache:", e.message || e); }
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
  const convId = LexaState.get("currentConversationId") || chatGetActiveConversationId();
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
    } catch (e) { console.warn("[Chat] Failed to load conversation from backend, falling back to volatile cache:", e.message || e); }
  }
  // Fallback: load from volatile session cache only.
  try {
    const messages = chatCachedHistorySnapshot();
    if (!Array.isArray(messages)) return;
    clearRenderedChatMessages();
    renderPersistedConversationMessages(messages, convId);
    if (convId) saveAgentRunMetaForConversation(convId);
  } catch (e) { console.warn("[Chat] Failed to load chat history from volatile cache:", e.message || e); }
}

// ── CHAT MESSAGE DISPLAY ─────────────────────────
function clearChat() {
  const msgs = chatMessages.querySelectorAll(".message");
  msgs.forEach((m) => m.remove());
  chatTransientRemoveItem(CHAT_HISTORY_CACHE_KEY);
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

// Agent step rendering and completion panel helpers live in chat_agent_runs.js.

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
  scrollChatMessageIntoCleanView(msg, { preferStartForLong: !isUser });
  trimChatMessages();
  if (!silent) saveChatHistory();
}

function renderFormattedMessage(target, text) {
  if (!target) return;
  target.replaceChildren();
  appendFormattedMessage(target, String(text || ""));
}

function scrollChatMessageIntoCleanView(messageEl, options = {}) {
  const container = messageEl?.closest?.(".chat-messages") || chatMessages;
  if (!container) return;
  const preferStartForLong = Boolean(options.preferStartForLong);
  const messageHeight = Number(messageEl?.offsetHeight || 0);
  const viewHeight = Number(container.clientHeight || 0);
  if (preferStartForLong && messageHeight > 0 && viewHeight > 0 && messageHeight > viewHeight * 0.82) {
    container.scrollTop = Math.max(0, Number(messageEl.offsetTop || 0) - 18);
    return;
  }
  container.scrollTop = container.scrollHeight;
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
function escapeSuggestionRegex(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function chatSuggestionHasWord(text, word) {
  const escaped = escapeSuggestionRegex(String(word || "").toLowerCase());
  if (!escaped) return false;
  return new RegExp("(^|[^\\p{L}\\p{N}_])" + escaped + "(?=$|[^\\p{L}\\p{N}_])", "iu")
    .test(String(text || "").toLowerCase());
}

function chatSuggestionHasAnyWord(text, words) {
  return (words || []).some((word) => chatSuggestionHasWord(text, word));
}

function generateSuggestions(responseText, userQuestion) {
  const suggestions = [];
  const lower = responseText.toLowerCase();
  const hasAny = (words) => chatSuggestionHasAnyWord(lower, words);

  // ── Topic-specific follow-ups (prioritized) ──
  // Music context
  if (hasAny(["spotify", "musik", "song", "playlist"])) {
    suggestions.push(t("chat.suggNextSong"), t("chat.suggQuieter"), t("chat.suggPause"));
  }
  // Todo/task context
  if (hasAny(["todo", "todos", "aufgabe", "aufgaben", "erledigt"])) {
    if (hasAny(["erledigt", "abgehakt"])) {
      suggestions.push(t("chat.suggWhatsLeft"), t("chat.suggNewTodo"));
    } else {
      suggestions.push(t("chat.suggShowTodos"), t("chat.suggNewTodo"));
    }
  }
  // Notes context
  if (hasAny(["notiz", "notizen", "note", "notes"])) {
    suggestions.push(t("chat.suggShowNotes"));
  }
  // System/performance context
  if (hasAny(["prozess", "prozesse", "ram", "cpu", "speicher"])) {
    if (lower.includes("85%") || lower.includes("90%") || lower.includes("95%") || lower.includes("hoch")) {
      suggestions.push(t("chat.suggShowMemHogs"), t("chat.suggKillProcess"));
    } else {
      suggestions.push(t("chat.suggProcessList"), t("chat.suggDiskAnalysis"));
    }
  }
  // Screenshot context
  if (hasAny(["screenshot"])) {
    suggestions.push(t("chat.suggScreenshotAgain"), t("chat.suggScreenshotPdf"));
  }
  // Timer/Pomodoro context
  if (hasAny(["timer", "pomodoro"])) {
    if (hasAny(["fertig", "abgelaufen"])) {
      suggestions.push(t("chat.suggNewTimer5"), t("chat.suggStartPomodoro"));
    } else {
      suggestions.push(t("chat.suggTimerStatus"), t("chat.suggStopPomodoro"));
    }
  }
  // File context
  if (hasAny(["datei", "dateien", "ordner", "file", "files", "download", "downloads"])) {
    suggestions.push(t("chat.suggCleanDownloads"), t("chat.suggFindDuplicates"));
  }
  // Git/Dev context
  if (hasAny(["git", "commit", "branch"])) {
    suggestions.push(t("chat.suggGitStatus"), t("chat.suggGitLog"));
  }
  // Email context
  if (hasAny(["email", "emails", "mail", "mails", "nachricht", "nachrichten"])) {
    suggestions.push(t("chat.suggCheckEmails"));
  }
  // Error/problem context — offer debugging help
  if (hasAny(["fehler", "error", "problem"]) || lower.includes("funktioniert nicht")) {
    suggestions.push(t("chat.suggRetry"), t("chat.suggSysteminfo"));
  }
  // Explanation context — offer deeper dive
  if (hasAny(["bedeutet", "erklaert", "verstehe"])) {
    suggestions.push(t("chat.suggMoreDetails"), t("chat.suggShowExample"));
  }

  // Deduplicate and limit
  return [...new Set(suggestions)].slice(0, 3);
}

// ── DRAFT RECOVERY ────────────────────────────────
function recoverDraft() {
  const draft = getChatDraft();
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
  const hermesManual = _isHermesWorkerCommand(text);
  const agentText = agentManual ? text.slice(7).trim() : _stripHermesWorkerPrefix(text);
  const agentWorker = hermesManual ? "hermes" : "lexa";
  if (agentManual || hermesManual || _needsAgentMode(text)) {
    if (agentText) {
      sendAgentMessage(agentText, { displayText: text, worker: agentWorker });
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
      chatSetActiveConversationId(result.id);
      const data = await window.lexa.conversations();
      LexaState.set("conversationsList", data.conversations || []);
      renderConversationList();
    } catch (e) { console.warn("[Chat] Failed to create conversation:", e.message || e); }
  }

  const isFirstMessage = chatMessages.querySelectorAll(".user-message").length === 0;
  // Typed messages always open chat view so user sees the response
  if (!window._chatViewOpen) toggleChatView();
  addMessage(text, "user");

  clearChatDraft();
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
    scrollChatMessageIntoCleanView(msgEl, { preferStartForLong: true });
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

function _normalizeGermanSearchText(text) {
  return String(text || "")
    .replace(/[\u00e4\u00c4]/g, "ae")
    .replace(/[\u00f6\u00d6]/g, "oe")
    .replace(/[\u00fc\u00dc]/g, "ue")
    .replace(/[\u00df\u1e9e]/g, "ss")
    .replace(/[\u0414\u0434]/g, "ae")
    .replace(/[\u0416\u0436]/g, "oe")
    .replace(/[\u042d\u044d]/g, "ue")
    .replace(/\u044a/g, "ss")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function _needsAgentMode(text) {
  if (!text || text.length < 15) return false;
  const lower = _normalizeGermanSearchText(text);
  return _AGENT_PATTERNS.some(p => p.test(lower));
}

function _normalizeAgentCommandText(text) {
  return _normalizeGermanSearchText(text);
}

function _isHermesWorkerCommand(text) {
  const lower = _normalizeAgentCommandText(text);
  return /^\/hermes\s+/.test(lower) ||
    /^hermes\b/.test(lower) ||
    /^(?:lass|lasse|beauftrag|beauftrage|starte|nutze|nimm)\s+hermes\b/.test(lower) ||
    /^lexa[\s,]+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes\b/.test(lower);
}

function _stripHermesWorkerPrefix(text) {
  const raw = String(text || "").trim();
  if (/^\/hermes\s+/i.test(raw)) return raw.replace(/^\/hermes\s+/i, "").trim();
  if (/^hermes\b[\s:,-]*/i.test(raw)) return raw.replace(/^hermes\b[\s:,-]*/i, "").trim();
  if (/^(?:lass|lasse|beauftrag|beauftrage|starte|nutze|nimm)\s+hermes\b[\s:,-]*/i.test(raw)) {
    return raw.replace(/^(?:lass|lasse|beauftrag|beauftrage|starte|nutze|nimm)\s+hermes\b[\s:,-]*/i, "").trim();
  }
  if (/^lexa[\s,]+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes\b[\s:,-]*/i.test(raw)) {
    return raw.replace(/^lexa[\s,]+(?:sag|sage|sagt|lass|lasse|beauftrag|beauftrage|gib)\s+hermes\b[\s:,-]*/i, "").trim();
  }
  return raw;
}

function _isHermesSystemStatusRequest(text) {
  const lower = _normalizeAgentCommandText(text);
  const systemTerms = [
    "systemstatus", "system status", "system-info", "system info",
    "pc status", "pc-status", "status vom system",
  ];
  const metricTerms = [
    "cpu", "ram", "arbeitsspeicher", "speicherplatz", "speicher",
    "disk", "platte", "festplatte", "auslastung",
  ];
  return systemTerms.some((term) => lower.includes(term))
    || metricTerms.filter((term) => lower.includes(term)).length >= 2;
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

function normalizeAgentStreamChunk(value) {
  if (!value) return value;
  if (value instanceof Uint8Array) return value;
  if (Array.isArray(value)) return new Uint8Array(value);
  if (value?.type === "Buffer" && Array.isArray(value.data)) return new Uint8Array(value.data);
  return value;
}

function createAgentStreamReader(response) {
  if (response?.body && typeof response.body.getReader === "function") {
    return response.body.getReader();
  }
  if (response?.streamId && typeof window.lexa?.agentStreamRead === "function") {
    const streamId = response.streamId;
    return {
      read: async () => {
        const result = await window.lexa.agentStreamRead(streamId);
        return {
          done: Boolean(result?.done),
          value: normalizeAgentStreamChunk(result?.value),
        };
      },
      cancel: async () => {
        if (typeof window.lexa?.agentStreamCancel === "function") {
          await window.lexa.agentStreamCancel(streamId);
        }
      },
    };
  }
  throw new Error("agent_stream_unavailable");
}

async function cancelAgentResponse(response) {
  if (response?.streamId && typeof window.lexa?.agentStreamCancel === "function") {
    await window.lexa.agentStreamCancel(response.streamId);
    return;
  }
  if (response?.body && typeof response.body.cancel === "function") {
    await response.body.cancel();
  }
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
      chatSetActiveConversationId(result.id);
      const data = await window.lexa.conversations();
      LexaState.set("conversationsList", data.conversations || []);
      renderConversationList();
    } catch (e) { console.warn("[Agent] Failed to create conversation:", e.message || e); }
  }

  const isFirstMessage = chatMessages.querySelectorAll(".user-message").length === 0;
  if (!window._chatViewOpen) toggleChatView();
  addMessage(displayText, "user");

  clearChatDraft();
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
  const hermesSystemStatusGuard = options?.worker === "hermes"
    && _isHermesSystemStatusRequest(`${displayText} ${agentText}`);

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
    const response = await window.lexa.agentRun(agentText, { worker: options?.worker || "lexa" });
    if (agentStoppedByUser) {
      try { await cancelAgentResponse(response); } catch (e) { console.warn("[Agent] Body cancel failed:", e.message || e); }
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

    agentReader = createAgentStreamReader(response);
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
      buffer += decoder.decode(normalizeAgentStreamChunk(value), { stream: true });
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
            let finalSteps = Array.isArray(run.steps) ? run.steps : [];
            let finalSummary = run.summary || "";
            if (hermesSystemStatusGuard && finalSteps.length === 0) {
              finalSummary = t("chat.hermesSystemStatusNoTool");
              finalSteps = [{
                index: 0,
                action: "system_info",
                status: "failed",
                error: finalSummary,
                result: finalSummary,
              }];
            }
            const finalOutcomeCounts = finalSteps.length
              ? agentRunOutcomeCounts(finalSteps)
              : agentOutcomeCounts;
            renderAgentOutcomeSummary(outcomeSummaryEl, finalOutcomeCounts);
            setMessageAgentRunMeta(msgEl, {
              summary: finalSummary || t("chat.agentCompleted"),
              steps: finalSteps,
              counts: finalOutcomeCounts,
              total_duration_ms: run.total_duration_ms,
            });
            renderAgentCompletionPanel(completionEl, finalOutcomeCounts, {
              continuePrompt: agentCompletionContinuePrompt({ ...run, steps: finalSteps, summary: finalSummary }, finalOutcomeCounts, finalSummary || summaryEl.textContent),
            });
            if (finalSummary) {
              summaryEl.classList.remove("agent-status");
              renderFormattedMessage(summaryEl, finalSummary);
              setMessagePersistText(msgEl, finalSummary);
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
            durEl.textContent = t("chat.agentSteps", {count: finalSteps.length, ms: Math.round(run.total_duration_ms || 0)});
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
window.ctrlEnterMode = lexaStorageGet("lexa-ctrl-enter") === "true";
function applySendModeToggle(enabled) {
  window.ctrlEnterMode = !!enabled;
  lexaStorageSet("lexa-ctrl-enter", enabled ? "true" : "false");
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

// Composer command palette and starter cards live in chat_composer_palette.js.

// Performance helpers.
function trimChatMessages() {
  const msgs = chatMessages.querySelectorAll(".message");
  if (msgs.length > LexaConfig.MAX_DOM_MESSAGES) {
    const toRemove = msgs.length - LexaConfig.MAX_DOM_MESSAGES;
    for (let i = 0; i < toRemove; i++) msgs[i].remove();
  }
}

// Conversation lifecycle and sidebar flow live in chat_conversations.js.

// Drag/drop and file-upload flow lives in chat_file_upload.js.

// Global search and conversation export live in chat_search.js.
