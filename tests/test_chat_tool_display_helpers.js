/**
 * Direct checks for extracted chat tool display helpers.
 * Run with: node tests/test_chat_tool_display_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const helperSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_tool_display_ui.js"), "utf8");

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

const context = { Set, Object, String };
vm.createContext(context);
vm.runInContext(helperSrc, context, { filename: "chat_tool_display_ui.js" });

console.log("\nchat tool display helper boundaries:");

assert("string tool data displays unchanged", context.toolResultDisplayText("plain result") === "plain result");
assert("summary field wins for object results", context.toolResultDisplayText({ summary: "summary text", message: "message text" }) === "summary text");
assert("message field is used when summary is missing", context.toolResultDisplayText({ message: "message text", error: "error text" }) === "message text");
assert("error field is used when summary/message are missing", context.toolResultDisplayText({ error: "error text" }) === "error text");

const fallback = context.toolResultDisplayText({
  cpu_percent: 12,
  ram_percent: 42,
  icon: "skip",
  icon_code: "skip",
  will_rain: false,
  success: true,
  empty: "",
});
assert("fallback formats visible key-value pairs", fallback === "cpu_percent: 12. ram_percent: 42", fallback);
assert("empty or unsupported data displays empty text", context.toolResultDisplayText(null) === "" && context.toolResultDisplayText({ icon: "skip" }) === "");
assert("unsafe text remains text for renderer formatting", context.toolResultDisplayText({ summary: "<img src=x onerror=alert(1)>" }) === "<img src=x onerror=alert(1)>");

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
