/**
 * Static-Regressionstests aus dem Gesamt-Scan (2026-06-25) — Frontend-Funde.
 * Run: node tests/test_scan_fixes_frontend.js
 */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const read = (...p) => fs.readFileSync(path.join(root, ...p), "utf8");

let passed = 0;
let failed = 0;
function ok(name, cond) {
  if (cond) { passed++; console.log("  ok:", name); }
  else { failed++; console.log("  FAIL:", name); }
}

const chatVoice = read("frontend", "src", "chat_voice.js");
const preload = read("frontend", "preload.js");

// Voice-Chat sendet die KORREKTE Konversations-ID (war: nicht existenter Key
// activeConversationId -> immer undefined).
ok(
  "chat_voice nutzt currentConversationId, nicht activeConversationId",
  /conversation_id:\s*LexaState\.get\("currentConversationId"\)/.test(chatVoice) &&
    !/activeConversationId/.test(chatVoice)
);

// Neue Voice-Key-Bridges existieren und zeigen auf die richtigen Endpunkte.
for (const [bridge, ep] of [
  ["openaiVoiceSetKey", "/voice/stt/openai/key"],
  ["openaiVoiceDeleteKey", "/voice/stt/openai/key"],
  ["groqVoiceSetKey", "/voice/stt/groq/key"],
  ["groqVoiceDeleteKey", "/voice/stt/groq/key"],
]) {
  ok(`preload Bridge ${bridge} -> ${ep}`,
    preload.includes(bridge) && preload.includes(ep));
}

// ── Light-Theme-Retrofit ──
const indexHtml = read("frontend", "src", "index.html");
const lightCss = read("frontend", "src", "css", "overrides_light_theme.css");

ok(
  "overrides_light_theme.css wird NACH premium_animations.css geladen (zuletzt)",
  indexHtml.indexOf("overrides_light_theme.css") >
    indexHtml.indexOf("premium_animations.css")
);
for (const sel of [".tool-card", ".sleek-pill", ".voice-status-bar", ".pos-panel", ".notif-center"]) {
  ok(`Light-Override deckt ${sel} ab`,
    lightCss.includes(sel) && lightCss.includes('[data-theme="light"]'));
}
// Regression: hartkodierter heller Text auf hellem Grund -> Text muss mitflippen
ok(
  "memory-graph Light-Override flippt Textfarbe (kein unsichtbarer Text)",
  /memory-graph-inspector[^}]*color:\s*var\(--text\)/s.test(lightCss) &&
    /memory-graph-fit-btn[^}]*color:\s*var\(--text\)/s.test(lightCss)
);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
