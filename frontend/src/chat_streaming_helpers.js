/*
 * Streaming parser helpers for classic renderer scripts.
 * Fetch orchestration, abort handling, rendering, and persistence stay in chat.js.
 */

function chatStreamBufferedLines(buffer) {
  const lines = String(buffer || "").split("\n");
  return { lines, buffer: lines.pop() || "" };
}

function parseChatStreamDataLine(line) {
  if (!line.startsWith("data: ")) return null;
  const raw = line.slice(6).trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    console.warn("SSE parse error:", e, "raw:", raw);
    return null;
  }
}
