/**
 * Direct checks for extracted chat streaming parser helpers.
 * Run with: node tests/test_chat_streaming_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const helperSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_streaming_helpers.js"), "utf8");

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

const warnings = [];
const context = {
  console: {
    warn: (...args) => warnings.push(args),
  },
  JSON,
  String,
};
vm.createContext(context);
vm.runInContext(helperSrc, context, { filename: "chat_streaming_helpers.js" });

console.log("\nchat streaming helper boundaries:");

const split = context.chatStreamBufferedLines('data: {"c":"A"}\n\ndata: {"c":"B"');
assert("buffer helper returns complete lines", Array.isArray(split.lines) && split.lines.length === 2 && split.lines[0] === 'data: {"c":"A"}' && split.lines[1] === "", JSON.stringify(split));
assert("buffer helper keeps incomplete tail", split.buffer === 'data: {"c":"B"', JSON.stringify(split));

const parsedContent = context.parseChatStreamDataLine('data: {"c":"Hello"}');
assert("data parser reads content chunks", parsedContent && parsedContent.c === "Hello", JSON.stringify(parsedContent));

const parsedDone = context.parseChatStreamDataLine('data: {"done":true,"rc":false}');
assert("data parser reads done events", parsedDone && parsedDone.done === true && parsedDone.rc === false, JSON.stringify(parsedDone));

assert("data parser ignores non-data lines", context.parseChatStreamDataLine("event: ping") === null);
assert("data parser ignores empty data lines", context.parseChatStreamDataLine("data: ") === null);

const malformed = context.parseChatStreamDataLine("data: {not-json}");
assert("data parser returns null for malformed JSON", malformed === null, JSON.stringify(malformed));
assert("data parser logs malformed JSON without throwing", warnings.length === 1 && warnings[0][0] === "SSE parse error:", JSON.stringify(warnings));
assert("data parser redacts malformed raw stream content by default", warnings[0][2]?.rawLength === "{not-json}".length && !JSON.stringify(warnings).includes("not-json"), JSON.stringify(warnings));
assert("stream debug raw preview is opt-in", helperSrc.includes("function chatStreamDebugEnabled") && helperSrc.includes("LEXA_DEBUG_STREAM") && helperSrc.includes("rawPreview") && !helperSrc.includes('console.warn("SSE parse error:", e, "raw:", raw)'));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
