/**
 * Static tests for Agent preload safety.
 * Run with: node tests/test_preload_agent_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "preload.js"),
  "utf8"
);

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

console.log("\nAgent preload:");
const start = src.indexOf("  agentRun: async");
const end = src.indexOf("  agentChat: async", start);
const agentRunSection = src.slice(start, end > start ? end : undefined);

assert("defines agentRun bridge", start >= 0 && agentRunSection.includes("/agent/run"));
assert("agentRun uses fetchWithTimeout", agentRunSection.includes("fetchWithTimeout(`${API}/agent/run`"));
assert("agentRun has connection timeout", agentRunSection.includes("}, 15000);"));
assert("agentRun does not use raw fetch", !agentRunSection.includes("await fetch(`${API}/agent/run`"));
assert("agentRun returns bridge-safe stream ids", src.includes("function registerAgentStreamResponse") && agentRunSection.includes("return registerAgentStreamResponse(res)") && src.includes("const agentStreamReaders = new Map()") && src.includes("streamId"));
assert("agent stream exposes explicit read and cancel bridge methods", src.includes('bridgePolicy("agentStreamRead", "low", "read", "agent-stream:read")') && src.includes('bridgePolicy("agentStreamCancel", "low", "write", "agent-stream:cancel")') && src.includes("agentStreamRead: async (streamId)") && src.includes("agentStreamCancel: async (streamId)") && src.includes("function readAgentStreamChunk") && src.includes("function cancelAgentStream"));
assert("agent stream chunks are serialized for the sandbox bridge", src.includes("function bridgeStreamChunk") && src.includes("ArrayBuffer.isView(value)") && src.includes("Array.from(new Uint8Array"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
