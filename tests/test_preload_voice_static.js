/**
 * Static and helper tests for voice preload handling.
 * Run with: node tests/test_preload_voice_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "preload.js"),
  "utf8"
);

function extractFn(source, name) {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

const sandbox = new Function(`
  "use strict";
  ${extractFn(src, "voiceMimeFilename")}
  return { voiceMimeFilename };
`);

const { voiceMimeFilename } = sandbox();

let passed = 0;
let failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

console.log("\nVoice preload:");
assert("maps plain webm mime type", voiceMimeFilename("audio/webm") === "recording.webm");
assert("strips codec parameters before mapping", voiceMimeFilename("audio/ogg;codecs=opus") === "recording.ogg");
assert("normalizes casing and whitespace", voiceMimeFilename(" Audio/MP4 ; codecs=mp4a ") === "recording.m4a");
assert("falls back to webm for unknown mime types", voiceMimeFilename("application/octet-stream") === "recording.webm");

const sttStart = src.indexOf("  stt: async");
const sttEnd = src.indexOf("  // Voice status", sttStart);
const sttSection = src.slice(sttStart, sttEnd > sttStart ? sttEnd : undefined);
assert("stt bridge uses shared mime filename helper", sttSection.includes("voiceMimeFilename(audioBlob.type)"));
assert("stt bridge appends audio field expected by backend", sttSection.includes('formData.append("audio", audioBlob, filename)'));

const voiceStatusStart = src.indexOf("  voiceStatus: async");
const voiceStatusEnd = src.indexOf("  // TTS Voice Management", voiceStatusStart);
const voiceStatusSection = src.slice(voiceStatusStart, voiceStatusEnd > voiceStatusStart ? voiceStatusEnd : undefined);
assert("voiceStatus uses aggregate voice diagnostics", voiceStatusSection.includes("/voice/diagnostics"));
assert("voiceStatus fallback includes wakeword and audio state", voiceStatusSection.includes("wakeword: { active: false, ready: false }") && voiceStatusSection.includes("audio: { available: false }"));
assert("voiceDiagnostics bridge supports optional audio probe", src.includes("voiceDiagnostics: async (probeAudio = false)") && src.includes('params.set("probeAudio", "true")'));
assert("voiceArchitecture bridge exposes architecture endpoint", src.includes("voiceArchitecture: async ()") && src.includes("/voice/architecture") && src.includes("voiceArchitecture failed"));
assert("voiceRealtimePreflight bridge exposes preflight endpoint", src.includes("voiceRealtimePreflight: async ()") && src.includes("/voice/realtime/preflight") && src.includes("can_start: false"));
assert("voiceRealtimeStart bridge exposes guarded start endpoint", src.includes("voiceRealtimeStart: async ()") && src.includes("/voice/realtime/start") && src.includes('session_state: "blocked"'));
assert("voiceRealtimeStop bridge exposes safe stop endpoint", src.includes("voiceRealtimeStop: async ()") && src.includes("/voice/realtime/stop") && src.includes('session_state: "unknown"'));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
