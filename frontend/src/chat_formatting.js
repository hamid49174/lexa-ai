/* Pure chat formatting helpers loaded before chat.js. Keep this file free of module syntax. */

function stripModelFunctionTags(text) {
  return String(text || "")
    .replace(/<function=\w+[^>]*>[\s\S]*?<\/function>/g, "")
    .replace(/<function=\w+[^>]*\/?>/g, "")
    .trim();
}

function normalizeChatUrl(rawUrl, { image = false } = {}) {
  const value = String(rawUrl || "").trim();
  if (!value) return "";
  try {
    const parsed = new URL(value);
    const protocol = parsed.protocol.toLowerCase();
    const allowed = image
      ? new Set(["http:", "https:"])
      : new Set(["http:", "https:", "mailto:"]);
    if (!allowed.has(protocol)) return "";
    return parsed.href;
  } catch (_) {
    return "";
  }
}
