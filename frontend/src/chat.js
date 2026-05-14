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

// ── CHAT PERSISTENCE ─────────────────────────────
// Data flow: SQLite (backend) = single source of truth.
// localStorage = session cache only (max CHAT_HISTORY_LOCAL_MAX messages).
// saveChatHistory() writes to localStorage as a fast local cache.
// loadChatHistory() tries backend conversation first, falls back to localStorage.
function saveChatHistory() {
  if (!chatMessages) return;
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg, i) => {
    if (i === 0) return;
    const text = msg.querySelector(".msg-text")?.textContent || "";
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
    chatMessages.querySelectorAll(".message").forEach((msg, i) => {
      if (i === 0) return;
      const text = msg.querySelector(".msg-text")?.textContent || "";
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
  msgs.forEach((m, i) => { if (i > 0) m.remove(); });
  localStorage.removeItem("lexa-chat-history");
  if (LexaState.get("currentConversationId")) {
    window.lexa.conversationUpdate(LexaState.get("currentConversationId"), { messages: [] }).catch(() => { });
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
  copyBtn.className = "msg-copy-btn";
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  header.appendChild(nameSpan);
  header.appendChild(timeSpan);

  if (!isUser) {
    // Thumbs-up to save as memory
    const thumbsBtn = document.createElement("button");
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
          if (i > 0) allMsgs[i].remove(); // Keep greeting (index 0)
        }
      }
      showToast(t("chat.editLoaded"), "info", 2000);
    });
    header.appendChild(editBtn);

    // Delete button for user messages
    const delBtn = document.createElement("button");
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
    confirmBtn.className = "confirm-btn";
    confirmBtn.textContent = t("chat.confirmBtn");
    confirmBtn.addEventListener("click", () => confirmAction(confirmBtn, encodeURIComponent(JSON.stringify(action))));
    const denyBtn = document.createElement("button");
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
    codeBlocks.push(`<div class="code-block-wrap"><div class="code-block-header">${langLabel}<button class="code-copy-btn" data-action="copy-code" title="${copyLabel}" aria-label="${copyLabel}" data-icon="&#x2398;"></button></div><pre class="code-block"><code>${escaped}</code></pre></div>`);
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

function syncChatInputSize() {
  if (!chatInput) return;
  chatInput.classList.toggle("has-content", Boolean(chatInput.value));
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
  stopBtn.className = "stop-thinking-btn";
  stopBtn.textContent = "\u25A0 Stop";
  stopBtn.title = "Antwort abbrechen";
  stopBtn.addEventListener("click", () => {
    if (window._lexaStreamAbort) {
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
  LexaState.set("isLoading", true);
  if (text.length > LexaConfig.MAX_CHAT_INPUT_LENGTH) { showToast(t("chat.messageTooLong", {max: LexaConfig.MAX_CHAT_INPUT_LENGTH}), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
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
  copyBtn.className = "msg-copy-btn";
  setIconButton(copyBtn, "\u2398", t("chat.copyTooltip"));
  copyBtn.addEventListener("click", () => copyMessage(copyBtn));
  const regenBtn = document.createElement("button");
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
    const _streamTimeout = setTimeout(() => window._lexaStreamAbort.abort(), 45000);
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
        streamRenderActive = false;
        textEl.classList.remove("streaming-text");
        textEl.textContent = t("chat.connectionTimeout");
        LexaState.set("isLoading", false); sendBtn.disabled = false;
        return;
      }
      throw abortErr;
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      streamRenderActive = false;
      textEl.classList.remove("streaming-text");
      let errMsg = errData.detail || t("common.connectionError");
      if (response.status === 429) { errMsg = t("chat.tooManyRequestsShort"); showToast(t("toast.rateLimitReached"), "warning"); }
      else if (response.status === 503) errMsg = t("chat.backendOverloaded");
      else if (response.status >= 500) errMsg = t("common.error") + ` (${response.status})`;
      renderFormattedMessage(textEl, errMsg);
      LexaState.set("isLoading", false); sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamError = null;
    const streamStart = Date.now();
    const STREAM_TIMEOUT_MS = 45000;
    try {
      while (true) {
        if (Date.now() - streamStart > STREAM_TIMEOUT_MS) {
          console.warn("[LEXA] Stream timeout after 45s");
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
    } catch (streamErr) { streamError = streamErr; console.warn("[LEXA] Stream unterbrochen:", streamErr); try { await reader.cancel(); } catch (e) { console.warn("[Chat] Reader cancel failed:", e.message || e); } }

    clearTimeout(_streamTimeout);
    streamRenderActive = false;
    textEl.classList.remove("streaming-text");
    if (fullText) {
      renderFormattedMessage(textEl, fullText);
      if (streamError) { const warn = document.createElement("span"); warn.className = "stream-warning"; warn.textContent = "\u26A0 " + t("chat.connectionInterrupted"); textEl.appendChild(warn); }
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
        confirmBtn.className = "confirm-btn";
        confirmBtn.textContent = t("chat.confirmBtn");
        confirmBtn.addEventListener("click", () => confirmAction(confirmBtn, encodeURIComponent(JSON.stringify(actionData))));
        const denyBtn = document.createElement("button");
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

  body.appendChild(header);
  body.appendChild(stepsContainer);
  body.appendChild(summaryEl);
  msgEl.appendChild(avatar);
  msgEl.appendChild(body);
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const response = await window.lexa.agentRun(text);
    if (!response.ok) {
      summaryEl.textContent = t("chat.agentError", {msg: response.statusText || "Unknown"});
      LexaState.set("isLoading", false);
      sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
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
    summaryEl.textContent = t("chat.agentUnreachable");
    showToast(t("chat.agentErrorGeneric"), "error");
  }

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
  silenceTimer: null,
  recordTimeout: null,
  audioCtx: null,
};

// ── SETUP (called once from app.js init) ──
function setupVoice() {
  const mic = document.getElementById("mic-btn");
  const tts = document.getElementById("tts-toggle");

  if (mic) {
    mic.addEventListener("click", voiceToggle);
    console.log("[Voice] Mic button ready");
  } else {
    console.warn("[Voice] mic-btn not found in DOM");
  }

  if (tts) {
    tts.classList.toggle("active", LexaState.get("ttsEnabled"));
    tts.addEventListener("click", () => {
      const on = !LexaState.get("ttsEnabled");
      LexaState.set("ttsEnabled", on);
      tts.classList.toggle("active", on);
      showToast(on ? "Sprachausgabe an" : "Sprachausgabe aus", "info", 1500);
    });
  }
}

// ── MIC TOGGLE ──
function voiceToggle() {
  if (Voice.recording) voiceStop(); else voiceStart();
}

// ── START RECORDING ──
async function voiceStart() {
  const mic = document.getElementById("mic-btn");
  try {
    Voice.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showToast("Mikrofon-Zugriff verweigert", "error");
    return;
  }

  Voice.audioChunks = [];
  Voice.mediaRecorder = new MediaRecorder(Voice.stream, { mimeType: "audio/webm" });
  Voice.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) Voice.audioChunks.push(e.data); };
  Voice.mediaRecorder.onstop = () => voiceProcess();
  Voice.mediaRecorder.start();
  Voice.recording = true;
  LexaState.set("isRecording", true);

  if (mic) mic.classList.add("recording");

  // Silence detection
  voiceStartSilenceDetect(Voice.stream);

  // Safety: max 30s
  Voice.recordTimeout = setTimeout(() => { if (Voice.recording) voiceStop(); }, 30000);

  console.log("[Voice] Recording started");
}

// ── STOP RECORDING ──
function voiceStop() {
  const mic = document.getElementById("mic-btn");
  if (Voice.silenceTimer) { clearInterval(Voice.silenceTimer); Voice.silenceTimer = null; }
  if (Voice.recordTimeout) { clearTimeout(Voice.recordTimeout); Voice.recordTimeout = null; }
  if (Voice.mediaRecorder && Voice.mediaRecorder.state !== "inactive") Voice.mediaRecorder.stop();
  if (Voice.stream) { Voice.stream.getTracks().forEach(t => t.stop()); Voice.stream = null; }
  Voice.recording = false;
  LexaState.set("isRecording", false);
  if (mic) mic.classList.remove("recording");
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
  const blob = new Blob(Voice.audioChunks, { type: "audio/webm" });
  if (blob.size < 100) { showToast("Keine Aufnahme", "warning"); return; }

  const mic = document.getElementById("mic-btn");
  if (mic) mic.classList.add("processing");

  // Auto-open chat so user sees results
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();

  try {
    // 1. STT
    console.log("[Voice] Sending to STT, blob size:", blob.size);
    const stt = await window.lexa.stt(blob);
    console.log("[Voice] STT result:", stt);

    if (!stt.success || !stt.text || !stt.text.trim()) {
      showToast("Konnte nichts verstehen — nochmal versuchen", "warning", 2500);
      if (mic) mic.classList.remove("processing");
      return;
    }

    // Show user text in chat
    addMessage(stt.text, "user", null, false, true);

    // 2. AI Chat (streaming)
    console.log("[Voice] Sending to AI:", stt.text);
    if (mic) mic.classList.remove("processing");

    await voiceStreamChat(stt.text);

  } catch (e) {
    console.error("[Voice] Pipeline error:", e);
    showToast("Sprachfehler: " + (e.message || e), "error");
    if (mic) mic.classList.remove("processing");
  }
}

// ── STREAMING CHAT + TTS ──
async function voiceStreamChat(text) {
  const API = "http://127.0.0.1:8000";
  let fullText = "";
  let action = null;
  let requiresConfirmation = false;

  try {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 45000);

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
      clearTimeout(timeout);
      return;
    }

    const reader = resp.body.getReader();
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
            // TTS at sentence boundaries
            const m = ttsBuf.match(/^(.*[.!?\n])\s*/s);
            if (m && m[1].trim().length > 10) {
              voiceTTSEnqueue(m[1].trim());
              ttsBuf = ttsBuf.slice(m[0].length);
            }
          }
          if (d.done) {
            action = d.action || null;
            requiresConfirmation = d.rc || false;
            if (ttsBuf.trim()) { voiceTTSEnqueue(ttsBuf.trim()); ttsBuf = ""; }
          }
        } catch (_) {}
      }
    }

    clearTimeout(timeout);

    if (fullText) {
      addMessage(fullText, "system", action, requiresConfirmation, true);
      if (action && !requiresConfirmation) {
        window.lexa.execute(action.action, action.params || {}).catch(() => {});
      }
    }

  } catch (e) {
    console.warn("[Voice] Stream failed, fallback:", e);
    try {
      const fb = await window.lexa.chat(text);
      handleChatResponse(fb, true);
    } catch (_) {
      addMessage("Verbindungsfehler — Backend nicht erreichbar.", "system");
    }
  }
}

// ── TTS QUEUE ──
function voiceTTSEnqueue(text) {
  if (!LexaState.get("ttsEnabled") || !text) return;
  Voice.ttsQueue.push(text);
  if (!Voice.ttsPlaying) voiceTTSNext();
}

async function voiceTTSNext() {
  if (Voice.ttsQueue.length === 0) { Voice.ttsPlaying = false; return; }
  Voice.ttsPlaying = true;
  const text = Voice.ttsQueue.shift();
  try {
    const url = await window.lexa.tts(text);
    if (url) {
      const audio = new Audio(url);
      audio.onended = () => { URL.revokeObjectURL(url); voiceTTSNext(); };
      audio.onerror = () => { URL.revokeObjectURL(url); voiceTTSNext(); };
      audio.play().catch(() => voiceTTSNext());
    } else {
      voiceTTSNext();
    }
  } catch (e) {
    console.warn("[TTS] Error:", e);
    voiceTTSNext();
  }
}

function voiceTTSClear() {
  Voice.ttsQueue.length = 0;
  Voice.ttsPlaying = false;
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
  const label = active ? "Stopp" : "Mit Lexa sprechen";
  btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="talk-btn-icon">' + icon + '</svg>' + label;
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
      { icon: "\u2600\uFE0F", title: t("chat.starterDayPlan"), text: t("chat.starterDayPlanDesc"), msg: t("chat.starterMsgDayPlan") },
      { icon: "\uD83D\uDCE7", title: t("chat.starterEmails"), text: t("chat.starterEmailsDesc"), msg: t("chat.starterMsgEmails") },
      { icon: "\uD83D\uDCCB", title: t("chat.starterTodos"), text: t("chat.starterTodosDescMorning"), msg: t("chat.starterMsgTodos") },
      { icon: "\uD83D\uDCBB", title: t("chat.starterSystem"), text: t("chat.starterSystemDesc"), msg: t("chat.starterMsgSysteminfo") },
    ],
    afternoon: [
      { icon: "\u23F1\uFE0F", title: t("chat.starterPomodoro"), text: t("chat.starterPomodoroDesc"), msg: t("chat.starterMsgPomodoro") },
      { icon: "\uD83D\uDCCB", title: t("chat.starterTodos"), text: t("chat.starterTodosDescAfternoon"), msg: t("chat.starterMsgTodos") },
      { icon: "\uD83C\uDFB5", title: t("chat.starterMusic"), text: t("chat.starterMusicDescWork"), msg: t("chat.starterMsgFocusMusic") },
      { icon: "\uD83D\uDCBB", title: t("chat.starterSystem"), text: t("chat.starterSystemDescPerf"), msg: t("chat.starterMsgSysteminfo") },
    ],
    evening: [
      { icon: "\uD83D\uDCCA", title: t("chat.starterReview"), text: t("chat.starterReviewDesc"), msg: t("chat.starterMsgWhatDone") },
      { icon: "\uD83C\uDFB5", title: t("chat.starterMusic"), text: t("chat.starterMusicDescChill"), msg: t("chat.starterMsgChillMusic") },
      { icon: "\uD83E\uDDF9", title: t("chat.starterCleanup"), text: t("chat.starterCleanupDesc"), msg: t("chat.starterMsgCleanDownloads") },
      { icon: "\uD83D\uDCDD", title: t("chat.starterNotes"), text: t("chat.starterNotesDesc"), msg: t("chat.starterMsgShowNotes") },
    ],
    night: [
      { icon: "\uD83C\uDF19", title: t("chat.starterNightMode"), text: t("chat.starterNightModeDesc"), msg: t("chat.starterMsgQuieter") },
      { icon: "\uD83D\uDCDD", title: t("chat.starterNotes"), text: t("chat.starterNotesDescNight"), msg: t("chat.starterMsgShowNotes") },
      { icon: "\u23F1\uFE0F", title: t("chat.starterTimer"), text: t("chat.starterTimerDesc"), msg: t("chat.starterMsgTimer30") },
      { icon: "\uD83D\uDCAC", title: t("chat.starterSmalltalk"), text: t("chat.starterSmalltalkDesc"), msg: t("chat.starterMsgHowAreYou") },
    ],
    general: [
      { icon: "\uD83D\uDD25", title: t("chat.starterQuickStart"), text: t("chat.starterQuickStartDesc"), msg: t("chat.starterMsgWhatCanYouDo") },
      { icon: "\uD83D\uDCCB", title: t("chat.starterTodos"), text: t("chat.starterTodosDescGeneral"), msg: t("chat.starterMsgTodos") },
      { icon: "\uD83C\uDFB5", title: t("chat.starterMusic"), text: t("chat.starterMusicDescGeneral"), msg: t("chat.starterMsgGoodMusic") },
      { icon: "\uD83D\uDCBB", title: t("chat.starterSystem"), text: t("chat.starterSystemDescGeneral"), msg: t("chat.starterMsgSysteminfo") },
    ],
  };
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
    card.className = "starter-card";
    const iconEl = document.createElement("span");
    iconEl.className = "starter-icon";
    iconEl.textContent = s.icon;
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
  if (msgs.length > LexaConfig.MAX_DOM_MESSAGES + 1) { const toRemove = msgs.length - LexaConfig.MAX_DOM_MESSAGES - 1; for (let i = 1; i <= toRemove; i++) msgs[i].remove(); }
}

// ── CONVERSATIONS ───────────────────────────────
async function loadConversations() {
  try {
    const data = await window.lexa.conversations();
    LexaState.set("conversationsList", data.conversations || []);
    if (typeof updateConversationCount === "function") {
      updateConversationCount(LexaState.get("conversationsList").length);
    }
    renderConversationList();

    // We explicitly do NOT auto-switch to an old conversation here
    // so the app remains in its beautiful, clean zero-state.
    LexaState.set("currentConversationId", null);
    localStorage.removeItem("lexa-active-conversation");
  } catch (e) {
    console.warn("[Chat] Failed to load conversations:", e.message || e);
  }
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
    exportBtn.className = "conv-action-btn";
    exportBtn.title = t("chat.export");
    exportBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
    exportBtn.addEventListener("click", (e) => { e.stopPropagation(); exportConversation(c.id); });
    const delBtn = document.createElement("button");
    delBtn.className = "conv-delete-btn";
    delBtn.title = t("common.delete");
    delBtn.textContent = "\u00d7";
    delBtn.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(c.id); });
    actions.appendChild(exportBtn);
    actions.appendChild(delBtn);
    item.appendChild(content);
    item.appendChild(actions);
    item.addEventListener("click", () => switchConversation(c.id));
    container.appendChild(item);
  });
}
async function newConversation() {
  try {
    const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
    LexaState.set("currentConversationId", result.id);
    localStorage.setItem("lexa-active-conversation", result.id);
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m, i) => { if (i > 0) m.remove(); });
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
    msgs.forEach((m, i) => { if (i > 0) m.remove(); });
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
  chatMessages.querySelectorAll(".message").forEach((msg, i) => {
    if (i === 0) return;
    const text = msg.querySelector(".msg-text")?.textContent || "";
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    if (text) messages.push({ role, content: text });
  });
  try { await window.lexa.conversationUpdate(LexaState.get("currentConversationId"), { messages }); } catch (e) { console.warn("[Chat] Failed to save conversation:", e.message || e); }
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
async function handleFileUpload(file) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const maxSize = 2 * 1024 * 1024;
  if (file.size > maxSize) { showToast(t("toast.fileTooLarge"), "error"); return; }
  if (!LexaState.get("currentConversationId")) { try { const result = await window.lexa.conversationCreate(t("chat.newChatTitle")); LexaState.set("currentConversationId", result.id); localStorage.setItem("lexa-active-conversation", result.id); const data = await window.lexa.conversations(); LexaState.set("conversationsList", data.conversations || []); renderConversationList(); } catch (e) { console.warn("[Chat] Failed to create conversation for file upload:", e.message || e); } }
  const sizeStr = file.size < 1024 ? file.size + " B" : file.size < 1048576 ? (file.size / 1024).toFixed(1) + " KB" : (file.size / 1048576).toFixed(1) + " MB";
  const ext = file.name.includes(".") ? file.name.split(".").pop().toUpperCase() : "FILE";
  const fileCardHtml = `<div class="file-card"><div class="file-card-icon">${getFileIcon(ext)}</div><div class="file-card-info"><div class="file-card-name">${escapeHtml(file.name)}</div><div class="file-card-meta">${ext} \u00b7 ${sizeStr}</div></div></div>`;
  const userMsg = chatInput.value.trim();
  addMessage(fileCardHtml + (userMsg ? `<br>${formatMessage(userMsg)}` : ""), "user");
  chatInput.value = ""; syncChatInputSize();
  const isFirst = chatMessages.querySelectorAll(".user-message").length <= 1;
  if (isFirst) autoTitleConversation(file.name);
  LexaState.set("isLoading", true); sendBtn.disabled = true; showTyping();
  try {
    const res = await window.lexa.chatFile(file, userMsg || "");
    hideTyping();
    if (res.detail) { addMessage(res.detail, "system"); showToast(t("toast.fileError"), "error"); }
    else {
      let infoHtml = "";
      if (res.file_info) { const fi = res.file_info; infoHtml = `<div class="file-info-badge">${fi.type.toUpperCase()} \u00b7 ${fi.size_kb} KB${fi.line_count ? " \u00b7 " + t("chat.fileLines", {count: fi.line_count}) : ""}</div>`; }
      addMessage(infoHtml + formatMessage(res.reply), "system", res.action, res.requires_confirmation);
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
function openSearchOverlay() {
  let overlay = document.getElementById("search-overlay");
  if (!overlay) {
    overlay = document.createElement("div"); overlay.id = "search-overlay"; overlay.className = "search-overlay";
    overlay.innerHTML = `<div class="search-panel"><div class="search-header"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input type="text" id="search-input" class="search-input" placeholder="${escapeHtml(t("chat.searchPlaceholder"))}" autocomplete="off"><button class="search-close-btn" id="search-close-btn">\u00d7</button></div><div id="search-results" class="search-results"><div class="search-empty">${escapeHtml(t("chat.searchHint"))}</div></div></div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeSearchOverlay(); });
    document.getElementById("search-close-btn").addEventListener("click", closeSearchOverlay);
    document.getElementById("search-input").addEventListener("input", (e) => { clearTimeout(searchDebounce); searchDebounce = setTimeout(() => performSearch(e.target.value.trim()), 300); });
    document.getElementById("search-input").addEventListener("keydown", (e) => { if (e.key === "Escape") closeSearchOverlay(); });
  }
  overlay.classList.add("visible");
  const input = document.getElementById("search-input"); input.value = ""; input.focus();
  renderSearchEmpty(document.getElementById("search-results"), t("chat.searchHint"));
}
function closeSearchOverlay() { document.getElementById("search-overlay")?.classList.remove("visible"); }
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
      item.addEventListener("click", () => { closeSearchOverlay(); action(); });
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
