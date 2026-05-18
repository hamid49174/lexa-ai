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
function getMessagePersistText(msg) {
  return (
    msg.querySelector(".msg-text")?.textContent
    || msg.querySelector(".agent-summary")?.textContent
    || ""
  ).trim();
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
    if (text) messages.push({ text, type });
  });
  const toSave = messages.slice(-(LexaConfig.CHAT_HISTORY_LOCAL_MAX));
  try {
    localStorage.setItem("lexa-chat-history", JSON.stringify(toSave));
  } catch (e) { console.warn("[Chat] Failed to save chat history to localStorage:", e.message || e); }
}

// ── AUTO-SAVE CONVERSATION ────────────────────────
async function autoSaveConversation() {
  if (!LexaState.get("currentConversationId") || !LexaState.get("backendOnline") || !chatMessages) return;
  try {
    const messages = [];
    chatMessages.querySelectorAll(".message").forEach((msg) => {
      if (!isPersistableChatMessage(msg)) return;
      const text = getMessagePersistText(msg);
      const role = msg.classList.contains("user-message") ? "user" : "assistant";
      if (text) messages.push({ role, content: text });
    });
    if (messages.length === 0) return;
    await window.lexa.conversationUpdate(LexaState.get("currentConversationId"), { messages });
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

async function loadChatHistory() {
  // Try loading from backend conversation (SQLite = source of truth)
  const convId = LexaState.get("currentConversationId") || localStorage.getItem("lexa-active-conversation");
  if (convId && LexaState.get("backendOnline")) {
    try {
      const conv = await window.lexa.conversationGet(convId);
      if (conv && !conv.detail && Array.isArray(conv.messages) && conv.messages.length > 0) {
        LexaState.set("currentConversationId", conv.id || convId);
        for (const msg of conv.messages) {
          addMessage(msg.content, msg.role === "user" ? "user" : "system", null, false, true);
        }
        return;
      }
    } catch (e) { console.warn("[Chat] Failed to load conversation from backend, falling back to localStorage:", e.message || e); }
  }
  // Fallback: load from localStorage session cache
  try {
    const saved = localStorage.getItem("lexa-chat-history");
    if (!saved) return;
    const messages = JSON.parse(saved);
    if (!Array.isArray(messages) || messages.length === 0) return;
    messages.forEach((m) => { addMessage(m.text, m.type, null, false, true); });
  } catch (e) { console.warn("[Chat] Failed to load chat history from localStorage:", e.message || e); }
}

// ── CHAT MESSAGE DISPLAY ─────────────────────────
function clearChat() {
  const msgs = chatMessages.querySelectorAll(".message");
  msgs.forEach((m) => m.remove());
  localStorage.removeItem("lexa-chat-history");
  if (LexaState.get("currentConversationId")) {
    window.lexa.conversationUpdate(LexaState.get("currentConversationId"), { messages: [] })
      .then(() => refreshConversationSidebar())
      .catch(() => { });
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

function setIconButton(button, icon, label) {
  button.textContent = "";
  button.dataset.icon = icon;
  button.title = label;
  button.setAttribute("aria-label", label);
}

function addMessage(text, type = "system", action = null, requiresConfirmation = false, silent = false) {
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
  const isUser = type === "user";
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
  const timeSpan = document.createElement("span");
  timeSpan.className = "msg-time";
  timeSpan.textContent = timeStr;
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "msg-copy-btn";
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  header.appendChild(nameSpan);
  header.appendChild(timeSpan);

  if (!isUser) {
    // Thumbs-up to save as memory
    const thumbsBtn = document.createElement("button");
    thumbsBtn.type = "button";
    thumbsBtn.className = "msg-thumbs-btn";
    setIconButton(thumbsBtn, "\u2605", t("chat.saveAsMemoryTooltip"));
    thumbsBtn.addEventListener("click", async () => {
      const msgText = msgTextEl.textContent || "";
      const snippet = msgText.substring(0, 200).trim();
      if (!snippet) return;
      await window.lexa.memoryAdd(t("chat.helpfulAnswer", {snippet}), "learned", 5);
      thumbsBtn.dataset.icon = "\u2713";
      thumbsBtn.disabled = true;
      showToast(t("toast.savedAsMemory"), "success");
    });
    header.appendChild(thumbsBtn);

    // Regenerate button for Lexa messages
    if (!silent) {
      const regenBtn = document.createElement("button");
      regenBtn.type = "button";
      regenBtn.className = "msg-action-btn msg-regen-btn";
      setIconButton(regenBtn, "\u21BB", t("chat.regenerateTooltip"));
      regenBtn.addEventListener("click", () => {
        // Find the user message right before this one
        const allMsgs = chatMessages.querySelectorAll(".message");
        let prevUserText = "";
        for (let i = allMsgs.length - 1; i >= 0; i--) {
          if (allMsgs[i] === msg) {
            // Look backwards for user message
            for (let j = i - 1; j >= 0; j--) {
              if (allMsgs[j].classList.contains("user-message")) {
                prevUserText = allMsgs[j].querySelector(".msg-text")?.textContent || "";
                break;
              }
            }
            break;
          }
        }
        if (prevUserText) regenerateMessage(prevUserText);
      });
      header.appendChild(regenBtn);
    }
  }

  if (isUser && !silent) {
    // Edit button for user messages
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "msg-action-btn msg-edit-btn";
    setIconButton(editBtn, "\u270E", t("chat.editTooltip"));
    editBtn.addEventListener("click", () => {
      const currentText = msgTextEl.textContent || "";
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
      msg.classList.add("msg-deleting");
      setTimeout(() => msg.remove(), 200);
      saveChatHistory();
    });
    header.appendChild(delBtn);
  }

  header.appendChild(copyBtn);

  const msgTextEl = document.createElement("div");
  msgTextEl.className = "msg-text";
  renderFormattedMessage(msgTextEl, text);
  body.appendChild(header);
  body.appendChild(msgTextEl);

  if (requiresConfirmation && action) {
    const actionDiv = document.createElement("div");
    actionDiv.className = "msg-action";
    const actionLabel = document.createElement("div");
    actionLabel.className = "action-label";
    actionLabel.textContent = t("chat.confirmationRequired");
    const actionCmd = document.createElement("div");
    actionCmd.className = "action-cmd";
    actionCmd.textContent = `${String(action.action)}(${JSON.stringify(action.params || {})})`;
    actionDiv.appendChild(actionLabel);
    actionDiv.appendChild(actionCmd);
    body.appendChild(actionDiv);

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "confirm-btn";
    confirmBtn.textContent = t("chat.confirmBtn");
    confirmBtn.addEventListener("click", () => confirmAction(confirmBtn, encodeURIComponent(JSON.stringify(action))));
    const denyBtn = document.createElement("button");
    denyBtn.type = "button";
    denyBtn.className = "deny-btn";
    denyBtn.textContent = t("common.cancel");
    denyBtn.addEventListener("click", () => denyAction(denyBtn));
    body.appendChild(confirmBtn);
    body.appendChild(denyBtn);
  }

  msg.appendChild(avatar);
  msg.appendChild(body);
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  trimChatMessages();
  if (!silent) saveChatHistory();
}

function copyCode(btn) {
  const code = btn.closest(".code-block-wrap")?.querySelector("code")?.textContent || "";
  navigator.clipboard?.writeText(code).then(() => {
    btn.textContent = "";
    btn.dataset.icon = "\u2713";
    setTimeout(() => { btn.dataset.icon = "\u2398"; }, 1500);
  });
}

function copyMessage(btn) {
  const text = btn.closest(".msg-body").querySelector(".msg-text")?.textContent || "";
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = "";
    btn.dataset.icon = "\u2713";
    setTimeout(() => { btn.dataset.icon = "\u2398"; }, 1500);
  }).catch(() => {
    showToast(t("toast.copyFailed") || "Kopieren fehlgeschlagen", "warning", 2000);
  });
}

function renderFormattedMessage(target, text) {
  if (!target) return;
  target.innerHTML = formatMessage(String(text || ""));
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
  try { fetch(`${window.lexa.API_BASE}/chat/confirm-clear`, { method: "POST" }); } catch (_) {}
  showToast(t("toast.actionCancelled"), "warning");
}

function formatMessage(text) {
  // Strip <function=name>...</function> tags (AI model artifact, not real content)
  text = text.replace(/<function=\w+[^>]*>[\s\S]*?<\/function>/g, "").trim();
  text = text.replace(/<function=\w+[^>]*\/?>/g, "").trim();
  if (!text) return "";
  const translate = (key, fallback = "") => {
    try {
      if (typeof t === "function") {
        const value = t(key);
        if (value !== undefined && value !== null && value !== "") return String(value);
      }
    } catch (_) {}
    return fallback || key;
  };

  // Phase 1: Extract code blocks (protect from other processing)
  const codeBlocks = [];
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = code.replace(/</g, "&lt;").replace(/>/g, "&gt;").trim();
    const placeholder = `\x00CODE${codeBlocks.length}\x00`;
    const langLabel = lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : "";
    const copyLabel = escapeHtml(translate("chat.copyTooltip", "Copy code"));
    codeBlocks.push(`<div class="code-block-wrap"><div class="code-block-header">${langLabel}<button type="button" class="code-copy-btn" data-action="copy-code" title="${copyLabel}" aria-label="${copyLabel}" data-icon="&#x2398;"></button></div><pre class="code-block"><code>${escaped}</code></pre></div>`);
    return placeholder;
  });

  // Phase 2: Extract tables (protect from escaping)
  const tables = [];
  text = text.replace(/((?:\|.+\|[\t ]*\n)+)/g, (tableBlock) => {
    const rows = tableBlock.trim().split("\n").filter(r => r.trim());
    if (rows.length < 2) return tableBlock;
    const isSep = /^\|[\s\-:|]+\|$/.test(rows[1].trim());
    const dataRows = isSep ? [rows[0], ...rows.slice(2)] : rows;
    if (dataRows.length === 0) return tableBlock;
    let html = '<div class="table-wrap"><table class="chat-table">';
    dataRows.forEach((row, i) => {
      const cells = row.split("|").filter((c, ci, arr) => ci > 0 && ci < arr.length);
      const tag = (i === 0 && isSep) ? "th" : "td";
      html += "<tr>" + cells.map(c => `<${tag}>${escapeHtml(c.trim())}</${tag}>`).join("") + "</tr>";
    });
    html += "</table></div>";
    const placeholder = `\x00TABLE${tables.length}\x00`;
    tables.push(html);
    return placeholder;
  });

  // Phase 3: Escape HTML (safety first)
  text = escapeHtml(text);

  // Phase 4: Restore protected blocks
  text = text.replace(/\x00CODE(\d+)\x00/g, (_, i) => codeBlocks[parseInt(i, 10)]);
  text = text.replace(/\x00TABLE(\d+)\x00/g, (_, i) => tables[parseInt(i, 10)]);

  // Phase 5: Inline formatting
  text = text.replace(/`([^`]+)`/g, (_, code) =>
    `<code class="inline-code">${code.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code>`
  );
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/~~([^~]+)~~/g, "<s>$1</s>");
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Phase 6: Images & links
  text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, url) => {
    const urlLower = url.trim().toLowerCase();
    if (/^https?:\/\//.test(urlLower) && !/^(javascript|data|vbscript|file):/i.test(urlLower)) {
      return `<img src="${escapeHtml(url.trim())}" alt="${escapeHtml(alt)}" class="chat-img">`;
    }
    return alt || "";
  });
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, url) => {
    if (!url.startsWith("http://") && !url.startsWith("https://")) return label;
    return `<a href="${url}" class="chat-link" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });

  // Phase 7: Block elements
  text = text.replace(/^### (.+)$/gm, '<h4 class="chat-h4">$1</h4>');
  text = text.replace(/^## (.+)$/gm, '<h3 class="chat-h3">$1</h3>');
  text = text.replace(/(?:^|\n)&gt; (.+)/g, '<blockquote class="chat-quote">$1</blockquote>');
  text = text.replace(/^-{3,}$/gm, '<hr class="chat-hr">');

  // Numbered lists
  text = text.replace(/((?:^\d+\.\s+.+$\n?)+)/gm, (block) => {
    const items = block.trim().split("\n").filter(l => /^\d+\.\s+/.test(l));
    if (items.length < 1) return block;
    return '<ol class="chat-ol">' + items.map(l => `<li>${l.replace(/^\d+\.\s+/, "")}</li>`).join("") + "</ol>";
  });

  // Unordered lists
  text = text.replace(/((?:^[-*] .+$\n?)+)/gm, (block) => {
    const lines = block.split("\n").filter(l => /^[-*] /.test(l));
    if (lines.length < 1) return block;
    return '<ul class="chat-ul">' + lines.map(l => `<li>${l.replace(/^[-*] /, "")}</li>`).join("") + "</ul>";
  });

  // Phase 8: Line breaks (skip inside block elements)
  text = text.replace(/\n(?!<\/?(ul|ol|li|pre|code|table|tr|td|th|div|h[34]|blockquote|hr))/g, "<br>");
  return text;
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

function chatInputMetrics(value, config = LexaConfig) {
  const text = String(value || "");
  const max = Number(config?.MAX_CHAT_INPUT_LENGTH) || 4000;
  const warnAt = Number(config?.CHAR_COUNTER_WARN) || Math.floor(max * 0.75);
  const dangerAt = Math.min(Number(config?.CHAR_COUNTER_DANGER) || Math.floor(max * 0.95), max);
  const length = text.length;
  return {
    length,
    max,
    warn: length >= warnAt && length < dangerAt,
    danger: length >= dangerAt && length <= max,
    over: length > max,
    visible: length >= warnAt,
    label: `${length}/${max}`,
  };
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
  const text = chatInput.value.trim();
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
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  const regenBtn = document.createElement("button");
  regenBtn.type = "button";
  regenBtn.className = "msg-action-btn msg-regen-btn";
  setIconButton(regenBtn, "\u21BB", t("chat.regenerateTooltip"));
  regenBtn.addEventListener("click", () => regenerateMessage(text));
  header.appendChild(nameSpan);
  header.appendChild(timeSpan);
  header.appendChild(copyBtn);
  header.appendChild(regenBtn);

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
      LexaState.set("isLoading", false); sendBtn.disabled = false;
      window._lexaStreamAbort = null;
      window._lexaStreamAbortReason = "";
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
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const data = JSON.parse(raw);
            if (data.c) { fullText += data.c; scheduleStreamRender(); }
            if (data.done) { actionData = data.action; requiresConfirmation = data.rc; if (data.reply && !fullText) { fullText = data.reply; } streamError = null; }
          } catch (e) { console.warn("SSE parse error:", e, "raw:", raw); }
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
    }

    if (actionData) {
      if (requiresConfirmation) {
        // Show confirmation UI only for dangerous actions
        const actionDiv = document.createElement("div");
        actionDiv.className = "msg-action";
        const actionLabel = document.createElement("div");
        actionLabel.className = "action-label";
        actionLabel.textContent = t("chat.confirmationRequired");
        const actionCmd = document.createElement("div");
        actionCmd.className = "action-cmd";
        actionCmd.textContent = `${String(actionData.action)}(${JSON.stringify(actionData.params || {})})`;
        actionDiv.appendChild(actionLabel);
        actionDiv.appendChild(actionCmd);
        body.appendChild(actionDiv);

        const confirmBtn = document.createElement("button");
        confirmBtn.type = "button";
        confirmBtn.className = "confirm-btn";
        confirmBtn.textContent = t("chat.confirmBtn");
        confirmBtn.addEventListener("click", () => confirmAction(confirmBtn, encodeURIComponent(JSON.stringify(actionData))));
        const denyBtn = document.createElement("button");
        denyBtn.type = "button";
        denyBtn.className = "deny-btn";
        denyBtn.textContent = t("common.cancel");
        denyBtn.addEventListener("click", () => denyAction(denyBtn));
        body.appendChild(confirmBtn);
        body.appendChild(denyBtn);
      } else {
        // Execute action and show REAL result in chat (not just toast)
        try {
          const execResult = await window.lexa.execute(actionData.action, actionData.params || {});
          if (execResult.success) {
            // Extract human-readable result
            let resultText = "";
            const d = execResult.data;
            if (d && typeof d === "string") {
              resultText = d;
            } else if (d && typeof d === "object") {
              resultText = d.summary || d.message || d.error || "";
              if (!resultText) {
                // Format key-value pairs, skip internal fields
                const skip = new Set(["icon", "icon_code", "will_rain", "success"]);
                resultText = Object.entries(d).filter(([k, v]) => v && !skip.has(k)).map(([k, v]) => `${k}: ${v}`).join(". ");
              }
            }
            if (resultText) {
              // Replace AI placeholder text with actual result
              renderFormattedMessage(textEl, resultText);
              fullText = resultText;
            }
            showToast(t("chat.actionDoneToast", {action: actionData.action}), "success", 2500);
            sendNotification("Lexa AI", resultText || t("chat.actionDoneToast", {action: actionData.action}));
          } else {
            const errMsg = execResult.error || t("chat.actionFailedToast", {action: actionData.action});
            renderFormattedMessage(textEl, errMsg);
            fullText = errMsg;
            showToast(errMsg, "error", 3000);
          }
        } catch (e) {
          console.warn("[Chat] Action execution failed:", e.message || e);
          showToast(t("chat.errorPrefix", {msg: e.message || e}), "error", 3000);
        }
      }
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
    playTTS(actionData?.message || fullText);
  } catch (err) {
    streamRenderActive = false;
    textEl.classList.remove("streaming-text");
    textEl.textContent = t("chat.backendUnreachable");
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

// Multi-step signal words/patterns (German + English)
const _AGENT_PATTERNS = [
  // Sequential actions
  /\bund\s+(dann|danach|anschlie[sß]end)\b/i,
  /\bdanach\b/i,
  /\berstens\b.*\bzweitens\b/i,
  /\bschritt\s*\d/i,
  /\b(zuerst|erst)\b.*\b(dann|danach)\b/i,
  // Batch/bulk operations
  /\b(alle|saemtliche|jeden|jede|jedes)\b.*\b(und|dann|danach)\b/i,
  /\braeume?\s+(auf|auf\b|den|die|das|meinen?)/i,
  /\bsortiere?\b.*\bund\b/i,
  /\borganisiere?\b/i,
  /\bbereinige?\b/i,
  // Multi-target actions
  /\b(oeffne|starte|schliesse)\b.*\bund\b.*\b(oeffne|starte|schliesse)\b/i,
  // Analysis + action combos
  /\b(finde|suche|pruefe|check)\b.*\b(und|dann)\b.*\b(loesch|entfern|verschieb|kopier|erstell)/i,
  /\b(analysiere?|scanne?)\b.*\bund\b/i,
  // Backup + cleanup combos
  /\bbackup\b.*\bund\b/i,
  /\b(loesch|entfern)\b.*\bduplikat/i,
  // Explicit multi-step language
  /\bfuer\s+mich\b.*\b(alles|komplett|vollstaendig)\b/i,
  /\bmach\s+(alles|das\s+alles)\b/i,
  /kuemmere?\s+dich\s+um/i,
];

function _needsAgentMode(text) {
  if (!text || text.length < 15) return false;
  const lower = text.toLowerCase()
    .replace(/[äÄ]/g, "ae").replace(/[öÖ]/g, "oe")
    .replace(/[üÜ]/g, "ue").replace(/[ß]/g, "ss");
  return _AGENT_PATTERNS.some(p => p.test(lower));
}

// Triggered by auto-detection or /agent prefix
async function sendAgentMessage(text) {
  pushChatHistory(text);
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
  addMessage(text, "user");

  localStorage.setItem("lexa-chat-draft", "");
  chatInput.value = "";
  syncChatInputSize();
  LexaState.set("isLoading", true);
  sendBtn.disabled = true;
  if (isFirstMessage) autoTitleConversation(text);

  // Build agent message container
  const msgEl = document.createElement("div");
  msgEl.className = "message system-message agent-message";

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
  nameSpan.textContent = t("chat.systemNameLexa") + " Agent";
  const badge = document.createElement("span");
  badge.className = "agent-badge";
  badge.textContent = t("chat.agentBadge");
  header.appendChild(nameSpan);
  header.appendChild(badge);

  const stepsContainer = document.createElement("div");
  stepsContainer.className = "agent-steps";

  const summaryEl = document.createElement("div");
  summaryEl.className = "agent-summary";

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
  body.appendChild(stepsContainer);
  body.appendChild(summaryEl);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const response = await window.lexa.agentRun(text);
    if (agentStoppedByUser) {
      try { await response?.body?.cancel?.(); } catch (e) { console.warn("[Agent] Body cancel failed:", e.message || e); }
      throw new Error("agent_stream_stopped");
    }
    if (!response.ok) {
      summaryEl.textContent = t("chat.agentError", {msg: response.statusText || "Unknown"});
      LexaState.set("isLoading", false);
      sendBtn.disabled = false;
      stopBtn.disabled = true;
      stopBtn.classList.add("is-complete");
      return;
    }

    agentReader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const AGENT_STREAM_TIMEOUT_MS = 120000;
    const agentStreamStartedAt = Date.now();

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
            renderFormattedMessage(summaryEl, event.message || "");
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }

          if (event.type === "step_start") {
            const step = event.step || {};
            const stepEl = document.createElement("div");
            stepEl.className = "agent-step running";
            stepEl.id = `agent-step-${step.index}`;
            const icon = document.createElement("span");
            icon.className = "agent-step-icon";
            icon.textContent = "\u23F3"; // hourglass
            const label = document.createElement("span");
            label.className = "agent-step-label";
            label.textContent = `${step.action}(${Object.keys(step.params || {}).join(", ")})`;
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
              // Add duration
              if (step.duration_ms) {
                const dur = document.createElement("span");
                dur.className = "agent-step-duration";
                dur.textContent = `${Math.round(step.duration_ms)}ms`;
                stepEl.appendChild(dur);
              }
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
            }
          }

          if (event.type === "done") {
            const run = event.run || {};
            if (run.summary) {
              renderFormattedMessage(summaryEl, run.summary);
            }
            const durEl = document.createElement("div");
            durEl.className = "agent-duration";
            durEl.textContent = t("chat.agentSteps", {count: run.steps?.length || 0, ms: Math.round(run.total_duration_ms || 0)});
            body.appendChild(durEl);
          }

          if (event.type === "error") {
            summaryEl.textContent = event.message || t("chat.agentErrorGeneric");
          }
        } catch (e) {
          console.warn("[Agent] SSE parse error:", e);
        }
      }
    }
  } catch (err) {
    const timedOut = err?.message === "agent_stream_timeout";
    const stopped = err?.message === "agent_stream_stopped" || agentStoppedByUser;
    summaryEl.textContent = stopped ? t("chat.agentStopped") : (timedOut ? t("chat.agentTimeout") : t("chat.agentUnreachable"));
    if (!stopped) showToast(timedOut ? t("chat.agentTimeout") : t("chat.agentErrorGeneric"), "error");
  }

  agentReader = null;
  stopBtn.disabled = true;
  stopBtn.classList.add("is-complete");
  saveChatHistory();
  saveCurrentConversation();
  LexaState.set("isLoading", false);
  sendBtn.disabled = false;
}

async function regenerateMessage(originalPrompt) {
  if (LexaState.get("isLoading") || !LexaState.get("backendOnline")) return;
  // Remove last system message
  const msgs = chatMessages.querySelectorAll(".message.system-message");
  if (msgs.length > 0) msgs[msgs.length - 1].remove();
  // Re-send the original message
  chatInput.value = originalPrompt;
  await sendMessage();
}

async function confirmAction(btn, actionStr) {
  const action = JSON.parse(decodeURIComponent(actionStr));
  btn.textContent = t("chat.executing");
  btn.disabled = true;
  // Clear pending confirmation on the backend (user clicked the button)
  try { await fetch(`${window.lexa.API_BASE}/chat/confirm-clear`, { method: "POST" }); } catch (_) {}
  try {
    const res = await window.lexa.execute(action.action, action.params || {}, true);
    if (res.success) { addMessage(t("chat.executed", {data: JSON.stringify(res.data).substring(0, 200)}), "system"); showToast(t("chat.actionExecuted", {action: action.action}), "success"); }
    else { addMessage(t("common.error") + ": " + res.error, "system"); showToast(t("chat.actionFailed", {action: action.action}), "error"); }
  } catch (e) { console.error("[Chat] Confirm action execution error:", e.message || e); addMessage(t("chat.executionErrorMsg"), "system"); showToast(t("toast.executionError"), "error"); }
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

const LEXA_COMPOSER_COMMANDS = [
  { id: "agent", icon: "command", prefixKey: "composer.agent.prefix", labelKey: "composer.agent.label", descKey: "composer.agent.desc", fallbackPrefix: "/agent ", fallbackLabel: "Agent Mode", fallbackDesc: "Plan and execute a multi-step task." },
  { id: "improve", icon: "spark", prefixKey: "composer.improve.prefix", labelKey: "composer.improve.label", descKey: "composer.improve.desc", fallbackPrefix: "/agent Verbessere Lexa UI/UX mit kleinen sicheren Code-Aenderungen und fuehre passende Tests aus: ", fallbackLabel: "Improve Lexa", fallbackDesc: "Start a professional UI/UX code pass." },
  { id: "os", icon: "map", prefixKey: "composer.os.prefix", labelKey: "composer.os.label", descKey: "composer.os.desc", fallbackPrefix: "Nutze das Personal OS als Kontext und fasse zusammen: ", fallbackLabel: "Personal OS", fallbackDesc: "Bring OS context into the current chat." },
  { id: "screen", icon: "image", prefixKey: "composer.screen.prefix", labelKey: "composer.screen.label", descKey: "composer.screen.desc", fallbackPrefix: "Analysiere den Bildschirm und gib mir konkrete UI/UX-Verbesserungen: ", fallbackLabel: "Screen Review", fallbackDesc: "Prepare a visual review prompt." },
  { id: "voice", icon: "wave", prefixKey: "composer.voice.prefix", labelKey: "composer.voice.label", descKey: "composer.voice.desc", fallbackPrefix: "Pruefe Voice/STT/TTS/Wake-Word-Status und nenne die naechsten echten Blocker: ", fallbackLabel: "Voice Check", fallbackDesc: "Focus on diagnostics instead of demo feel." },
];

function composerCommandText(command, field) {
  const key = command?.[`${field}Key`];
  const fallback = command?.[`fallback${field[0].toUpperCase()}${field.slice(1)}`] || "";
  if (!key) return fallback;
  const translated = t(key);
  return translated === key ? fallback : translated;
}

function composerCommandLabel(command) { return composerCommandText(command, "label"); }
function composerCommandDesc(command) { return composerCommandText(command, "desc"); }
function composerCommandPrefix(command) { return composerCommandText(command, "prefix"); }

let _composerCommandOpen = false;
let _composerCommandIdx = 0;

function composerCommandIconSvg(icon) {
  const icons = {
    command: '<path d="M18 6 6 18"/><path d="m8 6 4 6-4 6"/><path d="M14 18h4"/>',
    spark: '<path d="M12 2l1.8 6.1L20 10l-6.2 1.9L12 18l-1.8-6.1L4 10l6.2-1.9L12 2Z"/><path d="M19 15l.9 3.1L23 19l-3.1.9L19 23l-.9-3.1L15 19l3.1-.9L19 15Z"/>',
    map: '<path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2V6Z"/><path d="M9 4v14"/><path d="M15 6v14"/>',
    image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="10" r="1.5"/><path d="M21 15l-5-5L5 19"/>',
    wave: '<path d="M4 12h2l2-6 4 12 3-8 2 2h3"/>',
  };
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${icons[icon] || icons.command}</svg>`;
}

function composerCommandQuery() {
  const value = String(chatInput?.value || "");
  if (!value.startsWith("/")) return "";
  return value.slice(1).split(/\s+/)[0].toLowerCase();
}

function composerCommandMatches(command, query) {
  if (!query) return true;
  const haystack = `${command.id} ${composerCommandPrefix(command)} ${composerCommandLabel(command)} ${composerCommandDesc(command)}`.toLowerCase();
  return haystack.includes(query);
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
  const items = LEXA_COMPOSER_COMMANDS.filter((command) => composerCommandMatches(command, query));
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
    const prefix = composerCommandPrefix(command);
    const prefixHint = prefix.trim().split(/\s+/)[0] || "/";
    const row = document.createElement("button");
    row.type = "button";
    row.id = `composer-command-option-${command.id}`;
    row.className = "composer-command-item" + (index === _composerCommandIdx ? " selected" : "");
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", index === _composerCommandIdx ? "true" : "false");
    row.setAttribute("aria-label", `${label}: ${desc}`);
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

function voiceStatusBarUpdate({ state, transcript, provider, latency } = {}) {
  if (typeof VoiceStatusBar === "undefined") return;
  if (state === "speaking") {
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
    voiceStatusBarUpdate({ state: "processing", provider: "STT" });
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
  voiceStatusBarUpdate({ state: "processing", transcript: voiceUiText("chat.voiceTranscribing", "Transcribing speech..."), provider: "STT" });

  // Auto-open chat so user sees results
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();

  try {
    // 1. STT
    console.log("[Voice] Sending to STT, blob size:", blob.size);
    const stt = await window.lexa.stt(blob);
    console.log("[Voice] STT result:", stt);

    if (!stt.success || !stt.text || !stt.text.trim()) {
      voiceStatusBarUpdate({ state: "error", transcript: voiceUiText("chat.voiceNotUnderstood", "Could not understand."), provider: stt.engine || "STT" });
      showToast(voiceUiText("chat.voiceNotUnderstoodFull", "Could not understand. Please try again."), "warning", 2500);
      updateMicProcessingA11y(false);
      return;
    }

    voiceStatusBarUpdate({ state: "processing", transcript: stt.text, provider: stt.engine || "STT" });

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
    voiceStatusBarUpdate({ state: "processing", provider: "AI", transcript: text });
    const abort = new AbortController();
    timeout = setTimeout(() => abort.abort(), 45000);

    const resp = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
      addMessage(fullText, "system", action, requiresConfirmation, true);
      if (action && !requiresConfirmation) {
        window.lexa.execute(action.action, action.params || {}).catch(() => {});
      }
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
    if (ambient) showOrbTranscript(undefined, res.reply);
    addMessage(res.reply, "system", res.action, res.requires_confirmation, ambient);
    playTTS(res.reply);
    if (res.action && !res.requires_confirmation) {
      window.lexa.execute(res.action.action, res.action.params || {}).then((execResult) => {
        if (execResult.success) {
          // Show REAL result in chat, not just AI text
          let resultText = "";
          const d = execResult.data;
          if (d && typeof d === "string") resultText = d;
          else if (d && typeof d === "object") {
            resultText = d.summary || d.message || d.error || "";
            if (!resultText) {
              const skip = new Set(["icon", "icon_code", "will_rain", "success"]);
              resultText = Object.entries(d).filter(([k, v]) => v && !skip.has(k)).map(([k, v]) => `${k}: ${v}`).join(". ");
            }
          }
          if (resultText) {
            // Find last system message and update its text
            const msgs = chatMessages.querySelectorAll(".system-message .msg-text");
            if (msgs.length > 0) {
              const lastMsg = msgs[msgs.length - 1];
              renderFormattedMessage(lastMsg, resultText);
            }
          }
          showToast(t("chat.actionDoneToast", {action: res.action.action}), "success", 2500);
          sendNotification("Lexa AI", resultText || t("chat.actionDoneToast", {action: res.action.action}));
        }
        else { showToast(execResult.error || t("chat.actionFailedToast", {action: res.action.action}), "error", 3000); }
      }).catch((e) => { console.warn("[Chat] Action execution failed:", e.message || e); showToast(t("toast.executionError"), "error"); });
    }
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

  const hour = new Date().getHours();
  const _starters = _getConversationStarters();
  let starters;
  if (hour >= 6 && hour < 12) starters = _starters.morning;
  else if (hour >= 12 && hour < 18) starters = _starters.afternoon;
  else if (hour >= 18 && hour < 22) starters = _starters.evening;
  else if (hour >= 22 || hour < 6) starters = _starters.night;
  else starters = _starters.general;

  grid.innerHTML = "";
  starters.forEach(s => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "starter-card";
    card.setAttribute("aria-label", `${s.title}: ${s.text}`);
    const iconEl = document.createElement("span");
    iconEl.className = "starter-icon";
    iconEl.dataset.icon = s.icon;
    iconEl.innerHTML = starterIconSvg(s.icon);
    iconEl.setAttribute("aria-hidden", "true");
    const content = document.createElement("div");
    content.className = "starter-content";
    const titleEl = document.createElement("span");
    titleEl.className = "starter-title";
    titleEl.textContent = s.title;
    const descEl = document.createElement("span");
    descEl.className = "starter-desc";
    descEl.textContent = s.text;
    content.appendChild(titleEl);
    content.appendChild(descEl);
    card.appendChild(iconEl);
    card.appendChild(content);
    card.addEventListener("click", () => {
      chatInput.value = s.msg;
      // Hide starters
      const container = document.getElementById("conversation-starters");
      if (container) container.classList.add("hidden");
      sendMessage();
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

function renderConversationList() {
  const container = document.getElementById("conversation-list");
  if (!container) return;
  const convList = LexaState.get("conversationsList") || [];
  if (typeof updateConversationCount === "function") {
    updateConversationCount(convList.length);
  }
  if (convList.length === 0) { container.innerHTML = '<div class="conv-empty">' + escapeHtml(t("chat.noConversations")) + '</div>'; return; }
  container.innerHTML = "";
  convList.forEach(c => {
    const isActive = c.id === LexaState.get("currentConversationId");
    const title = c.title.length > 28 ? c.title.substring(0, 28) + "\u2026" : c.title;
    const count = c.message_count || 0;
    const item = document.createElement("div");
    item.className = "conv-item" + (isActive ? " active" : "");
    item.dataset.convId = c.id;
    item.title = c.title;
    item.setAttribute("aria-current", isActive ? "page" : "false");
    const content = document.createElement("div");
    content.className = "conv-item-content";
    const titleEl = document.createElement("div");
    titleEl.className = "conv-title";
    titleEl.textContent = title;
    content.appendChild(titleEl);
    if (c.last_message) { const preview = document.createElement("div"); preview.className = "conv-preview"; preview.textContent = c.last_message.substring(0, 50) + (c.last_message.length > 50 ? "\u2026" : ""); content.appendChild(preview); }
    const meta = document.createElement("div");
    meta.className = "conv-meta";
    meta.textContent = t("chat.messageCount", {count});
    content.appendChild(meta);
    const actions = document.createElement("div");
    actions.className = "conv-actions";
    const exportBtn = document.createElement("button");
    exportBtn.type = "button";
    exportBtn.className = "conv-action-btn";
    exportBtn.title = t("chat.export");
    exportBtn.setAttribute("aria-label", t("chat.exportConversationLabel", { title: c.title }));
    exportBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
    exportBtn.addEventListener("click", (e) => { e.stopPropagation(); exportConversation(c.id); });
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "conv-delete-btn";
    delBtn.title = t("common.delete");
    delBtn.setAttribute("aria-label", t("chat.deleteConversationLabel", { title: c.title }));
    delBtn.textContent = "\u00d7";
    delBtn.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(c.id); });
    actions.appendChild(exportBtn);
    actions.appendChild(delBtn);
    item.appendChild(content);
    item.appendChild(actions);
    bindKeyboardAction(item, () => switchConversation(c.id), {
      label: t("chat.openConversationLabel", { title: c.title, count }),
    });
    container.appendChild(item);
  });
}
async function newConversation() {
  try {
    const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
    LexaState.set("currentConversationId", result.id);
    localStorage.setItem("lexa-active-conversation", result.id);
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m) => m.remove());
    await window.lexa.historyClear();
    // Restore hero greeting view — orb always stays visible
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
    // Show conversation starters again on new chat
    const startersEl = document.getElementById("conversation-starters");
    if (startersEl) { startersEl.classList.remove("hidden"); renderConversationStarters(); }
    const data = await window.lexa.conversations();
    LexaState.set("conversationsList", data.conversations || []);
    if (typeof updateConversationCount === "function") {
      updateConversationCount(LexaState.get("conversationsList").length);
    }
    renderConversationList();
    switchView("chat");
    chatInput.focus();
    showToast(t("toast.newChatStarted"), "info", 2000);
  } catch (e) { console.warn("[Chat] Failed to create new conversation:", e.message || e); showToast(t("toast.createError"), "error"); }
}
async function switchConversation(convId, notify = true) {
  if (convId === LexaState.get("currentConversationId") && notify) return;
  await saveCurrentConversation();
  LexaState.set("currentConversationId", convId);
  localStorage.setItem("lexa-active-conversation", convId);
  try {
    const conv = await window.lexa.conversationGet(convId);
    if (!conv || conv.detail) { if (notify) showToast(t("toast.convNotFound"), "error"); return; }
    await window.lexa.conversationLoad(convId);
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m) => m.remove());
    const messages = conv.messages || [];
    for (const msg of messages) addMessage(msg.content, msg.role === "user" ? "user" : "system", null, false, true);
    renderConversationList();
    if (notify) {
      switchView("chat");
      // Open chat view to show loaded conversation
      if (!window._chatViewOpen && messages.length > 0) toggleChatView();
      showToast(t("chat.chatLoaded", {title: conv.title}), "info", 1500);
    }
  } catch (e) { console.warn("[Chat] Failed to switch conversation:", e.message || e); if (notify) showToast(t("toast.loadError"), "error"); }
}
async function saveCurrentConversation() {
  if (!LexaState.get("currentConversationId")) return;
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg) => {
    if (!isPersistableChatMessage(msg)) return;
    const text = getMessagePersistText(msg);
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    if (text) messages.push({ role, content: text });
  });
  try {
    await window.lexa.conversationUpdate(LexaState.get("currentConversationId"), { messages });
    await refreshConversationSidebar();
  } catch (e) { console.warn("[Chat] Failed to save conversation:", e.message || e); }
}
async function deleteConversation(convId) {
  try {
    await window.lexa.conversationDelete(convId);
    if (convId === LexaState.get("currentConversationId")) LexaState.set("currentConversationId", null);
    const data = await window.lexa.conversations();
    LexaState.set("conversationsList", data.conversations || []);
    const convList = LexaState.get("conversationsList");
    if (typeof updateConversationCount === "function") {
      updateConversationCount(convList.length);
    }
    renderConversationList();
    if (convId === parseInt(localStorage.getItem("lexa-active-conversation"))) {
      if (convList.length > 0) await switchConversation(convList[0].id);
      else await newConversation();
    }
    showToast(t("toast.chatDeleted"), "info", 2000);
  } catch (e) { console.warn("[Chat] Failed to delete conversation:", e.message || e); showToast(t("toast.deleteError"), "error"); }
}
async function autoTitleConversation(userMessage) {
  const convId = LexaState.get("currentConversationId");
  if (!convId) return;
  let title = userMessage.trim();
  if (title.length > 40) title = title.substring(0, 40) + "\u2026";
  if (!title) title = t("chat.newChatTitle");
  try { await window.lexa.conversationUpdate(convId, { title }); const convList = LexaState.get("conversationsList") || []; const conv = convList.find(c => c.id === convId); if (conv) conv.title = title; renderConversationList(); } catch (e) { console.warn("[Chat] Failed to set conversation title:", e.message || e); }
  try { const result = await window.lexa.generateTitle(userMessage); if (result.title && result.title !== title) { title = result.title; await window.lexa.conversationUpdate(convId, { title }); const convList = LexaState.get("conversationsList") || []; const conv = convList.find(c => c.id === convId); if (conv) conv.title = title; renderConversationList(); } } catch (e) { console.warn("[Chat] Failed to generate AI title:", e.message || e); }
}

// ── DRAG & DROP + FILE UPLOAD ────────────────────
let dragCounter = 0;
function setupDragDrop() {
  const chatContainer = document.getElementById("chat-container");
  const overlay = document.getElementById("drop-zone-overlay");
  if (!chatContainer || !overlay) return;
  chatContainer.addEventListener("dragenter", (e) => { e.preventDefault(); dragCounter++; overlay.classList.add("visible"); });
  chatContainer.addEventListener("dragleave", (e) => { e.preventDefault(); dragCounter--; if (dragCounter <= 0) { dragCounter = 0; overlay.classList.remove("visible"); } });
  chatContainer.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  chatContainer.addEventListener("drop", (e) => { e.preventDefault(); dragCounter = 0; overlay.classList.remove("visible"); const files = e.dataTransfer.files; if (files.length > 0) handleFileUpload(files[0]); });
}
function triggerFileUpload() { document.getElementById("file-input")?.click(); }
function handleFileSelect(event) { const file = event.target.files?.[0]; if (file) handleFileUpload(file); event.target.value = ""; }

function fileUploadSizeLabel(file) {
  if (file.size < 1024) return `${file.size} B`;
  if (file.size < 1048576) return `${(file.size / 1024).toFixed(1)} KB`;
  return `${(file.size / 1048576).toFixed(1)} MB`;
}

function fileUploadExtension(file) {
  return file.name.includes(".") ? file.name.split(".").pop().toUpperCase() : "FILE";
}

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
  const parts = [
    String(fileInfo.type || "file").toUpperCase(),
    `${fileInfo.size_kb || 0} KB`,
  ];
  if (fileInfo.line_count) parts.push(t("chat.fileLines", {count: fileInfo.line_count}));
  badge.textContent = parts.join(" · ");
  return badge;
}

function addFileUploadResponse(res) {
  addMessage(res.reply || "", "system", res.action, res.requires_confirmation);
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
      if (res.action && !res.requires_confirmation) { try { const execResult = await window.lexa.execute(res.action.action, res.action.params || {}); if (execResult.success) { showToast(t("chat.actionDoneToast", {action: res.action.action}), "success", 2500); } else { showToast(execResult.error || t("chat.actionFailedToast", {action: res.action.action}), "error", 3000); } } catch (e) { console.warn("[Chat] File upload action execution failed:", e.message || e); showToast(t("toast.executionError"), "error"); } }
      playTTS(res.reply);
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

// ── AI MODEL SELECTION ───────────────────────────
async function loadModelSelection() {
  try {
    const data = await window.lexa.aiModels();
    const select = document.getElementById("model-select");
    if (!select || !data.available) return;
    select.innerHTML = "";
    if (data.grouped) {
      for (const group of Object.values(data.grouped)) {
        const optgroup = document.createElement("optgroup");
        optgroup.label = group.label;
        for (const [id, name] of Object.entries(group.models || {})) {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = name;
          if (id === data.current) opt.selected = true;
          optgroup.appendChild(opt);
        }
        select.appendChild(optgroup);
      }
    } else {
      for (const [id, name] of Object.entries(data.available)) {
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = name;
        if (id === data.current) opt.selected = true;
        select.appendChild(opt);
      }
    }
    const desc = document.getElementById("model-desc");
    if (desc) desc.textContent = `Aktiv: ${data.current_name}`;
  } catch (e) { console.warn("[Chat] Failed to load model selection:", e.message || e); }
}
async function changeAiModel(modelId) {
  try { const result = await window.lexa.setAiModel(modelId); showToast(result.status || t("chat.modelChanged"), "success"); const desc = document.getElementById("model-desc"); if (desc && result.current) desc.textContent = `Aktiv: ${result.current.current_name}`; }
  catch (e) { console.warn("[Chat] Failed to change AI model:", e.message || e); showToast(t("toast.modelChangeFailed"), "error"); }
}
