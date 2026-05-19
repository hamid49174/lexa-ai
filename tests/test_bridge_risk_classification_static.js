/**
 * Static tests for param-sensitive preload bridge risk classification.
 * Run with: node tests/test_bridge_risk_classification_static.js
 */

const fs = require("fs");
const path = require("path");

const preloadSrc = fs.readFileSync(path.join(__dirname, "..", "frontend", "preload.js"), "utf8");
const mainSrc = fs.readFileSync(path.join(__dirname, "..", "frontend", "main.js"), "utf8");
const memorySrc = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "memory.js"), "utf8");
const uiSmokeSrc = fs.readFileSync(path.join(__dirname, "electron_ui_visual_smoke.js"), "utf8");

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

function extractFn(source, name) {
  const needles = [`async function ${name}(`, `function ${name}(`];
  const start = needles
    .map((needle) => source.indexOf(needle))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  if (start === undefined) throw new Error(`'${name}' not found`);
  const signatureEnd = source.indexOf(") {", start);
  const bodyStart = signatureEnd >= 0 ? source.indexOf("{", signatureEnd) : source.indexOf("{", start);
  if (bodyStart === -1) throw new Error(`No function body for '${name}'`);
  let depth = 0;
  for (let i = bodyStart; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

const sandboxFactory = new Function(`
  "use strict";
  const BRIDGE_RISK_RANK = Object.freeze({ low: 0, medium: 1, high: 2, critical: 3 });
  const BRIDGE_AUDIT_RISK = 1;
  const SIMPLE_PROFILE_KEYS = new Set(["name", "language", "theme", "accent", "locale"]);
  const SENSITIVE_PROFILE_KEY_PATTERN = /(?:api|auth|credential|email|identity|key|license|password|payment|secret|security|token)/i;
  const SENSITIVE_OS_PATH_PATTERN = /(?:^|[\\\\/])(?:00_System|03_Profile|05_Memory[\\\\/]Core|05_Memory[\\\\/]Stable)(?:[\\\\/]|$)|(?:\\.env|secret|token|credential|password|private|identity|key)/i;
  ${extractFn(preloadSrc, "bridgePolicy")}
  ${extractFn(preloadSrc, "buildBridgeMethodPolicy")}
  const BRIDGE_METHOD_POLICY = buildBridgeMethodPolicy([
    bridgePolicy("conversationUpdate", "high", "write", "/conversations/{id}"),
    bridgePolicy("conversationDelete", "high", "admin", "/conversations/{id}"),
    bridgePolicy("conversationGet", "low", "read", "/conversations/{id}", { batch_allowed: true }),
    bridgePolicy("conversationExport", "medium", "read", "/conversations/{id}/export"),
    bridgePolicy("setProfile", "high", "write", "/memory/profile"),
    bridgePolicy("personalOsReadFile", "medium", "read", "/personal-os/files/read"),
    bridgePolicy("personalOsQuery", "low", "read", "/personal-os/query", { batch_allowed: true }),
    bridgePolicy("personalOsContextPack", "low", "read", "/personal-os/context-pack", { batch_allowed: true }),
    bridgePolicy("personalOsObsidianContext", "low", "read", "/personal-os/obsidian-context", { batch_allowed: true }),
    bridgePolicy("notes", "low", "read", "/notes", { batch_allowed: true }),
    bridgePolicy("search", "low", "read", "/search", { batch_allowed: true }),
    bridgePolicy("ftsSearch", "low", "read", "/search/fts", { batch_allowed: true }),
    bridgePolicy("mcpServers", "low", "read", "/mcp/servers", { batch_allowed: true }),
    bridgePolicy("mcpServerTools", "low", "read", "/mcp/servers/{name}/tools", { batch_allowed: true }),
  ]);
  ${extractFn(preloadSrc, "riskAtLeast")}
  ${extractFn(preloadSrc, "effectiveBridgePolicy")}
  ${extractFn(preloadSrc, "firstPayloadObject")}
  ${extractFn(preloadSrc, "objectKeys")}
  ${extractFn(preloadSrc, "hasOnlyKeys")}
  ${extractFn(preloadSrc, "normalizedBridgePath")}
  ${extractFn(preloadSrc, "isPathTraversal")}
  ${extractFn(preloadSrc, "isSensitivePersonalOsPath")}
  ${extractFn(preloadSrc, "clampPositiveInteger")}
  ${extractFn(preloadSrc, "classifyConversationUpdate")}
  ${extractFn(preloadSrc, "classifyProfileSet")}
  ${extractFn(preloadSrc, "classifyPersonalOsReadFile")}
  ${extractFn(preloadSrc, "classifyBridgeCall")}
  return { classifyBridgeCall, clampPositiveInteger };
`);
const { classifyBridgeCall, clampPositiveInteger } = sandboxFactory();

console.log("\nParam-sensitive bridge classification:");
let policy = classifyBridgeCall("conversationUpdate", [42, { title: "New title" }]);
assert("conversation title update is medium audited without dialog", policy.risk === "medium" && !policy.requires_user_presence && policy.audit && policy.classification_reason === "conversation_title_update");
policy = classifyBridgeCall("conversationUpdate", [42, { messages: [{ role: "user", content: "hi" }] }]);
assert("conversation autosave messages are medium audited without dialog", policy.risk === "medium" && !policy.requires_user_presence && policy.rate_limited && policy.classification_reason === "conversation_autosave_messages");
policy = classifyBridgeCall("conversationUpdate", [42, { messages: [] }]);
assert("conversation message clear is high and presence-gated", policy.risk === "high" && policy.requires_user_presence && policy.classification_reason === "conversation_clear_messages");
policy = classifyBridgeCall("conversationUpdate", [42, { messages: [], title: "mixed" }]);
assert("unusual conversation mutation is high and presence-gated", policy.risk === "high" && policy.requires_user_presence && policy.classification_reason === "conversation_update_unusual_payload");
policy = classifyBridgeCall("setProfile", ["theme", "dark"]);
assert("simple profile keys are medium audited without dialog", policy.risk === "medium" && !policy.requires_user_presence && policy.classification_reason === "profile_simple_key");
policy = classifyBridgeCall("setProfile", ["api_key", "SECRET"]);
assert("sensitive profile keys are high and presence-gated", policy.risk === "high" && policy.requires_user_presence && policy.classification_reason === "profile_sensitive_key");
policy = classifyBridgeCall("personalOsReadFile", ["08_Lexa/Notes/example.md"]);
assert("scope-limited Personal OS file reads are medium audited without dialog", policy.risk === "medium" && !policy.requires_user_presence && policy.classification_reason === "personal_os_scope_limited_read");
policy = classifyBridgeCall("personalOsReadFile", ["00_System/Soul.md"]);
assert("core Personal OS reads are high and presence-gated", policy.risk === "high" && policy.requires_user_presence && policy.classification_reason === "personal_os_sensitive_path");
policy = classifyBridgeCall("personalOsReadFile", ["../.env"]);
assert("path traversal Personal OS reads are blocked", policy.blocked === true && policy.risk === "high" && policy.classification_reason === "personal_os_path_traversal");
policy = classifyBridgeCall("conversationExport", [42, "markdown"]);
assert("full conversation export is treated as high-risk privacy read", policy.risk === "high" && policy.requires_user_presence && policy.classification_reason === "conversation_full_export");
policy = classifyBridgeCall("personalOsContextPack", [{ maxFiles: 50, bodyChars: 50000 }]);
assert("context pack reads are medium audited and rate-limited", policy.risk === "medium" && !policy.requires_user_presence && policy.rate_limited);
policy = classifyBridgeCall("mcpServers", []);
assert("MCP server inventory is metadata-read medium audited", policy.risk === "medium" && !policy.requires_user_presence && policy.classification_reason === "mcp_metadata_read");

console.log("\nRead-side privacy clamps and UI behavior:");
assert("Personal OS query maxMatches is clamped to 50", clampPositiveInteger(999, 50, 1, 50) === 50 && preloadSrc.includes('params.set("maxMatches", String(clampPositiveInteger(maxMatches, 50, 1, 50)))'));
assert("Personal OS context bodies are clipped in preload", preloadSrc.includes("clampPositiveInteger(bodyChars, 700, 0, 700)") && preloadSrc.includes("clampPositiveInteger(bodyChars, 600, 0, 600)"));
assert("clipboard history is no longer loaded during memory refresh", !memorySrc.includes("window.lexa.clipboardHistory(),") && memorySrc.includes("renderClipboardPrivacyPrompt()") && memorySrc.includes("async function revealClipboardHistory"));
assert("clipboard history reveal stays explicit", memorySrc.includes("button.addEventListener(\"click\", revealClipboardHistory)") && memorySrc.includes("window.lexa.clipboardHistory()"));
assert("localized clipboard reveal text exists", preloadSrc && fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "i18n", "en.json"), "utf8").includes("memory.revealClipboardHistory") && fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "i18n", "de.json"), "utf8").includes("memory.revealClipboardHistory"));

console.log("\nMain-process bridge hooks:");
assert("main allows presence for effective high privacy reads", mainSrc.includes('"conversationExport"') && mainSrc.includes('"personalOsReadFile"'));
assert("main bridge audit carries classification metadata", mainSrc.includes("base_risk") && mainSrc.includes("effective_risk") && mainSrc.includes("classification_reason"));
assert("smoke mock requires explicit smoke context", preloadSrc.includes("function isLexaSmokeMockAllowed") && preloadSrc.includes("LEXA_ELECTRON_SMOKE_TEST") && uiSmokeSrc.includes("LEXA_ELECTRON_SMOKE_TEST"));
assert("packaged app deletes unsafe smoke mock env", mainSrc.includes("function hardenSmokeMockEnvironment") && mainSrc.includes("app.isPackaged") && mainSrc.includes("delete process.env.LEXA_ELECTRON_SMOKE_MOCK"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
