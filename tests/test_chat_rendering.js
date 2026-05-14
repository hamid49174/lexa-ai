/**
 * Smoke tests for escapeHtml() and formatMessage() extracted from app.js.
 * Run with: node tests/test_chat_rendering.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
  "utf8"
);

// ── Extract a function body (balanced-brace scan) ───────────────────────────
function extractFn(source, name) {
  const needle = `function ${name}(`;
  const start = source.indexOf(needle);
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0, i = start;
  while (i < source.length) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}") { if (--depth === 0) return source.slice(start, i + 1); }
    i++;
  }
  throw new Error(`No closing brace for '${name}'`);
}

// ── DOM stub ────────────────────────────────────────────────────────────────
// escapeHtml() does:  div.textContent = text;  return div.innerHTML;
// Browser encodes < > & " ' when you READ innerHTML after setting textContent.
function makeDomStub() {
  return {
    createElement: () => {
      let raw = "";
      return {
        set textContent(v) { raw = String(v); },
        get innerHTML() {
          return raw
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
        },
        // formatMessage also creates elements and sets innerHTML (for code blocks etc.)
        set innerHTML(v) { raw = v; },
        get textContent() { return raw; },
      };
    },
    getElementById: () => null,
  };
}

// ── Build a sandboxed module with both functions ────────────────────────────
const escHtml  = extractFn(src, "escapeHtml");
const fmtMsg   = extractFn(src, "formatMessage");
// formatMessage emits code-copy buttons that are handled by delegated events.
const copyCodeStub = `function copyCode() {}`;

const sandbox = new Function("document", `
  "use strict";
  ${escHtml}
  ${copyCodeStub}
  ${fmtMsg}
  return { escapeHtml, formatMessage };
`);

let escapeHtml, formatMessage;
try {
  ({ escapeHtml, formatMessage } = sandbox(makeDomStub()));
} catch (e) {
  console.error("Sandbox setup failed:", e.message);
  process.exit(1);
}

// ── Minimal test runner ──────────────────────────────────────────────────────
let passed = 0, failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) { console.log(`  ✓ ${desc}`); passed++; }
  else     { console.error(`  ✗ FAIL: ${desc}${detail ? " — " + detail : ""}`); failed++; }
}

// ── escapeHtml ───────────────────────────────────────────────────────────────
console.log("\nescapeHtml():");
assert("escapes <",              escapeHtml("<").includes("&lt;"));
assert("escapes >",              escapeHtml(">").includes("&gt;"));
assert("escapes &",              escapeHtml("a & b").includes("&amp;"));
assert("escapes \"",             escapeHtml('"').includes("&quot;"));
assert("plain text unchanged",   escapeHtml("hello") === "hello");
assert("full XSS tag escaped",   !escapeHtml('<script>alert(1)</script>').includes("<script>"));

// ── formatMessage ────────────────────────────────────────────────────────────
console.log("\nformatMessage():");

const r1 = formatMessage('<script>alert("xss")</script>');
assert("script tag not in output",        !r1.includes("<script>"),         r1.slice(0, 80));

const r2 = formatMessage('<img src=x onerror=alert(1)>');
assert("img onerror not rendered raw",    !r2.includes("<img src=x"),       r2.slice(0, 80));

const r3 = formatMessage("```python\nprint('<b>hi</b>')\n```");
assert("code block uses <pre><code>",     r3.includes("<pre") && r3.includes("<code"), r3.slice(0, 120));
assert("code content HTML-escaped",       !r3.includes("<b>hi</b>"),        r3.slice(0, 120));

const r4 = formatMessage("This is **bold** text");
assert("**bold** → <strong> or <b>",      r4.includes("<strong>") || r4.includes("<b>"), r4);

const r5 = formatMessage("This is *italic* word");
assert("*italic* → <em>",                  r5.includes("<em>italic</em>"), r5);

const r6 = formatMessage("**<script>evil()</script>**");
assert("XSS inside ** markers escaped",   !r6.includes("<script>"),         r6.slice(0, 100));

const r7 = formatMessage("![logo](javascript:alert(1))");
assert("unsafe image protocol not rendered", !r7.includes("<img"),          r7.slice(0, 100));

const r8 = formatMessage("[click](javascript:alert(1))");
assert("unsafe link protocol not rendered",  !r8.includes("<a "),           r8.slice(0, 100));

const r9 = formatMessage("![logo](https://example.com/logo.png)");
assert("chat image uses CSS class",           r9.includes('class="chat-img"'), r9);
assert("chat image has no inline style",      !r9.includes("style="),       r9);

// ── Summary ──────────────────────────────────────────────────────────────────
console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
