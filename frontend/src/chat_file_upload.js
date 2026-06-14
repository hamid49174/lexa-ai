/*
 * Chat drag/drop and file upload flow.
 */

let dragCounter = 0;
function setFileUploadBusy(isBusy) {
  LexaState.set("isLoading", Boolean(isBusy));
  sendBtn.disabled = Boolean(isBusy);
  const attachBtn = document.getElementById("attach-btn");
  if (attachBtn) {
    attachBtn.disabled = Boolean(isBusy);
    attachBtn.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
}

function saveFileUploadConversationSnapshot() {
  try { saveChatHistory(); }
  catch (e) { console.warn("[Chat] Failed to save local upload history:", e.message || e); }
  try {
    const savePromise = saveCurrentConversation();
    if (savePromise && typeof savePromise.catch === "function") {
      savePromise.catch((e) => console.warn("[Chat] Failed to save upload conversation:", e.message || e));
    }
  } catch (e) {
    console.warn("[Chat] Failed to start upload conversation save:", e.message || e);
  }
}

function setupDragDrop() {
  const chatContainer = document.getElementById("chat-container");
  const overlay = document.getElementById("drop-zone-overlay");
  if (!chatContainer || !overlay) return;
  const fileInput = document.getElementById("file-input");
  const attachBtn = document.getElementById("attach-btn");
  if (fileInput) fileInput.addEventListener("change", handleFileSelect);
  if (attachBtn) attachBtn.addEventListener("click", triggerFileUpload);
  chatContainer.addEventListener("dragenter", (e) => { e.preventDefault(); dragCounter++; overlay.classList.add("visible"); });
  chatContainer.addEventListener("dragleave", (e) => { e.preventDefault(); dragCounter--; if (dragCounter <= 0) { dragCounter = 0; overlay.classList.remove("visible"); } });
  chatContainer.addEventListener("dragover", (e) => { e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = "copy"; });
  chatContainer.addEventListener("drop", (e) => { e.preventDefault(); dragCounter = 0; overlay.classList.remove("visible"); const files = e.dataTransfer?.files; if (files && files.length > 0) handleAttachFiles(files); });

  // Paste-Upload: kopierte Bilder/Dateien direkt aus der Zwischenablage anhaengen.
  const pasteInput = document.getElementById("chat-input");
  if (pasteInput) {
    pasteInput.addEventListener("paste", (e) => {
      const items = e.clipboardData && e.clipboardData.items;
      if (!items) return;
      const files = [];
      for (const item of items) {
        if (item.kind === "file") {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length > 0) {
        e.preventDefault(); // sonst fuegt der Browser den Bild-Pfad als Text ein
        handleAttachFiles(files);
      }
    });
  }

  // Leerzustand: klickbare Beispiel-Prompts fuellen die Eingabe (kein Auto-Senden).
  document.querySelectorAll(".example-prompt").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = document.getElementById("chat-input");
      if (!input) return;
      input.value = (btn.dataset.prompt || btn.textContent || "").trim();
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
}
function triggerFileUpload() { document.getElementById("file-input")?.click(); }
function handleFileSelect(event) { const fileList = Array.from(event.target.files || []); if (fileList.length > 0) handleAttachFiles(fileList); event.target.value = ""; }

// Verarbeitet mehrere ausgewählte/gezogene Dateien sequenziell, damit keine
// Datei stillschweigend verworfen wird. Jeder Upload wird abgewartet, bevor der
// nächste startet (die isLoading-Sperre würde sonst Folge-Uploads abweisen).
async function handleFileUploadBatch(files) {
  for (const file of Array.from(files)) {
    await handleFileUpload(file);
  }
}

// ── Staged attachments (ChatGPT-style): anhaengen -> Vorschauen in der Eingabe ->
// erst beim Senden zusammen mit dem Text abschicken. Mehrere Bilder moeglich. ────
let _stagedUploads = [];
const MAX_STAGED_UPLOADS = 6;
function getStagedUploads() { return _stagedUploads; }

const ALLOWED_UPLOAD_EXT = new Set([
  "pdf", "txt", "md", "csv", "json", "js", "ts", "py", "html", "css",
  "xml", "yaml", "yml", "log", "sql",
]);
function isAllowedUploadFile(file) {
  if (!file) return false;
  if (String(file.type || "").startsWith("image/")) return true;
  const ext = String(file.name || "").split(".").pop().toLowerCase();
  return ALLOWED_UPLOAD_EXT.has(ext);
}

function handleAttachFiles(files) {
  const list = Array.from(files || []);
  if (!list.length) return;
  const maxSize = 2 * 1024 * 1024;
  let added = 0;
  for (const file of list) {
    if (!file) continue;
    if (_stagedUploads.length >= MAX_STAGED_UPLOADS) {
      showToast(`Maximal ${MAX_STAGED_UPLOADS} Dateien gleichzeitig.`, "warning", 2500);
      break;
    }
    // Typprüfung gilt für Button, Drag&Drop UND Paste (accept-Attribut wirkt nur im Dialog).
    if (!isAllowedUploadFile(file)) { showToast(`${file.name}: Dateityp nicht unterstützt.`, "warning", 2800); continue; }
    if (file.size > maxSize) { showToast(`${file.name}: zu groß (max 2 MB).`, "error"); continue; }
    _stagedUploads.push(file);
    added++;
  }
  if (!added) return;
  renderStagedUploads();
  const input = document.getElementById("chat-input");
  if (input) input.focus();
  if (sendBtn && !LexaState.get("isLoading")) sendBtn.disabled = false;
}

function renderStagedUploads() {
  const container = document.querySelector(".sleek-input-container");
  if (!container) return;
  document.getElementById("chat-attachment-preview")?.remove();
  if (!_stagedUploads.length) return;
  const wrap = document.createElement("div");
  wrap.id = "chat-attachment-preview";
  wrap.className = "chat-attachment-preview";
  _stagedUploads.forEach((file, index) => {
    let card;
    try {
      card = buildFileUploadCard(file);
    } catch (e) {
      card = document.createElement("div");
      card.className = "file-card";
      card.textContent = file.name || "Datei";
    }
    card.classList.add("attachment-staged-card");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "attachment-remove-btn";
    removeBtn.setAttribute("aria-label", "Anhang entfernen");
    removeBtn.title = "Anhang entfernen";
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", (e) => { e.stopPropagation(); removeStagedUpload(index); });
    card.appendChild(removeBtn);
    wrap.appendChild(card);
  });
  const pill = container.querySelector(".sleek-pill");
  container.insertBefore(wrap, pill || null);
}

function removeStagedUpload(index) {
  if (index < 0 || index >= _stagedUploads.length) return;
  _stagedUploads.splice(index, 1);
  renderStagedUploads();
}

function clearStagedUploads() {
  _stagedUploads = [];
  document.getElementById("chat-attachment-preview")?.remove();
}

// Called by sendMessage() when files are staged. One file -> single-upload path;
// multiple files -> combined multi-image analysis in one turn.
async function sendStagedUploads() {
  const files = _stagedUploads.slice();
  if (!files.length) return;
  _stagedUploads = [];
  document.getElementById("chat-attachment-preview")?.remove();
  if (files.length === 1) {
    await handleFileUpload(files[0]);
  } else {
    await handleMultiFileUpload(files);
  }
}

function addMultiFileUploadMessage(files, userMsg) {
  addMessage(userMsg || "", "user");
  const messages = chatMessages.querySelectorAll(".message.user-message");
  const msg = messages[messages.length - 1];
  const textEl = msg?.querySelector(".msg-text");
  if (!textEl) return;
  const grid = document.createElement("div");
  grid.className = "file-card-grid";
  files.forEach((file) => {
    try { grid.appendChild(buildFileUploadCard(file)); } catch (e) { /* skip card */ }
  });
  if (textEl.firstChild) textEl.insertBefore(document.createElement("br"), textEl.firstChild);
  textEl.insertBefore(grid, textEl.firstChild);
}

async function handleMultiFileUpload(files) {
  if (LexaState.get("isLoading")) { showToast(t("chat.uploadBusy"), "warning"); return; }
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  if (!LexaState.get("currentConversationId")) {
    try {
      const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
      if (!result?.id) { showToast(t("toast.createError"), "error"); return; }
      LexaState.set("currentConversationId", result.id);
      chatSetActiveConversationId(result.id);
      await refreshConversationSidebar();
    } catch (e) {
      console.warn("[Chat] Failed to create conversation for multi upload:", e.message || e);
      showToast(t("toast.createError"), "error");
      return;
    }
  }
  const userMsg = chatInput.value.trim();
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();
  addMultiFileUploadMessage(files, userMsg);
  chatInput.value = ""; syncChatInputSize();
  const isFirst = chatMessages.querySelectorAll(".user-message").length <= 1;
  if (isFirst) autoTitleConversation(files[0]?.name || t("chat.newChatTitle"));
  setFileUploadBusy(true); showTyping();
  try {
    const res = await window.lexa.chatFiles(files, userMsg || "", LexaState.get("currentConversationId") || null);
    if (res.detail) { addMessage(res.detail, "system"); showToast(t("toast.fileError"), "error"); }
    else {
      addMessage(res.reply || "Ich konnte die Bilder leider nicht auswerten.", "system", null, false);
      playTTS(res.reply || "");
    }
  } catch (err) {
    if (err?.name === "AbortError" || /abort/i.test(err?.message || "")) {
      addMessage("Upload abgebrochen.", "system", null, false, true);
    } else {
      addMessage(t("chat.uploadErrorMsg", {error: err.message}), "system");
      showToast(t("toast.uploadError"), "error");
    }
  } finally {
    hideTyping();
    saveFileUploadConversationSnapshot();
    setFileUploadBusy(false);
  }
}

function buildFileUploadIcon(ext) {
  const icon = document.createElement("div");
  icon.className = "file-card-icon";
  icon.textContent = getFileIcon(ext);
  return icon;
}

function buildFileUploadPreview(file, ext) {
  if (!fileUploadCanPreview(file)) return null;
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return null;
  let previewUrl = "";
  try {
    previewUrl = URL.createObjectURL(file);
  } catch (_) {
    return null;
  }
  const img = document.createElement("img");
  img.className = "file-card-preview";
  img.alt = "";
  img.decoding = "async";
  img.setAttribute("aria-hidden", "true");
  // Keep the object URL alive so a click can open the full-size lightbox.
  // (Revoked only on load error; minor per-session memory for a few images.)
  img.dataset.fullSrc = previewUrl;
  img.addEventListener("error", () => {
    try { URL.revokeObjectURL(previewUrl); } catch (_) { /* noop */ }
    img.parentElement?.classList.remove("file-card-with-preview", "file-card-clickable");
    img.replaceWith(buildFileUploadIcon(ext));
  }, { once: true });
  img.src = previewUrl;
  return img;
}

function buildFileUploadCard(file) {
  const ext = fileUploadExtension(file);
  const card = document.createElement("div");
  card.className = "file-card";

  const preview = buildFileUploadPreview(file, ext);
  if (preview) {
    card.classList.add("file-card-with-preview", "file-card-clickable");
    card.appendChild(preview);
    card.addEventListener("click", (e) => {
      if (e.target.closest(".attachment-remove-btn")) return;
      const src = preview.dataset?.fullSrc || preview.src;
      if (src) openImageLightbox(src);
    });
  } else {
    card.appendChild(buildFileUploadIcon(ext));
  }

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
  badge.textContent = fileInfoBadgeText(fileInfo);
  return badge;
}

function addFileUploadResponse(res) {
  addMessage(fileUploadDisplayReply(res), "system", null, false);
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
    let result = null;
    try {
      result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
    } catch (e) {
      console.warn("[Chat] Failed to create conversation for file upload:", e.message || e);
      showToast(t("toast.createError"), "error");
      return;
    }
    if (!result?.id) {
      console.warn("[Chat] Failed to create conversation for file upload: missing id");
      showToast(t("toast.createError"), "error");
      return;
    }
    LexaState.set("currentConversationId", result.id);
    chatSetActiveConversationId(result.id);
    try {
      await refreshConversationSidebar();
    } catch (e) {
      console.warn("[Chat] Upload conversation created but sidebar refresh failed:", e.message || e);
      showToast(t("toast.conversationRefreshFailed"), "warning", 3000);
    }
  }
  const userMsg = chatInput.value.trim();
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();
  addFileUploadMessage(file, userMsg);
  chatInput.value = ""; syncChatInputSize();
  const isFirst = chatMessages.querySelectorAll(".user-message").length <= 1;
  if (isFirst) autoTitleConversation(file.name);
  setFileUploadBusy(true); showTyping();
  try {
    const res = await window.lexa.chatFile(file, userMsg || "", LexaState.get("currentConversationId") || null);
    if (res.detail) { addMessage(res.detail, "system"); showToast(t("toast.fileError"), "error"); }
    else {
      addFileUploadResponse(res);
      if (res.action) handleChatToolActionBlocked(res.action, { source: "file-upload" });
      playTTS(fileUploadDisplayReply(res));
    }
  } catch (err) {
    if (err?.name === "AbortError" || /abort/i.test(err?.message || "")) {
      addMessage("Upload abgebrochen.", "system", null, false, true);
    } else {
      addMessage(t("chat.uploadErrorMsg", {error: err.message}), "system");
      showToast(t("toast.uploadError"), "error");
    }
  } finally {
    hideTyping();
    saveFileUploadConversationSnapshot();
    setFileUploadBusy(false);
  }
}
function getFileIcon(ext) {
  const icons = { PY: "\u{1F40D}", JS: "\u{1F7E8}", TS: "\u{1F535}", HTML: "\u{1F310}", CSS: "\u{1F3A8}", JSON: "\u{1F4CB}", MD: "\u{1F4DD}", TXT: "\u{1F4C4}", CSV: "\u{1F4CA}", LOG: "\u{1F4DC}", PDF: "\u{1F4D5}", PNG: "\u{1F5BC}", JPG: "\u{1F5BC}", JPEG: "\u{1F5BC}", GIF: "\u{1F5BC}", SVG: "\u{1F5BC}", SQL: "\u{1F5C3}", XML: "\u{1F4C3}", YAML: "\u2699", YML: "\u2699" };
  return icons[ext] || "\u{1F4CE}";
}

// \u2500\u2500 Image lightbox: click a chat image card to view it full size \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
let _lightboxKeyHandler = null;
function openImageLightbox(src) {
  if (!src) return;
  let overlay = document.getElementById("lexa-image-lightbox");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "lexa-image-lightbox";
    overlay.className = "image-lightbox";
    overlay.hidden = true;
    const img = document.createElement("img");
    img.className = "image-lightbox-img";
    img.alt = "";
    overlay.appendChild(img);
    overlay.addEventListener("click", closeImageLightbox);
    document.body.appendChild(overlay);
  }
  const img = overlay.querySelector(".image-lightbox-img");
  if (img) img.src = src;
  overlay.hidden = false;
  void overlay.offsetWidth; // reflow so the fade-in transition runs
  overlay.classList.add("open");
  _lightboxKeyHandler = (e) => { if (e.key === "Escape") closeImageLightbox(); };
  document.addEventListener("keydown", _lightboxKeyHandler);
}

function closeImageLightbox() {
  const overlay = document.getElementById("lexa-image-lightbox");
  if (!overlay) return;
  overlay.classList.remove("open");
  setTimeout(() => { if (!overlay.classList.contains("open")) overlay.hidden = true; }, 200);
  if (_lightboxKeyHandler) {
    document.removeEventListener("keydown", _lightboxKeyHandler);
    _lightboxKeyHandler = null;
  }
}
