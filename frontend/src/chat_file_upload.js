/*
 * Chat drag/drop and file upload flow.
 */

let dragCounter = 0;
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
  chatContainer.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  chatContainer.addEventListener("drop", (e) => { e.preventDefault(); dragCounter = 0; overlay.classList.remove("visible"); const files = e.dataTransfer.files; if (files.length > 0) handleFileUpload(files[0]); });
}
function triggerFileUpload() { document.getElementById("file-input")?.click(); }
function handleFileSelect(event) { const file = event.target.files?.[0]; if (file) handleFileUpload(file); event.target.value = ""; }

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
    try {
      const result = await window.lexa.conversationCreate(t("chat.newChatTitle"));
      LexaState.set("currentConversationId", result.id);
      chatSetActiveConversationId(result.id);
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
      if (res.action) handleChatToolActionBlocked(res.action, { source: "file-upload" });
      playTTS(fileUploadDisplayReply(res));
    }
  } catch (err) { hideTyping(); addMessage(t("chat.uploadErrorMsg", {error: err.message}), "system"); showToast(t("toast.uploadError"), "error"); }
  saveChatHistory(); saveCurrentConversation(); LexaState.set("isLoading", false); sendBtn.disabled = false;
}
function getFileIcon(ext) {
  const icons = { PY: "\u{1F40D}", JS: "\u{1F7E8}", TS: "\u{1F535}", HTML: "\u{1F310}", CSS: "\u{1F3A8}", JSON: "\u{1F4CB}", MD: "\u{1F4DD}", TXT: "\u{1F4C4}", CSV: "\u{1F4CA}", LOG: "\u{1F4DC}", PDF: "\u{1F4D5}", PNG: "\u{1F5BC}", JPG: "\u{1F5BC}", JPEG: "\u{1F5BC}", GIF: "\u{1F5BC}", SVG: "\u{1F5BC}", SQL: "\u{1F5C3}", XML: "\u{1F4C3}", YAML: "\u2699", YML: "\u2699" };
  return icons[ext] || "\u{1F4CE}";
}

