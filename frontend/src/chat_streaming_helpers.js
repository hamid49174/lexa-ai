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
