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
  chatContainer.addEventListener("drop", (e) => { e.preventDefault(); dragCounter = 0; overlay.classList.remove("visible"); const files = e.dataTransfer?.files; if (files && files.length > 0) handleFileUploadBatch(files); });
}
function triggerFileUpload() { document.getElementById("file-input")?.click(); }
function handleFileSelect(event) { const fileList = Array.from(event.target.files || []); if (fileList.length > 0) handleFileUploadBatch(fileList); event.target.value = ""; }

// Verarbeitet mehrere ausgewählte/gezogene Dateien sequenziell, damit keine
// Datei stillschweigend verworfen wird. Jeder Upload wird abgewartet, bevor der
// nächste startet (die isLoading-Sperre würde sonst Folge-Uploads abweisen).
async function handleFileUploadBatch(files) {
  for (const file of Array.from(files)) {
    await handleFileUpload(file);
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
  const revokePreviewUrl = () => {
    if (!previewUrl) return;
    URL.revokeObjectURL(previewUrl);
    previewUrl = "";
  };
  img.addEventListener("load", revokePreviewUrl, { once: true });
  img.addEventListener("error", () => {
    revokePreviewUrl();
    img.parentElement?.classList.remove("file-card-with-preview");
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
    card.classList.add("file-card-with-preview");
    card.appendChild(preview);
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
    const res = await window.lexa.chatFile(file, userMsg || "");
    if (res.detail) { addMessage(res.detail, "system"); showToast(t("toast.fileError"), "error"); }
    else {
      addFileUploadResponse(res);
      if (res.action) handleChatToolActionBlocked(res.action, { source: "file-upload" });
      playTTS(fileUploadDisplayReply(res));
    }
  } catch (err) {
    addMessage(t("chat.uploadErrorMsg", {error: err.message}), "system");
    showToast(t("toast.uploadError"), "error");
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
