/* ════════════════════════════════════════════════
   LEXA AI — Memory Module
   Memory view, Notes, Snippets, Clipboard history,
   Routines, Diagnostics, Memory cleanup
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── HELPER: safe overlay removal with escHandler cleanup ──
function _closeOverlay(overlay, escHandler) {
  if (overlay && overlay.parentNode) overlay.remove();
  if (escHandler) document.removeEventListener("keydown", escHandler);
}

function bindMemoryCardAction(el, handler, label) {
  if (!el || typeof handler !== "function") return;
  if (label) el.setAttribute("aria-label", label);
  if (!el.hasAttribute("role")) el.setAttribute("role", "button");
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
  el.addEventListener("keydown", (event) => {
    if (event.target !== el) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler(event);
    }
  });
  el.addEventListener("click", handler);
}

// ── MEMORY VIEW ──────────────────────────────────
async function refreshMemoryView() {
  if (!LexaState.get("backendOnline")) return;

  // Fetch all memory data in parallel
  const [statsRes, notesRes, snippetsRes, aiRes, routinesRes] = await Promise.allSettled([
    window.lexa.memoryStats(),
    window.lexa.notes(),
    window.lexa.snippets(),
    window.lexa.aiStatus(),
    window.lexa.routines(),
  ]);

  const stats = statsRes.status === "fulfilled" ? statsRes.value : {};
  const statsGrid = document.getElementById("memory-stats-grid");
  if (statsGrid) {
    statsGrid.innerHTML = `
      <div class="info-card"><div class="info-card-label">${t("memory.statsNotes")}</div><div class="info-card-value">${stats.notes || 0}</div></div>
      <div class="info-card"><div class="info-card-label">${t("memory.statsMemories")}</div><div class="info-card-value">${stats.memories || 0}</div></div>
      <div class="info-card"><div class="info-card-label">${t("memory.statsChats")}</div><div class="info-card-value">${stats.conversations || 0}</div></div>
      <div class="info-card"><div class="info-card-label">${t("memory.statsInteractions")}</div><div class="info-card-value">${stats.interactions || 0}</div></div>
      <div class="info-card"><div class="info-card-label">${t("memory.statsRoutines")}</div><div class="info-card-value">${stats.routines || 0}</div></div>
      <div class="info-card"><div class="info-card-label">${t("memory.statsClipboard")}</div><div class="info-card-value">${stats.clipboard_entries || 0}</div></div>
    `;
  }

  const notesData = notesRes.status === "fulfilled" ? notesRes.value : { notes: [] };
  const notesList = document.getElementById("notes-list");
  if (notesList) {
    if (notesData.notes?.length > 0) {
      notesList.innerHTML = "";
      notesData.notes.forEach(n => {
        const card = document.createElement("div");
        card.className = "note-card note-card-clickable";
        card.title = t("memory.clickToEditTooltip");

        const titleEl = document.createElement("div");
        titleEl.className = "note-title";
        titleEl.textContent = n.title || "";
        card.appendChild(titleEl);

        const metaEl = document.createElement("div");
        metaEl.className = "note-meta";
        metaEl.textContent = (n.category || "") + " \u00b7 " + (n.created_at || "");
        card.appendChild(metaEl);

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "note-delete-btn";
        delBtn.title = t("memory.deleteNoteTooltip");
        delBtn.setAttribute("aria-label", t("memory.deleteNoteLabel", { title: n.title || "" }));
        delBtn.textContent = "\u00d7";
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await showInputModal(t("common.confirm"), [
            { name: "confirm", label: t("memory.noteDeleteConfirm", {title: n.title}), type: "text", required: true }
          ], t("common.confirm"));
          if (!result || result.confirm.toLowerCase() !== "ja") return;
          await window.lexa.execute("note_delete", { title: n.title }, true);
          showToast(t("notes.deleted"), "info");
          refreshMemoryView();
        });
        card.appendChild(delBtn);

        bindMemoryCardAction(card, () => openNoteModal(n.id, n.title), t("memory.openNoteLabel", { title: n.title || "" }));
        notesList.appendChild(card);
      });
    } else {
      notesList.innerHTML = '<div class="empty-state">' + escapeHtml(t("memory.emptyNotes")) + '</div>';
    }
  }

  // Snippets
  try {
    const snippetsData = snippetsRes.status === "fulfilled" ? snippetsRes.value : { snippets: [] };
    const snippetsList = document.getElementById("snippets-list");
    if (snippetsList) {
      if (snippetsData.snippets?.length > 0) {
        snippetsList.innerHTML = "";
        snippetsData.snippets.forEach(s => {
          const card = document.createElement("div");
          card.className = "note-card snippet-card";
          const snippetText = String(s.text || "");
          const preview = snippetText.length > 50 ? snippetText.substring(0, 50) + "\u2026" : snippetText;
          const title = document.createElement("div");
          title.className = "note-title";
          title.textContent = s.name || "";
          const meta = document.createElement("div");
          meta.className = "note-meta";
          meta.textContent = preview;
          const deleteBtn = document.createElement("button");
          deleteBtn.type = "button";
          deleteBtn.className = "snippet-delete";
          deleteBtn.title = t("memory.deleteSnippetTooltip");
          deleteBtn.setAttribute("aria-label", t("memory.deleteSnippetLabel", { name: s.name || "" }));
          deleteBtn.textContent = "\u00d7";
          card.appendChild(title);
          card.appendChild(meta);
          card.appendChild(deleteBtn);
          bindMemoryCardAction(card, () => useSnippet(snippetText), t("memory.useSnippetLabel", { name: s.name || "" }));
          deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteSnippet(s.name);
          });
          snippetsList.appendChild(card);
        });
      } else {
        snippetsList.innerHTML = '<div class="empty-state">' + escapeHtml(t("memory.emptySnippets")) + '</div>';
      }
    }
  } catch (e) { console.warn("[Memory] Failed to render snippets:", e.message || e); }

  const aiStatus = aiRes.status === "fulfilled" ? aiRes.value : {
    groq: { available: false },
    openai: { available: false },
    gemini: { available: false },
  };
  const aiPanel = document.getElementById("ai-status-panel");
  if (aiPanel) {
    const providers = [
      ["groq", "Groq API", aiStatus.groq?.model_name || t("memory.groqFallback")],
      ["openai", "OpenAI API", aiStatus.openai?.model_name || t("memory.openaiFallback")],
      ["gemini", "Gemini API", aiStatus.gemini?.model_name || t("memory.geminiFallback")],
    ];
    aiPanel.innerHTML = providers.map(([key, label, detail]) => {
      const ok = aiStatus[key]?.available;
      return `<div class="info-card provider-card"><span class="provider-dot ${ok ? "active" : "inactive"}"></span><div><div class="fw-600 text-norm">${label}</div><div class="fs-11 text-muted">${ok ? escapeHtml(String(detail || t("memory.providerReady"))) : t("memory.providerOffline")}</div></div></div>`;
    }).join("");
  }

  const routinesData = routinesRes.status === "fulfilled" ? routinesRes.value : { routines: [] };
  const routinesList = document.getElementById("routines-list");
  if (routinesList) {
    if (routinesData.routines?.length > 0) {
      routinesList.innerHTML = "";
      routinesData.routines.forEach(r => {
        const card = document.createElement("div");
        card.className = "routine-card";
        const info = document.createElement("div");
        info.className = "routine-info";
        const name = document.createElement("div");
        name.className = "routine-name";
        name.textContent = r.name || "";
        const schedule = document.createElement("div");
        schedule.className = "routine-schedule";
        schedule.textContent = (r.schedule || "") + (r.description ? ` \u00b7 ${r.description}` : "");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "routine-toggle" + (r.enabled ? " enabled" : "");
        toggle.setAttribute("aria-pressed", r.enabled ? "true" : "false");
        toggle.setAttribute("aria-label", t("memory.toggleRoutineLabel", { name: r.name || "" }));
        info.appendChild(name);
        info.appendChild(schedule);
        card.appendChild(info);
        card.appendChild(toggle);
        toggle.addEventListener("click", () => toggleRoutine(r.name));
        routinesList.appendChild(card);
      });
    } else {
      routinesList.innerHTML = '<div class="empty-state">' + escapeHtml(t("memory.emptyRoutines")) + '</div>';
    }
  }

  renderClipboardPrivacyPrompt();

  // Add cleanup info
  const cleanupEl = document.getElementById("memory-cleanup-info");
  if (cleanupEl) {
    cleanupEl.innerHTML = "";
    const cleanBtn = document.createElement("button");
    cleanBtn.type = "button";
    cleanBtn.className = "action-btn memory-cleanup-btn";
    cleanBtn.textContent = t("memory.cleanupBtn", {count: parseInt(stats.memories) || 0});
    cleanBtn.addEventListener("click", runMemoryCleanup);
    cleanupEl.appendChild(cleanBtn);
  }
}

function renderClipboardEntries(entries = []) {
  const cbList = document.getElementById("clipboard-history-list");
  if (!cbList) return;
  if (entries.length > 0) {
    cbList.innerHTML = "";
    entries.slice(0, 20).forEach(e => {
      const preview = String(e.text || "").substring(0, 80);
      const card = document.createElement("div");
      card.className = "note-card clipboard-entry";
      const title = document.createElement("div");
      title.className = "note-title";
      title.textContent = preview + ((e.text?.length > 80) ? "\u2026" : "");
      const meta = document.createElement("div");
      meta.className = "note-meta";
      meta.textContent = String(e.created_at || "").substring(0, 16);
      card.appendChild(title);
      card.appendChild(meta);
      const rawText = e.text || "";
      bindMemoryCardAction(card, () => {
        window.lexa.execute("clipboard_write", { text: rawText }, true);
        showToast(t("toast.clipboardCopied"), "success", 2000);
      }, t("memory.copyClipboardLabel"));
      cbList.appendChild(card);
    });
  } else {
    cbList.innerHTML = '<div class="empty-state">' + escapeHtml(t("memory.emptyClipboard")) + '</div>';
  }
}

function renderClipboardPrivacyPrompt() {
  const cbList = document.getElementById("clipboard-history-list");
  if (!cbList) return;
  cbList.innerHTML = "";
  const card = document.createElement("div");
  card.className = "empty-state";
  const hint = document.createElement("div");
  hint.textContent = t("memory.clipboardPrivacyHint");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-btn mt-2";
  button.textContent = t("memory.revealClipboardHistory");
  button.addEventListener("click", revealClipboardHistory);
  card.appendChild(hint);
  card.appendChild(button);
  cbList.appendChild(card);
}

async function revealClipboardHistory() {
  const cbData = await window.lexa.clipboardHistory();
  renderClipboardEntries(cbData.entries || []);
}

async function clearClipboardHistory() {
  await window.lexa.clipboardClear();
  showToast(t("toast.clipboardCleared"), "info");
  refreshMemoryView();
}

function createNote() {
  quickCreateNote();
}

function quickCreateNote() {
  // Open an inline modal for fast note creation (Ctrl+Shift+N)
  document.getElementById("note-modal")?.remove();

  const overlay = document.createElement("div");
  overlay.id = "note-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("notes.newNote"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "note-modal-title-input";
  titleInput.placeholder = t("memory.noteTitlePlaceholder");
  header.appendChild(titleInput);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const textarea = document.createElement("textarea");
  textarea.className = "note-modal-textarea";
  textarea.placeholder = t("memory.noteContentPlaceholder");
  panel.appendChild(textarea);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const ti = titleInput.value.trim();
    const c = textarea.value.trim();
    if (!ti) { showToast(t("notes.titleEmpty"), "error"); return; }
    if (!c) { showToast(t("notes.contentEmpty"), "error"); return; }
    await window.lexa.execute("note_create", { title: ti, content: c }, true);
    showToast(t("notes.created"), "success");
    _closeOverlay(overlay, escHandler);
    if (LexaState.get("currentView") === "memory") refreshMemoryView();
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  titleInput.focus();
}

async function createRoutine() {
  switchView("chat");
  chatInput.value = t("memory.createRoutinePrompt");
  chatInput.focus();
}

async function toggleRoutine(name) {
  await window.lexa.execute("routine_toggle", { name }, true);
  showToast(t("memory.routineToggled", {name}), "info");
  refreshMemoryView();
}

function filterNotes(query) {
  const cards = document.querySelectorAll("#notes-list .note-card");
  const q = query.toLowerCase().trim();
  cards.forEach(card => {
    const title = card.querySelector(".note-title")?.textContent.toLowerCase() || "";
    const meta = card.querySelector(".note-meta")?.textContent.toLowerCase() || "";
    card.classList.toggle("hidden", !(!q || title.includes(q) || meta.includes(q)));
  });
}

async function openNoteModal(noteId, noteTitle) {
  // Fetch full note content
  const note = await window.lexa.noteGet(noteId);
  if (!note || note.error) {
    showToast(t("notes.loadFailed"), "error");
    return;
  }

  // Remove any existing note modal
  document.getElementById("note-modal")?.remove();

  const overlay = document.createElement("div");
  overlay.id = "note-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("notes.editNote"));

  const header = document.createElement("div");
  header.className = "note-modal-header";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "note-modal-title-input";
  titleInput.value = note.title || "";
  header.appendChild(titleInput);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const metaEl = document.createElement("div");
  metaEl.className = "note-modal-meta";
  metaEl.textContent = (note.category || "general") + " \u00b7 " + (note.created_at || "");
  panel.appendChild(metaEl);

  const textarea = document.createElement("textarea");
  textarea.className = "note-modal-textarea";
  textarea.value = note.content || "";
  textarea.placeholder = t("memory.noteContentPlaceholderShort");
  panel.appendChild(textarea);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const newTitle = titleInput.value.trim();
    const newContent = textarea.value.trim();
    if (!newTitle) { showToast(t("notes.titleEmpty"), "error"); return; }
    const result = await window.lexa.noteUpdate(noteId, { title: newTitle, content: newContent });
    if (result?.status === "ok") {
      showToast(t("notes.saved"), "success");
      _closeOverlay(overlay, escHandler);
      refreshMemoryView();
    } else {
      showToast(t("notes.saveFailed"), "error");
    }
  });
  footer.appendChild(saveBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);

  panel.appendChild(footer);
  overlay.appendChild(panel);

  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);

  document.body.appendChild(overlay);
  textarea.focus();
}

// ── CLIPBOARD HISTORY & SNIPPETS (Phase 16) ─────
async function trackClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      await window.lexa.clipboardAdd(text.trim().substring(0, 1000));
    }
  } catch (e) { console.warn("[Memory] Failed to track clipboard:", e.message || e); }
}

function createSnippet() {
  document.getElementById("snippet-create-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "snippet-create-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-narrow";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("memory.newSnippetTitle"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = t("memory.newSnippetTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const form = document.createElement("div");
  form.className = "note-modal-form";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = t("memory.snippetNamePlaceholder");
  nameInput.className = "settings-input";
  form.appendChild(nameInput);

  const textArea = document.createElement("textarea");
  textArea.placeholder = t("memory.snippetTextPlaceholder");
  textArea.className = "note-modal-textarea note-modal-textarea-compact";
  form.appendChild(textArea);
  panel.appendChild(form);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    const text = textArea.value.trim();
    if (!name) { showToast(t("snippets.nameEmpty"), "error"); return; }
    if (!text) { showToast(t("snippets.textEmpty"), "error"); return; }
    await window.lexa.snippetCreate(name, text);
    invalidateSnippetCache();
    showToast(t("snippets.saved"), "success");
    _closeOverlay(overlay, escHandler);
    refreshMemoryView();
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  nameInput.focus();
}

async function deleteSnippet(name) {
  await window.lexa.snippetDelete(name);
  invalidateSnippetCache();
  showToast(t("snippets.deleted"), "info");
  refreshMemoryView();
}

async function useSnippet(text) {
  chatInput.value = text;
  chatInput.focus();
  switchView("chat");
  showToast(t("snippets.inserted"), "info", 1500);
}

// ── DIAGNOSTICS ──────────────────────────────────
async function showDiagnostics() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    const d = await window.lexa.diagnostics();
    const lines = [
      `Version: ${d.version}`,
      `Python: ${d.python}`,
      `DB: ${d.db_size_kb} KB`,
      `Audit-Log: ${d.audit_log_size_kb} KB`,
      t("memory.diagChatHistory", {count: d.conversation_history_len}),
      `Memories: ${d.memory?.memories || 0}`,
      `Notes: ${d.memory?.notes || 0}`,
      `Conversations: ${d.memory?.conversations || 0}`,
      t("memory.diagAiProvider", {provider: d.ai?.active_provider || t("memory.diagAiUnknown")}),
      `Scheduler: ${d.scheduler?.running ? t("memory.diagSchedulerActive") : t("memory.diagSchedulerInactive")}`,
    ].join('\n');
    addMessage('\uD83D\uDCCA Diagnostics:\n```\n' + lines + '\n```', 'system');
    switchView('chat');
  } catch (e) {
    showToast(t("memory.diagnosticsError", {error: e.message}), 'error');
  }
}

async function runMemoryCleanup() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    const d = await window.lexa.memoryCleanup(90, 3);
    showToast(t("memory.cleanupDone", {count: d.deleted}), d.deleted > 0 ? "success" : "info");
  } catch (e) {
    showToast(t("memory.cleanupFailed", {error: e.message}), "error");
  }
}
