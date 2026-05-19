/**
 * Static and helper tests for preload bridge mutation guards.
 * Run with: node tests/test_preload_bridge_security_static.js
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const preloadSrc = fs.readFileSync(path.join(__dirname, "..", "frontend", "preload.js"), "utf8");
const mainSrc = fs.readFileSync(path.join(__dirname, "..", "frontend", "main.js"), "utf8");

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

function extractConstBlock(source, name) {
  const start = source.indexOf(`const ${name}`);
  if (start === -1) throw new Error(`'${name}' not found`);
  const end = source.indexOf("]);", start);
  if (end === -1) throw new Error(`No closing block for '${name}'`);
  return source.slice(start, end + 3);
}

function extractObjectSection(source, startNeedle, endNeedle) {
  const start = source.indexOf(startNeedle);
  const end = source.indexOf(endNeedle, start);
  if (start === -1 || end === -1) throw new Error(`Cannot extract section ${startNeedle}`);
  return source.slice(start, end);
}

const policyEntries = [...preloadSrc.matchAll(/bridgePolicy\("([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"/g)]
  .map((match) => ({
    name: match[1],
    risk: match[2],
    actionType: match[3],
    target: match[4],
    line: match[0],
  }));
const policies = new Map(policyEntries.map((entry) => [entry.name, entry]));
const realBridgeSection = extractObjectSection(
  preloadSrc,
  "const lexaBridge = {",
  "\n};\n\ncontextBridge.exposeInMainWorld",
);
const exposedMethods = [...realBridgeSection.matchAll(/^  ([A-Za-z0-9_]+):/gm)].map((match) => match[1]);
const highRiskMethods = policyEntries
  .filter((entry) => ["high", "critical"].includes(entry.risk))
  .map((entry) => entry.name);
const mainPresenceBlock = extractConstBlock(mainSrc, "BRIDGE_PRESENCE_METHODS");
const mainPresenceMethods = [...mainPresenceBlock.matchAll(/"([^"]+)"/g)].map((match) => match[1]);

console.log("\nPreload bridge policy:");
assert("defines central BRIDGE_METHOD_POLICY", preloadSrc.includes("const BRIDGE_METHOD_POLICY = buildBridgeMethodPolicy(["));
assert("all exposed window.lexa methods have policy", exposedMethods.every((name) => policies.has(name)), exposedMethods.filter((name) => !policies.has(name)).join(", "));
assert("policy does not contain stale methods", policyEntries.every((entry) => exposedMethods.includes(entry.name)), policyEntries.filter((entry) => !exposedMethods.includes(entry.name)).map((entry) => entry.name).join(", "));
assert("createGuardedBridge fails closed on missing policy", preloadSrc.includes("function assertBridgePolicyComplete") && preloadSrc.includes("Missing bridge method policy") && preloadSrc.includes("createGuardedBridge(lexaBridge)"));
assert("high and critical policies require presence by default", preloadSrc.includes('const requiresGate = risk === "high" || risk === "critical"') && preloadSrc.includes("requires_user_presence: options.requires_user_presence ?? requiresGate") && preloadSrc.includes("requires_main_confirmation: options.requires_main_confirmation ?? requiresGate"));

const expectedCritical = [
  "executeBatch",
  "execute",
  "executeWithConfirmation",
  "mcpCallTool",
  "mcpConnect",
  "mcpDisconnect",
  "backupRestore",
  "backupRestoreDb",
  "elevenlabsSetKey",
  "elevenlabsDeleteKey",
  "deepgramSetKey",
  "deepgramDeleteKey",
  "cartesiaSetKey",
  "cartesiaDeleteKey",
  "visionAnalyze",
  "agentRun",
  "agentChat",
  "personalOsDraftApply",
];
const expectedHigh = [
  "personalOsDraftDecision",
  "personalOsRawSubmit",
  "memoryCleanup",
  "historyClear",
  "conversationDelete",
  "conversationUpdate",
  "setProfile",
  "clipboardHistory",
  "clipboardClear",
  "setAutostart",
  "hermesGatewayAutostartSet",
  "calendarConnect",
  "voiceRealtimeStart",
  "wakewordStart",
  "conversationStart",
];
assert("critical methods are classified critical", expectedCritical.every((name) => policies.get(name)?.risk === "critical"), expectedCritical.filter((name) => policies.get(name)?.risk !== "critical").join(", "));
assert("required high methods are classified high or critical", expectedHigh.every((name) => ["high", "critical"].includes(policies.get(name)?.risk)), expectedHigh.filter((name) => !["high", "critical"].includes(policies.get(name)?.risk)).join(", "));
assert("all high and critical policies are accepted by main-process presence allowlist", highRiskMethods.every((name) => mainPresenceMethods.includes(name)), highRiskMethods.filter((name) => !mainPresenceMethods.includes(name)).join(", "));
assert("read-only status methods stay low risk", ["health", "startupHealth", "aiStatus", "aiModels", "diagnostics", "healthTools", "commands", "timers", "agentStatus", "visionStatus"].every((name) => policies.get(name)?.risk === "low"));

console.log("\nBridge args hashing and batch validation:");
const helperSandbox = new Function("crypto", `
  "use strict";
  ${extractFn(preloadSrc, "stableBridgeValue")}
  ${extractFn(preloadSrc, "bridgeArgKeys")}
  ${extractFn(preloadSrc, "companionBatchCommandName")}
  const READ_ONLY_COMPANION_BATCH_COMMANDS = new Set(["system_info", "weather_current", "weather_forecast"]);
  ${extractFn(preloadSrc, "validateExecuteBatchCommands")}
  return { stableBridgeValue, bridgeArgKeys, validateExecuteBatchCommands };
`);
const { stableBridgeValue, bridgeArgKeys, validateExecuteBatchCommands } = helperSandbox(crypto);
function testBridgeArgsHash(args = []) {
  const normalized = stableBridgeValue(Array.from(args));
  return crypto.createHash("sha256").update(JSON.stringify(normalized)).digest("hex");
}
const hashA = testBridgeArgsHash([{ b: 2, a: { y: "yes", x: 1 } }]);
const hashB = testBridgeArgsHash([{ a: { x: 1, y: "yes" }, b: 2 }]);
const hashC = testBridgeArgsHash([{ a: { x: 2, y: "yes" }, b: 2 }]);
assert("preload uses sandbox-safe WebCrypto for args_hash", preloadSrc.includes("async function bridgeArgsHash") && preloadSrc.includes("globalThis.crypto?.subtle") && !preloadSrc.includes('require("crypto")'));
assert("args_hash is stable for key order", hashA === hashB && /^[a-f0-9]{64}$/.test(hashA));
assert("args_hash changes when args change", hashA !== hashC);
assert("arg keys expose only structure, not values", bridgeArgKeys([{ api_key: "SECRET", nested: "private" }]).join(",") === "arg0.api_key,arg0.nested");
assert("executeBatch allows only read-only companion commands", validateExecuteBatchCommands([{ command: "system_info" }, { command: "weather_current" }]).ok === true);
assert("executeBatch blocks mutating or unknown companion commands", validateExecuteBatchCommands([{ command: "file_write" }]).ok === false && validateExecuteBatchCommands([{ command: "personal_os_apply" }]).ok === false);

console.log("\nGuarded bridge call:");
const guardedSource = extractFn(preloadSrc, "guardedBridgeCall");
assert("guarded bridge applies param-sensitive policy classification", guardedSource.includes("classifyBridgeCall(method, args)") && preloadSrc.includes("function classifyBridgeCall"));
assert("high-risk calls request main-process presence", guardedSource.includes('ipcRenderer.invoke("bridge:presence:request"') && guardedSource.includes('ipcRenderer.invoke("bridge:presence:consume"'));
assert("high-risk call without challenge is rejected", guardedSource.includes("!challenge?.ok") && guardedSource.includes("bridge_presence_denied"));
assert("consume failure is rejected", guardedSource.includes("!consumed?.ok") && guardedSource.includes("bridge_presence_invalid"));
assert("executeBatch denial happens before backend execution", guardedSource.indexOf("validateExecuteBatchCommands") < guardedSource.indexOf("return executor()") && guardedSource.includes("bridge_batch_denied"));
assert("confirmed true remains a legacy UI hint only", preloadSrc.includes("void confirmed; // Legacy UI hint only") && !preloadSrc.includes("JSON.stringify({ command, params, confirmed })"));
assert("presence requests include effective classification metadata", guardedSource.includes("base_risk: policy.base_risk") && guardedSource.includes("effective_risk: policy.effective_risk") && guardedSource.includes("classification_reason: policy.classification_reason"));
assert("audit logs only arg keys and hash prefixes", preloadSrc.includes("args_hash: String(argsHash || \"\").slice(0, 16)") && preloadSrc.includes("arg_keys: Array.isArray(argKeys)") && !preloadSrc.includes("args: args") && !preloadSrc.includes("JSON.stringify(args)"));
assert("preload forwards only redacted bridge audit events", preloadSrc.includes('ipcRenderer.invoke("bridge:audit", event)') && !preloadSrc.includes('ipcRenderer.invoke("bridge:audit", args'));

console.log("\nMain-process user-presence challenge:");
assert("defines short bridge presence TTL", mainSrc.includes("const BRIDGE_PRESENCE_TTL_MS = 60 * 1000"));
assert("stores challenges in main process only", mainSrc.includes("const bridgePresenceChallenges = new Map()"));
assert("registers request, consume, and audit IPC handlers", mainSrc.includes('ipcMain.handle("bridge:presence:request"') && mainSrc.includes('ipcMain.handle("bridge:presence:consume"') && mainSrc.includes('ipcMain.handle("bridge:audit"'));
assert("shows native confirmation dialog", mainSrc.includes("dialog.showMessageBox") && mainSrc.includes("Allow once") && mainSrc.includes("Deny"));
assert("rejects untrusted renderer senders", mainSrc.includes("function bridgePresenceSenderTrusted") && mainSrc.includes("isTrustedRendererUrl(frameUrl)") && mainSrc.includes("untrusted_renderer"));
assert("binds challenges to method and args_hash", mainSrc.includes("record.method !== method") && mainSrc.includes("record.argsHash !== argsHash"));
assert("rejects expired challenges", mainSrc.includes("record.expiresAt <= Date.now()") && mainSrc.includes("challenge_expired"));
assert("rejects replay/single-use consume", mainSrc.includes("record.used") && mainSrc.includes("challenge_replay") && mainSrc.includes("bridgePresenceChallenges.delete(challengeId)"));
assert("redacted main audit avoids raw args", mainSrc.includes("[BridgePresenceAudit]") && mainSrc.includes("function sanitizeBridgeAuditEvent") && mainSrc.includes("args_hash: String(payload.args_hash") && mainSrc.includes("arg_keys: Array.isArray") && !mainSrc.includes("JSON.stringify(rawPayload)") && !mainSrc.includes("args: rawPayload"));
assert("main process persists redacted bridge audit outside repo", mainSrc.includes('app.getPath("userData")') && mainSrc.includes('"bridge-audit.log"') && mainSrc.includes("fs.appendFileSync(auditPath"));
assert("main process rotates bridge audit log", mainSrc.includes("BRIDGE_AUDIT_MAX_BYTES") && mainSrc.includes("function rotateBridgeAuditIfNeeded") && mainSrc.includes("`${auditPath}.1`") && mainSrc.includes("previous_size"));
assert("smoke mock is not enabled outside explicit non-packaged smoke context", preloadSrc.includes("function isLexaSmokeMockAllowed") && mainSrc.includes("function hardenSmokeMockEnvironment") && mainSrc.includes("app.isPackaged") && mainSrc.includes("LEXA_ELECTRON_SMOKE_TEST"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
