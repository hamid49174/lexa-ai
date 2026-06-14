const MESSAGE_ACTION_ICON_NS = "http://www.w3.org/2000/svg";
const MESSAGE_ACTION_ICON_SPECS = {
  "\u2398": [
    { tag: "rect", attrs: { x: "8", y: "8", width: "11", height: "11", rx: "2.5" } },
    { tag: "path", attrs: { d: "M15 8V6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H8" } },
  ],
  "\u2605": [
    { tag: "path", attrs: { d: "M7 22V10" } },
    { tag: "path", attrs: { d: "M15 6.2 14 10h5.4a2 2 0 0 1 1.9 2.5l-1.6 6A3 3 0 0 1 16.8 21H7" } },
    { tag: "path", attrs: { d: "M7 10H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" } },
    { tag: "path", attrs: { d: "M15 6.2V4.5A2.5 2.5 0 0 0 12.5 2L9 10" } },
  ],
  "\u21BB": [
    { tag: "path", attrs: { d: "M21 12a9 9 0 1 1-2.64-6.36" } },
    { tag: "path", attrs: { d: "M21 4v6h-6" } },
  ],
  "\u270E": [
    { tag: "path", attrs: { d: "M12 20h9" } },
    { tag: "path", attrs: { d: "m16.5 3.5 4 4L8 20l-5 1 1-5 12.5-12.5Z" } },
  ],
  "\u00D7": [
    { tag: "path", attrs: { d: "M18 6 6 18" } },
    { tag: "path", attrs: { d: "m6 6 12 12" } },
  ],
  "\u22EF": [
    { tag: "circle", attrs: { cx: "5", cy: "12", r: "1.7" } },
    { tag: "circle", attrs: { cx: "12", cy: "12", r: "1.7" } },
    { tag: "circle", attrs: { cx: "19", cy: "12", r: "1.7" } },
  ],
  "\u25A3": [
    { tag: "rect", attrs: { x: "4", y: "4", width: "16", height: "16", rx: "3" } },
    { tag: "path", attrs: { d: "M8 8h8" } },
    { tag: "path", attrs: { d: "M8 12h5" } },
    { tag: "path", attrs: { d: "M8 16h7" } },
  ],
  "\u21AA": [
    { tag: "path", attrs: { d: "M4 12h13" } },
    { tag: "path", attrs: { d: "m12 7 5 5-5 5" } },
  ],
  "?": [
    { tag: "circle", attrs: { cx: "11", cy: "11", r: "7" } },
    { tag: "path", attrs: { d: "m20 20-4.2-4.2" } },
    { tag: "path", attrs: { d: "m8.5 11 1.8 1.8 3.7-4.1" } },
  ],
  "\u21E9": [
    { tag: "path", attrs: { d: "M12 16V4" } },
    { tag: "path", attrs: { d: "m7 9 5-5 5 5" } },
    { tag: "path", attrs: { d: "M5 20h14" } },
  ],
  "\u2713": [
    { tag: "path", attrs: { d: "m5 12 4 4 10-10" } },
  ],
};

function createMessageActionSvgIcon(icon) {
  const spec = MESSAGE_ACTION_ICON_SPECS[String(icon || "")];
  if (!spec) return null;
  const svg = document.createElementNS(MESSAGE_ACTION_ICON_NS, "svg");
  svg.setAttribute("class", "msg-action-icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  spec.forEach((child) => {
    const el = document.createElementNS(MESSAGE_ACTION_ICON_NS, child.tag);
    Object.entries(child.attrs || {}).forEach(([name, value]) => el.setAttribute(name, value));
    svg.appendChild(el);
  });
  return svg;
}

function renderIconButtonVisual(button, icon) {
  if (!button?.matches?.(".msg-copy-btn, .msg-thumbs-btn, .msg-action-btn")) return;
  button.querySelector(".msg-action-icon")?.remove();
  const svg = createMessageActionSvgIcon(icon);
  if (!svg) {
    delete button.dataset.svgIcon;
    return;
  }
  button.prepend(svg);
  button.dataset.svgIcon = "true";
}

function setIconButton(button, icon, label) {
  button.textContent = "";
  button.dataset.icon = icon;
  renderIconButtonVisual(button, icon);
  button.title = label;
  button.setAttribute("aria-label", label);
}

function setMessageActionMenuOpen(menu, open) {
  if (!menu) return;
  menu.classList.toggle("open", Boolean(open));
  const trigger = menu.querySelector(".msg-more-btn");
  if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");
}

function closeMessageActionMenus(except = null) {
  document.querySelectorAll(".msg-more-actions.open").forEach((menu) => {
    if (menu !== except) setMessageActionMenuOpen(menu, false);
  });
}

let _messageActionMenuDismissBound = false;
function ensureMessageActionMenuDismiss() {
  if (_messageActionMenuDismissBound) return;
  _messageActionMenuDismissBound = true;
  document.addEventListener("click", (event) => {
    if (event.target?.closest?.(".msg-more-actions")) return;
    closeMessageActionMenus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMessageActionMenus();
  });
}

function createMessageActionOverflowMenu(actions) {
  const actionButtons = (actions || []).filter(Boolean);
  if (!actionButtons.length) return null;
  ensureMessageActionMenuDismiss();
  const wrap = document.createElement("div");
  wrap.className = "msg-more-actions";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "msg-action-btn msg-more-btn";
  setIconButton(trigger, "\u22EF", t("chat.moreActionsTooltip"));
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "msg-more-menu";
  menu.setAttribute("role", "menu");
  actionButtons.forEach((button) => {
    button.classList.add("msg-more-item");
    button.setAttribute("role", "menuitem");
    menu.appendChild(button);
  });
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const shouldOpen = !wrap.classList.contains("open");
    closeMessageActionMenus(wrap);
    setMessageActionMenuOpen(wrap, shouldOpen);
    if (shouldOpen) {
      const firstEnabled = menu.querySelector("button:not(:disabled)");
      if (firstEnabled && window.matchMedia?.("(hover: none), (pointer: coarse)")?.matches) firstEnabled.focus();
    }
  });
  wrap.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setMessageActionMenuOpen(wrap, false);
      trigger.focus();
    }
  });
  menu.addEventListener("click", (event) => {
    const actionButton = event.target?.closest?.("button");
    if (!actionButton || !menu.contains(actionButton)) return;
    setMessageActionMenuOpen(wrap, false);
    const rect = trigger.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) trigger.focus();
  });
  wrap.appendChild(trigger);
  wrap.appendChild(menu);
  return wrap;
}

async function startWorkspaceDraftFromMessage(btn) {
  if (btn?.disabled) return;
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const prompt = workspaceDraftPromptFromText(getMessagePersistText(btn?.closest(".message")));
  if (!prompt) { showToast(t("chat.workspaceHandoffEmpty"), "warning"); return; }
  showToast(t("chat.workspaceHandoffStarted"), "info", 1800);
  flashIconButton(btn, "\u2713", "\u25A3", 1800, t("chat.workspaceHandoffStarted"));
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    await sendAgentMessage(prompt, { displayText: t("chat.workspaceHandoffUserMessage") });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

function createWorkspaceHandoffButton() {
  const workspaceBtn = document.createElement("button");
  workspaceBtn.type = "button";
  workspaceBtn.className = "msg-action-btn msg-workspace-btn";
  setIconButton(workspaceBtn, "\u25A3", t("chat.workspaceHandoffTooltip"));
  workspaceBtn.addEventListener("click", () => startWorkspaceDraftFromMessage(workspaceBtn));
  return workspaceBtn;
}

function startContinueFromMessage(btn) {
  if (btn?.disabled) return;
  const prompt = continuePromptFromText(getMessagePersistText(btn?.closest(".message")));
  if (!prompt.text) { showToast(t("chat.continueFromAnswerEmpty"), "warning", 2000); return; }
  chatInput.value = prompt.text;
  syncChatInputSize();
  if (typeof setChatDraft === "function") setChatDraft(prompt.text);
  chatInput.focus();
  if (typeof chatInput.setSelectionRange === "function") {
    chatInput.setSelectionRange(prompt.cursorStart, prompt.cursorStart);
  }
  flashIconButton(btn, "\u2713", "\u21AA", 1500, t("chat.continueFromAnswerStarted"));
  showToast(t("chat.continueFromAnswerStarted"), "success", 1600);
}

function createContinueFromMessageButton(disabled = false) {
  const continueBtn = document.createElement("button");
  continueBtn.type = "button";
  continueBtn.className = "msg-action-btn msg-continue-btn";
  continueBtn.disabled = Boolean(disabled);
  setIconButton(continueBtn, "\u21AA", t("chat.continueFromAnswerTooltip"));
  continueBtn.addEventListener("click", () => startContinueFromMessage(continueBtn));
  return continueBtn;
}

async function startVerifyAnswerFromMessage(btn) {
  if (btn?.disabled) return;
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const messageEl = btn?.closest(".message");
  const answer = String(getMessagePersistText(messageEl) || "").trim();
  if (!answer) { showToast(t("chat.verifyAnswerEmpty"), "warning", 2000); return; }
  // Originalfrage als Suchquery (bessere Treffer); Backend faellt sonst auf den Antworttext zurueck.
  const question = String(previousUserPromptForMessage(messageEl) || "").slice(0, 2000);
  showToast(t("chat.verifyAnswerStarted"), "info", 1800);
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  addMessage(t("chat.verifyAnswerUserMessage"), "user");
  try {
    // Echte Quellen-Recherche ueber das Backend (Suche + Fetch + LLM-Pruefung).
    const res = await window.lexa.verifyWithSources(answer, question);
    let out = (res && res.brief) ? String(res.brief) : t("chat.verifyAnswerEmpty");
    const sources = (res && Array.isArray(res.sources)) ? res.sources : [];
    if (sources.length) {
      // Kanonische Quellenliste aus den ECHTEN Daten (nicht aus Modell-URLs) als klickbare Links.
      out += "\n\n**Quellen:**\n" + sources
        .map((s, i) => `${i + 1}. [${String(s.title || s.url || "Quelle").slice(0, 120)}](${s.url})`)
        .join("\n");
    }
    addMessage(out, "assistant");
  } catch (e) {
    console.warn("[Chat] verify-with-sources failed:", e?.message || e);
    addMessage(t("chat.verifyAnswerEmpty"), "assistant");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

function createVerifyAnswerButton(disabled = false) {
  const verifyBtn = document.createElement("button");
  verifyBtn.type = "button";
  verifyBtn.className = "msg-action-btn msg-verify-btn";
  verifyBtn.disabled = Boolean(disabled);
  setIconButton(verifyBtn, "?", t("chat.verifyAnswerTooltip"));
  verifyBtn.addEventListener("click", () => startVerifyAnswerFromMessage(verifyBtn));
  return verifyBtn;
}

async function saveMessageAsMemory(btn, msg) {
  if (btn?.disabled || btn?.dataset.saved === "true") return;
  const msgText = getMessagePersistText(msg);
  const snippet = msgText.substring(0, 200).trim();
  if (!snippet) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    await window.lexa.memoryAdd(t("chat.helpfulAnswer", {snippet}), "learned", 5);
    if (btn) {
      btn.dataset.saved = "true";
      btn.dataset.icon = "\u2713";
      renderIconButtonVisual(btn, "\u2713");
      btn.setAttribute("aria-label", t("toast.savedAsMemory"));
      btn.title = t("toast.savedAsMemory");
      btn.removeAttribute("aria-busy");
    }
    showToast(t("toast.savedAsMemory"), "success");
  } catch (e) {
    console.warn("[Chat] Save message as memory failed:", e.message || e);
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
    showToast(t("toast.executionError"), "error", 2200);
  }
}

function previousUserPromptForMessage(msg) {
  const allMsgs = chatMessages?.querySelectorAll(".message") || [];
  for (let i = allMsgs.length - 1; i >= 0; i--) {
    if (allMsgs[i] !== msg) continue;
    for (let j = i - 1; j >= 0; j--) {
      if (allMsgs[j].classList.contains("user-message")) {
        return getMessagePersistText(allMsgs[j]);
      }
    }
    break;
  }
  return "";
}

async function startRegenerateMessage(btn, msg, fallbackPrompt = "") {
  if (btn?.disabled) return;
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const prompt = String(fallbackPrompt || previousUserPromptForMessage(msg)).trim();
  if (!prompt) { showToast(t("chat.regenerateMissingPrompt"), "warning", 2200); return; }
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    await regenerateMessage(prompt);
  } finally {
    if (btn?.isConnected) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

function flashIconButton(button, icon, restoreIcon, durationMs, feedbackLabel) {
  if (!button) return;
  if (!button._lexaIconTimer) {
    button._lexaOriginalIcon = restoreIcon || button.dataset.icon || "";
    button._lexaOriginalText = button.textContent || "";
    button._lexaOriginalAriaLabel = button.getAttribute("aria-label");
    button._lexaOriginalTitle = button.getAttribute("title");
  }
  const originalIcon = button._lexaOriginalIcon || restoreIcon || "";
  const originalText = button._lexaOriginalText || "";
  button.textContent = originalText.trim() ? originalText : "";
  button.dataset.icon = icon;
  renderIconButtonVisual(button, icon);
  if (feedbackLabel) {
    button.setAttribute("aria-label", feedbackLabel);
    button.title = feedbackLabel;
  }
  if (button._lexaIconTimer) clearTimeout(button._lexaIconTimer);
  button._lexaIconTimer = setTimeout(() => {
    button.dataset.icon = originalIcon;
    button.textContent = originalText;
    renderIconButtonVisual(button, originalIcon);
    if (button._lexaOriginalAriaLabel) button.setAttribute("aria-label", button._lexaOriginalAriaLabel);
    else button.removeAttribute("aria-label");
    if (button._lexaOriginalTitle) button.title = button._lexaOriginalTitle;
    else button.removeAttribute("title");
    button._lexaIconTimer = null;
    delete button._lexaOriginalIcon;
    delete button._lexaOriginalText;
    delete button._lexaOriginalAriaLabel;
    delete button._lexaOriginalTitle;
  }, durationMs || 1500);
}

async function copyTextToClipboard(text) {
  const source = String(text ?? "");
  const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : null;
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(source);
      return true;
    } catch (e) {
      console.warn("[Chat] Clipboard API failed, trying fallback:", e.message || e);
    }
  }
  if (typeof document === "undefined" || !document.body || typeof document.execCommand !== "function") {
    throw new Error("clipboard_unavailable");
  }
  const textarea = document.createElement("textarea");
  textarea.value = source;
  textarea.setAttribute("readonly", "");
  textarea.className = "clipboard-copy-buffer";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    if (!document.execCommand("copy")) throw new Error("clipboard_copy_failed");
    return true;
  } finally {
    textarea.remove();
  }
}

function copyCode(btn) {
  const code = btn.closest(".code-block-wrap")?.querySelector("code")?.textContent || "";
  copyTextToClipboard(code).then(() => {
    flashIconButton(btn, "\u2713", "\u2398", 1500, t("toast.clipboardCopied"));
  }).catch(() => {
    showToast(t("toast.copyFailed") || "Kopieren fehlgeschlagen", "warning", 2000);
  });
}

function copyMessage(btn) {
  const text = getMessagePersistText(btn.closest(".message"));
  copyTextToClipboard(text).then(() => {
    flashIconButton(btn, "\u2713", "\u2398", 1500, t("toast.clipboardCopied"));
  }).catch(() => {
    showToast(t("toast.copyFailed") || "Kopieren fehlgeschlagen", "warning", 2000);
  });
}

function exportMessageMarkdown(btn) {
  if (btn?.disabled) return;
  const text = getMessagePersistText(btn?.closest(".message"));
  if (!text) { showToast(t("chat.messageExportEmpty"), "warning", 2000); return; }
  const markdown = messageExportMarkdownFromText(text);
  let url = "";
  let link = null;
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    url = URL.createObjectURL(blob);
    link = document.createElement("a");
    link.href = url;
    link.download = messageExportFilename();
    document.body.appendChild(link);
    link.click();
    flashIconButton(btn, "\u2713", "\u21E9", 1500, t("chat.messageExported"));
    showToast(t("chat.messageExported"), "success", 1800);
    setTimeout(() => {
      if (url) URL.revokeObjectURL(url);
    }, 1000);
    if (btn) {
      setTimeout(() => {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }, 1500);
    }
  } catch (e) {
    console.warn("[Chat] Message markdown export failed:", e.message || e);
    if (url) URL.revokeObjectURL(url);
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
    showToast(t("toast.exportError") || "Export error", "error", 2200);
  } finally {
    if (link) link.remove();
  }
}

function createMessageExportButton(disabled = false) {
  const exportBtn = document.createElement("button");
  exportBtn.type = "button";
  exportBtn.className = "msg-action-btn msg-export-btn";
  exportBtn.disabled = Boolean(disabled);
  setIconButton(exportBtn, "\u21E9", t("chat.exportMessageTooltip"));
  exportBtn.addEventListener("click", () => exportMessageMarkdown(exportBtn));
  return exportBtn;
}
