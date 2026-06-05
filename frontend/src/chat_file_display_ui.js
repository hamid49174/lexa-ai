/* File upload display helpers loaded before chat.js. Keep this file free of module syntax. */

function fileUploadSizeLabel(file) {
  const size = Number(file?.size || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1048576) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1048576).toFixed(1)} MB`;
}

function fileUploadExtension(file) {
  const name = String(file?.name || "");
  return name.includes(".") ? name.split(".").pop().toUpperCase() : "FILE";
}

function fileUploadCanPreview(file) {
  const type = String(file?.type || "").toLowerCase();
  const ext = fileUploadExtension(file);
  if (type === "image/svg+xml" || ext === "SVG") return false;
  return type.startsWith("image/") || ["PNG", "JPG", "JPEG", "GIF", "WEBP", "BMP", "AVIF"].includes(ext);
}

function fileUploadSafeNumber(value, fallback = 0) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return fallback;
  return num;
}

function fileUploadDisplayNumber(value, fallback = 0) {
  const num = fileUploadSafeNumber(value, fallback);
  return Number.isInteger(num) ? String(num) : String(Math.round(num * 10) / 10);
}

function fileInfoBadgeType(fileInfo) {
  const raw = String(fileInfo?.extension || fileInfo?.type || "file").trim();
  const withoutDot = raw.replace(/^\.+/, "");
  return String(withoutDot || "file").toUpperCase();
}

function fileInfoBadgeText(fileInfo) {
  const lineCount = fileUploadSafeNumber(fileInfo?.line_count, 0);
  const parts = [
    fileInfoBadgeType(fileInfo),
    `${fileUploadDisplayNumber(fileInfo?.size_kb)} KB`,
  ];
  if (lineCount) parts.push(t("chat.fileLines", {count: fileUploadDisplayNumber(lineCount)}));
  const status = String(fileInfo?.analysis_status || "");
  if (status === "vision_provider_required") parts.push(t("chat.fileVisionPendingBadge"));
  else if (status === "analyzed" || status === "text_analyzed") parts.push(t("chat.fileAnalyzedBadge"));
  return parts.join(" \u00b7 ");
}

function fileUploadActionFallbackText() {
  const locale = String(t?._locale || navigator.language || "de").toLowerCase();
  if (locale.startsWith("de")) {
    return "Ich habe den Anhang bereit. Sag mir kurz, was ich daran prüfen soll.";
  }
  return "I have the attachment ready. Tell me what you want me to check.";
}

function fileUploadReplyLooksLikeToolExecution(reply, action) {
  const text = String(reply || "").trim();
  if (!text) return true;
  const actionName = chatToolActionName(action).toLowerCase();
  const normalized = text.toLowerCase();
  const mentionsAction = actionName && normalized.includes(actionName);
  const looksLikeExecute = /\b(fuehre|führe|execute|run)\b/i.test(text)
    || /\bausf(?:ue|ü)hren\b/i.test(text);
  return Boolean(mentionsAction && looksLikeExecute);
}

function fileUploadDisplayReply(res) {
  if (String(res?.analysis_status || res?.file_info?.analysis_status || "") === "vision_provider_required") {
    return t("chat.fileVisionProviderRequired", {
      filename: String(res?.file_info?.filename || t("chat.fileAttachmentFallback")),
    });
  }
  const reply = String(res?.reply || "").trim();
  if (!res?.action) return reply;
  if (fileUploadReplyLooksLikeToolExecution(reply, res.action)) {
    return fileUploadActionFallbackText();
  }
  return reply;
}
