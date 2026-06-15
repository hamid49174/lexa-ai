/*
 * Streaming parser helpers for classic renderer scripts.
 * Fetch orchestration, abort handling, rendering, and persistence stay in chat.js.
 */

function chatStreamBufferedLines(buffer) {
  const lines = String(buffer || "").split("\n");
  return { lines, buffer: lines.pop() || "" };
}

function chatStreamFinalLines(buffer) {
  const tail = String(buffer || "");
  if (!tail.trim()) return [];
  return tail.split("\n");
}

function chatStreamDebugEnabled() {
  return typeof window !== "undefined" && window?.LEXA_DEBUG_STREAM === true;
}

function parseChatStreamDataLine(line) {
  if (!line.startsWith("data: ")) return null;
  const raw = line.slice(6).trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    const meta = { rawLength: raw.length };
    if (chatStreamDebugEnabled()) meta.rawPreview = raw.slice(0, 80);
    console.warn("SSE parse error:", e?.message || e, meta);
    return null;
  }
}

function chatStreamClientErrorText(value, fallback = "") {
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  const base = raw || String(fallback || "").replace(/\s+/g, " ").trim();
  if (!base) return "";
  const redacted = base
    .replace(/(?<![A-Za-z])[A-Za-z]:[\\/][^\s"'<>|)]+/g, "[local-path-redacted]")
    .replace(/(^|\s)\/(?:Users|home|tmp|var|etc|mnt)\/[^\s"'<>|)]+/g, "$1[local-path-redacted]");
  if (redacted.length <= 220) return redacted;
  return redacted.slice(0, 217).trimEnd() + "...";
}
