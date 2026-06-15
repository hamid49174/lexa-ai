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

// ── Web sources (ChatGPT-style citation chips) ───────────────────────────────
// Sources live in the message dataset (persistText stays clean, so copy/verify/
// export are unaffected). On save they are embedded as a fenced ```lexa-sources
// block; on restore addMessage extracts them back into the dataset + component.
const LEXA_SOURCES_FENCE_RE = /\n*```lexa-sources\s*\n([\s\S]*?)\n```\s*$/;

function getMessageSources(msg) {
  const raw = msg?.dataset?.lexaSources;
  if (!raw) return [];
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v : []; }
  catch (e) { return []; }
}

function setMessageSources(msg, sources) {
  if (!msg) return;
  const list = Array.isArray(sources) ? sources.filter((s) => s && s.url) : [];
  if (list.length) msg.dataset.lexaSources = JSON.stringify(list.map((s) => ({ title: s.title || "", url: s.url, snippet: s.snippet || "" })));
  else delete msg.dataset.lexaSources;
}

function encodeSourcesBlock(sources) {
  const list = Array.isArray(sources) ? sources.filter((s) => s && s.url) : [];
  if (!list.length) return "";
  const slim = list.map((s) => ({ title: s.title || "", url: s.url, snippet: s.snippet || "" }));
  return "\n\n```lexa-sources\n" + JSON.stringify(slim) + "\n```";
}

function extractSourcesBlock(text) {
  const str = String(text || "");
  const m = str.match(LEXA_SOURCES_FENCE_RE);
  if (!m) return { text: str, sources: [] };
  try {
    const v = JSON.parse(m[1]);
    const sources = Array.isArray(v) ? v.filter((s) => s && s.url) : [];
    return { text: str.slice(0, m.index).replace(/\s+$/, ""), sources };
  } catch (e) {
    return { text: str, sources: [] };
  }
}

// Used by the save paths so the durable store carries the sources, while the
// in-DOM persistText stays clean for copy/verify/continue/workspace.
function serializeMessageForStorage(msg) {
  return getMessagePersistText(msg) + encodeSourcesBlock(getMessageSources(msg));
}

// Einzige Quelle der Wahrheit fuer {role, content}-Serialisierung aus dem DOM
// (inkl. Quellen-Fence). Optionales msgEls fuer Teilmengen (z.B. Edit-Fork).
function collectPersistableMessages(msgEls) {
  const list = msgEls || (chatMessages ? Array.from(chatMessages.querySelectorAll(".message")) : []);
  const messages = [];
  for (const msg of list) {
    if (!isPersistableChatMessage(msg)) continue;
    const text = getMessagePersistText(msg);
    if (!text) continue;
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    messages.push({ role, content: serializeMessageForStorage(msg) });
  }
  return messages;
}

function sourceDomain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch (e) { return ""; }
}

function sourceFaviconUrl(url) {
  const d = sourceDomain(url);
  return d ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(d)}&sz=64` : "";
}

function appendSourceFavicon(parent, src, cls) {
  const dom = sourceDomain(src.url);
  const initial = (dom[0] || "?").toUpperCase();
  const url = sourceFaviconUrl(src.url);
  if (url) {
    const img = document.createElement("img");
    img.className = cls;
    img.src = url;
    img.alt = "";
    img.loading = "lazy";
    img.addEventListener("error", () => {
      const fb = document.createElement("span");
      fb.className = `${cls} src-favicon-fallback`;
      fb.textContent = initial;
      img.replaceWith(fb);
    });
    parent.appendChild(img);
  } else {
    const fb = document.createElement("span");
    fb.className = `${cls} src-favicon-fallback`;
    fb.textContent = initial;
    parent.appendChild(fb);
  }
}

// Build the collapsible ChatGPT-style sources widget and append it to a .msg-body.
function renderChatSources(bodyEl, sources) {
  if (!bodyEl) return;
  bodyEl.querySelector(".chat-sources")?.remove();
  const list = Array.isArray(sources) ? sources.filter((s) => s && s.url) : [];
  if (!list.length) return;

  const wrap = document.createElement("div");
  wrap.className = "chat-sources";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "chat-sources-toggle";
  toggle.setAttribute("aria-haspopup", "dialog");

  const favRow = document.createElement("span");
  favRow.className = "chat-sources-favicons";
  list.slice(0, 4).forEach((s) => appendSourceFavicon(favRow, s, "src-favicon"));

  const label = document.createElement("span");
  label.className = "chat-sources-label";
  label.textContent = "Quellen";

  const count = document.createElement("span");
  count.className = "chat-sources-count";
  count.textContent = String(list.length);

  const chevron = document.createElement("span");
  chevron.className = "chat-sources-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "›";

  toggle.append(favRow, label, count, chevron);
  toggle.addEventListener("click", () => openSourcesPanel(list));

  wrap.appendChild(toggle);
  bodyEl.appendChild(wrap);
}

// ── ChatGPT-style right-side sources panel ───────────────────────────────────
let _sourcesPanelKeyHandler = null;

function ensureSourcesPanel() {
  let overlay = document.getElementById("lexa-sources-overlay");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "lexa-sources-overlay";
  overlay.className = "sources-overlay";
  overlay.hidden = true;

  const panel = document.createElement("aside");
  panel.className = "sources-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Quellen");

  const head = document.createElement("div");
  head.className = "sources-panel-head";
  const title = document.createElement("span");
  title.className = "sources-panel-title";
  title.textContent = "Quellen";
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "sources-panel-close";
  closeBtn.setAttribute("aria-label", "Schliessen");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", closeSourcesPanel);
  head.append(title, closeBtn);

  const listEl = document.createElement("div");
  listEl.className = "sources-panel-list";

  panel.append(head, listEl);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeSourcesPanel(); });
  document.body.appendChild(overlay);
  return overlay;
}

function closeSourcesPanel() {
  const overlay = document.getElementById("lexa-sources-overlay");
  if (!overlay) return;
  overlay.classList.remove("open");
  setTimeout(() => { if (!overlay.classList.contains("open")) overlay.hidden = true; }, 240);
  if (_sourcesPanelKeyHandler) {
    document.removeEventListener("keydown", _sourcesPanelKeyHandler);
    _sourcesPanelKeyHandler = null;
  }
}

function openSourcesPanel(sources) {
  const list = Array.isArray(sources) ? sources.filter((s) => s && s.url) : [];
  if (!list.length) return;
  const overlay = ensureSourcesPanel();
  const titleEl = overlay.querySelector(".sources-panel-title");
  if (titleEl) titleEl.textContent = `Quellen · ${list.length}`;

  const listEl = overlay.querySelector(".sources-panel-list");
  listEl.replaceChildren();
  list.forEach((s, i) => {
    const card = document.createElement("a");
    card.className = "sources-panel-card";
    card.href = s.url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";

    const top = document.createElement("div");
    top.className = "sources-panel-card-top";
    appendSourceFavicon(top, s, "src-favicon");
    const dom = document.createElement("span");
    dom.className = "sources-panel-domain";
    dom.textContent = sourceDomain(s.url);
    const idx = document.createElement("span");
    idx.className = "sources-panel-index";
    idx.textContent = String(i + 1);
    top.append(dom, idx);

    const title = document.createElement("div");
    title.className = "sources-panel-card-title";
    title.textContent = (s.title || sourceDomain(s.url) || s.url).trim();

    card.append(top, title);

    const snip = String(s.snippet || "").trim();
    if (snip) {
      const snippet = document.createElement("div");
      snippet.className = "sources-panel-snippet";
      snippet.textContent = snip;
      card.appendChild(snippet);
    }
    listEl.appendChild(card);
  });

  overlay.hidden = false;
  void overlay.offsetWidth; // reflow so the slide-in transition runs
  overlay.classList.add("open");

  _sourcesPanelKeyHandler = (e) => { if (e.key === "Escape") closeSourcesPanel(); };
  document.addEventListener("keydown", _sourcesPanelKeyHandler);
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
      const stored = serializeMessageForStorage(msg);
      messages.push(meta ? { text: stored, type, meta } : { text: stored, type });
    }
  });
  const toSave = messages.slice(-(LexaConfig.CHAT_HISTORY_LOCAL_MAX));
  try {
    chatTransientSetItem(CHAT_HISTORY_CACHE_KEY, JSON.stringify(toSave));
  } catch (e) { console.warn("[Chat] Failed to save chat history to volatile cache:", e.message || e); }
}

// Debounced Konversations-Speicherung: bündelt häufige Auslöser (Stream-Ende,
// DOM-Mutationen) zu EINER Speicherung statt vieler PUTs. Geht durch die
// serialisierte saveCurrentConversation-Kette (kein Last-Write-Wins).
let _convSaveTimer = null;
function scheduleConversationSave(delay = 1200) {
  if (_convSaveTimer) clearTimeout(_convSaveTimer);
  _convSaveTimer = setTimeout(() => {
    _convSaveTimer = null;
    if (typeof saveCurrentConversation === "function") saveCurrentConversation();
  }, delay);
}

// Pendenten Debounce-Save verwerfen (vor Switch/New/Clear), damit er nicht in
// die falsche Konversation feuert.
function cancelScheduledConversationSave() {
  if (_convSaveTimer) { clearTimeout(_convSaveTimer); _convSaveTimer = null; }
}

function persistChatAfterDomMutation() {
  saveChatHistory();
  scheduleConversationSave();
}

function clearRenderedChatMessages() {
  if (!chatMessages) return;
  chatMessages.querySelectorAll(".message").forEach((msg) => msg.remove());
}

// ── AUTO-SAVE CONVERSATION (Intervall-Sicherheitsnetz) ────────────────────────
// Delegiert an die serialisierte Save-Kette statt eines eigenen, parallelen PUT.
async function autoSaveConversation() {
  if (_conversationSwitchInFlight > 0) return;
  if (!LexaState.get("currentConversationId") || !LexaState.get("backendOnline")) return;
  return saveCurrentConversation();
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
  // Pendenten Auto-Save verwerfen, damit er nicht NACH dem Leeren die alten
  // Nachrichten zurueckschreibt (DOM ist gleich leer -> Wipe-Schutz greift ohnehin).
  cancelScheduledConversationSave();
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

// Note: `requiresConfirmation` is kept as a positional placeholder for call-site
// compatibility (callers pass `silent`/`options` by position); the confirmation
// flow was removed and the value is intentionally unused here.
function addMessage(text, type = "system", action = null, requiresConfirmation = false, silent = false, options = {}) {
  // Restored messages may carry an embedded ```lexa-sources block — split it off
  // so persistText/render stay clean and the sources render as the chips widget.
  const _parsedSources = extractSourcesBlock(text);
  const _msgSources = _parsedSources.sources;
  text = _parsedSources.text;
  const sleekGreeting = document.getElementById("sleek-greeting");
  if (sleekGreeting && !sleekGreeting.classList.contains("hidden")) sleekGreeting.classList.add("hidden");
  // Orb stays visible — don't hide voice-orb-container
  const floatingCards = document.getElementById("floating-cards-container");
  if (floatingCards && !floatingCards.classList.contains("hidden")) floatingCards.classList.add("hidden");
  // Chat messages stay hidden in ambient mode — only revealed by arrow key
  // (chat-messages visibility is managed by toggleChatView)

  const msg = document.createElement("div");
  msg.className = `message ${type}-message`;
  setMessagePersistText(msg, text);
  setMessageSources(msg, _msgSources);
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

    // Regenerate visible in the bar (ChatGPT-style); only for non-restored messages.
    if (!silent) {
      const regenBtn = document.createElement("button");
      regenBtn.type = "button";
      regenBtn.className = "msg-action-btn msg-regen-btn";
      setIconButton(regenBtn, "\u21BB", t("chat.regenerateTooltip"));
      regenBtn.addEventListener("click", () => startRegenerateMessage(regenBtn, msg));
      header.appendChild(regenBtn);
    }
    header.appendChild(createVerifyAnswerButton());
    header.appendChild(createMessageExportButton());
    header.appendChild(createMessageActionOverflowMenu([
      createContinueFromMessageButton(),
      createWorkspaceHandoffButton(),
      thumbsBtn,
    ]));
  }

  if (isUser && !silent) {
    // Edit button for user messages
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "msg-action-btn msg-edit-btn";
    setIconButton(editBtn, "\u270E", t("chat.editTooltip"));
    editBtn.addEventListener("click", async () => {
      const currentText = getMessagePersistText(msg);
      const allMsgs = Array.from(chatMessages.querySelectorAll(".message"));
      const idx = allMsgs.indexOf(msg);
      const hasFollowing = idx >= 0 && allMsgs.slice(idx + 1).some(isPersistableChatMessage);
      // Nicht-destruktiv: gibt es Nachrichten DANACH, wird in einen neuen Chat geforkt
      // (Original bleibt vollstaendig erhalten). Letzte Nachricht -> in-place (kein Verlust).
      if (hasFollowing && typeof forkConversationForEdit === "function") {
        const forked = await forkConversationForEdit(allMsgs, idx, currentText);
        if (forked) return;
      }
      chatInput.value = currentText;
      syncChatInputSize();
      chatInput.focus();
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
  if (_msgSources.length) renderChatSources(body, _msgSources);

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

function renderChatMath(target) {
  // KaTeX: $...$, $$...$$, \(...\), \[...\] in den bereits gerenderten Knoten aufloesen.
  // Code/Pre werden ignoriert (kein $ im Code zu Mathe machen).
  if (!target || typeof window.renderMathInElement !== "function") return;
  try {
    window.renderMathInElement(target, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
      ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"],
    });
  } catch (e) { /* Mathe-Render fehlgeschlagen -> roher Text bleibt erhalten */ }
}

function renderFormattedMessage(target, text, options) {
  if (!target) return;
  options = options || {};
  target.replaceChildren();
  appendFormattedMessage(target, String(text || ""));
  if (options.math !== false && typeof renderChatMath === "function") renderChatMath(target);
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

function isChatNearBottom(container, threshold = 140) {
  // True, wenn der Nutzer (fast) am unteren Ende ist — Basis fuer Scroll-Lock.
  if (!container) return true;
  return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
}

function renderStreamingFormatted(target, text) {
  // Live-Markdown waehrend des Streams: voller, sicherer DOM-Render + Cursor.
  // try/catch faengt unvollstaendiges Markdown (offene ```-Codeblocks) waehrend des Tippens ab.
  if (!target) return;
  if (typeof setStreamingRenderMode === "function") setStreamingRenderMode(true);
  try {
    renderFormattedMessage(target, text, { math: false });
  } catch (e) {
    target.textContent = String(text || "");
  } finally {
    if (typeof setStreamingRenderMode === "function") setStreamingRenderMode(false);
  }
  const cursor = document.createElement("span");
  cursor.className = "streaming-cursor";
  target.appendChild(cursor);
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
  try {
    fetch(`${window.lexa.API_BASE}/chat/confirm-clear`, { method: "POST", credentials: "include" })
      .catch((e) => console.warn("[Chat] Failed to clear pending confirmation:", e?.message || e));
  } catch (e) { console.warn("[Chat] Failed to clear pending confirmation:", e?.message || e); }
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

function chatSuggestionNormalizedText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss");
}

function chatSuggestionSearchText(value) {
  return chatSuggestionNormalizedText(value)
    .replace(/[^\p{L}\p{N}_]+/gu, " ")
    .trim();
}

function chatSuggestionHasWord(text, word) {
  const escaped = escapeSuggestionRegex(chatSuggestionSearchText(word)).replace(/\s+/g, "\\s+");
  if (!escaped) return false;
  return new RegExp("(^|\\s)" + escaped + "(?=$|\\s)", "iu")
    .test(chatSuggestionSearchText(text));
}

function chatSuggestionHasAnyWord(text, words) {
  return (words || []).some((word) => chatSuggestionHasWord(text, word));
}

function chatSuggestionShouldStayQuietForExactOutput(userQuestion) {
  const query = chatSuggestionNormalizedText(userQuestion);
  return /\b(beende|endet|ende)\b.*\b(exakt|genau)\b/.test(query)
    || /\b(exakt|genau)\b.*\b(beende|endet|ende)\b/.test(query)
    || /\b(beginnt|starte|start)\b.*\bendet\b/.test(query)
    || /\bmarkdown[-\s]?format\b.*\b(codeblock|code block|tabelle)\b/.test(query);
}

function generateSuggestions(responseText, userQuestion) {
  if (chatSuggestionShouldStayQuietForExactOutput(userQuestion)) return [];

  const suggestions = [];
  const lower = chatSuggestionNormalizedText(responseText);
  const questionLower = chatSuggestionNormalizedText(userQuestion);
  const topicText = `${lower}\n${questionLower}`;
  const hasAny = (words) => chatSuggestionHasAnyWord(lower, words);
  const hasAnyTopic = (words) => chatSuggestionHasAnyWord(topicText, words);
  const hasLexaImprovementAction = hasAnyTopic([
    "verbesser", "verbessere", "verbessern", "verbesserung",
    "verbesserungen", "verbessert",
    "improve", "improvement", "improvements", "improved",
    "upgrade", "polish", "optimize", "optimise", "optimieren",
    "optimierung", "ausbau", "ausbauen", "weiterentwickeln",
    "weiterentwicklung", "weiterentwickle", "weiterentwickelt",
  ]);

  // ── Topic-specific follow-ups (prioritized) ──
  // Lexa/product improvement context
  if (
    hasAnyTopic(["lexa", "assistant", "assistent"]) &&
    hasLexaImprovementAction &&
    hasAnyTopic([
      "verbessern", "verbesserung", "verbesserungen", "verbessert",
      "feature", "features", "feture", "futere", "futeres",
      "ausbau", "ausbauen",
      "weiterentwickeln", "weiterentwicklung", "weiterentwickle",
      "weiterentwickelt",
      "funktion", "funktionen", "intelligenz", "intelligen", "intilegnz",
      "antwortqualitaet", "answer quality", "memory", "gedaechtnis",
      "erinnerung", "erinnerungen", "context", "kontext", "kontextfenster",
      "personalization", "personalisierung", "personalisiert",
      "conversation", "conversation flow", "konversation", "gespraech",
      "gespraechsverlauf", "dialog", "follow up", "followup", "follow ups",
      "followups", "folgenfrage", "folgenfragen", "intent", "intention",
      "intent recognition", "intent erkennung", "reasoning", "schlussfolgern",
      "planung", "priorisierung",
      "automatisierung", "automatiersung",
      "autoamtion", "ux", "zuverlaessigkeit", "reliability", "stability",
      "robust", "robuster", "robustheit", "robustness", "stabil", "stabilitaet",
      "usability", "bedienbarkeit", "performance", "accessibility", "a11y",
      "barrierefreiheit", "zugaenglichkeit", "speed", "schnell", "schneller",
      "geschwindigkeit", "latency", "latenz", "reaktionszeit", "response time",
      "ladezeit", "startzeit",
    ])
  ) {
    suggestions.push(t("chat.suggNextLexaImprovement"), t("chat.suggRunFocusedTests"), t("chat.suggCheckRisks"));
  }
  const hasSourceEvidenceTopic = hasAnyTopic([
    "quelle", "quellen", "sources", "reference", "references", "referenz", "referenzen",
    "citation", "citations", "literatur", "study", "studies", "studie", "studien", "paper", "papers",
    "beleg", "belege", "evidence", "claim", "claims", "aussage", "aussagen",
  ]);
  const hasVerificationActionTopic = hasAnyTopic([
    "unbelegt", "unsupported", "unverified", "verifiziere", "verifiziert", "verifizieren",
    "validate", "validation", "validiere", "validieren", "validiert",
    "verification", "verify", "faktencheck", "fact check",
    "cross check", "gegencheck", "gegenpruefe", "gegenpruefen",
    "plausibilitaet", "plausibilitaetscheck",
    "pruefe", "pruefen", "geprueft", "ueberpruefe", "ueberpruefen",
  ]);
  const hasStrongSourceVerificationTopic = hasAnyTopic([
    "source backed", "source backed brief", "source backed research",
    "unsupported claims", "unverified claims",
    "unbelegte claims", "ungepruefte claims",
    "verify answer", "verify this answer", "verify the answer",
    "verify my answer",
    "fact check answer", "fact check this answer", "fact check my answer",
    "fact-check answer", "fact-check this answer", "fact-check my answer",
    "double check answer", "double check this answer",
    "double check my answer",
    "verify claim", "verify this claim", "check claim", "check this claim",
    "fact check claim", "fact check this claim", "fact-check claim",
    "fact-check this claim", "double check claim",
    "double check this claim",
    "verify statement", "verify this statement", "check statement",
    "check this statement", "fact check statement",
    "fact check this statement", "fact-check statement",
    "fact-check this statement", "double check statement",
    "double check this statement", "verify assertion",
    "verify this assertion", "check assertion", "check this assertion",
    "fact check assertion", "fact check this assertion",
    "fact-check assertion", "fact-check this assertion",
    "double check assertion", "double check this assertion",
    "check answer", "check the answer", "check this answer",
    "check my answer",
    "antwort pruefen", "diese antwort pruefen", "die antwort pruefen",
    "meine antwort pruefen",
    "pruef die antwort", "pruef diese antwort", "pruef meine antwort",
    "pruefe die antwort", "pruefe diese antwort", "pruefe meine antwort",
    "ueberpruef die antwort", "ueberpruef diese antwort",
    "ueberpruef meine antwort", "ueberpruefe die antwort",
    "ueberpruefe diese antwort", "ueberpruefe meine antwort",
    "aussage pruefen", "diese aussage pruefen", "pruef diese aussage",
    "pruefe diese aussage", "behauptung pruefen",
    "diese behauptung pruefen", "pruef diese behauptung",
    "pruefe diese behauptung",
    "faktencheck antwort", "faktencheck diese antwort",
    "faktencheck meine antwort",
    "faktencheck aussage", "faktencheck diese aussage",
    "faktencheck behauptung", "faktencheck diese behauptung",
    "antwort verifizieren", "meine antwort verifizieren",
  ]);
  // Source/verification context
  if ((hasSourceEvidenceTopic && hasVerificationActionTopic) || hasStrongSourceVerificationTopic) {
    suggestions.push(t("chat.suggVerifyAnswer"), t("chat.suggFindSources"), t("chat.suggExtractClaims"));
  }
  const hasDecisionIntentTopic = hasAnyTopic([
    "decision", "decide", "choose", "choice",
    "rank", "ranking",
    "entscheidung", "entscheiden", "wahl", "waehle",
    "prioritaet", "prioritaeten", "priority", "priorities",
    "prioritize", "prioritise", "prioritization", "prioritisation",
    "priorisieren", "priorisierung", "rangfolge",
    "strategy", "strategie", "roadmap", "plan", "plane", "planen", "planung",
    "abwaegung", "abwaegen", "abwaeg",
  ]);
  const hasDecisionStructureTopic = hasAnyTopic([
    "option", "options", "optionen", "alternative", "alternatives", "alternativen",
    "choice", "choices", "wahl", "auswahl",
    "tradeoff", "tradeoffs", "trade off", "trade offs",
    "pros", "cons", "pro", "contra",
    "risiko", "risiken", "risk", "risks",
    "vorteil", "vorteile", "nachteil", "nachteile",
    "reversibilitaet", "reversible", "irreversible",
    "recommendation", "empfehlung", "confidence", "konfidenz",
    "offene fragen", "open questions", "naechste schritte", "next steps",
  ]);
  const hasStrongDecisionTopic = hasAnyTopic([
    "decision brief", "entscheidungsbrief", "deep think", "deepthink",
    "which option is better", "which option should i choose",
    "which option should i pick", "which option should i take",
    "which should i choose", "which should i pick",
    "welche option ist besser", "welche option soll ich waehlen",
    "welche option soll ich nehmen", "welche soll ich waehlen",
    "welche soll ich nehmen",
    "rank these options", "rank the options", "rank these choices",
    "prioritize these options", "prioritise these options",
    "score these options", "rate these options",
    "evaluate these options", "evaluate the options",
    "weighted decision matrix",
    "bewerte diese optionen", "bewerte die optionen",
    "bewertungsmatrix", "entscheidungsmatrix",
    "scoring matrix", "scoring tabelle",
    "priorisiere diese optionen", "priorisiere die optionen",
    "ordne die optionen", "mach eine rangfolge",
    "help me decide", "hilf mir entscheiden", "hilf mir bei der entscheidung",
    "make the call", "triff die entscheidung", "triff eine entscheidung",
    "entscheide fuer mich", "entscheid fuer mich",
    "extended thinking", "strategy review", "strategie review", "roadmap review",
  ]);
  const hasDecisionAskTopic = hasAnyTopic([
    "soll ich", "was soll ich", "should i", "which should i",
    "welche soll ich", "welchen soll ich", "welches soll ich",
  ]);
  const hasDecisionBetterTopic = hasAnyTopic([
    "was ist besser", "welche ist besser", "welcher ist besser", "welches ist besser",
    "which is better", "which one is better", "what is better",
    "besser fuer", "better for", "empfiehlst du", "would you recommend",
    "what would you do", "what would you pick", "what would you choose",
    "was wuerdest du machen", "was wuerdest du tun",
    "was wuerdest du nehmen", "was wuerdest du waehlen",
  ]);
  const hasDecisionCompareTopic = hasAnyTopic([
    "vergleiche", "vergleich", "vergleichs",
    "gegenueberstellen", "gegenueberstellung",
    "compare", "comparison", "compare options",
  ]);
  const hasDecisionTradeoffTopic = hasAnyTopic([
    "pros and cons", "pros cons", "pro und contra",
    "vor und nachteile", "vorteile und nachteile",
    "tradeoff", "tradeoffs", "trade off", "trade offs",
    "risks and benefits", "risiken und vorteile",
  ]);
  const hasDecisionTradeoffContextTopic = hasAnyTopic([
    "of", "for", "between", "von", "fuer", "zwischen", "ueber", "about",
  ]);
  const hasDecisionScoringTopic = hasAnyTopic([
    "criteria", "criterion", "kriterium", "kriterien",
    "score", "scores", "scoring",
    "bewerte", "bewerten", "bewertung", "bewertungsmatrix",
    "entscheidungsmatrix", "matrix",
    "weighted", "gewichtet", "gewichtung", "punkte", "punktezahl",
  ]);
  const hasDecisionPlanningTopic = hasAnyTopic([
    "roadmap", "fahrplan", "umsetzungsplan", "execution plan",
    "action plan", "rollout plan", "release plan", "plan of attack",
    "projektplan", "project plan", "plan", "plane", "planen",
  ]);
  const hasDecisionPlanningStructureTopic = hasAnyTopic([
    "meilenstein", "meilensteine", "milestone", "milestones",
    "phase", "phases", "phasen", "timeline", "zeitplan",
    "quartal", "quarter", "schritt", "schritte", "step", "steps",
    "owner", "owners", "abhaengigkeit", "abhaengigkeiten",
    "dependency", "dependencies",
  ]);
  const hasDecisionConstraintTopic = hasAnyTopic([
    "constraint", "constraints", "einschraenkung", "einschraenkungen",
    "bedingung", "bedingungen", "deadline", "frist", "termin",
    "budget", "timebox", "zeitlimit", "limit", "limited", "begrenzt",
    "resource", "resources", "ressource", "ressourcen",
    "kapazitaet", "kapazitaeten", "stunden", "hours",
    "tage", "days", "wochen", "weeks",
  ]);
  const hasDecisionRiskTopic = hasAnyTopic([
    "risk assessment", "risk analysis", "risk register", "risk plan",
    "mitigation plan", "rollback plan", "contingency plan",
    "failure mode", "failure modes", "abort criteria",
    "go no go", "go/no-go", "ship risk", "release risk",
    "risikoanalyse", "risikoplan", "risikobewertung", "risikoregister",
    "mitigationsplan", "notfallplan", "abbruchkriterien",
  ]);
  const hasDirectDecisionRiskTopic = hasAnyTopic([
    "risk register", "risk plan", "mitigation plan", "rollback plan",
    "contingency plan", "abort criteria", "go no go", "go/no-go",
    "risikoplan", "risikoregister", "mitigationsplan", "notfallplan",
    "abbruchkriterien",
  ]);
  const hasDecisionRiskContextTopic = hasAnyTopic([
    "for", "fuer", "von", "before", "vor", "release", "ship", "launch",
    "lexa", "create", "make", "run", "erstelle", "mach", "pruefe",
    "check", "bewerte",
  ]);
  const hasRiskPlanningTopic = hasDirectDecisionRiskTopic || (hasDecisionRiskTopic && hasDecisionRiskContextTopic);
  const hasSecurityPrivacyTopic = hasAnyTopic([
    "threat model", "threat modeling", "security review", "security audit",
    "privacy review", "privacy audit", "privacy impact assessment",
    "permission review", "permissions review", "least privilege",
    "data loss", "data-loss", "data loss risk", "data exfiltration",
    "exfiltration", "secret leak", "secret leakage", "prompt injection",
    "security", "privacy", "secrets", "secret", "api key", "api keys",
    "token", "tokens", "system prompt", "system prompts", "hidden instructions",
      "audit logs", "raw logs", "stacktrace", "private paths", "sensitive data",
      "safe error", "safe error message", "secure error message",
    "datenschutz review", "datenschutz audit", "bedrohungsmodell",
    "berechtigungsreview", "berechtigungspruefung", "berechtigungen pruefen",
    "datenschutz", "sicherheit", "secrets", "api keys", "token", "tokens",
    "systemprompt", "systemprompts", "systemanweisung", "systemanweisungen",
    "versteckte anweisungen", "rohlogs", "audit logs", "stacktrace",
    "private pfade", "sensible daten", "sensible upload", "interne fehlermeldungen",
    "datenleck", "datenleak", "datenverlust", "datenabfluss",
  ]);
  const hasSecurityPrivacyContextTopic = hasAnyTopic([
    "for", "fuer", "von", "before", "vor", "lexa", "memory",
    "tool", "tools", "hermes", "agent", "release", "launch",
    "run", "create", "make", "erstelle",
    "mach", "pruefe", "check", "bewerte",
  ]);
  const hasSecurityPrivacyReviewTopic = hasSecurityPrivacyTopic && hasSecurityPrivacyContextTopic;
  const hasAccessibilityTopic = hasAnyTopic([
    "accessibility", "a11y", "accessibility review", "accessibility audit",
    "barrierefreiheit", "barrierefrei", "zugaenglichkeit",
    "screen reader", "screenreader", "sr label", "aria",
    "keyboard navigation", "keyboard access",
    "tastaturbedienung", "tastaturnavigation",
    "focus order", "focus trap", "fokusreihenfolge", "fokusfalle",
    "contrast", "kontrast", "reduced motion", "motion sensitivity",
  ]);
  const hasAccessibilityContextTopic = hasAnyTopic([
    "for", "fuer", "von", "before", "vor", "lexa", "app", "chat",
    "ui", "ux", "frontend", "settings", "modal", "button", "buttons",
    "page", "run", "create", "make", "pruefe", "check",
    "bewerte",
  ]);
  const hasAccessibilityReviewTopic = hasAccessibilityTopic && hasAccessibilityContextTopic;
  const hasPerformanceTopic = hasAnyTopic([
    "performance review", "performance audit", "performance budget",
    "latency budget", "latency review", "startup time",
    "startup performance", "load time", "loading time", "response time",
    "throughput", "profiling", "profile performance",
    "bottleneck", "bottlenecks", "memory footprint", "cpu usage",
    "bundle size", "render performance", "streaming latency",
    "perf review", "perf audit", "latenz review", "latenzbudget",
    "startzeit", "ladezeit", "reaktionszeit",
    "flaschenhals", "flaschenhaelse",
  ]);
  const hasPerformanceContextTopic = hasAnyTopic([
    "for", "fuer", "von", "before", "vor", "lexa", "app", "chat",
    "streaming", "frontend", "backend", "startup", "release", "launch",
    "run", "create", "make", "measure", "benchmark", "profile",
    "optimize", "optimise", "improve", "erstelle", "mach", "miss",
    "messe", "benchmarke", "optimiere", "verbessere", "pruefe",
    "check", "bewerte",
  ]);
  const hasPerformanceReviewTopic = hasPerformanceTopic && hasPerformanceContextTopic;
  const hasTestingTopic = hasAnyTopic([
    "test plan", "testing plan", "qa checklist", "qa plan",
    "quality checklist", "acceptance criteria", "acceptance test",
    "regression test plan", "regression tests", "smoke test plan",
    "smoke tests", "test matrix", "testmatrix",
    "test coverage review", "eval plan", "evaluation plan",
    "abnahmekriterien", "abnahmetest", "testplan", "qa checkliste",
    "qualitaetscheckliste", "regressionstestplan", "smoketest",
  ]);
  const hasTestingContextTopic = hasAnyTopic([
    "for", "fuer", "von", "before", "vor", "lexa", "app", "chat",
    "agent", "release", "launch", "feature", "workflow", "streaming",
    "memory", "create", "make", "write", "run", "build", "review",
    "erstelle", "mach", "schreibe", "pruefe", "baue",
  ]);
  const hasTestingReviewTopic = hasTestingTopic && hasTestingContextTopic;
  const hasMemoryContextTopic = hasAnyTopic([
    "memory review", "memory audit", "memory hygiene",
    "memory cleanup", "memory clean up", "memory pruning",
    "context pack", "context brief", "context review", "context audit",
    "context window review", "stable memory", "draft memory",
    "save this memory", "save to memory", "remember this",
    "what should lexa remember", "what should you remember",
    "personalization review", "personalisation review", "profile review",
    "gedaechtnis review", "gedaechtnis audit", "gedaechtnis hygiene",
    "gedaechtnis bereinigen", "gedaechtnis pruefen",
    "kontextpaket", "kontext brief", "kontext review",
    "kontextfenster review", "was soll lexa speichern",
    "was sollst du speichern", "merk dir", "speicher das",
    "speichere das", "personalisierung review", "profil review",
  ]);
  const hasMemoryContextContextTopic = hasAnyTopic([
    "lexa", "assistant", "personal os", "conversation", "chat",
    "profile", "user", "task", "tasks", "project", "decision",
    "decisions", "facts", "assumptions", "preference", "preferences",
    "privacy", "consent", "write", "writes", "build", "create",
    "make", "save", "remember", "prune", "delete", "correct",
    "konversation", "gespraech", "profil", "nutzer", "aufgabe",
    "aufgaben", "projekt", "entscheidung", "entscheidungen", "fakten",
    "annahmen", "praeferenz", "praeferenzen", "datenschutz",
    "einwilligung", "schreibe", "baue", "erstelle", "mach",
    "speicher", "speichere", "merk", "bereinige", "loesche",
    "loeschen", "korrigiere",
  ]);
  const hasMemoryContextReviewTopic = hasMemoryContextTopic && hasMemoryContextContextTopic;
  const hasAgentToolTopic = hasAnyTopic([
    "agent run", "agent task", "agent workflow", "agent execution",
    "agent plan", "agent handoff", "tool workflow", "tool plan",
    "tool execution", "tool execution plan", "tool run",
    "tool use plan", "toolchain", "workspace handoff",
    "handoff plan", "desktop action", "local action",
    "os agent runtime", "background task", "hermes worker",
    "multi step agent", "multistep agent", "run tools", "use tools",
    "agent lauf", "agent aufgabe", "agent ausfuehrung",
    "agent uebergabe", "werkzeug workflow", "werkzeug plan",
    "tool ausfuehrung", "werkzeug ausfuehrung", "tool lauf",
    "workspace uebergabe", "arbeitsuebergabe", "desktop aktion",
    "lokale aktion", "hintergrundaufgabe",
  ]);
  const hasAgentToolContextTopic = hasAnyTopic([
    "lexa", "assistant", "workspace", "repository", "repo",
    "project", "file", "files", "desktop", "browser", "os",
    "personal os", "hermes", "automation", "release", "chat",
    "memory", "permissions", "approval", "rollback", "verification",
    "verify", "safe", "dry run", "read only", "read-only",
    "background", "create", "build", "start", "execute", "projekt",
    "datei", "dateien", "automatisierung", "freigabe",
    "berechtigungen", "verifikation", "verifiziere", "sicher",
    "nur lesend", "lesend", "hintergrund", "erstelle", "baue",
    "starte", "fuehre aus",
  ]);
  const hasAgentToolReviewTopic = hasAgentToolTopic && hasAgentToolContextTopic;
  const hasShipCheckTopic = hasAnyTopic([
    "ship check", "production ship check", "release check",
    "release readiness", "readiness check", "launch readiness",
    "launch blocker", "launch blockers", "publish check",
    "pre publish check", "pre release checklist", "release checklist",
    "release quality", "ship readiness", "go live check",
    "go-live check", "deployment readiness", "deployment check",
    "production readiness", "produktreife", "release pruefung",
    "release pruefen", "publish pruefung", "vor publish",
    "vor release", "go live pruefung", "deployment pruefung",
  ]);
  const hasShipCheckContextTopic = hasAnyTopic([
    "lexa", "assistant", "app", "product", "production",
    "user facing", "user-facing", "ux", "accessibility",
    "performance", "reliability", "security", "privacy",
    "data loss", "docs", "onboarding", "tests", "migration",
    "rollback", "publish", "deploy", "go live", "go-live",
    "before", "for", "produkt", "produktion", "nutzerseitig",
    "barrierefreiheit", "zuverlaessigkeit", "datenschutz",
    "datenverlust", "dokumentation", "veroeffentlichen",
    "deployen", "vor", "fuer",
  ]);
  const hasShipCheckReviewTopic = hasShipCheckTopic && hasShipCheckContextTopic;
  const hasDataSafetyTopic = hasAnyTopic([
    "delete files", "delete data", "delete memory", "delete memories",
    "delete old memories", "cleanup old memories",
    "clean up old memories", "cleanup downloads", "clean up downloads",
    "overwrite file", "overwrite files", "reset database",
    "reset settings", "wipe data", "purge data", "drop table",
    "truncate table", "restore backup", "migrate database",
    "apply migration", "migration apply", "rebuild index",
    "mass delete", "bulk delete", "destructive action",
    "dangerous change", "data loss risk", "dateien loeschen",
    "daten loeschen", "memory loeschen", "erinnerungen loeschen",
    "alte erinnerungen loeschen", "erinnerungen aufraeumen",
    "downloads aufraeumen", "datei ueberschreiben",
    "dateien ueberschreiben", "datenbank zuruecksetzen",
    "einstellungen zuruecksetzen", "backup wiederherstellen",
    "migration anwenden", "datenbank migrieren", "index neu aufbauen",
    "massenloeschung", "destruktive aktion", "gefaehrliche aenderung",
    "gefaehrliche desktop aktion", "datei ausserhalb", "ausserhalb des projekts loeschen",
    "datenverlust risiko",
  ]);
  const hasDataSafetyContextTopic = hasAnyTopic([
    "lexa", "assistant", "app", "workspace", "project", "repo",
    "database", "sqlite", "memory", "memories", "settings",
    "downloads", "files", "folder", "folders", "desktop", "backup",
    "migration", "index", "local", "dry run", "read only",
    "read-only", "restore", "rollback", "confirm", "confirmation",
    "projekt", "datenbank", "erinnerung", "erinnerungen",
    "einstellungen", "datei", "dateien", "ordner", "lokal",
    "nur lesend", "wiederherstellen", "bestaetigen", "bestaetigung",
  ]);
  const hasDataSafetyReviewTopic = hasDataSafetyTopic && hasDataSafetyContextTopic;
  const hasSecuritySensitiveSuggestionContext = hasSecurityPrivacyReviewTopic
    || hasDataSafetyReviewTopic
    || hasAnyTopic([
      "secret", "secrets", "api key", "api keys", "token", "tokens",
      "system prompt", "system prompts", "hidden instructions", "raw logs",
      "audit logs", "stacktrace", "private paths", "sensitive data",
      "prompt injection", "data leak", "data exfiltration", "dangerous action",
      "secret leak",
      "systemprompt", "systemprompts", "systemanweisung", "systemanweisungen",
      "versteckte anweisungen", "rohlogs", "private pfade", "sensible daten",
      "sensible upload", "interne fehlermeldungen", "datenleck", "datenabfluss",
      "sichere fehlermeldung", "sichere fehlermeldungen",
      "gefaehrliche aktion", "gefaehrliche desktop aktion", "datei ausserhalb",
      "ausserhalb des projekts",
    ]);
  const hasDebugTriageTopic = hasAnyTopic([
    "bug triage", "incident triage", "debug plan", "debugging plan",
    "debug this", "debug lexa", "debug the error", "debug error",
    "root cause analysis", "root-cause analysis", "root cause", "rca",
    "crash report", "crash investigation", "error investigation",
    "error log analysis", "log analysis", "analyze logs", "analyse logs",
    "failing test", "failing tests", "test failure",
    "regression investigation", "production incident", "outage",
    "broken workflow", "bug report", "reproduce bug", "repro steps",
    "triage fehler", "fehler triage", "stoerung analysieren",
    "stoerung triage", "absturzbericht", "absturz analysieren",
    "fehler analysieren", "logs analysieren", "log analyse",
    "ursachenanalyse", "root cause analyse", "fehlgeschlagener test",
    "fehlgeschlagene tests", "regression untersuchen",
    "bug reproduzieren", "repro schritte",
  ]);
  const hasDebugTriageContextTopic = hasAnyTopic([
    "lexa", "assistant", "app", "chat", "frontend", "backend",
    "agent", "tool", "memory", "release", "startup", "streaming",
    "workflow", "user", "production", "local", "logs", "log",
    "stack trace", "traceback", "error", "crash", "failure",
    "failing", "reproduce", "repro", "fix", "verify", "rollback",
    "projekt", "lokal", "benutzer", "fehler", "absturz",
    "fehlermeldung", "stacktrace", "reproduzieren", "beheben",
    "verifizieren",
  ]);
  const hasDebugTriageReviewTopic = hasDebugTriageTopic && hasDebugTriageContextTopic;
  const hasStatusHandoffTopic = hasAnyTopic([
    "status update", "progress update", "project status", "work status",
    "implementation summary", "change summary", "verification summary",
    "handoff summary", "handoff note", "handoff brief", "handoff",
    "where are we", "what changed", "what was changed",
    "what have we done", "what did we accomplish", "what is done",
    "what remains", "recap progress", "summarize progress",
    "summarize the work", "statusbericht", "fortschrittsbericht",
    "projektstatus", "arbeitsstand", "zwischenstand", "uebergabe",
    "uebergabe summary", "uebergabe notiz", "wie weit sind wir",
    "wo stehen wir", "was hast du erreicht", "was haben wir erreicht",
    "was wurde geaendert", "was wurde umgesetzt", "was ist erledigt",
    "was ist offen", "fortschritt zusammenfassen",
    "arbeit zusammenfassen",
  ]);
  const hasStatusHandoffContextTopic = hasAnyTopic([
    "lexa", "assistant", "project", "workspace", "repo", "repository",
    "implementation", "changes", "tests", "verified", "verification",
    "next", "risk", "risks", "done", "open", "remaining", "we",
    "wir", "projekt", "arbeitsstand", "aenderungen", "umsetzung",
    "verifiziert", "naechste", "risiko", "risiken", "erledigt",
    "offen", "rest",
  ]);
  const hasStatusHandoffReviewTopic = hasStatusHandoffTopic && hasStatusHandoffContextTopic;
  const hasClarificationTopic = hasAnyTopic([
    "ask clarifying questions", "ask clarification questions",
    "clarifying questions", "clarification questions",
    "clarify requirements", "clarify the requirements",
    "clarify scope", "missing context", "missing information",
    "missing info", "state assumptions", "list assumptions",
    "call out assumptions", "assumption check", "ambiguity check",
    "ambiguous requirements", "if unclear", "when unclear",
    "before proceeding", "blocker questions", "ask only if needed",
    "frage nach wenn unklar", "rueckfragen stellen",
    "rueckfrage stellen", "klaerungsfragen", "klaerungsfrage",
    "anforderungen klaeren", "umfang klaeren", "fehlender kontext",
    "fehlende informationen", "fehlende infos", "annahmen nennen",
    "annahmen auflisten", "annahmen pruefen", "unklarheiten",
    "unklare anforderungen", "falls unklar", "wenn unklar",
    "bevor du fortfaehrst", "blockierende fragen",
  ]);
  const hasClarificationContextTopic = hasAnyTopic([
    "lexa", "assistant", "task", "project", "feature",
    "implementation", "plan", "decision", "requirements", "scope",
    "user", "workflow", "answer", "before", "proceed", "build",
    "create", "write", "do", "aufgabe", "projekt", "umsetzung",
    "entscheidung", "anforderungen", "umfang", "nutzer",
    "antwort", "bevor", "fortfahren", "bauen", "erstellen",
    "schreiben", "machen",
  ]);
  const hasClarificationReviewTopic = hasClarificationTopic && hasClarificationContextTopic;
  const hasFeatureSpecTopic = hasAnyTopic([
    "feature spec", "feature specification", "product spec",
    "product specification", "technical spec", "technical specification",
    "requirements spec", "requirements document", "product requirements",
    "prd", "write a spec", "draft a spec", "create a spec",
    "write requirements", "draft requirements", "define requirements",
    "write user stories", "draft user stories", "create user stories",
    "edge cases", "non goals", "non-goals", "out of scope",
    "success metrics", "feature spek", "produkt spec",
    "produkt spezifikation", "technische spezifikation",
    "anforderungsdokument", "anforderungen schreiben",
    "anforderungen definieren", "user stories schreiben",
    "user stories erstellen",
    "randfaelle", "nicht ziele", "nicht-ziele",
    "ausserhalb scope", "erfolgsmetriken",
  ]);
  const hasFeatureSpecContextTopic = hasAnyTopic([
    "lexa", "assistant", "app", "product", "feature", "workflow",
    "user", "ux", "ui", "agent", "memory", "chat", "release",
    "engineering", "implementation", "build", "create", "draft",
    "write", "define", "produkt", "funktion", "nutzer",
    "entwicklung", "umsetzung", "bauen", "erstellen", "entwerfen",
    "schreiben", "definieren",
  ]);
  const hasFeatureSpecReviewTopic = hasFeatureSpecTopic && hasFeatureSpecContextTopic;
  const hasEvalBenchmarkTopic = hasAnyTopic([
    "assistant eval", "assistant evaluation", "answer quality eval",
    "answer quality evaluation", "response quality eval",
    "response quality evaluation", "quality rubric", "evaluation rubric",
    "scoring rubric", "rubric for lexa", "rubric for assistant",
    "benchmark lexa", "benchmark assistant", "benchmark assistants",
    "benchmark answers", "benchmark responses",
    "compare assistant answers", "compare model answers",
    "compare models against", "compare against gpt",
    "compare against claude", "compare against gemini",
    "gpt comparison", "claude comparison", "gemini comparison",
    "golden set for lexa", "eval dataset", "evaluation dataset",
    "regression eval", "hallucination eval",
    "antwortqualitaet bewerten", "antwortqualitaet evaluation",
    "antwortqualitaet benchmark", "antworten bewerten",
    "antworten benchmarken", "bewertungsrubrik fuer lexa",
    "rubrik fuer lexa", "lexa benchmark", "assistant benchmark",
    "modelle gegen", "gegen gpt vergleichen",
    "gegen claude vergleichen", "gegen gemini vergleichen",
    "golden set fuer lexa", "eval datensatz",
    "halluzinationen bewerten",
  ]);
  const hasEvalBenchmarkContextTopic = hasAnyTopic([
    "lexa", "assistant", "chat", "answer", "answers", "response",
    "responses", "quality", "model", "models", "gpt", "claude",
    "gemini", "benchmark", "rubric", "eval", "evaluation",
    "score", "scores", "test", "tests", "antwort", "antworten",
    "antwortqualitaet", "modell", "modelle", "rubrik", "bewertung",
    "punkte", "testen",
  ]);
  const hasEvalBenchmarkReviewTopic = hasEvalBenchmarkTopic && hasEvalBenchmarkContextTopic;
  const hasSummaryExtractionTopic = hasAnyTopic([
    "summarize meeting", "summarize transcript", "summarize call",
    "summarize notes", "summarize email thread",
    "summarize discussion", "create meeting summary",
    "write meeting summary", "meeting notes summary",
    "transcript summary", "call summary", "discussion summary",
    "extract action items", "extract decisions", "extract todos",
    "extract tasks", "extract follow ups", "extract follow-ups",
    "turn notes into action items",
    "turn transcript into action items", "create meeting minutes",
    "write meeting minutes", "make meeting minutes",
    "meeting minutes from notes", "meeting minutes from transcript",
    "notes to tasks", "transcript to tasks", "meeting recap",
    "call recap", "meeting brief", "transcript brief",
    "meeting zusammenfassen", "transkript zusammenfassen",
    "notizen zusammenfassen", "call zusammenfassen",
    "meeting summary erstellen", "meeting protokoll erstellen",
    "protokoll aus notizen", "protokoll aus transkript",
    "action items extrahieren", "entscheidungen extrahieren",
    "todos extrahieren", "aufgaben extrahieren",
    "follow ups extrahieren", "notizen in aufgaben",
    "transkript in aufgaben",
  ]);
  const hasSummaryExtractionContextTopic = hasAnyTopic([
    "meeting", "transcript", "call", "notes", "email", "thread",
    "discussion", "minutes", "action items", "decisions", "todos",
    "tasks", "owner", "owners", "deadline", "deadlines",
    "follow ups", "follow-ups", "speaker", "speakers",
    "transkript", "notizen", "diskussion", "protokoll",
    "entscheidungen", "aufgaben", "sprecher",
  ]);
  const hasSummaryExtractionReviewTopic = hasSummaryExtractionTopic && hasSummaryExtractionContextTopic;
  const hasNumericAnalysisTopic = hasAnyTopic([
    "calculate", "compute", "estimate", "work out", "how much",
    "how many", "what is the total", "what is the cost",
    "what is the price", "what is the percentage",
    "percent change", "percentage change", "growth rate",
    "conversion rate", "cost estimate", "cost breakdown",
    "cost comparison", "price estimate", "roi",
    "return on investment", "break even", "break-even",
    "average of", "sum of", "total cost", "monthly cost",
    "annual cost", "unit economics",
    "berechne", "berechnen", "rechne", "rechnen",
    "kalkuliere", "kalkulieren", "schaetze", "schaetzen",
    "wieviel", "wie viel", "wie viele", "gesamt",
    "gesamtpreis", "gesamtkosten", "prozentuale aenderung",
    "prozent berechnen", "wachstumsrate", "kosten schaetzen",
    "kosten berechnen", "kostenvergleich", "durchschnitt von",
    "summe von",
  ]);
  const hasNumericAnalysisContextTopic = hasAnyTopic([
    "cost", "costs", "price", "prices", "budget", "revenue",
    "profit", "margin", "discount", "tax", "interest", "users",
    "requests", "tokens", "hours", "minutes", "days", "weeks",
    "months", "years", "percent", "percentage", "rate", "ratio",
    "growth", "conversion", "metric", "metrics", "latency",
    "cost per", "per month", "per year",
    "kosten", "preis", "preise", "umsatz", "gewinn", "marge",
    "rabatt", "steuer", "zinsen", "nutzer", "nutzern", "anfragen",
    "stunden", "minuten", "tage", "wochen", "monate", "jahre",
    "prozent", "prozentual", "prozentuale", "verhaeltnis", "wachstum", "metrik", "metriken",
    "latenz", "pro monat", "pro jahr",
  ]);
  const hasNumericOperatorTopic = /\d\s*(?:[%+\-*/x=]|percent|prozent)\s*\d/u.test(topicText);
  const hasNumericUnitTopic = /\d.*\b(?:eur|usd|euro|dollar|tokens?|users?|requests?|hours?|minutes?|days?|weeks?|months?|years?|stunden?|minuten?|tage?|wochen?|monate?|jahre?|kosten|preis|umsatz|budget|revenue|costs?|prices?|rate|ratio|growth|prozent(?:ual\w*)?|percent|nutzern?)\b/u.test(topicText);
  const hasNumericAnalysisReviewTopic = hasNumericAnalysisTopic && (
    hasNumericAnalysisContextTopic || hasNumericOperatorTopic || hasNumericUnitTopic
  );
  const hasCommunicationDraftTopic = hasAnyTopic([
    "draft email", "draft an email", "draft customer email",
    "draft a customer email", "write email", "write an email",
    "compose email", "compose an email", "reply to email",
    "reply to this email", "respond to email", "draft reply",
    "write reply", "compose reply", "draft response",
    "write response", "draft message", "write message",
    "compose message", "draft announcement", "write announcement",
    "draft slack message", "write slack message", "draft teams message",
    "write teams message", "customer reply", "customer response",
    "customer email reply", "email reply", "email response",
    "outreach email", "follow up email", "follow-up email",
    "polish this email", "rewrite this email",
    "email schreiben", "mail schreiben", "schreibe eine email",
    "schreib eine email", "schreibe eine mail", "schreib eine mail",
    "antwort schreiben", "antwort formulieren",
    "formuliere eine antwort", "kundenantwort",
    "nachricht schreiben", "nachricht formulieren",
    "ankuendigung schreiben", "schreibe eine ankuendigung",
    "schreib eine ankuendigung", "absage formulieren",
    "follow up schreiben", "follow-up schreiben",
  ]);
  const hasCommunicationDraftContextTopic = hasAnyTopic([
    "email", "mail", "message", "reply", "response", "announcement",
    "slack", "teams", "customer", "client", "recipient", "audience",
    "subject", "tone", "cta", "call to action", "follow up",
    "follow-up", "nachricht", "antwort", "ankuendigung", "kunde",
    "kunden", "empfaenger", "zielgruppe", "betreff", "ton",
    "naechster schritt",
  ]);
  const hasCommunicationDraftReviewTopic = hasCommunicationDraftTopic && hasCommunicationDraftContextTopic;
  const hasLearningExplanationTopic = hasAnyTopic([
    "teach me", "teach", "explain step by step", "explain like i am",
    "explain like i'm", "explain like im", "explain for beginners",
    "explain with examples", "walk me through", "help me understand",
    "learning path", "beginner explanation", "for beginners",
    "step by step", "common mistakes", "quiz me", "practice exercise",
    "tutorial for", "bring mir bei", "erklaer mir schritt fuer schritt",
    "erklaere mir schritt fuer schritt", "erklaer es schritt fuer schritt",
    "erklaere es schritt fuer schritt", "erklaer es fuer anfaenger",
    "erklaere es fuer anfaenger", "fuer anfaenger", "mit beispielen",
    "ich verstehe nicht", "hilf mir verstehen", "lernpfad",
    "haeufige fehler", "uebung", "mini quiz",
  ]);
  const hasLearningExplanationContextTopic = hasAnyTopic([
    "concept", "topic", "architecture", "system", "code", "python",
    "javascript", "typescript", "async", "api", "database", "memory",
    "agent", "tool", "workflow", "math", "metric", "lexa",
    "assistant", "feature", "produkt", "konzept", "thema",
    "architektur", "datenbank", "gedaechtnis", "werkzeug",
    "mathe", "metrik", "assistent", "funktion",
  ]);
  const hasLearningExplanationReviewTopic = hasLearningExplanationTopic && hasLearningExplanationContextTopic;
  const hasDecisionComparisonTopic = hasAnyTopic([
    "oder", "or", "vs", "versus", "statt", "instead",
    "zuerst", "first", "priorisieren", "prioritaet", "priority",
  ]);
  // Decision/planning context
  if (
    hasStrongDecisionTopic ||
    (hasDecisionIntentTopic && hasDecisionStructureTopic) ||
    (hasDecisionAskTopic && hasDecisionComparisonTopic) ||
    (hasDecisionBetterTopic && hasDecisionComparisonTopic) ||
    (hasDecisionCompareTopic && (hasDecisionComparisonTopic || hasDecisionStructureTopic)) ||
    (hasDecisionTradeoffTopic && (hasDecisionComparisonTopic || hasDecisionTradeoffContextTopic)) ||
    (hasDecisionScoringTopic && (hasDecisionStructureTopic || hasDecisionComparisonTopic)) ||
    (hasDecisionPlanningTopic && hasDecisionPlanningStructureTopic) ||
    (hasDecisionConstraintTopic && (hasDecisionPlanningTopic || hasDecisionIntentTopic)) ||
    hasRiskPlanningTopic ||
    hasSecurityPrivacyReviewTopic ||
    hasSecuritySensitiveSuggestionContext ||
    hasAccessibilityReviewTopic ||
    hasPerformanceReviewTopic ||
    hasTestingReviewTopic ||
    hasMemoryContextReviewTopic ||
    hasAgentToolReviewTopic ||
    hasShipCheckReviewTopic ||
    hasDataSafetyReviewTopic ||
    hasDebugTriageReviewTopic ||
    hasStatusHandoffReviewTopic ||
    hasClarificationReviewTopic ||
    hasFeatureSpecReviewTopic ||
    hasEvalBenchmarkReviewTopic ||
    hasSummaryExtractionReviewTopic ||
    hasNumericAnalysisReviewTopic ||
    hasCommunicationDraftReviewTopic ||
    hasLearningExplanationReviewTopic
  ) {
    if (hasLearningExplanationReviewTopic) {
      suggestions.unshift(t("chat.suggSimplify"), t("chat.suggShowExample"), t("chat.suggQuizMe"));
    } else if (hasCommunicationDraftReviewTopic) {
      suggestions.unshift(t("chat.suggAdjustTone"), t("chat.suggAddCta"), t("chat.suggMakeConcise"));
    } else if (hasNumericAnalysisReviewTopic) {
      suggestions.unshift(t("chat.suggCheckMath"), t("chat.suggShowFormula"), t("chat.suggListAssumptions"));
    } else if (hasSummaryExtractionReviewTopic) {
      suggestions.unshift(t("chat.suggExtractActionItems"), t("chat.suggListDecisions"), t("chat.suggMakeBrief"));
    } else if (hasEvalBenchmarkReviewTopic) {
      suggestions.unshift(t("chat.suggDefineRubric"), t("chat.suggRunEval"), t("chat.suggCompareBaseline"));
    } else if (hasFeatureSpecReviewTopic) {
      suggestions.unshift(t("chat.suggDefineAcceptanceCriteria"), t("chat.suggListEdgeCases"), t("chat.suggDefineMvp"));
    } else if (hasClarificationReviewTopic) {
      suggestions.unshift(t("chat.suggShowAssumptions"), t("chat.suggListMissingContext"), t("chat.suggAskClarifyingQuestions"));
    } else if (hasStatusHandoffReviewTopic) {
      suggestions.unshift(t("chat.suggShowVerifiedChanges"), t("chat.suggShowNextSteps"), t("chat.suggShowOpenRisks"));
    } else if (hasDebugTriageReviewTopic) {
      suggestions.unshift(t("chat.suggStartTriage"), t("chat.suggFindLogs"), t("chat.suggVerifyFix"));
    } else if (hasDataSafetyReviewTopic) {
      suggestions.unshift(t("chat.suggDryRunFirst"), t("chat.suggCheckBackup"), t("chat.suggConfirmChanges"));
    } else if (hasShipCheckReviewTopic) {
      suggestions.unshift(t("chat.suggShipChecklist"), t("chat.suggRunSmokeTests"), t("chat.suggCheckRollback"));
    } else if (hasRiskPlanningTopic || hasSecurityPrivacyReviewTopic || hasSecuritySensitiveSuggestionContext) {
      suggestions.unshift(t("chat.suggCheckRisks"), t("chat.suggMakeRecommendation"), t("chat.suggListOpenQuestions"));
    } else if (hasMemoryContextReviewTopic) {
      suggestions.unshift(t("chat.suggReviewMemory"), t("chat.suggBuildContextPack"), t("chat.suggListOpenQuestions"));
    } else if (hasAgentToolReviewTopic) {
      suggestions.unshift(t("chat.suggPlanToolRun"), t("chat.suggCheckPermissions"), t("chat.suggVerifyResult"));
    } else if (hasTestingReviewTopic) {
      suggestions.unshift(t("chat.suggRunFocusedTests"), t("chat.suggCheckRisks"), t("chat.suggListOpenQuestions"));
    } else if (hasPerformanceReviewTopic) {
      suggestions.unshift(t("chat.suggMeasurePerformance"), t("chat.suggRunFocusedTests"), t("chat.suggCheckRisks"));
    } else if (hasAccessibilityReviewTopic) {
      suggestions.unshift(t("chat.suggCheckAccessibility"), t("chat.suggRunFocusedTests"), t("chat.suggListOpenQuestions"));
    } else {
      suggestions.unshift(t("chat.suggCompareOptions"), t("chat.suggMakeRecommendation"), t("chat.suggListOpenQuestions"));
    }
  }
  if (hasSecuritySensitiveSuggestionContext) {
    return [...new Set(suggestions)].slice(0, 3);
  }
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
  // File-management context. Keep this narrow so uploaded-document analysis does not suggest cleanup actions.
  if (hasAnyTopic([
    "downloads aufraeumen", "downloads bereinigen", "download ordner aufraeumen",
    "duplikate finden", "doppelte dateien", "dateien aufraeumen",
    "ordner aufraeumen", "clean downloads", "clean up downloads",
    "find duplicates", "duplicate files", "file cleanup",
  ])) {
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
    // Reset to 1 row first, otherwise scrollHeight reflects the previous (expanded)
    // size and the box never shrinks back after sending a long message.
    chatInput.rows = 1;
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
    // Laufenden Datei-Upload ebenfalls abbrechen (no-op, wenn keiner laeuft).
    try { window.lexa?.cancelUpload?.(); } catch (e) { /* noop */ }
    hideTyping();
    LexaState.set("isLoading", false);
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
  // Staged attachments: send the file(s) with the typed text as caption instead of a text turn.
  if (typeof getStagedUploads === "function" && getStagedUploads().length) {
    sendStagedUploads();
    return;
  }
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
  header.appendChild(regenBtn);
  header.appendChild(verifyBtn);
  header.appendChild(exportBtn);
  header.appendChild(createMessageActionOverflowMenu([continueBtn, workspaceBtn, memoryBtn]));

  const textEl = document.createElement("div");
  textEl.className = "msg-text streaming-text";
  // Screenreader: streamende Antwort als höfliche Live-Region ankündigen.
  textEl.setAttribute("aria-live", "polite");
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
  let streamRenderQueued = false;
  let streamRenderActive = true;
  let _lastStreamRenderTs = 0;
  const STREAM_RENDER_INTERVAL_MS = 90; // Live-Markdown, aber gedrosselt (kein O(n^2)-Reflow pro Token)
  const scheduleStreamRender = () => {
    if (streamRenderQueued) return;
    streamRenderQueued = true;
    const schedule = window.requestAnimationFrame || ((fn) => setTimeout(fn, 16));
    schedule(() => {
      streamRenderQueued = false;
      if (!streamRenderActive) return;
      const now = Date.now();
      if (now - _lastStreamRenderTs < STREAM_RENDER_INTERVAL_MS) {
        scheduleStreamRender(); // gedrosselt erneut versuchen
        return;
      }
      _lastStreamRenderTs = now;
      // Scroll-Lock: nur ans Ende ziehen, wenn der Nutzer ohnehin (fast) unten ist.
      const stick = isChatNearBottom(chatMessages);
      renderStreamingFormatted(textEl, fullText);
      if (stick) chatMessages.scrollTop = chatMessages.scrollHeight;
    });
  };

  let _streamTimeout = null;
  let _lastStreamActivity = Date.now();
  // Inaktivitäts-Timeout (60s OHNE neue Daten) statt absolutem 45s-Limit: lange, aber
  // stetig streamende Antworten und Web-Recherche werden nicht mehr fälschlich abgebrochen.
  const STREAM_INACTIVITY_MS = 60000;
  const armStreamWatchdog = () => {
    _lastStreamActivity = Date.now();
    if (_streamTimeout) clearTimeout(_streamTimeout);
    _streamTimeout = setTimeout(() => {
      window._lexaStreamAbortReason = "timeout";
      if (window._lexaStreamAbort) window._lexaStreamAbort.abort();
    }, STREAM_INACTIVITY_MS);
  };
  try {
    window._lexaStreamAbort = new AbortController();
    window._lexaStreamAbortReason = "";
    armStreamWatchdog();
    let response;
    try {
      response = await fetch(`${window.lexa.API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text, conversation_id: LexaState.get("currentConversationId") || null }),
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
    let streamEventError = "";
    let streamStoppedByUser = false;
    let streamTimedOut = false;
    let webSources = [];
    const handleStreamData = (data) => {
      if (!data) return;
      // Heuristik-Grounding-Pfad meldet status: "web_search".
      if (data.status === "web_search" && !fullText) {
        textEl.textContent = "🔍 Ich durchsuche das Web …";
      }
      // Agentischer Loop meldet pro Hop status: "tool:<name>" (web_search + Read-Tools).
      if (typeof data.status === "string" && data.status.startsWith("tool:") && !fullText) {
        const toolName = data.status.slice(5);
        const TOOL_STATUS = {
          web_search: "🔍 Ich durchsuche das Web …",
          system_info: "⚙️ Ich lese Systeminfos …",
          battery_status: "🔋 Ich prüfe den Akku …",
          window_list: "🪟 Ich sehe mir offene Fenster an …",
          process_list: "📊 Ich prüfe laufende Prozesse …",
          memory_search: "🧠 Ich durchsuche mein Gedächtnis …",
          file_search: "📁 Ich suche Dateien …",
          app_search: "📱 Ich suche Apps …",
          app_list: "📱 Ich sehe mir Apps an …",
          app_list_installed: "📱 Ich liste installierte Apps …",
          wifi_status: "📶 Ich prüfe das WLAN …",
          brightness_get: "💡 Ich prüfe die Helligkeit …",
        };
        textEl.textContent = TOOL_STATUS[toolName] || `⚙️ Ich nutze ein Werkzeug: ${toolName} …`;
      }
      if (data.status === "web_search_empty" && !fullText) {
        textEl.textContent = "🔍 Keine Web-Quellen gefunden – ich antworte aus meinem Wissen …";
      }
      if (Array.isArray(data.sources)) {
        // Mehrere sources-Events pro Antwort (Heuristik-Grounding + agentische web_search-Hops):
        // mergen statt überschreiben, nach URL deduplizieren (sonst gehen frühe Quellen verloren).
        const seen = new Set(webSources.map((s) => s && s.url));
        data.sources.forEach((s) => {
          if (s && s.url && !seen.has(s.url)) { seen.add(s.url); webSources.push(s); }
        });
      }
      if (data.c) { fullText += data.c; scheduleStreamRender(); }
      if (data.error) {
        streamEventError = chatStreamClientErrorText(data.error, t("chat.connectionLostRetry"));
        streamError = streamError || new Error("backend_stream_error_event");
      }
      if (data.done) {
        actionData = data.action;
        if (data.reply && !fullText) fullText = data.reply;
        if (!streamEventError) streamError = null;
      }
    };
    try {
      while (true) {
        if (Date.now() - _lastStreamActivity > STREAM_INACTIVITY_MS) {
          console.warn("[LEXA] Stream inactivity timeout");
          streamTimedOut = true;
          window._lexaStreamAbortReason = "timeout";
          await reader.cancel();
          break;
        }
        const { done, value } = await reader.read();
        if (done) break;
        armStreamWatchdog(); // neue Daten -> Inaktivitäts-Uhr zurücksetzen
        buffer += decoder.decode(value, { stream: true });
        const parsedBuffer = chatStreamBufferedLines(buffer);
        const lines = parsedBuffer.lines;
        buffer = parsedBuffer.buffer;
        for (const line of lines) {
          const data = parseChatStreamDataLine(line);
          handleStreamData(data);
        }
      }
      buffer += decoder.decode();
      for (const line of chatStreamFinalLines(buffer)) {
        const data = parseChatStreamDataLine(line);
        handleStreamData(data);
      }
      buffer = "";
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
    // Web-Grounding: echte, live abgerufene Quellen als ChatGPT-artige Chip-Liste
    // (in dataset; gerendert via renderChatSources weiter unten, persistiert beim Save).
    if (webSources.length && !streamStoppedByUser && !streamTimedOut && !streamError) {
      setMessageSources(msgEl, webSources);
    }
    if (fullText) {
      renderFormattedMessage(textEl, fullText);
      if (streamStoppedByUser || streamTimedOut || streamError) {
        const warn = document.createElement("span");
        warn.className = "stream-warning";
        warn.textContent = streamStoppedByUser ? t("chat.responseStopped") : "\u26A0 " + (streamEventError || t("chat.connectionInterrupted"));
        textEl.appendChild(warn);
      }
    } else if (streamStoppedByUser) {
      textEl.textContent = t("chat.responseStopped");
    } else if (streamTimedOut) {
      textEl.textContent = t("chat.connectionTimeout");
    } else if (streamEventError) {
      fullText = streamEventError;
      renderFormattedMessage(textEl, fullText);
    } else if (streamError) {
      textEl.textContent = t("chat.connectionLostRetry");
    } else {
      fullText = t("chat.emptyResponseFallback");
      renderFormattedMessage(textEl, fullText);
    }

    // Quellen-Chips direkt unter der Antwort (vor den Vorschlags-Chips).
    renderChatSources(body, getMessageSources(msgEl));

    if (actionData) {
      handleChatToolActionBlocked(actionData);
    }
    // Show follow-up suggestion chips only for a complete, error-free response
    if (fullText && fullText.length > 50 && !actionData
        && !streamStoppedByUser && !streamTimedOut && !streamError) {
      const suggestDiv = document.createElement("div");
      suggestDiv.className = "msg-suggestions";
      const suggestions = generateSuggestions(fullText, text);
      suggestions.forEach(s => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "suggestion-chip";
        chip.textContent = s;
        chip.addEventListener("click", () => {
          if (LexaState.get("isLoading")) return;
          chatInput.value = s;
          syncChatInputSize();
          suggestDiv.remove();
          sendMessage();
        });
        suggestDiv.appendChild(chip);
      });
      if (suggestions.length > 0) body.appendChild(suggestDiv);
    }
    scrollChatMessageIntoCleanView(msgEl, { preferStartForLong: true });
    // Nur echte Antworten persistieren. Bei leerem fullText UND Fehler-/Abbruch-Status
    // NICHT den Status-Text ("Timeout"/"Verbindung unterbrochen") als Assistenten-Antwort
    // speichern (sonst landen Fehlermeldungen dauerhaft in der Konversations-History).
    const hadFailure = streamStoppedByUser || streamTimedOut || streamError || Boolean(streamEventError);
    const persistText = (fullText && fullText.trim()) ? fullText : (hadFailure ? "" : textEl.textContent);
    setMessagePersistText(msgEl, persistText);
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
    clearTimeout(_streamTimeout);
    streamRenderActive = false;
    textEl.classList.remove("streaming-text");
    // Offline (kein Internet) klar von "Backend down" unterscheiden.
    const isOffline = (typeof navigator !== "undefined" && navigator.onLine === false)
      || /networkerror|failed to fetch|network request failed/i.test(String((err && err.message) || ""));
    textEl.textContent = isOffline ? t("chat.noInternetConnection") : t("chat.backendUnreachable");
    setMessagePersistText(msgEl, "");
    copyBtn.disabled = false;
    memoryBtn.disabled = false;
    workspaceBtn.disabled = false;
    continueBtn.disabled = false;
    verifyBtn.disabled = false;
    exportBtn.disabled = false;
    regenBtn.disabled = false;
    showToast(t("toast.chatError"), "error");
  }

  clearTimeout(_streamTimeout);
  saveChatHistory();
  saveCurrentConversation();
  LexaState.set("isLoading", false);
  sendBtn.disabled = false;
  window._lexaStreamAbort = null;
  window._lexaStreamAbortReason = "";
  // Fokus zurück ins Eingabefeld (Tastatur-/Screenreader-Nutzer), wie bei ChatGPT/Claude —
  // aber NICHT, wenn ein Modal/Dialog offen ist (sonst würde dem User die Eingabe im Modal
  // entrissen / der Dialog implizit geschlossen).
  const _modalOpen = Boolean(document.querySelector('[aria-modal="true"]'));
  if (window._chatViewOpen && chatInput && !_modalOpen && document.activeElement !== chatInput) {
    try { chatInput.focus({ preventScroll: true }); } catch (e) { chatInput.focus(); }
  }
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
    const agentRunDomId = `agent-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

    const normalizeAgentStepIndex = (step, fallbackIndex = 0) => {
      const rawIndex = step?.index;
      const numeric = Number(rawIndex);
      return Number.isFinite(numeric) ? numeric : fallbackIndex;
    };

    const ensureAgentStepElement = (step, fallbackIndex = 0) => {
      const normalizedStep = { ...(step || {}), index: normalizeAgentStepIndex(step, fallbackIndex) };
      let stepEl = Array.from(stepsContainer.querySelectorAll(".agent-step"))
        .find((el) => el.dataset.agentStepIndex === String(normalizedStep.index));
      if (stepEl) return { stepEl, step: normalizedStep };

      stepEl = document.createElement("div");
      stepEl.className = "agent-step running";
      stepEl.id = `agent-step-${agentRunDomId}-${normalizedStep.index}`;
      stepEl.dataset.agentStepIndex = String(normalizedStep.index);
      stepEl.setAttribute("role", "listitem");
      const readableLabel = agentStepDisplayLabel(normalizedStep);
      const technicalLabel = agentStepTechnicalLabel(normalizedStep);
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
      return { stepEl, step: normalizedStep };
    };

    const markAgentStepFinished = (step, fallbackIndex = 0) => {
      const ensured = ensureAgentStepElement(step, fallbackIndex);
      const stepEl = ensured.stepEl;
      const normalizedStep = ensured.step;
      const blocked = normalizedStep.status === "blocked";
      const success = normalizedStep.status === "success";
      stepEl.className = `agent-step ${blocked ? "blocked" : (success ? "success" : "failed")}`;
      const icon = stepEl.querySelector(".agent-step-icon");
      if (icon) icon.textContent = blocked ? "\u26A0\uFE0F" : (success ? "\u2705" : "\u274C");
      if (blocked && !stepEl.querySelector(".agent-step-note")) {
        const note = document.createElement("span");
        note.className = "agent-step-note";
        note.textContent = t("chat.agentNeedsConfirmation");
        stepEl.appendChild(note);
      }
      if (normalizedStep.duration_ms && !stepEl.querySelector(".agent-step-duration")) {
        const dur = document.createElement("span");
        dur.className = "agent-step-duration";
        dur.textContent = `${Math.round(normalizedStep.duration_ms)}ms`;
        stepEl.appendChild(dur);
      }
      renderAgentStepOutcome(stepEl, normalizedStep);
      return normalizedStep;
    };

    const handleAgentStreamEvent = (event) => {
      if (!event || typeof event !== "object") return;

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
        ensureAgentStepElement(event.step || {});
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      if (event.type === "step_done") {
        const step = markAgentStepFinished(event.step || {});
        recordAgentStepOutcome(step, agentOutcomeCounts, agentStepOutcomes);
        renderAgentOutcomeSummary(outcomeSummaryEl, agentOutcomeCounts);
      }

      if (event.type === "step_blocked") {
        const step = markAgentStepFinished({ ...(event.step || {}), status: "blocked" });
        recordAgentStepOutcome(step, agentOutcomeCounts, agentStepOutcomes);
        renderAgentOutcomeSummary(outcomeSummaryEl, agentOutcomeCounts);
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
        finalSteps.forEach((step, index) => markAgentStepFinished(step, index));
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
    };

    const processAgentStreamLines = (lines) => {
      for (const line of lines) {
        const event = parseChatStreamDataLine(line);
        try {
          handleAgentStreamEvent(event);
        } catch (e) {
          console.warn("[Agent] SSE event error:", e?.message || e);
        }
      }
    };

    while (true) {
      const remainingMs = AGENT_STREAM_TIMEOUT_MS - (Date.now() - agentStreamStartedAt);
      if (remainingMs <= 0) {
        try { await agentReader.cancel(); } catch (e) { console.warn("[Agent] Reader cancel failed:", e.message || e); }
        throw new Error("agent_stream_timeout");
      }
      let readTimeoutHandle = null;
      const readResult = await Promise.race([
        agentReader.read(),
        new Promise((resolve) => { readTimeoutHandle = setTimeout(() => resolve({ timeout: true }), remainingMs); }),
      ]);
      clearTimeout(readTimeoutHandle);
      if (readResult.timeout) {
        try { await agentReader.cancel(); } catch (e) { console.warn("[Agent] Reader cancel failed:", e.message || e); }
        throw new Error("agent_stream_timeout");
      }
      const { done, value } = readResult;
      if (done) break;
      buffer += decoder.decode(normalizeAgentStreamChunk(value), { stream: true });
      const parsedBuffer = chatStreamBufferedLines(buffer);
      buffer = parsedBuffer.buffer;
      processAgentStreamLines(parsedBuffer.lines);
    }

    buffer += decoder.decode();
    processAgentStreamLines(chatStreamFinalLines(buffer));
    buffer = "";
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

// Composer command palette helpers live in chat_composer_palette.js.

// Performance helpers.
function trimChatMessages() {
  const msgs = chatMessages.querySelectorAll(".message");
  if (msgs.length > LexaConfig.MAX_DOM_MESSAGES) {
    const toRemove = msgs.length - LexaConfig.MAX_DOM_MESSAGES;
    const beforeHeight = chatMessages.scrollHeight;
    const beforeTop = chatMessages.scrollTop;
    for (let i = 0; i < toRemove; i++) msgs[i].remove();
    // Scroll-Position erhalten: um die entfernte Höhe nach oben korrigieren, damit der
    // sichtbare Inhalt nicht springt (kein Jank, wenn ältere Nachrichten weggetrimmt werden).
    const removedHeight = beforeHeight - chatMessages.scrollHeight;
    if (removedHeight > 0 && beforeTop > 0) {
      chatMessages.scrollTop = Math.max(0, beforeTop - removedHeight);
    }
  }
}

// Conversation lifecycle and sidebar flow live in chat_conversations.js.

// Drag/drop and file-upload flow lives in chat_file_upload.js.

// Global search and conversation export live in chat_search.js.
