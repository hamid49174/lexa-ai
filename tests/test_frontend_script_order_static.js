/**
 * Static checks for classic renderer script loading order.
 * Run with: node tests/test_frontend_script_order_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const chatSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat.js"), "utf8");
const chatConstantsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_constants.js"), "utf8");
const chatFormattingSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_formatting.js"), "utf8");
const chatMarkdownSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_markdown.js"), "utf8");

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

function scriptSources(source) {
  return Array.from(source.matchAll(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>/g)).map((match) => match[1]);
}

console.log("\nFrontend script order:");

const scripts = scriptSources(html);
const expectedTail = [
  "./config.js",
  "./state.js",
  "./orb3d.js",
  "./modals.js",
  "./chat_constants.js",
  "./chat_formatting.js",
  "./chat_markdown.js",
  "./chat.js",
  "./productivity.js",
  "./dashboard.js",
  "./system.js",
  "./commands.js",
  "./memory.js",
  "./personal_os.js",
  "./settings.js",
  "./devtools.js",
];
const tail = scripts.slice(-expectedTail.length);

assert("renderer uses expected classic script order", JSON.stringify(tail) === JSON.stringify(expectedTail), JSON.stringify(tail));
assert("chat constants load before chat.js", scripts.indexOf("./chat_constants.js") >= 0 && scripts.indexOf("./chat_constants.js") < scripts.indexOf("./chat.js"));
assert("chat formatting loads after constants and before chat.js", scripts.indexOf("./chat_formatting.js") > scripts.indexOf("./chat_constants.js") && scripts.indexOf("./chat_formatting.js") < scripts.indexOf("./chat.js"));
assert("chat markdown loads after formatting and before chat.js", scripts.indexOf("./chat_markdown.js") > scripts.indexOf("./chat_formatting.js") && scripts.indexOf("./chat_markdown.js") < scripts.indexOf("./chat.js"));
assert("renderer scripts do not opt into module mode", !/<script\b[^>]*type=["']module["']/i.test(html));
assert("chat constants file is classic script data", chatConstantsSrc.includes("const _AGENT_PATTERNS = [") && !/\b(import|export)\b/.test(chatConstantsSrc));
assert("chat formatting file is classic helper script", chatFormattingSrc.includes("function stripModelFunctionTags(") && chatFormattingSrc.includes("function normalizeChatUrl(") && !/\b(import|export)\b/.test(chatFormattingSrc));
assert("chat markdown file is classic helper script", chatMarkdownSrc.includes("function appendInlineMarkdown(") && chatMarkdownSrc.includes("function appendCodeBlock(") && !/\b(import|export)\b/.test(chatMarkdownSrc));
assert("chat.js consumes extracted agent patterns", !chatSrc.includes("const _AGENT_PATTERNS = [") && chatSrc.includes("_AGENT_PATTERNS.some"));
assert("extracted formatting helpers remain consumed", !chatSrc.includes("function stripModelFunctionTags(") && !chatSrc.includes("function normalizeChatUrl(") && chatSrc.includes("stripModelFunctionTags(text)") && chatMarkdownSrc.includes("normalizeChatUrl(match["));
assert("chat.js consumes extracted markdown helpers", !chatSrc.includes("function appendInlineMarkdown(") && !chatSrc.includes("function appendCodeBlock(") && chatSrc.includes("appendMarkdownSegment(parent") && chatSrc.includes("appendCodeBlock(parent"));
assert("Beta/Internal readiness labels remain in the shell", html.includes('data-readiness="beta"') && html.includes('data-readiness="internal"'));

const ids = Array.from(html.matchAll(/\bid="([^"]+)"/g)).map((match) => match[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
assert("index.html has no duplicate DOM ids", duplicates.length === 0, duplicates.join(", "));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
